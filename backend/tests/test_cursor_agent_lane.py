"""P2-2 Cursor SDK Lane — 单元测试（3 条）。"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cursor_sdk import CustomTool


class TestCursorAgentLaneTools(unittest.TestCase):
    """测试 cursor_agent_lane 工具注册与审计路径"""

    def test_custom_tool_registration(self):
        """14 个 CustomTool name/parameters/handler callable 正确"""
        from cursor_agent_lane import _build_custom_tools

        tools = _build_custom_tools(conversation_id="test-cid", user_id="test-uid")
        self.assertEqual(len(tools), 14)
        expected_names = {
            "jira_search_issues", "jira_read_issue_detail", "list_jira_issuetypes",
            "read_file", "search_code", "svn_log", "list_directory",
            "get_issue_commits", "get_single_commit_diff",
            "search_docs_catalog", "read_specific_doc",
            "jira_create_subtasks", "jira_update_status", "jira_add_comment",
        }
        self.assertEqual(set(tools.keys()), expected_names)

        for name, tool in tools.items():
            self.assertIsInstance(tool, CustomTool, f"{name} 不是 CustomTool 实例")
            self.assertIsNotNone(tool.description, f"{name} 缺少 description")
            self.assertIsNotNone(tool.input_schema, f"{name} 缺少 input_schema")
            self.assertTrue(callable(tool.execute), f"{name} handler 不可调用")

    @patch("jira_operation_manager.create_operation_card_with_audit")
    def test_jira_create_subtasks_audit(self, mock_audit):
        """jira_create_subtasks handler -> 调 create_operation_card_with_audit"""
        from cursor_agent_lane import _build_custom_tools

        tools = _build_custom_tools(conversation_id="test-cid", user_id="test-uid")
        create_tool = tools["jira_create_subtasks"]

        mock_audit.return_value = {
            "status": "awaiting_confirmation",
            "reason": "批量创建 (v1.0.30 - Cursor SDK 工具)",
        }

        result_json = create_tool.execute(
            {"summaries": ["子任务A", "子任务B"], "project_key": "CT", "issue_type": "Task"},
            None,
        )
        result = json.loads(result_json)

        # 验证审计闸门被调用
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        self.assertEqual(call_kwargs.get("kind"), "jira_bulk_create")
        self.assertEqual(call_kwargs.get("trigger_source"), "cursor_sdk")
        self.assertTrue(call_kwargs.get("ai_created"))
        self.assertEqual(call_kwargs.get("conversation_id"), "test-cid")
        self.assertEqual(call_kwargs.get("user_id"), "test-uid")

        # 验证 drafts 结构
        drafts = call_kwargs.get("drafts") or []
        self.assertEqual(len(drafts), 2)
        self.assertEqual(drafts[0]["summary"], "子任务A")
        self.assertEqual(drafts[0]["projectKey"], "CT")

        # 验证返回状态
        self.assertEqual(result["status"], "awaiting_confirmation")

    @patch("jira_operation_manager.create_operation_card_with_audit")
    def test_jira_update_status_audit(self, mock_audit):
        """jira_update_status handler -> 调 create_operation_card_with_audit(kind=jira_transition)"""
        from cursor_agent_lane import _build_custom_tools

        tools = _build_custom_tools(conversation_id="test-cid", user_id="test-uid")
        transition_tool = tools["jira_update_status"]

        mock_audit.return_value = {
            "status": "awaiting_confirmation",
            "reason": "状态流转",
        }

        result_json = transition_tool.execute(
            {"issue_key": "CT-12345", "target_status": "已完成"},
            None,
        )
        result = json.loads(result_json)

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        self.assertEqual(call_kwargs.get("kind"), "jira_transition")
        self.assertEqual(call_kwargs.get("trigger_source"), "cursor_sdk")
        self.assertEqual(result["status"], "awaiting_confirmation")

        drafts = call_kwargs.get("drafts") or []
        self.assertEqual(len(drafts), 1)
        self.assertIn("CT-12345", drafts[0]["issue_key"])
        self.assertEqual(drafts[0]["target_status"], "已完成")


if __name__ == "__main__":
    unittest.main()
