"""P1-2 Jira 单 Issue 详情增强 — 单元测试（5 条）。"""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_bridge import _strip_html, _exec_query_jira_metadata


class TestStripHtml(unittest.TestCase):
    """测试 _strip_html — HTML 标签 + 实体清理"""

    def test_removes_html_tags(self):
        """HTML 标签被移除"""
        text = "<p>这是<b>一段</b>HTML 文本</p>"
        result = _strip_html(text)
        self.assertNotIn("<p>", result)
        self.assertNotIn("<b>", result)
        self.assertIn("一段", result)
        self.assertIn("HTML 文本", result)

    def test_replaces_html_entities(self):
        """HTML 实体被替换"""
        text = "&nbsp;空格 &amp; 与号 &lt; 小于 &gt; 大于 &quot;引号"
        result = _strip_html(text)
        self.assertNotIn("&nbsp;", result)
        self.assertNotIn("&amp;", result)
        self.assertNotIn("&lt;", result)
        self.assertIn("与号", result)

    def test_empty_returns_empty(self):
        """空字符串返回空"""
        self.assertEqual(_strip_html(""), "")
        self.assertEqual(_strip_html(None), "")


class TestQueryJiraMetadataEnhanced(unittest.TestCase):
    """测试 _exec_query_jira_metadata 增强返回结构"""

    def _make_mock_jira_response(self, overrides: dict = None):
        """构造 Jira API mock 响应"""
        base = {
            "key": "CT-10899",
            "id": "10001",
            "fields": {
                "summary": "战术养成系统",
                "issuetype": {"name": "Story"},
                "status": {"name": "完成"},
                "assignee": {"displayName": "张锡涛"},
                "priority": {"name": "High"},
                "created": "2026-05-01T10:00:00.000+0800",
                "updated": "2026-06-01T10:00:00.000+0800",
                "duedate": "2026-06-15",
                "project": {"key": "CT"},
                "description": "这是一个战术养成系统的详细设计文档。",
                "comment": {
                    "comments": [
                        {
                            "author": {"displayName": "李四"},
                            "body": "代码已提交，请查看。",
                            "created": "2026-06-01T09:00:00.000+0800",
                        },
                        {
                            "author": {"displayName": "王五"},
                            "body": "已验收通过。",
                            "created": "2026-06-01T12:00:00.000+0800",
                        },
                    ],
                },
            },
        }
        if overrides:
            base.update(overrides)
        return base

    def test_returns_enhanced_structure(self):
        """返回结构包含 priority/created/updated/duedate/description/comments"""
        mock_data = self._make_mock_jira_response()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        with patch("ai_bridge.jira") as mock_jira:
            mock_jira.base_url = "https://jira.example.com"
            mock_jira.api_url = "https://jira.example.com/rest/api/3"
            mock_jira.jira_get.return_value = mock_resp
            result_str = _exec_query_jira_metadata({"issue_key": "CT-10899"})
            result = json.loads(result_str)

        self.assertEqual(result["status"], "ok")
        r = result["result"]
        self.assertEqual(r["key"], "CT-10899")
        self.assertEqual(r["title"], "战术养成系统")
        self.assertEqual(r["type"], "Story")
        self.assertEqual(r["status"], "完成")
        self.assertEqual(r["assignee"], "张锡涛")
        self.assertEqual(r["priority"], "High")
        self.assertEqual(r["created"], "2026-05-01T10:00:00.000+0800")
        self.assertEqual(r["duedate"], "2026-06-15")
        self.assertIn("description", r)
        self.assertIn("comments", r)
        self.assertIn("url", r)
        self.assertIn("CT-10899", r["url"])

    def test_description_truncated_to_500(self):
        """描述超过 500 字被截断"""
        long_desc = "战术" * 300  # 600 chars
        mock_data = self._make_mock_jira_response()
        mock_data["fields"]["description"] = long_desc
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        with patch("ai_bridge.jira") as mock_jira:
            mock_jira.base_url = "https://jira.example.com"
            mock_jira.api_url = "https://jira.example.com/rest/api/3"
            mock_jira.jira_get.return_value = mock_resp
            result_str = _exec_query_jira_metadata({"issue_key": "CT-10899"})
            result = json.loads(result_str)

        desc = result["result"]["description"]
        self.assertLessEqual(len(desc), 500)

    def test_comments_truncated_last_3_max_200_chars(self):
        """评论取最近 3 条，每条 ≤200 字"""
        # 构造 5 条评论，每条 300 chars
        long_body = "A" * 300
        mock_data = self._make_mock_jira_response()
        mock_data["fields"]["comment"]["comments"] = [
            {"author": {"displayName": f"用户{i}"}, "body": long_body, "created": "2026-01-01"}
            for i in range(5)
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        with patch("ai_bridge.jira") as mock_jira:
            mock_jira.base_url = "https://jira.example.com"
            mock_jira.api_url = "https://jira.example.com/rest/api/3"
            mock_jira.jira_get.return_value = mock_resp
            result_str = _exec_query_jira_metadata({"issue_key": "CT-10899"})
            result = json.loads(result_str)

        comments = result["result"]["comments"]
        self.assertEqual(len(comments), 3, "应取最近 3 条评论")
        for c in comments:
            self.assertLessEqual(len(c["body"]), 200, "每条评论 ≤200 字")
        # 前 2 条被丢弃，保留的是 index 2,3,4
        self.assertEqual(comments[0]["author"], "用户2")
        self.assertEqual(comments[2]["author"], "用户4")

    def test_no_description_or_comments_does_not_crash(self):
        """无描述、无评论时不崩溃"""
        mock_data = {
            "key": "CT-10001",
            "id": "10002",
            "fields": {
                "summary": "最小 Issue",
                "issuetype": {"name": "Task"},
                "status": {"name": "待办"},
                "assignee": None,
                "priority": None,
                "created": "2026-01-01",
                "updated": "2026-01-01",
                "duedate": None,
                "project": {"key": "CT"},
            },
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        with patch("ai_bridge.jira") as mock_jira:
            mock_jira.base_url = "https://jira.example.com"
            mock_jira.api_url = "https://jira.example.com/rest/api/3"
            mock_jira.jira_get.return_value = mock_resp
            result_str = _exec_query_jira_metadata({"issue_key": "CT-10001"})
            result = json.loads(result_str)

        self.assertEqual(result["status"], "ok")
        r = result["result"]
        self.assertEqual(r["key"], "CT-10001")
        self.assertEqual(r["description"], "")
        self.assertEqual(r["comments"], [])


if __name__ == "__main__":
    unittest.main()
