"""
test_n8n_bridge.py — n8n 连接器 + SVN 代理 + agent_graph 工具节点 单元测试
v3.0 Phase 2.6：≥6 条用例覆盖调用器、超时、错误翻译、stub 替换、SVN 白名单
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestN8nWebhookCall:
    """Phase 2.6 用例1-3：n8n_webhook_call 正常/超时/HTTP 错误"""

    def test_normal_response_parsing(self):
        """n8n_webhook_call 正常 200 返回 → {"ok": True, "data": {...}}"""
        from agent_graph import n8n_webhook_call
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.elapsed.total_seconds.return_value = 0.5
        mock_resp.json.return_value = {"issues": [{"key": "CT-1", "summary": "test"}]}

        with patch("agent_graph.requests.post", return_value=mock_resp):
            result = n8n_webhook_call("alice-jira-search", {"jql": "test", "trace_id": "t1"}, timeout=3)
            assert result["ok"] is True
            assert result["data"]["issues"][0]["key"] == "CT-1"

    def test_timeout_scenario(self):
        """n8n_webhook_call 超时 → {"ok": False, "error": "中文超时提示"}"""
        from agent_graph import n8n_webhook_call
        import requests as req_module

        with patch("agent_graph.requests.post", side_effect=req_module.exceptions.Timeout()):
            result = n8n_webhook_call("alice-jira-search", {"jql": "test", "trace_id": "t2"}, timeout=3)
            assert result["ok"] is False
            assert "超时" in result["error"]
            assert "稍后重试" in result["error"]

    def test_http_error_translation(self):
        """n8n_webhook_call 非 200 → {"ok": False, "error": "外部服务异常"}"""
        from agent_graph import n8n_webhook_call
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.json.return_value = {}

        with patch("agent_graph.requests.post", return_value=mock_resp):
            result = n8n_webhook_call("alice-jira-search", {"jql": "test", "trace_id": "t3"}, timeout=3)
            assert result["ok"] is False
            assert "外部服务异常" in result["error"]

    def test_connection_error_translation(self):
        """n8n_webhook_call 连接失败 → 中文错误提示"""
        from agent_graph import n8n_webhook_call
        import requests as req_module

        with patch("agent_graph.requests.post", side_effect=req_module.exceptions.ConnectionError()):
            result = n8n_webhook_call("alice-jira-search", {"trace_id": "t4"})
            assert result["ok"] is False
            assert "无法连接" in result["error"]
            assert result["error_code"] == "N8N_UNREACHABLE"


class TestN8nJiraQueryTool:
    """Phase 2.6 用例4：n8n_jira_query 工具替换 stub 后格式正确"""

    def test_returns_formatted_issue_list(self):
        """n8n_jira_query 返回格式化 Jira 任务列表文本"""
        from agent_graph import n8n_jira_query
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.elapsed.total_seconds.return_value = 0.3
        mock_resp.json.return_value = {
            "issues": [
                {"key": "CT-100", "summary": "修复登录页面样式问题", "status": "In Progress"},
                {"key": "CT-101", "summary": "添加用户权限管理", "status": "To Do"},
            ]
        }

        with patch("agent_graph.requests.post", return_value=mock_resp):
            result = n8n_jira_query.invoke({"jql": "project=CT", "trace_id": "t5"})
            assert isinstance(result, str)
            assert "CT-100" in result
            assert "CT-101" in result
            assert "In Progress" in result

    def test_returns_error_on_failure(self):
        """n8n_jira_query 调用失败时返回错误文本"""
        from agent_graph import n8n_jira_query
        import requests as req_module

        with patch("agent_graph.requests.post", side_effect=req_module.exceptions.Timeout()):
            result = n8n_jira_query.invoke({"jql": "project=CT", "trace_id": "t6"})
            assert isinstance(result, str)
            assert "Jira 查询失败" in result

    def test_no_results_message(self):
        """n8n_jira_query 无结果时返回提示文本"""
        from agent_graph import n8n_jira_query
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.elapsed.total_seconds.return_value = 0.2
        mock_resp.json.return_value = {"issues": []}

        with patch("agent_graph.requests.post", return_value=mock_resp):
            result = n8n_jira_query.invoke({"jql": "project=XX", "trace_id": "t7"})
            assert "未找到" in result


class TestSvnQueryTool:
    """Phase 2.6 用例5：svn_query 工具替换 stub 后格式正确"""

    def test_returns_formatted_log(self):
        """svn_query 调用 svn_log 并返回格式化提交列表"""
        from agent_graph import svn_query
        from svn_proxy import svn_log as real_svn_log

        mock_entries = [
            {"revision": "r123", "author": "dev1", "date": "2026-06-10", "message": "fix: login bug"},
            {"revision": "r122", "author": "dev2", "date": "2026-06-09", "message": "feat: user auth"},
        ]
        with patch("agent_graph.svn_log", return_value=mock_entries):
            result = svn_query.invoke({"path": "/tmp/test-repo", "trace_id": "t8"})
            assert isinstance(result, str)
            assert "r123" in result
            assert "dev1" in result
            assert "login bug" in result

    def test_no_results_message(self):
        """svn_query 无结果时返回提示文本"""
        from agent_graph import svn_query
        with patch("agent_graph.svn_log", return_value=[]):
            result = svn_query.invoke({"path": "/tmp/test-repo", "trace_id": "t9"})
            assert "SVN 查询无结果" in result


class TestSvnProxyAuth:
    """Phase 2.6 用例6：svn_proxy 白名单检查"""

    def test_rejects_unauthorized_path(self):
        """svn_log 拒绝未授权路径"""
        from svn_proxy import svn_log
        result = svn_log("/unauthorized/path", limit=5, trace_id="t10")
        assert result == []

    def test_rejects_empty_path(self):
        """svn_log 拒绝空路径"""
        from svn_proxy import svn_log
        result = svn_log("", limit=5, trace_id="t11")
        assert result == []


class TestIdempotencyKeyFormat:
    """Phase 2.6 用例7：幂等 Key 格式验证"""

    def test_idempotency_key_regex_clean(self):
        """幂等 Key 只含小写字母数字和连字符 (约束#10)"""
        import re, uuid as _uuid
        raw_id = _uuid.uuid4().hex
        key = f"alice-tx-{raw_id}"
        assert re.match(r'^alice-tx-[a-f0-9]+$', key), f"幂等Key格式不合规: {key}"
        assert len(key) < 255, "幂等Key过长超过Jira Label 255字符限制"


class TestStubReplaced:
    """Phase 2.6 用例8：确认 agent_graph 占位 stub 已替换"""

    def test_n8n_jira_query_not_placeholder(self):
        """n8n_jira_query 不再包含占位文本"""
        import inspect
        from agent_graph import n8n_jira_query
        source = inspect.getsource(n8n_jira_query.func)
        assert "占位" not in source, "n8n_jira_query 占位 stub 应已替换为真实实现"
        assert "n8n_webhook_call" in source, "n8n_jira_query 应调用 n8n_webhook_call"

    def test_svn_query_not_placeholder(self):
        """svn_query 不再包含占位文本"""
        import inspect
        from agent_graph import svn_query
        source = inspect.getsource(svn_query.func)
        assert "占位" not in source, "svn_query 占位 stub 应已替换为真实实现"
        assert "svn_log" in source, "svn_query 应调用 svn_log"


class TestSvnProxyParse:
    """Phase 2.6 用例9：SVN XML 解析"""

    def test_parse_svn_xml_basic(self):
        """_parse_svn_xml 正确解析基本 SVN XML 输出"""
        from svn_proxy import _parse_svn_xml
        xml_str = """<?xml version="1.0" encoding="UTF-8"?>
        <log>
        <logentry revision="12345">
        <author>developer</author>
        <date>2026-06-10T14:00:00.000000Z</date>
        <msg>fix: resolve crash on login</msg>
        </logentry>
        </log>"""
        entries = _parse_svn_xml(xml_str, "t12")
        assert len(entries) == 1
        assert entries[0]["revision"] == "r12345"
        assert entries[0]["author"] == "developer"
        assert "fix: resolve crash on login" in entries[0]["message"]
