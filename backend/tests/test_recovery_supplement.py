"""E2.4 — submit_supplement recovery path."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jira_operation_manager import (
    create_operation_card,
    mark_failed,
    mark_running,
    apply_supplement_to_operation,
)


def test_apply_supplement_patches_project_key():
    op = create_operation_card(
        [
            {"summary": "A", "projectKey": "", "issueType": "Task"},
            {"summary": "B", "projectKey": "CT", "issueType": "Task"},
        ],
        conversation_id="c1",
        kind="jira_bulk_create",
    )
    op = mark_running(op)
    op = mark_failed(op, "存在未配置项目 Key 的草稿")
    assert op["status"] == "recovery_required"
    op2 = apply_supplement_to_operation(op, {"projectKey": "CT"})
    assert op2["status"] == "awaiting_confirmation"
    assert op2["drafts"][0]["projectKey"] == "CT"
    assert op2.get("recovery") is None


if __name__ == "__main__":
    test_apply_supplement_patches_project_key()
    print("test_recovery_supplement OK")
