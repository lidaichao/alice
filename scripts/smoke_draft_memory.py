#!/usr/bin/env python3
"""Smoke: memory CRUD + draft reject/confirm API (no live Jira write)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")


def req(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(r, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    try:
        health = req("GET", "/health")
        assert health.get("status") == "ok", health
    except Exception as e:
        print(f"FAIL health: {e}")
        return 1

    # Memory CRUD
    created = req("POST", "/api/memory/entries", {"text": "smoke test rule"})
    eid = created["entry"]["id"]
    listed = req("GET", "/api/memory/entries")
    assert any(x["id"] == eid for x in listed.get("entries", []))
    req("PUT", f"/api/memory/entries/{eid}", {"text": "smoke test rule updated"})
    req("DELETE", f"/api/memory/entries/{eid}")
    print("OK memory CRUD")

    # Draft via backend module (no HTTP create draft route — use local API after chat or module)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    import jira_operation_manager as jom

    draft = jom.create_issues_draft(
        [{"summary": "smoke", "projectKey": "CT", "issueType": "Task"}],
        conversation_id="smoke-conv",
    )
    did = draft["id"]
    jom.reject_draft(did)
    print("OK draft reject (module)")

    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
