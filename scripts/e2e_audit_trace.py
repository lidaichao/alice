#!/usr/bin/env python3
"""
M4.4–M4.6 E2E — 审批白名单 403 + 持久 audit.log + GET /v1/audit/logs。
Requires Hub on 9099.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")
CREATOR = os.environ.get("AUDIT_E2E_CREATOR", "e2e-audit-creator")
APPROVER = os.environ.get("AUDIT_E2E_APPROVER", "e2e-audit-pm")
STRANGER = os.environ.get("AUDIT_E2E_STRANGER", "e2e-audit-stranger")
CONV_ID = os.environ.get("AUDIT_E2E_CONV", "e2e-audit-trace")
PROJECT = os.environ.get("OPS_E2E_PROJECT", "CT")


def call(
    method: str,
    path: str,
    body: dict | None = None,
    *,
    user_id: str | None = CREATOR,
) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers: dict[str, str] = {}
    if data:
        headers["Content-Type"] = "application/json"
    if user_id:
        headers["X-Alice-User-Id"] = user_id
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw or e.reason}
        return e.code, payload


def promote_awaiting(summary: str) -> str:
    status, created = call(
        "POST",
        "/drafts",
        {
            "items": [
                {
                    "summary": summary,
                    "projectKey": PROJECT,
                    "issueType": "Task",
                }
            ],
            "conversation_id": CONV_ID,
        },
        user_id=CREATOR,
    )
    assert status == 200 and created.get("ok"), created
    draft_id = created["draft_id"]
    status, promoted = call("POST", f"/drafts/{draft_id}/confirm", {}, user_id=CREATOR)
    assert status == 200 and promoted.get("ok"), promoted
    op_id = promoted.get("operation_id") or (promoted.get("operation") or {}).get("id")
    assert op_id, promoted
    return op_id


def main() -> int:
    try:
        status, health = call("GET", "/health", user_id="")
    except Exception:
        print("FAIL hub down")
        return 1
    if status != 200 or health.get("status") not in ("ok", "degraded"):
        print(f"FAIL health: {health}")
        return 1
    print("OK health")

    op_reject = promote_awaiting("M4.6 e2e authorized reject")
    status, rej = call("POST", f"/operations/{op_reject}/reject", {}, user_id=APPROVER)
    if status != 200 or not rej.get("ok"):
        print(f"FAIL authorized reject: HTTP {status} {rej}")
        return 1
    if rej.get("operation", {}).get("rejected_by") != APPROVER:
        print(f"FAIL rejected_by: {rej}")
        return 1
    print(f"OK authorized reject by {APPROVER}")

    op_deny = promote_awaiting("M4.6 e2e unauthorized reject")
    status, denied = call("POST", f"/operations/{op_deny}/reject", {}, user_id=STRANGER)
    if status != 403:
        print(f"FAIL unauthorized reject expected 403, got {status}: {denied}")
        return 1
    err = denied.get("error") or ""
    if "无权" not in err and "白名单" not in err:
        print(f"FAIL 403 error message: {err}")
        return 1
    print(f"OK unauthorized reject 403: {err[:80]}")

    status, logs_resp = call(
        "GET",
        f"/v1/audit/logs?limit=30&operation_id={op_deny}",
        user_id="",
    )
    if status != 200 or not logs_resp.get("ok"):
        print(f"FAIL audit logs: {logs_resp}")
        return 1
    logs = logs_resp.get("logs") or []
    if not logs:
        print(f"FAIL audit logs empty for {op_deny}")
        return 1
    deny_entries = [
        x for x in logs
        if x.get("operation_id") == op_deny
        and x.get("action") == "operation_reject"
        and x.get("decision") == "deny"
        and x.get("actor") == STRANGER
    ]
    if not deny_entries:
        print(f"FAIL no deny audit entry: {logs[:3]}")
        return 1
    print(f"OK audit logs contain deny entry ({len(deny_entries)})")

    status, logs_rej = call(
        "GET",
        f"/v1/audit/logs?limit=10&operation_id={op_reject}",
        user_id="",
    )
    allow_entries = [
        x for x in (logs_rej.get("logs") or [])
        if x.get("action") == "operation_reject" and x.get("decision") == "allow"
    ]
    if not allow_entries:
        print(f"FAIL no reject allow audit: {logs_rej}")
        return 1
    print("OK audit logs contain authorized reject")

    print("E2E_AUDIT_TRACE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
