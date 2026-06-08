"""M5.1/M5.3 — workflow_engine 单元测试（≥11 条）。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml

# M5.3 — 避免 _step_kb_search 中 `import rag_engine` 导入 numpy 失败，提前 stub
if "rag_engine" not in sys.modules:
    from unittest.mock import MagicMock as _Mm
    _mock_rag = _Mm()
    _mock_rag.is_index_ready = _Mm(return_value=False)
    _mock_rag.search_doc_chunks = _Mm(return_value="[RAG] mock")
    _mock_rag.get_indexed_doc_count = _Mm(return_value=0)
    sys.modules["rag_engine"] = _mock_rag

import workflow_engine as we

VALID_YAML = """
templates:
  - id: version-day-check
    name: "版本日检查"
    description: "版本日检查说明"
    steps:
      - id: jql_query
        tool: jira_search
        description: "查询"
      - id: format_checklist
        tool: format
        description: "格式化"
      - id: summarize
        tool: llm_summarize
        description: "汇总"
  - id: design-to-subtasks
    name: "策划→子任务"
    description: "策划子任务说明"
    steps:
      - id: read_design_doc
        tool: kb_search
        description: "读取策划文档"
      - id: identify_subtasks
        tool: llm_summarize
        description: "LLM提取子任务"
      - id: create_drafts
        tool: jira_create_drafts
        description: "创建草稿"
      - id: return_draft_list
        tool: format
        description: "整理草稿列表"
"""

DUPLICATE_YAML = """
templates:
  - id: dup
    name: "A"
    description: "a"
    steps:
      - id: s1
        tool: t
        description: "d"
  - id: dup
    name: "B"
    description: "b"
    steps:
      - id: s1
        tool: t
        description: "d"
"""

MISSING_FIELD_YAML = """
templates:
  - id: broken
    name: "缺 description"
    steps:
      - id: s1
        tool: t
"""

NO_STEPS_YAML = """
templates:
  - id: empty-steps
    name: "空 steps"
    description: "d"
    steps: []
"""


def _write_tmp_yaml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


class TestLoadTemplates(unittest.TestCase):
    def test_load_valid_templates(self):
        path = _write_tmp_yaml(VALID_YAML)
        try:
            templates = we.load_templates(path)
            self.assertEqual(len(templates), 2)
        finally:
            os.unlink(path)

    def test_get_template_structure(self):
        path = _write_tmp_yaml(VALID_YAML)
        try:
            t = we.get_template("version-day-check")
            self.assertIsNotNone(t)
            self.assertEqual(t["name"], "版本日检查")
            self.assertGreaterEqual(len(t.get("steps") or []), 1)
        finally:
            os.unlink(path)


class TestValidation(unittest.TestCase):
    def test_duplicate_id_raises(self):
        path = _write_tmp_yaml(DUPLICATE_YAML)
        try:
            with self.assertRaises(ValueError) as cm:
                we.load_templates(path)
            self.assertIn("重复", str(cm.exception))
        finally:
            os.unlink(path)

    def test_missing_field_raises(self):
        path = _write_tmp_yaml(MISSING_FIELD_YAML)
        try:
            with self.assertRaises(ValueError) as cm:
                we.load_templates(path)
            self.assertIn("缺", str(cm.exception))
        finally:
            os.unlink(path)

    def test_empty_steps_raises(self):
        path = _write_tmp_yaml(NO_STEPS_YAML)
        try:
            with self.assertRaises(ValueError) as cm:
                we.load_templates(path)
            self.assertIn("非空", str(cm.exception))
        finally:
            os.unlink(path)


class TestListTemplates(unittest.TestCase):
    def test_list_ids(self):
        path = _write_tmp_yaml(VALID_YAML)
        try:
            ids = we.list_template_ids()
            self.assertEqual(set(ids), {"design-to-subtasks", "version-day-check"})
        finally:
            os.unlink(path)


class TestExecuteTemplate(unittest.TestCase):
    """M5.2 — 模板执行器单元测试（version-day-check）。"""

    def test_execute_version_day_check_structure(self):
        """模拟执行 version-day-check — 验证 execution_log 含 3 步。"""
        from unittest.mock import patch, MagicMock
        import json as _json

        ctx = {
            "jql": 'project=CT AND labels=version-day AND status!=Done',
            "jira_pat": "mock-pat",
            "jira_url": "https://jira.example.com",
            "deepseek_key": "",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "issues": [
                {"key": "CT-100", "fields": {"summary": "验证功能A", "status": {"name": "进行中"}, "assignee": {"displayName": "张三"}}},
                {"key": "CT-101", "fields": {"summary": "验证功能B", "status": {"name": "已完成"}, "assignee": {"displayName": "李四"}}},
            ],
            "total": 2,
        }

        with patch("requests.get", return_value=mock_resp):
            result = we.execute_template("version-day-check", context=ctx)

        self.assertTrue(result["ok"], f"expected ok=True, got {result}")
        self.assertEqual(result["template_id"], "version-day-check")
        self.assertEqual(len(result["execution_log"]), 3)
        self.assertEqual(result["execution_log"][0]["step_id"], "jql_query")
        self.assertEqual(result["execution_log"][1]["step_id"], "format_checklist")
        self.assertEqual(result["execution_log"][2]["step_id"], "summarize")
        self.assertEqual(len(result["steps"]), 3)
        for s in result["steps"]:
            self.assertEqual(s["status"], "done", f"step {s['id']} expected done, got {s['status']}")

        self.assertIn("CT-100", result["execution_log"][0]["output"])
        self.assertIn("版本日检查清单", result["execution_log"][1]["output"])

    def test_execute_step_failure_stops(self):
        """某步抛异常 → ok=False + failed_step 有值。"""
        ctx = {
            "jql": "",
            "jira_pat": "mock-pat",
            "jira_url": "https://jira.example.com",
        }
        result = we.execute_template("version-day-check", context=ctx)
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_step"], "jql_query")
        self.assertIn("JQL", result.get("error", ""))
        self.assertEqual(result["steps"][0]["status"], "failed")


class TestExecuteDesignToSubtasks(unittest.TestCase):
    """M5.3 — design-to-subtasks 模板执行器单元测试。"""

    _FAISS_DOC = "[球员名单.xlsx] (相似度:0.95)\n策划文档内容：需要实现球员系统，包含属性设计和位置管理..."

    _LLM_SUBTASKS = json.dumps([
        {"summary": "实现球员属性系统", "issueType": "Task"},
        {"summary": "实现球员位置管理器", "issueType": "Task"},
        {"summary": "编写球员系统测试", "issueType": "Task"},
    ])

    def setUp(self):
        import rag_engine as _rag_mod
        _rag_mod.is_index_ready.return_value = False
        _rag_mod.search_doc_chunks.return_value = "[RAG] mock"
        self._ctx = {
            "parent_issue_key": "CT-10000",
            "project_key": "CT",
            "doc_query": "球员系统策划案",
            "deepseek_key": "mock-key",
            "user_id": "test-user",
        }

    def test_execute_design_to_subtasks_structure(self):
        """模拟执行 design-to-subtasks — 4 步全量成功。"""
        from unittest.mock import patch, MagicMock
        import rag_engine as _rag_mod

        _rag_mod.is_index_ready.return_value = True
        _rag_mod.search_doc_chunks.return_value = self._FAISS_DOC

        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch("jira_operation_manager.create_issues_draft") as mock_create_draft:

            mock_llm = MagicMock()
            mock_llm.read.return_value = json.dumps({
                "choices": [{"message": {"content": self._LLM_SUBTASKS}}]
            }).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_llm

            mock_create_draft.side_effect = [
                {"id": "draft-a1", "status": "awaiting_review"},
                {"id": "draft-a2", "status": "awaiting_review"},
                {"id": "draft-a3", "status": "awaiting_review"},
            ]

            result = we.execute_template("design-to-subtasks", context=self._ctx)

        self.assertTrue(result["ok"], f"expected ok=True, got {result}")
        self.assertEqual(result["template_id"], "design-to-subtasks")
        self.assertEqual(len(result["execution_log"]), 4)
        self.assertEqual(result["execution_log"][0]["step_id"], "read_design_doc")
        self.assertEqual(result["execution_log"][1]["step_id"], "identify_subtasks")
        self.assertEqual(result["execution_log"][2]["step_id"], "create_drafts")
        self.assertEqual(result["execution_log"][3]["step_id"], "return_draft_list")

        for s in result["steps"]:
            self.assertEqual(s["status"], "done", f"step {s['id']} expected done, got {s['status']}")

        self.assertIn("球员名单", result["execution_log"][0]["output"])
        self.assertIn("draft-a1", result["execution_log"][2]["output"])
        self.assertIn("策划→子任务", result["execution_log"][3]["output"])

    def test_draft_creation_with_partial_failure(self):
        """某条 draft 创建失败不终止 — 验证 partial_failures。"""
        from unittest.mock import patch, MagicMock
        import rag_engine as _rag_mod

        _rag_mod.is_index_ready.return_value = True
        _rag_mod.search_doc_chunks.return_value = self._FAISS_DOC

        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch("jira_operation_manager.create_issues_draft") as mock_create_draft:

            mock_llm = MagicMock()
            mock_llm.read.return_value = json.dumps({
                "choices": [{"message": {"content": self._LLM_SUBTASKS}}]
            }).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_llm

            mock_create_draft.side_effect = [
                {"id": "draft-b1", "status": "awaiting_review"},
                ValueError("issueType 不合法"),
                {"id": "draft-b3", "status": "awaiting_review"},
            ]

            result = we.execute_template("design-to-subtasks", context=self._ctx)

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["execution_log"]), 4)

        step3 = result["steps"][2]
        self.assertEqual(step3["status"], "done")
        pf = step3.get("partial_failures") or []
        self.assertEqual(len(pf), 1, f"expected 1 partial failure, got {pf}")
        self.assertEqual(pf[0]["index"], 1)
        self.assertIn("draft-b1", result["execution_log"][2]["output"])
        self.assertIn("draft-b3", result["execution_log"][2]["output"])

    def test_kb_search_step_with_faiss_fallback(self):
        """FAISS 不可用 → 降级返回 fallback；FAISS 可用 → 语义命中。"""
        import rag_engine as _rag_mod

        _rag_mod.is_index_ready.return_value = False
        result = we._step_kb_search(
            {"id": "read_design_doc", "tool": "kb_search", "description": "read"},
            self._ctx, [])
        self.assertIn("KB 检索降级", result)
        self.assertIn("球员系统策划案", result)

        _rag_mod.is_index_ready.return_value = True
        _rag_mod.search_doc_chunks.return_value = self._FAISS_DOC
        result = we._step_kb_search(
            {"id": "read_design_doc", "tool": "kb_search", "description": "read"},
            self._ctx, [])
        self.assertIn("FAISS 语义检索结果", result)
        self.assertIn("球员名单", result)

    def test_jira_create_drafts_all_fail_stops(self):
        """全部子任务 draft 创建失败 → 抛 ValueError 阻止继续。"""
        from unittest.mock import patch

        ctx = dict(self._ctx)
        prev_log = [{"step_id": "identify_subtasks", "tool": "llm_summarize", "status": "done",
                      "output": self._LLM_SUBTASKS}]

        with patch("jira_operation_manager.create_issues_draft") as mock_create_draft:
            mock_create_draft.side_effect = ValueError("Jira API 不可用")
            with self.assertRaises(ValueError) as cm:
                we._step_jira_create_drafts(
                    {"id": "create_drafts", "tool": "jira_create_drafts", "description": "drafts"},
                    ctx, prev_log)
            self.assertIn("均失败", str(cm.exception))


class TestWorkflowTrigger(unittest.TestCase):
    """M5.4 — [WORKFLOW:xxx] 聊天触发测试。"""

    def test_workflow_trigger_regex_matches(self):
        """[WORKFLOW:version-day-check] 命中、[WORKFLOW:nonexistent] 也匹配但模板不存在。"""
        import re

        wf_re = re.compile(r"^\s*\[WORKFLOW:([a-z0-9_-]+)\]\s*", re.I)

        # 命中
        m = wf_re.match("[WORKFLOW:version-day-check]")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "version-day-check")

        m = wf_re.match("[WORKFLOW:design-to-subtasks]")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "design-to-subtasks")

        m = wf_re.match("[WORKFLOW:nonexistent]")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "nonexistent")

        # 不命中
        m = wf_re.match("随便聊聊")
        self.assertIsNone(m)

        m = wf_re.match("[INTENT:doc_search] 查一下文档")
        self.assertIsNone(m)

    def test_workflow_trigger_via_orchestrator(self):
        """模拟消息 [WORKFLOW:version-day-check] → execute_template 被调。"""
        from unittest.mock import patch, MagicMock

        # 模拟 orchestrator 中的 [WORKFLOW:xxx] 分支逻辑
        import re
        user_text = "[WORKFLOW:version-day-check]"
        m = re.match(r"^\s*\[WORKFLOW:([a-z0-9_-]+)\]\s*", user_text, re.I)
        self.assertIsNotNone(m, "regex must match [WORKFLOW:xxx]")

        template_id = m.group(1).lower()
        from workflow_engine import list_template_ids as _list_ids
        available = _list_ids()
        self.assertIn(template_id, available, "version-day-check must be in available templates")

        # 模拟 execute_template 调用（使用 mock jira_search）
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "issues": [],
                "total": 0,
            }
            mock_get.return_value = mock_resp

            from workflow_engine import execute_template as _exec_wf
            result = _exec_wf(template_id, context={"jql": "project=CT AND labels=version-day", "jira_pat": "mock", "jira_url": "https://jira.example.com"})
            self.assertTrue(result["ok"], f"expected ok=True, got {result}")
            self.assertEqual(result["template_id"], "version-day-check")
            self.assertEqual(len(result["execution_log"]), 3)
            self.assertEqual(result["execution_log"][0]["step_id"], "jql_query")


if __name__ == "__main__":
    unittest.main()
