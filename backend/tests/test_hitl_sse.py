"""E2.2 — hitl_sse / operation_confirm helpers."""
from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hitl_sse import operation_progress, sse_event


def test_operation_progress_event():
    raw = operation_progress("running", "调用 Jira…", percent=50, op_id="op-1")
    text = raw.decode("utf-8")
    assert text.startswith("data: ")
    payload = json.loads(text.split("data: ", 1)[1].strip())
    assert payload["_event"] == "operation_progress"
    assert payload["phase"] == "running"
    assert payload["percent"] == 50
    assert payload["op_id"] == "op-1"


def test_sse_event_shape():
    raw = sse_event("operation_complete", {"ok": True, "message": "done"})
    payload = json.loads(raw.decode("utf-8").split("data: ", 1)[1].strip())
    assert payload["_event"] == "operation_complete"
    assert payload["ok"] is True


if __name__ == "__main__":
    test_operation_progress_event()
    test_sse_event_shape()
    print("test_hitl_sse OK")
