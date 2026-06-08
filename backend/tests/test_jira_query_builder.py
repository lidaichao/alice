"""P1-1 Jira 聪明度第一弹 — jira_query_builder 单元测试（6 条）。"""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jira_query_builder import (
    build_jira_search_prompt,
    parse_query_llm,
    _parse_llm_json,
    _resolve_api_key,
)


class TestBuildPrompt(unittest.TestCase):
    """测试 prompt 构造——产出合法 prompt 字符串"""

    def test_prompt_contains_field_descriptions(self):
        """prompt 含字段说明、时间规则、状态映射"""
        prompt = build_jira_search_prompt("查一下 CT 项目进行中的任务")
        self.assertIn("assignee", prompt.lower())
        self.assertIn("projectKey", prompt)
        self.assertIn("issueType", prompt)
        self.assertIn("updatedAfter", prompt)
        self.assertIn("updatedBefore", prompt)
        self.assertIn("进行中", prompt)
        self.assertIn("待办", prompt)
        self.assertIn("完成", prompt)
        self.assertIn("本周", prompt)
        self.assertIn("上个月", prompt)
        self.assertIn("search", prompt.lower())

    def test_prompt_injects_today_date(self):
        """prompt 注入今天的日期"""
        from datetime import date
        prompt = build_jira_search_prompt("test")
        today_str = date.today().isoformat()
        self.assertIn(today_str, prompt)


class TestParseLLMJson(unittest.TestCase):
    """测试 JSON 解析——不调真实 API"""

    def test_parse_clean_json(self):
        """标准 JSON 直接解析"""
        result = _parse_llm_json('{"action":"search","params":{"assignee":"张锡涛"}}')
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "search")
        self.assertEqual(result["params"]["assignee"], "张锡涛")

    def test_parse_markdown_wrapped_json(self):
        """```json ... ``` 包裹的 JSON 去除包裹后解析"""
        result = _parse_llm_json(
            '```json\n{"action":"search","params":{"status":"进行中"}}\n```'
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["params"]["status"], "进行中")

    def test_parse_invalid_json_returns_none(self):
        """非法 JSON 返回 None"""
        result = _parse_llm_json("这不是 JSON，是一段废话。")
        self.assertIsNone(result)


class TestParseQueryLLM(unittest.TestCase):
    """测试 parse_query_llm —— mock DeepSeek API 调用"""

    def setUp(self):
        self.patch_env = patch.dict(os.environ, {"DEEPSEEK_KEY": "sk-test-mock-key"})
        self.patch_env.start()

    def tearDown(self):
        self.patch_env.stop()

    def _mock_response(self, content: str, status_code: int = 200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": content}}],
        }
        return mock_resp

    def test_parse_query_llm_returns_structured_params(self):
        """正常 LLM 返回 → 提取结构化 params"""
        mock_resp = self._mock_response(
            '{"action":"search","params":{"assignee":"张锡涛","status":"进行中","projectKey":"CT"}}'
        )
        with patch("jira_query_builder.requests.post", return_value=mock_resp):
            result = parse_query_llm("张锡涛 CT 项目进行中的任务")
        self.assertIsNotNone(result)
        self.assertEqual(result["assignee"], "张锡涛")
        self.assertEqual(result["status"], "进行中")
        self.assertEqual(result["projectKey"], "CT")

    def test_parse_query_llm_timeout_returns_none(self):
        """超时 → 返回 None，不抛异常"""
        import requests as req_lib

        with patch(
            "jira_query_builder.requests.post",
            side_effect=req_lib.exceptions.Timeout("timed out"),
        ):
            result = parse_query_llm("test")
        self.assertIsNone(result)

    def test_parse_query_llm_connection_error_returns_none(self):
        """网络错误 → 返回 None，不抛异常"""
        import requests as req_lib

        with patch(
            "jira_query_builder.requests.post",
            side_effect=req_lib.exceptions.ConnectionError("refused"),
        ):
            result = parse_query_llm("test")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
