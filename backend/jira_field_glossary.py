"""
Jira 字段含义词典 — PM 标注的业务语义，注入 LLM / 规则引擎。
"""
from __future__ import annotations

import re
from typing import Any, Optional


def normalize_glossary(raw: Any) -> list[dict]:
    """将 global_config JIRA_FIELD_GLOSSARY 规范为条目列表。"""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else []
    if isinstance(raw, dict):
        items = [{"fieldName": k, **(v if isinstance(v, dict) else {"meaning": str(v)})} for k, v in raw.items()]
    out = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("fieldName") or entry.get("name") or "").strip()
        if not name:
            continue
        aliases = entry.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [a.strip() for a in re.split(r"[,，;；]", aliases) if a.strip()]
        elif not isinstance(aliases, list):
            aliases = []
        out.append({
            "fieldId": (entry.get("fieldId") or entry.get("id") or "").strip(),
            "fieldName": name,
            "meaning": (entry.get("meaning") or entry.get("description") or "").strip(),
            "aliases": [str(a).strip() for a in aliases if str(a).strip()],
        })
    return out


def format_glossary_for_prompt(glossary: list[dict], max_items: int = 30) -> str:
    """格式化为决策 / JQL 提示词片段。"""
    if not glossary:
        return ""
    lines = []
    for entry in glossary[:max_items]:
        name = entry.get("fieldName") or ""
        meaning = entry.get("meaning") or ""
        aliases = entry.get("aliases") or []
        alias_s = "、".join(aliases[:8]) if aliases else ""
        part = f"- 「{name}」"
        if meaning:
            part += f"：{meaning}"
        if alias_s:
            part += f"（口语：{alias_s}）"
        lines.append(part)
    if len(glossary) > max_items:
        lines.append(f"- … 另有 {len(glossary) - max_items} 条未列出")
    return "\n".join(lines)


def _text_matches_term(text: str, term: str) -> bool:
    if not text or not term:
        return False
    t = term.strip()
    if len(t) < 2:
        return t in text
    return t in text or re.search(re.escape(t), text, re.I) is not None


def resolve_glossary_entry_by_text(user_text: str, glossary: list[dict]) -> Optional[dict]:
    """用户话术命中别名或字段名时返回词典条目。"""
    text = (user_text or "").strip()
    if not text or not glossary:
        return None
    for entry in glossary:
        name = entry.get("fieldName") or ""
        if name and _text_matches_term(text, name):
            return entry
        for alias in entry.get("aliases") or []:
            if _text_matches_term(text, alias):
                return entry
        meaning = entry.get("meaning") or ""
        if len(meaning) >= 4 and meaning in text:
            return entry
    return None


def resolve_field_by_alias(user_text: str, glossary: list[dict]) -> Optional[str]:
    """命中词典时返回 Jira 字段显示名。"""
    entry = resolve_glossary_entry_by_text(user_text, glossary)
    return entry.get("fieldName") if entry else None


def glossary_suggests_deadline(user_text: str, glossary: list[dict]) -> bool:
    """话术是否像「截止时间 / 本周要交」类，且命中词典。"""
    text = user_text or ""
    if not re.search(r"本周|截止|ddl|要交|待办|周报|完成日|结束", text, re.I):
        return False
    return resolve_glossary_entry_by_text(text, glossary) is not None
