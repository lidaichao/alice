"""Long-document skeleton extraction for read_specific_doc (E6.1)."""
from __future__ import annotations

import re
from typing import List

MAX_FULL_CHARS = 12000
SKELETON_PREVIEW_CHARS = 2500


def should_use_skeleton(full_text: str) -> bool:
    return len(full_text or "") > MAX_FULL_CHARS


def build_skeleton_from_markdown(full_text: str, title: str = "") -> str:
    """超长正文：输出标题 + 目录式 heading + 前段摘要。"""
    lines = (full_text or "").splitlines()
    headings: List[str] = []
    preview_lines: List[str] = []
    for line in lines:
        if re.match(r"^#{1,4}\s+\S", line):
            headings.append(line.strip())
        if len("\n".join(preview_lines)) < SKELETON_PREVIEW_CHARS:
            preview_lines.append(line)
    parts = ["【文档骨架模式 · 全文过长已截断】"]
    if title:
        parts.append(f"# {title}")
    if headings:
        parts.append("\n## 目录（标题）\n" + "\n".join(headings[:40]))
    parts.append("\n## 开头摘要\n" + "\n".join(preview_lines).strip()[:SKELETON_PREVIEW_CHARS])
    parts.append(
        "\n\n提示：如需某章节全文，请缩小 doc_id 范围或指定章节标题后再读。"
    )
    return "\n".join(parts)
