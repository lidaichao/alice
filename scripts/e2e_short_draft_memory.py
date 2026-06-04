#!/usr/bin/env python3
"""Short end-to-end: memory HTTP + draft confirm/pending/reject."""
from __future__ import annotations

import json
import os
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    health = req("GET", "/health")
    assert health.get("status") == "ok", health

    entry = req("POST", "/api/memory/entries", {"text": "e2e rule"})["entry"]
    eid = entry["id"]
    req("PUT", f"/api/memory/entries/{eid}", {"text": "e2e rule updated"})
    listed = req("GET", "/api/memory/entries")
    assert any(x["id"] == eid for x in listed["entries"])
    req("DELETE", f"/api/memory/entries/{eid}")
    print("OK memory HTTP CRUD")

    created = req(
        "POST",
        "/drafts",
        {
            "items": [{"summary": "E2E Task", "projectKey": "CT", "issueType": "Task"}],
            "conversation_id": "e2e-session-1",
        },
    )
    assert created.get("ok"), created
    did = created["draft_id"]
    items = created["items"]
    conf = req("POST", f"/drafts/{did}/confirm", {"items": items})
    assert conf.get("ok"), conf
    assert conf.get("drafts"), "missing drafts in confirm response"
    op_id = conf["operation_id"]
    print(f"OK draft confirm op={op_id} drafts={len(conf['drafts'])}")

    pend = req("GET", "/operations/pending?conversation_id=e2e-session-1")
    ops = pend.get("operations") or []
    assert any(o["id"] == op_id for o in ops), pend
    print(f"OK pending restore count={len(ops)}")

    d2 = req(
        "POST",
        "/drafts",
        {"items": [{"summary": "cancel me", "projectKey": "CT", "issueType": "Task"}]},
    )
    rej = req("POST", f"/drafts/{d2['draft_id']}/reject")
    assert rej.get("ok"), rej
    print("OK draft reject HTTP")

    print("E2E_SHORT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
