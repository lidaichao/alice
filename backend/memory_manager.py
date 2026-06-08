"""
浅层记忆引擎 — 本地 JSON 持久化（无向量库）。
对齐白泽 shallow memory：团队常驻规则、人名分工等。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger("memory-manager")

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_MEMORY_FILE = os.path.join(_DATA_DIR, "shallow_memory.json")
_lock = threading.RLock()

_REMEMBER_PATTERNS = [
    re.compile(
        r"(?:请记住|记住|记下|铭记|以后都|往后都)(?:[，,:：\s]*)(.+?)(?:[。.!！?？]|$)",
        re.I,
    ),
    re.compile(
        r"(?:规则|约定)[:：]\s*(.+?)(?:[。.!！?？]|$)",
        re.I,
    ),
]


def _default_store() -> dict:
    return {"version": 1, "entries": [], "updated_at": None}


def _load_store() -> dict:
    try:
        if os.path.isfile(_MEMORY_FILE):
            with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                return data
    except Exception as e:
        logger.warning(f"[Memory] load failed: {e}")
    return _default_store()


def _persist_store(store: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    store["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = _MEMORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _MEMORY_FILE)


def add_memory_entry(text: str, *, source: str = "user", key: Optional[str] = None) -> dict:
    """写入一条浅层记忆。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("记忆内容不能为空")
    with _lock:
        store = _load_store()
        entry = {
            "id": f"mem-{uuid.uuid4().hex[:10]}",
            "key": (key or "").strip() or None,
            "text": text,
            "source": source,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        store.setdefault("entries", []).append(entry)
        _persist_store(store)
        logger.info(f"[Memory] saved entry {entry['id']}: {text[:80]}")
        return entry


def parse_remember_instruction(user_text: str) -> Optional[str]:
    """从「请记住…」类句子提取要记住的规则文本。"""
    t = (user_text or "").strip()
    if not t:
        return None
    if not re.search(r"请记住|记住|记下|铭记|以后都|往后都", t):
        return None
    for pat in _REMEMBER_PATTERNS:
        m = pat.search(t)
        if m:
            captured = (m.group(1) or "").strip()
            if len(captured) >= 4:
                return captured
    if len(t) >= 6:
        return t
    return None


def get_all_memory() -> list[dict]:
    with _lock:
        store = _load_store()
        return list(store.get("entries") or [])


def get_memory_meta() -> dict:
    """供 UI 展示注入上限与截断提示。"""
    entries = get_all_memory()
    count = len(entries)
    char_sum = sum(len((e.get("text") or "")) for e in entries)
    budget = 2000
    meta = {
        "count": count,
        "inject_char_budget": budget,
        "approx_chars": min(char_sum, budget),
        "inject_note": f"约 {budget} 字会注入模型（取最近条目，超出截断）",
    }
    if count > 50:
        meta["truncation_warning"] = "规则较多，仅部分会注入 Prompt，建议删除过时条目。"
    return meta


def update_memory_entry(entry_id: str, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("记忆内容不能为空")
    with _lock:
        store = _load_store()
        for e in store.get("entries") or []:
            if e.get("id") == entry_id:
                e["text"] = text
                e["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                _persist_store(store)
                logger.info(f"[Memory] updated {entry_id}")
                return e
    raise ValueError("记忆条目不存在")


def delete_memory_entry(entry_id: str) -> bool:
    with _lock:
        store = _load_store()
        entries = store.get("entries") or []
        new_entries = [e for e in entries if e.get("id") != entry_id]
        if len(new_entries) == len(entries):
            raise ValueError("记忆条目不存在")
        store["entries"] = new_entries
        _persist_store(store)
        logger.info(f"[Memory] deleted {entry_id}")
        return True


_INTENT_MEMORY_HINTS: dict[str, tuple[str, ...]] = {
    "CHAT_ONLY": ("闲聊", "打招呼", "问候"),
    "JIRA_STRUCTURED_SEARCH": ("Jira", "任务", "项目", "CT-", "筛选"),
    "JIRA_WRITE": ("Jira", "创建", "流转", "状态", "确认"),
    "DOC_SEARCH": ("文档", "策划", "KB-", "Notion", "设计"),
    "KNOWLEDGE_QUERY": ("文档", "策划", "KB-", "方案", "设计", "知识"),
    "WORKFLOW_TRIGGER": ("模板", "检查", "子任务", "工作流"),
    "CODE_COMMIT_LIST": ("提交", "commit", "SVN", "revision", "代码"),
    "WEEKLY_REPORT": ("周报", "日报", "总结"),
}


def _memory_matches_intent(text: str, intent_label: str) -> bool:
    """按 intent 过滤浅层记忆（E6.3）；闲聊道排除 Jira/代码类规则。"""
    if not intent_label or intent_label in ("FULL_SET", "EMPTY"):
        return True
    if intent_label == "CHAT_ONLY":
        t = (text or "").lower()
        noisy = ("jira", "ct-", "commit", "svn", "确认卡", "流转", "草稿")
        return not any(n in t for n in noisy)
    hints = _INTENT_MEMORY_HINTS.get(intent_label)
    if not hints:
        return True
    t = (text or "").lower()
    return any(h.lower() in t for h in hints)


def format_memory_for_prompt(max_chars: int = 2000, intent_label: str = "") -> str:
    """组装注入 System Prompt 的常驻记忆块；可按 intent 过滤无关规则。"""
    entries = get_all_memory()
    if not entries:
        return ""
    lines = ["【团队浅层记忆 · 必须遵守】"]
    used = 0
    for e in entries[-30:]:
        text = e.get("text", "")
        if intent_label and not _memory_matches_intent(text, intent_label):
            continue
        line = f"- {text}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def try_capture_memory_from_message(user_text: str) -> Optional[dict]:
    """若用户消息是记忆写入指令，落盘并返回 entry。"""
    rule = parse_remember_instruction(user_text)
    if not rule:
        return None
    return add_memory_entry(rule, source="user_instruction")
