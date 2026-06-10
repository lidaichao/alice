"""v1.9-hotfix2 Jira issuetype 动态解析 — 单元测试（3 条）。"""
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDraftToFieldsIssueTypeResolve(unittest.TestCase):
    """测试 draft_to_fields 的 issuetype 动态解析（不再硬编码 "Task"）。"""

    def _make_client(self, issuetypes=None):
        """构造 mock JiraClient 实例，可注入 get_project_issuetypes 返回值。"""
        from jira_api import JiraClient
        client = JiraClient.__new__(JiraClient)
        client.api_url = "https://issues.example.com/rest/api/2"
        client.auth = ("user", "token")

        def _do_empty_req(*_a, **_kw):
            return MagicMock(status_code=200, json=lambda: {}, text="")
        client._request = _do_empty_req

        client.get_project_issuetypes = MagicMock(
            return_value=issuetypes or [],
        )
        return client

    def test_1_issue_type_id_present_uses_id_directly(self):
        """draft 有 issueTypeId → 直接用 id，不调 get_project_issuetypes。"""
        client = self._make_client()
        draft = {
            "projectKey": "CT",
            "summary": "测试任务",
            "issueTypeId": "10001",
        }
        fields = client.draft_to_fields(draft)
        self.assertEqual(fields["issuetype"], {"id": "10001"})
        # 确保没调用 API
        client.get_project_issuetypes.assert_not_called()

    def test_2_exact_name_match_resolves_to_id(self):
        """draft 的 issueType 名称精确匹配真实类型 → 解析成功，用 id。"""
        client = self._make_client(issuetypes=[
            {"id": "10002", "name": "客户端", "subtask": False},
            {"id": "10003", "name": "服务器", "subtask": False},
        ])
        draft = {
            "projectKey": "CT",
            "summary": "测试子任务",
            "issueType": "服务器",
        }
        fields = client.draft_to_fields(draft)
        self.assertEqual(fields["issuetype"], {"id": "10003"})
        client.get_project_issuetypes.assert_called_once_with("CT", user_pat=None)

    def test_3_unknown_issue_type_raises_value_error(self):
        """draft 的 issueType 不存在真实类型 → 抛 ValueError 含可用类型列表。"""
        client = self._make_client(issuetypes=[
            {"id": "10002", "name": "客户端", "subtask": False},
            {"id": "10003", "name": "服务器", "subtask": False},
        ])
        draft = {
            "projectKey": "CT",
            "summary": "测试",
            "issueType": "Task",
        }
        with self.assertRaises(ValueError) as ctx:
            client.draft_to_fields(draft)
        msg = str(ctx.exception)
        self.assertIn("issueType 'Task'", msg)
        self.assertIn("CT", msg)
        self.assertIn("客户端", msg)
        self.assertIn("服务器", msg)


if __name__ == "__main__":
    unittest.main()
