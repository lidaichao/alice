"""P1-3 Jira 写操作审计闸门 — 单元测试（8 条）。"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jira_operation_manager import (
    audit_jira_operation,
    create_operation_card_with_audit,
)


class TestAuditJiraOperation(unittest.TestCase):
    """测试 audit_jira_operation 三态决策"""

    def test_jira_search_allow(self):
        """jira_search → allow"""
        result = audit_jira_operation(kind="jira_search")
        self.assertEqual(result["decision"], "allow")
        self.assertIn("只读", result["reason"])

    def test_bulk_create_require_confirmation(self):
        """jira_bulk_create → require_confirmation"""
        result = audit_jira_operation(kind="jira_bulk_create")
        self.assertEqual(result["decision"], "require_confirmation")
        self.assertIn("批量创建", result["reason"])

    def test_transition_non_ai_deny(self):
        """jira_transition_issue + ai_created=False → deny"""
        result = audit_jira_operation(
            kind="jira_transition_issue", ai_created=False,
        )
        self.assertEqual(result["decision"], "deny")
        self.assertIn("非 AI 创建", result["reason"])

    def test_comment_non_ai_require_confirmation(self):
        """jira_add_comment + ai_created=False → require_confirmation"""
        result = audit_jira_operation(
            kind="jira_add_comment", ai_created=False,
        )
        self.assertEqual(result["decision"], "require_confirmation")
        self.assertIn("评论", result["reason"])

    def test_update_scheduled_ai_allow(self):
        """jira_update_issue + scheduled + ai_created=True → allow"""
        result = audit_jira_operation(
            kind="jira_update_issue", trigger_source="scheduled", ai_created=True,
        )
        self.assertEqual(result["decision"], "allow")
        self.assertIn("定时任务", result["reason"])

    def test_unknown_kind_deny(self):
        """未知 kind → deny"""
        result = audit_jira_operation(kind="jira_nuke_everything")
        self.assertEqual(result["decision"], "deny")
        self.assertIn("不支持", result["reason"])

    def test_delete_ai_client_require_confirmation(self):
        """jira_delete_issue + client + ai_created=True → require_confirmation"""
        result = audit_jira_operation(
            kind="jira_delete_issue", trigger_source="client", ai_created=True,
        )
        self.assertEqual(result["decision"], "require_confirmation")
        self.assertIn("确认", result["reason"])


class TestCreateOperationCardWithAudit(unittest.TestCase):
    """测试 create_operation_card_with_audit 包装行为"""

    def test_deny_does_not_create_card(self):
        """deny 时不创建确认卡，返回 status=denied"""
        result = create_operation_card_with_audit(
            drafts=[{"summary": "test", "projectKey": "CT", "issueType": "Task"}],
            kind="jira_transition_issue",
            ai_created=False,
        )
        self.assertEqual(result["status"], "denied")
        self.assertIn("非 AI 创建", result["reason"])
        self.assertNotIn("operation", result)


if __name__ == "__main__":
    unittest.main()
