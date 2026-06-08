#!/usr/bin/env python3
"""
M2.9 — Mailbox E2E: dispatch → pull → claim → report → verify.
Requires Hub on 9099 (restart after ai_bridge mailbox routes change).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099").rstrip("/")
ASSIGNEE = os.environ.get("MAILBOX_E2E_ASSIGNEE", "e2e-mailbox-agent")


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"ok": False, "error": raw[:300]}
        return e.code, payload


def main() -> int:
    try:
        code, health = req("GET", "/health")
        if code != 200 or health.get("status") not in ("ok", "degraded"):
            print(f"FAIL hub health code={code} body={health}")
            return 1
    except Exception as e:
        print(f"FAIL hub down: {e}")
        return 1

    code, dispatched = req(
        "POST",
        "/v1/mailbox/dispatch",
        {
            "assignee": ASSIGNEE,
            "payload": {"kind": "e2e_mailbox", "step": "full_loop"},
        },
    )
    if code != 200 or not dispatched.get("ok"):
        print(f"FAIL dispatch HTTP {code}: {dispatched}")
        return 1
    task_id = dispatched.get("mailbox_task_id") or (dispatched.get("task") or {}).get("id")
    if not task_id:
        print(f"FAIL dispatch missing mailbox_task_id: {dispatched}")
        return 1
    print(f"OK dispatch {task_id}")

    code, listed = req(
        "GET",
        f"/v1/mailbox/tasks?status=pending&assignee={ASSIGNEE}&limit=20",
    )
    if code != 200 or not listed.get("ok"):
        print(f"FAIL list pending HTTP {code}: {listed}")
        return 1
    ids = [t["id"] for t in (listed.get("tasks") or [])]
    if task_id not in ids:
        print(f"FAIL list pending: {task_id} not in {ids}")
        return 1
    print("OK list pending")

    code, claimed = req("POST", f"/v1/mailbox/tasks/{task_id}/claim", {})
    if code != 200 or not claimed.get("ok"):
        print(f"FAIL claim HTTP {code}: {claimed}")
        return 1
    if (claimed.get("task") or {}).get("status") != "claimed":
        print(f"FAIL claim status: {claimed}")
        return 1
    print("OK claim")

    code, reported = req(
        "POST",
        f"/v1/mailbox/tasks/{task_id}/report",
        {"status": "done", "result": {"ok": True, "e2e": "mailbox", "rows": 1}},
    )
    if code != 200 or not reported.get("ok"):
        print(f"FAIL report HTTP {code}: {reported}")
        return 1
    rep_task = reported.get("task") or {}
    if rep_task.get("status") != "done":
        print(f"FAIL report status: {reported}")
        return 1
    if (rep_task.get("result") or {}).get("e2e") != "mailbox":
        print(f"FAIL report result: {reported}")
        return 1
    print("OK report done")

    code, done_list = req(
        "GET",
        f"/v1/mailbox/tasks?status=done&assignee={ASSIGNEE}&limit=5",
    )
    if code != 200 or task_id not in [t["id"] for t in (done_list.get("tasks") or [])]:
        print(f"FAIL verify done list HTTP {code}: {done_list}")
        return 1
    print("OK verify done")

    # 非法转移：done → failed 应 409
    code, conflict = req(
        "POST",
        f"/v1/mailbox/tasks/{task_id}/report",
        {"status": "failed", "result": {"ok": False}},
    )
    if code != 409:
        print(f"FAIL illegal transition expected 409 got {code}: {conflict}")
        return 1
    print("OK illegal transition 409")

    print("E2E_MAILBOX_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
