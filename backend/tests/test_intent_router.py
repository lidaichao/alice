"""E5 — intent_router confidence & disambiguation."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from intent_router import (
    apply_route_meta_to_tools,
    build_disambiguation_payload,
    route_intent,
    _fast_path_intent,
    CONFIDENCE_TOOL_FILTER_THRESHOLD,
)


def test_low_confidence_does_not_narrow_tools():
    verdict = {"intent": "jira_search", "confidence": 0.5}
    tools, meta = apply_route_meta_to_tools(["search_jira_issues"], verdict)
    assert tools is None
    assert meta.get("tools_narrowed") is False


def test_high_confidence_narrows_tools():
    verdict = {"intent": "jira_search", "confidence": 0.95}
    tools, meta = apply_route_meta_to_tools(["search_jira_issues"], verdict)
    assert tools is not None
    assert meta.get("tools_narrowed") is True


def test_disambiguation_payload_when_low_conf():
    payload = build_disambiguation_payload(
        {"intent": "full_set", "confidence": 0.4},
        "帮我看看这周情况",
    )
    assert payload is not None
    assert len(payload.get("choices", [])) >= 2
    assert payload.get("confidence", 1) < CONFIDENCE_TOOL_FILTER_THRESHOLD


def test_intent_user_override_prefix():
    tools, label, meta = route_intent("[INTENT:jira_search] 请按此意图处理我上一条需求。")
    assert label == "JIRA_STRUCTURED_SEARCH"
    assert meta.get("user_override") is True


# ── Baize 路由分离测试 (v1.0.23) ──

def test_issue_key_no_write_keywords_routes_to_jira_search():
    """「CT-10899 是什么」→ 无写操作关键词 → jira_search"""
    intent = _fast_path_intent("CT-10899 是什么")
    assert intent == "jira_search", f"expected jira_search, got {intent}"


def test_issue_key_with_status_routes_to_jira_write():
    """「CT-10899 的状态」→ 含「状态」关键词 → jira_write（保留原有精确路径）"""
    intent = _fast_path_intent("CT-10899 的状态")
    assert intent == "jira_write", f"expected jira_write, got {intent}"


def test_issue_key_what_does_routes_to_jira_search():
    """「CT-10899 这个任务做什么」→ 无写操作关键词 → jira_search"""
    intent = _fast_path_intent("CT-10899 这个任务做什么")
    assert intent == "jira_search", f"expected jira_search, got {intent}"


def test_revision_not_misrouted_as_jira_search():
    """「r40966 是什么提交」→ 不是 Issue Key → 不误判为 jira_search"""
    intent = _fast_path_intent("r40966 是什么提交")
    # r40966 is not an Issue Key pattern, should not hit jira_search catch-all
    assert intent != "jira_search", f"r40966 should NOT route to jira_search, got {intent}"
    # Should not match any fast-path (falls to LLM routing)
    assert intent is None, f"expected None (LLM routing), got {intent}"


if __name__ == "__main__":
    test_low_confidence_does_not_narrow_tools()
    test_high_confidence_narrows_tools()
    test_disambiguation_payload_when_low_conf()
    test_intent_user_override_prefix()
    test_issue_key_no_write_keywords_routes_to_jira_search()
    test_issue_key_with_status_routes_to_jira_write()
    test_issue_key_what_does_routes_to_jira_search()
    test_revision_not_misrouted_as_jira_search()
    print("test_intent_router OK")
