#!/usr/bin/env python3
"""MCP registry readonly + mailbox worker gate."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_registry import (
    MAILBOX_TOOL_NAMES,
    get_readonly_tools,
    get_tool_meta,
    get_worker_tools,
    list_mcp_tools_payload,
)


def main():
    readonly = get_readonly_tools()
    assert len(readonly) >= 5, readonly
    worker = get_worker_tools()
    assert len(worker) >= 3, worker
    assert MAILBOX_TOOL_NAMES.issubset({t["name"] for t in worker})

    draft = get_tool_meta("create_issues_draft")
    assert draft and draft.get("risk") == "write"

    payload = list_mcp_tools_payload()
    readonly_payload = [p for p in payload if p.get("risk") == "readonly"]
    worker_payload = [p for p in payload if p.get("risk") == "worker"]
    assert len(readonly_payload) >= 5
    assert len(worker_payload) >= 3
    assert all(p.get("risk") == "readonly" for p in readonly_payload)
    assert all(p.get("risk") == "worker" for p in worker_payload)
    print("test_mcp_registry OK")


if __name__ == "__main__":
    main()
