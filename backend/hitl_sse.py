"""HITL SSE event helpers (E2.2)."""
from __future__ import annotations

import json
from typing import Any, Optional


def sse_event(event: str, payload: dict) -> bytes:
    body = dict(payload or {})
    body["_event"] = event
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n".encode("utf-8")


def intent_disambiguation(payload: dict) -> bytes:
    body = dict(payload or {})
    body["_event"] = "intent_disambiguation"
    return sse_event("intent_disambiguation", body)


def operation_progress(
    phase: str,
    message: str,
    *,
    percent: Optional[int] = None,
    op_id: str = "",
) -> bytes:
    return sse_event(
        "operation_progress",
        {
            "phase": phase,
            "message": message,
            "percent": percent,
            "op_id": op_id,
        },
    )
