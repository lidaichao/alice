"""
Unified SSE collector for Alice /v1/chat/completions stream.
Used by KB regression and Jira E2E tests.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests

DEFAULT_BASE_URL = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")


def build_chat_payload(question: str, config: dict | None = None) -> dict:
    payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": question}],
        "config": dict(config or {}),
    }
    if os.environ.get("JIRA_PAT"):
        payload["user_config"] = {"jira_pat": os.environ["JIRA_PAT"]}
        payload["config"]["jira_pat"] = os.environ["JIRA_PAT"]
    if os.environ.get("JIRA_PROJECTS"):
        payload["config"]["jira_projects"] = os.environ["JIRA_PROJECTS"]
    return payload


def parse_sse_line(decoded: str, state: dict) -> None:
    """Update *state* in place from one SSE data line."""
    if "data: [DONE]" in decoded:
        state["done"] = True
        return
    if not decoded.startswith("data: "):
        return
    try:
        data = json.loads(decoded[6:])
    except json.JSONDecodeError:
        return

    state["lines"] += 1

    if data.get("_event") == "confirm_card" or data.get("custom_type") == "confirm_required":
        state["confirm_card"] = True
    if data.get("_event") == "draft_card":
        state["draft_card"] = True
        state["draft_id"] = data.get("draft_id") or state.get("draft_id")
        state["draft_items_count"] = len(data.get("items") or [])
    if data.get("_event") == "jira_search_supplement":
        state["supplement"] = True

    if data.get("custom_type") == "plugin_state":
        plugin = data.get("plugin") or {}
        if isinstance(plugin, dict):
            name = (plugin.get("name") or "").strip()
            if name:
                state["plugins_seen"].add(name)
            if name == "jira_structured_search":
                state["structured_lane"] = True
                if plugin.get("jql"):
                    state["jql_in_stream"] = plugin.get("jql") or state["jql_in_stream"]
            if name == "search_jira_issues" and plugin.get("status") == "running":
                state["weekly_lane"] = True
            if name == "get_issue_commits":
                state["commits_lane"] = True

    delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
    if delta:
        state["content"] += delta


def empty_stream_state() -> dict:
    return {
        "done": False,
        "lines": 0,
        "content": "",
        "confirm_card": False,
        "draft_card": False,
        "draft_id": "",
        "draft_items_count": 0,
        "supplement": False,
        "plugins_seen": set(),
        "structured_lane": False,
        "weekly_lane": False,
        "commits_lane": False,
        "jql_in_stream": "",
        "error": None,
        "latency_s": 0.0,
    }


def stream_chat(
    question: str,
    *,
    base_url: str | None = None,
    config: dict | None = None,
    timeout: int = 180,
) -> dict:
    """
    POST chat completions and collect full SSE into a result dict.
    plugins_seen is returned as a set on the dict (serialized separately if needed).
    """
    import time

    url = f"{base_url or DEFAULT_BASE_URL}/v1/chat/completions"
    state = empty_stream_state()
    start = time.time()

    try:
        resp = requests.post(
            url,
            json=build_chat_payload(question, config),
            stream=True,
            timeout=timeout,
        )
        if resp.status_code != 200:
            state["error"] = f"HTTP {resp.status_code}"
            state["latency_s"] = round(time.time() - start, 2)
            return state
    except Exception as e:
        state["error"] = str(e)
        state["latency_s"] = round(time.time() - start, 2)
        return state

    for raw in resp.iter_lines():
        if not raw:
            continue
        decoded = raw.decode("utf-8", errors="replace")
        parse_sse_line(decoded, state)
        if state.get("done"):
            break

    state["latency_s"] = round(time.time() - start, 2)
    return state


def stream_result_to_serializable(result: dict) -> dict:
    """Copy result with plugins_seen as sorted list for JSON/report."""
    out = {k: v for k, v in result.items() if k != "plugins_seen"}
    plugins = result.get("plugins_seen") or set()
    out["plugins_seen"] = sorted(plugins) if isinstance(plugins, set) else list(plugins)
    return out
