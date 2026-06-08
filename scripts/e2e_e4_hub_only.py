#!/usr/bin/env python3
"""E4 acceptance: Hub-only Jira — client requests without jira_pat."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")
ISSUE = os.environ.get("E4_TEST_ISSUE", "CT-11152")


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


def post_chat_sse(content: str) -> str:
    body = json.dumps({
        "messages": [{"role": "user", "content": content}],
        "config": {},
    }).encode("utf-8")
    r = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=90) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    health = req("GET", "/health")
    assert health.get("status") in ("ok", "degraded"), health
    if not health.get("hub_only_jira"):
        print("FAIL hub_only_jira=false — set ALICE_HUB_ONLY_JIRA=1 on Hub")
        return 1
    print("OK health hub_only_jira=true")

    stream = post_chat_sse(f"查询 {ISSUE} 的标题和状态")
    if "plugin_state" not in stream and "query_jira" not in stream.lower():
        print("WARN jira read path not obvious in stream")
    else:
        print("OK jira search without client jira_pat")

    created = req(
        "POST",
        "/drafts",
        {
            "items": [{"summary": "E4 hub-only draft", "projectKey": "CT", "issueType": "Task"}],
            "conversation_id": "e4-hub-only",
        },
    )
    assert created.get("ok"), created
    did = created["draft_id"]
    conf = req("POST", f"/drafts/{did}/reject", {})
    assert conf.get("ok"), conf
    print("OK draft reject without jira_pat in body")

    print("E4_HUB_ONLY_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:300]}")
        raise SystemExit(1)
