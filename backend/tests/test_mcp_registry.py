#!/usr/bin/env python3
"""MCP registry readonly gate."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_registry import get_readonly_tools, get_tool_meta, list_mcp_tools_payload


def main():
    readonly = get_readonly_tools()
    assert len(readonly) >= 5, readonly
    draft = get_tool_meta("create_issues_draft")
    assert draft and draft.get("risk") == "write"
    payload = list_mcp_tools_payload()
    assert all(p.get("risk") == "readonly" for p in payload)
    print("test_mcp_registry OK")


if __name__ == "__main__":
    main()
