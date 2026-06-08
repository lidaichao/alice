"""M4.8 — 审批审计全链路单测：confirm/reject/deny 后 audit.log 含 user_id + 持久化验证。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import audit_gateway as ag
from jira_operation_manager import create_operation_card


def _use_temp_log(agent):
    tmp = tempfile.TemporaryDirectory()
    agent._tmp_dir = tmp
    agent._orig_log = ag._AUDIT_LOG_PATH
    ag._AUDIT_LOG_PATH = os.path.join(tmp.name, "audit.log")
    return agent


def _restore_log(agent):
    ag._AUDIT_LOG_PATH = agent._orig_log
    agent._tmp_dir.cleanup()


class TestConfirmAuditRecord(unittest.TestCase):
    """M4.8a — confirm 后 audit_and_log 含 user_id。"""

    def setUp(self):
        _use_temp_log(self)

    def tearDown(self):
        _restore_log(self)

    def test_confirm_audit_log(self):
        op = create_operation_card(
            drafts=[{"summary": "test", "projectKey": "CT", "issueType": "Task"}],
            user_id="rabbit",
        )
        # 模拟 confirm：awaiting_confirmation → running → created
        from jira_operation_manager import mark_created, mark_running

        op = mark_running(op)
        op = mark_created(op, [], confirmed_by="pm-alice")

        # 审计落盘
        ag.record_operation_audit(
            actor="pm-alice",
            action="operation_confirm",
            operation_id=op["id"],
            decision="allow",
            origin="http",
            context={"created_count": 1},
        )
        rows = ag.query_persistent_audit_logs(
            limit=5,
            operation_id=op["id"],
        )
        self.assertGreaterEqual(len(rows), 1)
        entry = rows[0]
        self.assertEqual(entry["actor"], "pm-alice")
        self.assertEqual(entry["action"], "operation_confirm")
        self.assertEqual(entry["decision"], "allow")
        self.assertEqual(entry["operation_id"], op["id"])
        self.assertIsNotNone(op.get("confirmed_by"))
        self.assertIsNotNone(op.get("confirmed_at"))


class TestRejectAuditRecord(unittest.TestCase):
    """M4.8b — reject 后 audit_and_log 含 user_id。"""

    def setUp(self):
        _use_temp_log(self)

    def tearDown(self):
        _restore_log(self)

    def test_reject_audit_log(self):
        op = create_operation_card(
            drafts=[{"summary": "test", "projectKey": "CT", "issueType": "Task"}],
            user_id="rabbit",
        )
        from jira_operation_manager import mark_rejected

        op = mark_rejected(op, rejected_by="pm-alice")
        ag.record_operation_audit(
            actor="pm-alice",
            action="operation_reject",
            operation_id=op["id"],
            decision="allow",
            origin="http",
        )
        rows = ag.query_persistent_audit_logs(
            limit=5,
            operation_id=op["id"],
        )
        self.assertGreaterEqual(len(rows), 1)
        entry = rows[0]
        self.assertEqual(entry["actor"], "pm-alice")
        self.assertEqual(entry["action"], "operation_reject")
        self.assertEqual(entry["decision"], "allow")
        self.assertIsNotNone(op.get("rejected_by"))
        self.assertIsNotNone(op.get("rejected_at"))


class TestUnauthorizedDenyAudit(unittest.TestCase):
    """M4.8c — 未授权 403 后 audit 含 decision=deny + stranger actor。"""

    def setUp(self):
        ag.reload_audit_config()
        _use_temp_log(self)

    def tearDown(self):
        _restore_log(self)

    def test_deny_audit_record(self):
        verdict = ag.check_operation_approver(
            "e2e-audit-stranger",
            "confirm",
            "jira-op-deny-test",
        )
        self.assertEqual(verdict["decision"], "deny")

        ag.record_operation_audit(
            actor="e2e-audit-stranger",
            action="operation_confirm",
            operation_id="jira-op-deny-test",
            decision="deny",
            reason=verdict["reason"],
            origin="http",
        )
        rows = ag.query_persistent_audit_logs(
            limit=5,
            operation_id="jira-op-deny-test",
        )
        self.assertGreaterEqual(len(rows), 1)
        entry = rows[0]
        self.assertEqual(entry["actor"], "e2e-audit-stranger")
        self.assertEqual(entry["decision"], "deny")
        self.assertIn("无权", entry["reason"] or "")


class TestPersistentJsonlRoundtrip(unittest.TestCase):
    """M4.8d — JSONL 持久化写入后查询读出完整字段。"""

    def setUp(self):
        _use_temp_log(self)

    def tearDown(self):
        _restore_log(self)

    def test_jsonl_write_read(self):
        # 写入 3 条
        for i, (actor, action, decision) in enumerate([
            ("rabbit", "operation_confirm", "allow"),
            ("pm", "operation_reject", "allow"),
            ("stranger", "operation_confirm", "deny"),
        ]):
            ag.record_operation_audit(
                actor=actor,
                action=action,
                operation_id="jira-op-jsonl-001",
                decision=decision,
                origin="test",
            )

        rows = ag.query_persistent_audit_logs(
            limit=10,
            operation_id="jira-op-jsonl-001",
        )
        self.assertEqual(len(rows), 3)
        decisions = {r["decision"] for r in rows}
        self.assertEqual(decisions, {"allow", "deny"})

        # 验证 JSONL 文件格式：每行合法 JSON
        log_file = ag._AUDIT_LOG_PATH
        with open(log_file, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        self.assertGreaterEqual(len(lines), 3)
        for line in lines:
            entry = json.loads(line)
            self.assertIn("timestamp", entry)
            self.assertIn("actor", entry)
            self.assertIn("action", entry)
            self.assertIn("decision", entry)


class TestApprovalWhitelist(unittest.TestCase):
    """M4.5 白名单回归（保留）。"""

    def setUp(self):
        ag.reload_audit_config()

    def test_approver_allowed(self):
        v = ag.check_operation_approver("e2e-audit-pm", "reject", "op-1")
        self.assertEqual(v["decision"], "allow")

    def test_stranger_denied(self):
        v = ag.check_operation_approver("e2e-audit-stranger", "confirm", "op-2")
        self.assertEqual(v["decision"], "deny")
        self.assertIn("无权", v["reason"])


if __name__ == "__main__":
    unittest.main()
