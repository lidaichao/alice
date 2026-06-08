#!/usr/bin/env python3
"""
M2.7 — Mailbox MCP E2E: list / claim / report via /mcp/v1/tools (Hub 9099).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099").rstrip("/")
ASSIGNEE = os.environ.get("MAILBOX_MCP_ASSIGNEE", "e2e-mcp-agent")

MAILBOX_TOOLS = (
    "mailbox_list_tasks",
    "mailbox_claim_task",
    "mailbox_report_task",
)


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


def mcp_call(tool: str, arguments: dict) -> tuple[int, dict]:
    return req("POST", f"/mcp/v1/tools/{tool}", {"arguments": arguments})


def main() -> int:
    try:
        code, health = req("GET", "/health")
        if code != 200:
            print(f"FAIL hub health HTTP {code}")
            return 1
    except Exception as e:
        print(f"FAIL hub down: {e}")
        return 1

    code, listing = req("GET", "/mcp/v1/tools")
    if code != 200 or not listing.get("ok"):
        print(f"FAIL mcp tool list HTTP {code}: {listing}")
        return 1
    names = {t["name"] for t in (listing.get("tools") or [])}
    for need in MAILBOX_TOOLS:
        if need not in names:
            print(f"FAIL missing mcp tool: {need}")
            return 1
    print(f"OK mcp tool list includes mailbox ({len(names)} tools)")

    code, dispatched = req(
        "POST",
        "/v1/mailbox/dispatch",
        {
            "assignee": ASSIGNEE,
            "payload": {"kind": "e2e_mailbox_mcp", "via": "mcp"},
        },
    )
    if code != 200 or not dispatched.get("ok"):
        print(f"FAIL dispatch HTTP {code}: {dispatched}")
        return 1
    task_id = dispatched.get("mailbox_task_id")
    print(f"OK dispatch {task_id}")

    code, listed = mcp_call(
        "mailbox_list_tasks",
        {"assignee": ASSIGNEE, "status": "pending", "limit": 20},
    )
    if code != 200 or not listed.get("ok"):
        print(f"FAIL mailbox_list_tasks HTTP {code}: {listed}")
        return 1
    ids = [t["id"] for t in (listed.get("tasks") or [])]
    if task_id not in ids:
        print(f"FAIL list pending via MCP: {task_id} not in {ids}")
        return 1
    print("OK mailbox_list_tasks")

    code, claimed = mcp_call("mailbox_claim_task", {"mailbox_task_id": task_id})
    if code != 200 or not claimed.get("ok"):
        print(f"FAIL mailbox_claim_task HTTP {code}: {claimed}")
        return 1
    if (claimed.get("task") or {}).get("status") != "claimed":
        print(f"FAIL claim status: {claimed}")
        return 1
    print("OK mailbox_claim_task")

    code, reported = mcp_call(
        "mailbox_report_task",
        {
            "mailbox_task_id": task_id,
            "status": "done",
            "result": {"ok": True, "e2e": "mailbox_mcp"},
        },
    )
    if code != 200 or not reported.get("ok"):
        print(f"FAIL mailbox_report_task HTTP {code}: {reported}")
        return 1
    if (reported.get("task") or {}).get("status") != "done":
        print(f"FAIL report status: {reported}")
        return 1
    print("OK mailbox_report_task")

    code, conflict = mcp_call(
        "mailbox_report_task",
        {"mailbox_task_id": task_id, "status": "failed", "result": {"ok": False}},
    )
    if code != 409:
        print(f"FAIL illegal transition expected 409 got {code}: {conflict}")
        return 1
    print("OK illegal transition 409")

    print("E2E_MAILBOX_MCP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
