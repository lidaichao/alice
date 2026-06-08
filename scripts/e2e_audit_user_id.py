#!/usr/bin/env python3
"""
M4 E2E — user_id 创建绑定 + reject 审批人落盘。
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
REJECTOR = os.environ.get("AUDIT_E2E_REJECTOR", "e2e-audit-pm")
CONV_ID = os.environ.get("AUDIT_E2E_CONV", "e2e-audit-user-id")
PROJECT = os.environ.get("OPS_E2E_PROJECT", "CT")


def req(
    method: str,
    path: str,
    body: dict | None = None,
    *,
    user_id: str | None = None,
) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers: dict[str, str] = {}
    if data:
        headers["Content-Type"] = "application/json"
    uid = user_id if user_id is not None else CREATOR
    if uid:
        headers["X-Alice-User-Id"] = uid
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    try:
        health = req("GET", "/health", user_id="")
    except Exception:
        print("FAIL hub down")
        return 1
    if health.get("status") not in ("ok", "degraded"):
        print(f"FAIL health: {health}")
        return 1
    print("OK health")

    created = req(
        "POST",
        "/drafts",
        {
            "items": [
                {
                    "summary": "M4 e2e audit user_id",
                    "projectKey": PROJECT,
                    "issueType": "Task",
                }
            ],
            "conversation_id": CONV_ID,
        },
        user_id=CREATOR,
    )
    if not created.get("ok"):
        print(f"FAIL create draft: {created}")
        return 1
    if created.get("user_id") != CREATOR:
        print(f"FAIL draft user_id: expected {CREATOR}, got {created.get('user_id')}")
        return 1
    draft_id = created["draft_id"]
    print(f"OK create draft user_id={CREATOR} ({draft_id})")

    promoted = req("POST", f"/drafts/{draft_id}/confirm", {}, user_id=CREATOR)
    if not promoted.get("ok"):
        print(f"FAIL promote: {promoted}")
        return 1
    op_id = promoted.get("operation_id") or (promoted.get("operation") or {}).get("id")
    if not op_id:
        print(f"FAIL no operation_id: {promoted}")
        return 1
    print(f"OK promote → {op_id}")

    listed = req("GET", "/operations?status=awaiting_confirmation&limit=80", user_id="")
    if not listed.get("ok"):
        print(f"FAIL list: {listed}")
        return 1
    row = next((o for o in (listed.get("operations") or []) if o.get("id") == op_id), None)
    if not row:
        print(f"FAIL list missing {op_id}")
        return 1
    if row.get("user_id") != CREATOR:
        print(f"FAIL operation user_id: expected {CREATOR}, got {row.get('user_id')}")
        return 1
    print(f"OK list user_id={CREATOR}")

    detail = req("GET", f"/operations/{op_id}", user_id="")
    if detail.get("operation", {}).get("user_id") != CREATOR:
        print(f"FAIL GET detail user_id: {detail}")
        return 1
    print("OK GET detail user_id")

    rej = req("POST", f"/operations/{op_id}/reject", {}, user_id=REJECTOR)
    if not rej.get("ok"):
        print(f"FAIL reject: {rej}")
        return 1
    op = rej.get("operation") or {}
    if op.get("status") != "rejected":
        print(f"FAIL status: {op}")
        return 1
    if op.get("rejected_by") != REJECTOR:
        print(f"FAIL rejected_by: expected {REJECTOR}, got {op.get('rejected_by')}")
        return 1
    if not op.get("rejected_at"):
        print(f"FAIL rejected_at missing: {op}")
        return 1
    print(f"OK reject rejected_by={REJECTOR} rejected_at={op.get('rejected_at')}")

    print("E2E_AUDIT_USER_ID_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
