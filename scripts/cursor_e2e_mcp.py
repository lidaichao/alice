#!/usr/bin/env python3
"""M1 Cursor E2E — 3 readonly MCP HTTP tool invocations."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")
ISSUE = os.environ.get("MCP_TEST_ISSUE", "CT-11152")


def mcp_call(tool: str, arguments: dict) -> dict:
    body = json.dumps({"arguments": arguments}).encode("utf-8")
    r = urllib.request.Request(
        f"{BASE}/mcp/v1/tools/{tool}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    tools = urllib.request.urlopen(f"{BASE}/mcp/v1/tools", timeout=15)
    listing = json.loads(tools.read().decode("utf-8"))
    names = {t["name"] for t in listing.get("tools") or []}
    for need in ("query_jira_metadata", "get_issue_commits", "search_docs_catalog"):
        if need not in names:
            print(f"FAIL missing readonly tool in registry: {need}")
            return 1
    print(f"OK mcp tool list ({len(names)} readonly)")

    meta = mcp_call("query_jira_metadata", {"issue_key": ISSUE})
    assert meta.get("ok"), meta
    print(f"OK query_jira_metadata {ISSUE}")

    commits = mcp_call("get_issue_commits", {"issue_key": ISSUE})
    assert commits.get("ok"), commits
    print(f"OK get_issue_commits {ISSUE}")

    catalog = mcp_call("search_docs_catalog", {"query": "路由", "source": "all"})
    assert catalog.get("ok"), catalog
    print("OK search_docs_catalog")

    print("CURSOR_MCP_E2E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
