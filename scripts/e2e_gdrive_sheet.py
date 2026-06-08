#!/usr/bin/env python3
"""
E2E: GDrive spreadsheet catalog + read via Hub tools.
Requires GDRIVE_KEY + GDRIVE_FOLDERS in global_config and optional:
  GDRIVE_E2E_QUERY, GDRIVE_E2E_FILE_ID, GDRIVE_E2E_EXPECT
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")
BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND)


def mcp_tool(name: str, arguments: dict) -> dict:
    body = json.dumps({"arguments": arguments}).encode("utf-8")
    r = urllib.request.Request(
        f"{BASE}/mcp/v1/tools/{name}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=120) as resp:
        outer = json.loads(resp.read().decode("utf-8"))
    if not outer.get("ok"):
        return outer
    inner = json.loads(outer.get("result", "{}"))
    return inner


def main() -> int:
    health = urllib.request.urlopen(f"{BASE}/health", timeout=10)
    if health.status != 200:
        print("FAIL hub down")
        return 1

    from ai_bridge import load_global_config

    cfg = load_global_config()
    if not cfg.get("GDRIVE_KEY") or not cfg.get("GDRIVE_FOLDERS"):
        print("SKIP gdrive e2e (GDRIVE_KEY/FOLDERS not configured)")
        return 0

    os.environ["GDRIVE_KEY"] = cfg.get("GDRIVE_KEY", "")
    os.environ["GDRIVE_FOLDERS"] = cfg.get("GDRIVE_FOLDERS", "")

    query = os.environ.get("GDRIVE_E2E_QUERY", "").strip()
    file_id = os.environ.get("GDRIVE_E2E_FILE_ID", "").strip()
    expect = os.environ.get("GDRIVE_E2E_EXPECT", "").strip()

    if not query and not file_id:
        print("SKIP gdrive e2e (set GDRIVE_E2E_QUERY or GDRIVE_E2E_FILE_ID)")
        return 0

    if query:
        cat = mcp_tool("search_docs_catalog", {"query": query, "source": "gdrive"})
        assert cat.get("status") == "ok", cat
        results = cat.get("result") or []
        assert results, f"catalog empty for query={query!r}"
        print(f"OK catalog hits={len(results)}")
        if not file_id:
            file_id = results[0].get("doc_id", "")

    read = mcp_tool("read_specific_doc", {"doc_id": file_id, "source": "gdrive"})
    assert read.get("status") == "ok", read
    text = read.get("llm_text") or ""
    assert len(text) > 20, "read too short"
    print(f"OK read_specific_doc len={len(text)}")
    if expect and expect not in text:
        print(f"FAIL expected substring missing: {expect!r}")
        return 1

    print("GDRIVE_SHEET_E2E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
