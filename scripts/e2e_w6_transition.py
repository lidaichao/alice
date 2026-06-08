#!/usr/bin/env python3
"""W6: Jira state transition via confirm card (HTTP e2e)."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")
BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND)

ISSUE = os.environ.get("W6_ISSUE_KEY", "CT-11152")


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def jira_status(issue_key: str) -> str:
    from ai_bridge import load_global_config
    from jira_mcp_server import ensure_jira_connected

    cfg = load_global_config()
    os.environ["JIRA_BASE_URL"] = cfg.get("JIRA_BASE_URL", "")
    os.environ["JIRA_PAT"] = cfg.get("JIRA_PAT", "")
    os.environ["JIRA_USERNAME"] = cfg.get("JIRA_USERNAME", "admin")
    client, err = ensure_jira_connected()
    if err:
        raise RuntimeError(err)
    r = client._request("GET", f"/issue/{issue_key}?fields=status", timeout=15)
    return r.json()["fields"]["status"]["name"]


def pick_target_phrase(issue_key: str, current: str) -> tuple[str, str]:
    """Return (phrase for parse_jira_transition_target, expected_to_status)."""
    from ai_bridge import load_global_config
    from jira_mcp_server import ensure_jira_connected
    from jira_search_engine import parse_jira_transition_target
    from jira_operation_manager import resolve_transition_for_target

    cfg = load_global_config()
    os.environ["JIRA_BASE_URL"] = cfg.get("JIRA_BASE_URL", "")
    os.environ["JIRA_PAT"] = cfg.get("JIRA_PAT", "")
    os.environ["JIRA_USERNAME"] = cfg.get("JIRA_USERNAME", "admin")
    client, _ = ensure_jira_connected()
    trans = client.list_transitions(issue_key)
    cur = current.strip().lower()
    candidates: list[tuple[str, str]] = []
    for t in trans:
        to_name = (t.get("to") or {}).get("name") or ""
        if to_name.strip().lower() == cur:
            continue
        low = to_name.lower()
        if "完成" in to_name or "done" in low or "解决" in to_name:
            candidates.append(("完成", to_name))
        elif "处理" in to_name or "progress" in low:
            candidates.append(("处理中", to_name))
        elif "待" in to_name or "to do" in low or "open" in low:
            candidates.append(("待办", to_name))
        elif "关闭" in to_name or "closed" in low:
            candidates.append(("关闭", to_name))
        else:
            candidates.append((to_name, to_name))
    for phrase, to_name in candidates:
        parsed = parse_jira_transition_target(f"改成{phrase}")
        resolved = resolve_transition_for_target(trans, parsed)
        if resolved.get("to_status") == to_name:
            return phrase, to_name
    if candidates:
        phrase, to_name = candidates[0]
        return phrase, to_name
    raise RuntimeError(f"no alternate transition from status={current}")


def post_chat_sse(user_text: str, conversation_id: str) -> str:
    body = json.dumps(
        {
            "messages": [{"role": "user", "content": user_text}],
            "config": {"conversation_id": conversation_id},
        }
    ).encode("utf-8")
    r = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=90) as resp:
        return resp.read().decode("utf-8", errors="replace")


def create_transition_op(user_text: str, conversation_id: str) -> dict:
    stream = post_chat_sse(user_text, conversation_id)
    op_id = None
    for line in stream.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            continue
        try:
            evt = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if evt.get("_event") == "confirm_card":
            op_id = evt.get("op_id")
            break
    if not op_id:
        raise RuntimeError("Hub chat did not emit confirm_card")
    op = req("GET", f"/operations/{op_id}")
    assert op.get("ok"), op
    return op["operation"]


def main() -> int:
    before = jira_status(ISSUE)
    phrase, expected_to = pick_target_phrase(ISSUE, before)
    user_text = f"请把 {ISSUE} 状态改成{phrase}"
    print(f"before={before} target_phrase={phrase} expected_to={expected_to}")
    print(f"user_text={user_text}")

    op = create_transition_op(user_text, "w6-e2e-session")
    assert op.get("kind") == "jira_transition_issue", op
    op_id = op["id"]
    print(f"OK confirm_card op={op_id}")

    conf = req("POST", f"/operations/{op_id}/confirm", {})
    assert conf.get("ok"), conf
    assert conf.get("operation", {}).get("status") in ("created", "completed", "succeeded"), conf
    print(f"OK confirm status={conf['operation']['status']}")

    after = jira_status(ISSUE)
    print(f"after={after}")
    assert after != before, f"status unchanged: {before}"
    if expected_to:
        assert after == expected_to or expected_to in after or after in expected_to, (
            f"expected ~{expected_to}, got {after}"
        )

    print("W6_TRANSITION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
