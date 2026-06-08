"""
Hub MCP tool registry — readonly tools from tools/registry.yaml.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

import yaml

_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "tools", "registry.yaml")

_AUDIT_MAP = {
    "jira": "jira_query",
    "knowledge": "notion_docs",
    "svn": "svn_code",
}


@lru_cache(maxsize=1)
def load_tool_registry() -> list[dict]:
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get("tools") or [])


def get_readonly_tools() -> list[dict]:
    return [t for t in load_tool_registry() if (t.get("risk") or "readonly") == "readonly"]


def get_tool_meta(name: str) -> dict | None:
    for t in load_tool_registry():
        if t.get("name") == name:
            return t
    return None


def invoke_readonly_tool(
    name: str,
    args: dict | None = None,
    user_cfg: dict | None = None,
    *,
    origin: str = "mcp",
) -> dict:
    """Invoke a readonly registry tool; returns {ok, result|error}."""
    meta = get_tool_meta(name)
    if not meta:
        return {"ok": False, "error": f"unknown tool: {name}"}
    if (meta.get("risk") or "readonly") != "readonly":
        return {"ok": False, "error": f"tool {name} is not readonly (use HITL write path)"}

    from audit_gateway import audit_and_log

    category = meta.get("category", "jira")
    audit_id = _AUDIT_MAP.get(category, "jira_query")
    verdict = audit_and_log(audit_id, name, args or {}, origin=origin)
    if verdict.get("decision") == "deny":
        return {"ok": False, "error": verdict.get("reason", "denied"), "audit": verdict}

    from ai_bridge import execute_tool_call

    try:
        raw = execute_tool_call(name, json.dumps(args or {}), user_cfg=user_cfg or {})
        return {"ok": True, "result": raw, "audit": verdict}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500], "audit": verdict}


def list_mcp_tools_payload() -> list[dict]:
    out = []
    for t in get_readonly_tools():
        fn = t.get("function") or {}
        out.append({
            "name": t.get("name"),
            "description": (t.get("description") or "").strip(),
            "category": t.get("category"),
            "risk": t.get("risk"),
            "parameters": fn.get("parameters") or {},
        })
    return out
