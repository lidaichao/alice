"""
Plugin-Gateway — 草稿箱 / Jira 写操作直通车（HITL 卡片，禁止直写 Jira）。

从 ai_bridge 绞杀者迁出（E1.2）；ai_bridge 仅保留薄 re-export。
"""
from __future__ import annotations

import json
import re
from typing import List, Optional


def heuristic_issues_drafts(user_text: str) -> list:
    """无 LLM 时的批量草稿兜底。"""
    t = user_text or ""
    count = 3
    m = re.search(r"(\d+)\s*个", t)
    if m:
        try:
            count = min(max(int(m.group(1)), 1), 20)
        except ValueError:
            count = 3
    topic = "UI 优化"
    m2 = re.search(r"关于(.+?)(?:的\s*)?(?:Jira|任务|issue|bug)?", t, re.I)
    if m2 and m2.group(1).strip():
        topic = m2.group(1).strip()[:60]
    elif re.search(r"UI|界面|前端", t, re.I):
        topic = "UI 优化"
    return [
        {
            "summary": f"{topic} — {i + 1}",
            "projectKey": "CT",
            "issueType": "Task",
            "description": f"草拟自用户描述：{t[:300]}",
        }
        for i in range(count)
    ]


def collect_jira_write_sse_chunks(user_text, user_cfg, intent_info) -> list:
    """Jira 写操作直通车：返回 confirm_card SSE 块列表。"""
    from jira_search_engine import (
        is_jira_transition_write_request,
        parse_jira_transition_target,
        ISSUE_KEY_RE,
    )
    from jira_operation_manager import (
        create_transition_operation_card,
        save_operation,
        build_confirm_tool_response,
    )

    if not is_jira_transition_write_request(user_text, intent_info.get("route", "")):
        return []

    m = ISSUE_KEY_RE.search(user_text)
    if not m:
        return []
    issue_key = m.group(1).upper()
    target = parse_jira_transition_target(user_text)

    op = create_transition_operation_card(
        issue_key=issue_key,
        target_status=target,
        transition_id="",
        transition_name="",
        to_status="",
    )
    save_operation(op)
    preview = (
        f"【操作确认卡】已生成。即将把 **{issue_key}** 流转到「{target}」。\n"
        f"请在确认卡上点击授权后执行；Alice 不会未经您确认直接修改 Jira。\n"
        f"（您拥有完整改状态权限，系统仅做安全确认，并非无权限。）"
    )
    payload = build_confirm_tool_response(op, preview)
    return [
        f"data: {json.dumps({'_event': 'confirm_card', 'op_id': op['id'], 'operation': payload.get('operation'), 'preview': preview}, ensure_ascii=False)}\n\n".encode("utf-8"),
        f"data: {json.dumps({'choices': [{'delta': {'content': preview}}]}, ensure_ascii=False)}\n\n".encode("utf-8"),
    ]


def collect_draft_sse_chunks(
    user_text: str,
    issues_list: list = None,
    conversation_id: str = "",
) -> list:
    """草稿箱直通车：draft_card SSE，禁止直写 Jira。"""
    from jira_operation_manager import (
        create_issues_draft,
        build_draft_tool_response,
    )

    items = issues_list if issues_list else heuristic_issues_drafts(user_text)
    draft = create_issues_draft(
        items,
        source_text=user_text,
        conversation_id=conversation_id or "",
    )
    payload = build_draft_tool_response(draft)
    preview = payload.get("result", "")
    card_evt = {
        "_event": "draft_card",
        "draft_id": draft["id"],
        "items": payload.get("items") or [],
        "warnings": payload.get("warnings") or [],
        "preview": preview,
    }
    return [
        f"data: {json.dumps(card_evt, ensure_ascii=False)}\n\n".encode("utf-8"),
        f"data: {json.dumps({'choices': [{'delta': {'content': preview}}]}, ensure_ascii=False)}\n\n".encode("utf-8"),
    ]


def is_draft_request(user_text: str, intent_route: str) -> bool:
    if not user_text:
        return False
    try:
        from intent_classifier import is_jira_draft_request

        return intent_route == "jira_draft" or is_jira_draft_request(user_text)
    except ImportError:
        return intent_route == "jira_draft"


def is_jira_write_request(user_text: str, intent_route: str) -> bool:
    if not user_text:
        return False
    try:
        from jira_search_engine import is_jira_transition_write_request as _is_write

        return intent_route == "jira_write" or _is_write(user_text, intent_route)
    except ImportError:
        return intent_route == "jira_write"


def try_express_lanes(
    user_text: str,
    intent_info: dict,
    user_cfg: dict,
    conversation_id: str = "",
) -> Optional[list]:
    """
    若命中草稿或写操作快车道，返回 SSE chunk 列表；否则 None。
    """
    route = intent_info.get("route", "")
    if is_draft_request(user_text, route):
        chunks = collect_draft_sse_chunks(user_text, conversation_id=conversation_id)
        return chunks if chunks else None
    if is_jira_write_request(user_text, route):
        chunks = collect_jira_write_sse_chunks(user_text, user_cfg, intent_info)
        return chunks if chunks else None
    return None
