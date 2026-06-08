"""
Hub MCP tool registry — readonly + mailbox worker tools from tools/registry.yaml.
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
    "mailbox": "mailbox_worker",
}

MAILBOX_TOOL_NAMES = frozenset({
    "mailbox_list_tasks",
    "mailbox_claim_task",
    "mailbox_report_task",
})


@lru_cache(maxsize=1)
def load_tool_registry() -> list[dict]:
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get("tools") or [])


def get_readonly_tools() -> list[dict]:
    return [t for t in load_tool_registry() if (t.get("risk") or "readonly") == "readonly"]


def get_worker_tools() -> list[dict]:
    return [t for t in load_tool_registry() if (t.get("risk") or "") == "worker"]


def get_tool_meta(name: str) -> dict | None:
    for t in load_tool_registry():
        if t.get("name") == name:
            return t
    return None


def is_mailbox_tool(name: str) -> bool:
    return name in MAILBOX_TOOL_NAMES


def _tool_payload_entry(t: dict) -> dict:
    fn = t.get("function") or {}
    return {
        "name": t.get("name"),
        "description": (t.get("description") or "").strip(),
        "category": t.get("category"),
        "risk": t.get("risk"),
        "parameters": fn.get("parameters") or {},
    }


def _mailbox_task_api(task: dict) -> dict:
    return {
        "id": task["id"],
        "mailbox_task_id": task["id"],
        "status": task["status"],
        "assignee": task["assignee"],
        "payload": task.get("payload"),
        "result": task.get("result"),
        "operation_id": task.get("operation_id"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


def invoke_mailbox_tool(
    name: str,
    args: dict | None = None,
    *,
    origin: str = "mcp",
) -> dict:
    """Invoke a mailbox worker tool via mailbox_store (no duplicate SQL)."""
    meta = get_tool_meta(name)
    if not meta or not is_mailbox_tool(name):
        return {"ok": False, "error": f"unknown mailbox tool: {name}", "http_status": 400}
    if (meta.get("risk") or "") != "worker":
        return {"ok": False, "error": f"tool {name} is not a mailbox worker tool", "http_status": 400}

    from audit_gateway import audit_and_log

    category = meta.get("category", "mailbox")
    audit_id = _AUDIT_MAP.get(category, "mailbox_worker")
    verdict = audit_and_log(audit_id, name, args or {}, origin=origin)
    if verdict.get("decision") == "deny":
        return {
            "ok": False,
            "error": verdict.get("reason", "denied"),
            "audit": verdict,
            "http_status": 400,
        }

    from mailbox_store import get_mailbox_store

    store = get_mailbox_store()
    a = args or {}

    try:
        if name == "mailbox_list_tasks":
            tasks = store.list_tasks(
                status=a.get("status"),
                assignee=a.get("assignee"),
                limit=a.get("limit", 50),
            )
            return {
                "ok": True,
                "tasks": [_mailbox_task_api(t) for t in tasks],
                "audit": verdict,
            }

        if name == "mailbox_claim_task":
            task_id = (a.get("mailbox_task_id") or "").strip()
            if not task_id:
                return {"ok": False, "error": "mailbox_task_id 不能为空", "http_status": 400}
            if not store.get_task(task_id):
                return {"ok": False, "error": "任务不存在", "http_status": 404}
            updated = store.update_task(task_id, status="claimed")
            return {"ok": True, "task": _mailbox_task_api(updated or {}), "audit": verdict}

        if name == "mailbox_report_task":
            task_id = (a.get("mailbox_task_id") or "").strip()
            new_status = (a.get("status") or "").strip().lower()
            if not task_id:
                return {"ok": False, "error": "mailbox_task_id 不能为空", "http_status": 400}
            if new_status not in ("done", "failed"):
                return {"ok": False, "error": "status 必须为 done 或 failed", "http_status": 400}
            if new_status == "done" and a.get("result") is None:
                return {"ok": False, "error": "status=done 时建议提供 result 对象", "http_status": 400}
            if not store.get_task(task_id):
                return {"ok": False, "error": "任务不存在", "http_status": 404}
            updated = store.update_task(task_id, status=new_status, result=a.get("result"))
            return {"ok": True, "task": _mailbox_task_api(updated or {}), "audit": verdict}

        return {"ok": False, "error": f"unhandled mailbox tool: {name}", "http_status": 400}
    except ValueError as e:
        msg = str(e)
        if "非法状态转移" in msg or "非法 status" in msg:
            return {"ok": False, "error": msg, "audit": verdict, "http_status": 409}
        return {"ok": False, "error": msg, "audit": verdict, "http_status": 400}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500], "audit": verdict, "http_status": 500}


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
        return {"ok": False, "error": f"unknown tool: {name}", "http_status": 400}
    if (meta.get("risk") or "readonly") != "readonly":
        return {"ok": False, "error": f"tool {name} is not readonly (use HITL write path)", "http_status": 400}

    from audit_gateway import audit_and_log

    category = meta.get("category", "jira")
    audit_id = _AUDIT_MAP.get(category, "jira_query")
    verdict = audit_and_log(audit_id, name, args or {}, origin=origin)
    if verdict.get("decision") == "deny":
        return {"ok": False, "error": verdict.get("reason", "denied"), "audit": verdict, "http_status": 400}

    from ai_bridge import execute_tool_call

    try:
        raw = execute_tool_call(name, json.dumps(args or {}), user_cfg=user_cfg or {})
        return {"ok": True, "result": raw, "audit": verdict}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500], "audit": verdict, "http_status": 500}


def invoke_mcp_tool(
    name: str,
    args: dict | None = None,
    user_cfg: dict | None = None,
    *,
    origin: str = "mcp",
) -> dict:
    """Route to readonly or mailbox worker invoker."""
    if is_mailbox_tool(name):
        return invoke_mailbox_tool(name, args, origin=origin)
    return invoke_readonly_tool(name, args, user_cfg, origin=origin)


def list_mcp_tools_payload() -> list[dict]:
    return [_tool_payload_entry(t) for t in get_readonly_tools() + get_worker_tools()]
