#!/usr/bin/env python3
"""Smoke: chat-only lane (no Jira plugin) vs work query."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")


def post_chat(content: str) -> str:
    body = json.dumps({"messages": [{"role": "user", "content": content}], "config": {}}).encode()
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    hello_body = post_chat("你好")
    if "plugin_state" in hello_body or "jira_structured" in hello_body:
        print("FAIL hello: unexpected Jira plugin in stream")
        print(hello_body[:400])
        return 1
    # 旧固定模板特征（不应再出现整段 bullet 清单）
    if "查看任务的代码提交记录" in hello_body and "本周待办" in hello_body:
        print("WARN hello: looks like legacy fixed template (check model prompt)")
    print("OK hello chat-only (no jira plugin)")

    work_body = post_chat("统计本周 CT 项目未完成任务")
    if "plugin_state" not in work_body and "Jira" not in work_body and "jql" not in work_body.lower():
        print("WARN work: no obvious Jira path in response (may still be ok if LLM-only)")
    else:
        print("OK work query may hit Jira path")
    print("SMOKE_CHAT_ONLY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
