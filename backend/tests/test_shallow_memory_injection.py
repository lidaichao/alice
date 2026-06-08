"""O1 调试阶段 — 浅层记忆注入单元测试（≥3 条）。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import memory_manager as mm


class TestShallowMemoryInjection(unittest.TestCase):
    """O1 — inject_shallow_memory_for_intent 行为测试。"""

    _SAVED_FILE = None

    @classmethod
    def setUpClass(cls):
        # 备份真实 shallow_memory.json
        real_path = os.path.join(os.path.dirname(__file__), "..", "data", "shallow_memory.json")
        if os.path.exists(real_path):
            with open(real_path, "r", encoding="utf-8") as f:
                cls._SAVED_FILE = f.read()

    @classmethod
    def tearDownClass(cls):
        # 恢复真实 shallow_memory.json
        if cls._SAVED_FILE is not None:
            real_path = os.path.join(os.path.dirname(__file__), "..", "data", "shallow_memory.json")
            with open(real_path, "w", encoding="utf-8") as f:
                f.write(cls._SAVED_FILE)

    def setUp(self):
        # 覆写 _MEMORY_FILE 指向临时文件，隔离测试
        import memory_manager as mm_mod
        self._tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({
            "version": 1,
            "entries": [
                {"id": "mem-001", "key": "kb", "text": "球员系统策划案 KB-001 已缓存——属性系统设计", "source": "test", "created_at": "2026-06-08T20:00:00"},
                {"id": "mem-002", "key": "rule", "text": "团队规则：代码提交前必须 CI 通过", "source": "test", "created_at": "2026-06-08T20:00:00"},
                {"id": "mem-003", "key": "kb2", "text": "后卫名单已查过——后卫：张三、李四、王五", "source": "test", "created_at": "2026-06-08T20:00:00"},
                {"id": "mem-004", "key": "jira", "text": "CT-10000 球员系统父 Issue，含子任务创建指令", "source": "test", "created_at": "2026-06-08T20:00:00"},
            ],
            "updated_at": "2026-06-08T21:00:00",
        }, self._tmp, ensure_ascii=False)
        self._tmp.close()
        self._orig_path = mm_mod._MEMORY_FILE
        mm_mod._MEMORY_FILE = self._tmp.name

    def tearDown(self):
        import memory_manager as mm_mod
        mm_mod._MEMORY_FILE = self._orig_path
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_knowledge_query_intent_injects_kb_memories(self):
        """knowledge_query 意图 → 注入策划案相关记忆（含策划/KB-/设计等提示词过滤），排除 Jira 专属。"""
        result = mm.format_memory_for_prompt(intent_label="KNOWLEDGE_QUERY")
        self.assertIsNotNone(result)
        self.assertIn("球员系统策划案", result, "should include KB cache memory (has hint keywords)")
        self.assertNotIn("CT-10000", result, "should exclude Jira-related memory")

    def test_chat_intent_excludes_kb_jira(self):
        """CHAT_ONLY 意图 → 排除含 Jira/技术关键词的记忆。"""
        result = mm.format_memory_for_prompt(intent_label="CHAT_ONLY")
        self.assertIsNotNone(result)
        # CHAT_ONLY 过滤器排除含 jira/ct-/commit/svn 等词条
        # 不含噪声词的 KB 记忆可能保留，这是预期行为
        self.assertNotIn("CT-10000", result, "chat-only should exclude Jira-specific memory")
        # 团队规则应保留（不含噪声词）
        self.assertIn("CI 通过", result, "chat-only should keep team rules")

    def test_empty_memory_file_no_crash(self):
        """shallow_memory.json 为空 → format_memory_for_prompt 返回空串，不崩。"""
        import memory_manager as mm_mod
        # Point to non-existent file
        mm_mod._MEMORY_FILE = os.path.join(tempfile.gettempdir(), f"nonexistent_mem_{os.getpid()}.json")
        try:
            result = mm.format_memory_for_prompt(intent_label="KNOWLEDGE_QUERY")
            self.assertEqual(result, "", "empty memory should return empty string")
        finally:
            mm_mod._MEMORY_FILE = self._orig_path

    def test_all_memories_without_intent_filter(self):
        """不传 intent_label → 返回所有记忆（不过滤）。"""
        result = mm.format_memory_for_prompt(intent_label="")
        self.assertIsNotNone(result)
        self.assertIn("球员系统策划案", result or "")
        self.assertIn("后卫名单", result or "")
        self.assertIn("CI 通过", result or "")


if __name__ == "__main__":
    unittest.main()
