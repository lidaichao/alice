#!/usr/bin/env python3
"""M2.1 — MailboxStore unit checks (in-memory SQLite)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from mailbox_store import MailboxStore  # noqa: E402


def main() -> int:
    store = MailboxStore(":memory:")

    task = store.create_task(
        assignee="test-agent",
        payload={"kind": "dispatch_test", "query": "sync docs"},
        operation_id="jira-op-deadbeef01",
    )

    assert task["id"].startswith("mbox-"), task
    assert task["mailbox_task_id"] == task["id"]
    assert task["status"] == "pending"
    assert task["assignee"] == "test-agent"
    assert task["payload"]["kind"] == "dispatch_test"
    assert task["operation_id"] == "jira-op-deadbeef01"
    assert task["created_at"]
    assert task["updated_at"]

    fetched = store.get_task(task["id"])
    assert fetched is not None
    assert fetched["payload"] == task["payload"]
    assert fetched["result"] is None

    listed = store.list_tasks(status="pending", assignee="test-agent", limit=10)
    assert any(t["id"] == task["id"] for t in listed)

    claimed = store.update_task(task["id"], status="claimed")
    assert claimed and claimed["status"] == "claimed"

    done = store.update_task(task["id"], status="done", result={"ok": True, "rows": 3})
    assert done and done["status"] == "done"
    assert done["result"]["rows"] == 3

    try:
        store.update_task(task["id"], status="pending")
        print("FAIL illegal transition should raise")
        return 1
    except ValueError:
        pass

    print("TEST_MAILBOX_STORE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
