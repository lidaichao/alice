"""E6.2 / E6.5 — catalog 关键词 + KB-id / Issue Key 穿透与 hybrid 重排。"""
from __future__ import annotations

import re
from typing import List


_KB_ID_RE = re.compile(r"\b(KB-[\w-]+)\b", re.I)
_ISSUE_KEY_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])")


def extract_catalog_needles(query: str) -> List[str]:
    """从 query 提取 KB-id、Issue Key 用于加权。"""
    needles: List[str] = []
    for m in _KB_ID_RE.finditer(query or ""):
        needles.append(m.group(1).upper())
    for m in _ISSUE_KEY_RE.finditer(query or ""):
        needles.append(m.group(1).upper())
    return needles


def boost_catalog_entries(catalog: list, query: str) -> list:
    """对目录结果按 KB-id / Issue Key / 标题关键词重排（确定性 L1）。"""
    if not catalog:
        return catalog
    needles = extract_catalog_needles(query)
    q_lower = (query or "").lower()

    def score(item: dict) -> float:
        blob = " ".join(
            [
                str(item.get("title", "")),
                str(item.get("doc_id", "")),
                str(item.get("snippet", "")),
            ]
        ).upper()
        s = 0.0
        for n in needles:
            if n in blob:
                s += 10.0
        if q_lower and q_lower[:4] in blob.lower():
            s += 1.0
        return s

    return sorted(catalog, key=score, reverse=True)


def merge_hybrid_snippets(keyword_hits: list, vector_hits: list, top_k: int = 5) -> list:
    """E6.5：合并关键词目录命中与向量 chunk 命中（按 doc_id 去重）。"""
    seen = set()
    out = []
    for row in keyword_hits + vector_hits:
        doc_id = row.get("doc_id") or row.get("id") or ""
        key = doc_id or row.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= top_k:
            break
    return out
