"""E5 — intent_router confidence & disambiguation."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from intent_router import (
    apply_route_meta_to_tools,
    build_disambiguation_payload,
    route_intent,
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


if __name__ == "__main__":
    test_low_confidence_does_not_narrow_tools()
    test_high_confidence_narrows_tools()
    test_disambiguation_payload_when_low_conf()
    test_intent_user_override_prefix()
    print("test_intent_router OK")
