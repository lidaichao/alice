"""
Strip DSML / tool_calls text leaks from model output (DeepSeek v4-flash variants).
"""
from __future__ import annotations

import re

_TOOL_CALLS_BLOCK = re.compile(r"<\|tool_calls\|>.*?</\|tool_calls\|>", re.DOTALL | re.I)
_INVOKE_BLOCK = re.compile(r"<\|invoke\|>.*?</\|invoke\|>", re.DOTALL | re.I)
_PARAMETER_BLOCK = re.compile(r"<\|parameter\|>.*?</\|parameter\|>", re.DOTALL | re.I)
_DSML_BLOCK = re.compile(r"<\|DSML\|>.*?</\|DSML\|>", re.DOTALL | re.I)
_DSML_TAG = re.compile(r"</?\|DSML\|>", re.I)

_LINE_OPEN = re.compile(
    r"^\s*<\s*\|?\s*(?:tool_calls|DSML|invoke|parameter)\s*\|?\s*>",
    re.I,
)
_LINE_CLOSE = re.compile(
    r"^\s*<\s*\|?\s*/\s*(?:tool_calls|DSML)\s*\|?\s*>",
    re.I,
)

_LEAK_MARKERS = ("<|tool_calls|>", "<|DSML|>", "<|invoke|>", "<|parameter|>")


def clean_dsml_leak(text: str) -> str:
    """Remove DSML/tool_calls blocks and stray tags from a text blob."""
    if not text:
        return ""
    out = text
    out = _TOOL_CALLS_BLOCK.sub("", out)
    out = _INVOKE_BLOCK.sub("", out)
    out = _PARAMETER_BLOCK.sub("", out)
    out = _DSML_BLOCK.sub("", out)
    out = _DSML_TAG.sub("", out)
    return out.strip()


def line_is_dsml_leak(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if any(m in stripped for m in _LEAK_MARKERS):
        if _LINE_OPEN.match(stripped) or _LINE_CLOSE.match(stripped):
            return True
        if stripped.startswith("<|") and "|>" in stripped:
            return True
    return bool(_LINE_OPEN.match(stripped) or _LINE_CLOSE.match(stripped))


def filter_content_lines(text: str) -> str:
    """Line-level filter: drop DSML lines, keep natural language."""
    if not text:
        return ""
    kept = [ln for ln in text.splitlines() if not line_is_dsml_leak(ln)]
    return "\n".join(kept).strip()


def sse_line_has_dsml_leak(decoded_line: str) -> bool:
    """Skip entire SSE raw line if it contains leak markers."""
    return any(tag in (decoded_line or "") for tag in _LEAK_MARKERS)
