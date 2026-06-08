#!/usr/bin/env python3
"""
E2E: GDrive queries via chat SSE path (not MCP only).
Requires Hub on 9099 + GDRIVE_KEY/FOLDERS in global_config.
Runs gdrive_sheet_cases.yaml entries with skip: false unless GDRIVE_E2E_ID set.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")


def extract_sse_answer_text(stream: str) -> str:
    """Concatenate chat completion deltas from SSE (Unicode may split across chunks)."""
    parts: list[str] = []
    for block in stream.split("\n\n"):
        for line in block.split("\n"):
            if not line.startswith("data: ") or "[DONE]" in line:
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            msg = choice.get("message") or {}
            chunk = delta.get("content") or msg.get("content") or ""
            if chunk:
                parts.append(str(chunk))
    return "".join(parts)


def post_chat_sse(content: str) -> str:
    body = json.dumps(
        {"messages": [{"role": "user", "content": content}], "config": {}}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_cases() -> list[dict]:
    try:
        import yaml
    except ImportError:
        yaml = None
    path = os.path.join(ROOT, "backend", "eval", "datasets", "gdrive_sheet_cases.yaml")
    if yaml and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cases = data.get("test_cases") or []
        only = os.environ.get("GDRIVE_E2E_ID", "").strip()
        out = []
        for c in cases:
            if c.get("skip"):
                continue
            if only and c.get("id") != only:
                continue
            out.append(c)
        return out
    q = os.environ.get("GDRIVE_E2E_QUERY", "").strip()
    if q:
        return [{
            "id": "env",
            "input": q,
            "expected_cell_contains": os.environ.get("GDRIVE_E2E_EXPECT", ""),
        }]
    return []


def main() -> int:
    try:
        urllib.request.urlopen(f"{BASE}/health", timeout=10)
    except Exception:
        print("FAIL hub down")
        return 1

    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from ai_bridge import load_global_config

    cfg = load_global_config()
    if not cfg.get("GDRIVE_KEY") or not cfg.get("GDRIVE_FOLDERS"):
        print("SKIP gdrive chat e2e (GDRIVE not configured)")
        return 0

    cases = load_cases()
    if not cases:
        print("SKIP gdrive chat e2e (no cases)")
        return 0

    ok_all = True
    for case in cases:
        cid = case.get("id", "?")
        text = (case.get("input") or "").strip()
        expect = (case.get("expected_cell_contains") or "").strip()
        if not text:
            continue
        stream = post_chat_sse(text)
        if "search_docs_catalog" not in stream and "read_specific_doc" not in stream:
            print(f"FAIL {cid}: no KB tool in SSE stream")
            ok_all = False
            continue
        if expect:
            answer_text = extract_sse_answer_text(stream)
            if expect not in answer_text and expect not in stream:
                print(f"FAIL {cid}: missing expected {expect!r} in answer")
                ok_all = False
                continue
        print(f"OK {cid} chat path KB tools + content check")

    if not ok_all:
        return 1
    print("GDRIVE_CHAT_E2E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
