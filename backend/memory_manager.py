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


def format_memory_for_prompt(max_chars: int = 2000) -> str:
    """组装注入 System Prompt 的常驻记忆块。"""
    entries = get_all_memory()
    if not entries:
        return ""
    lines = ["【团队浅层记忆 · 必须遵守】"]
    used = 0
    for e in entries[-30:]:
        line = f"- {e.get('text', '')}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def try_capture_memory_from_message(user_text: str) -> Optional[dict]:
    """若用户消息是记忆写入指令，落盘并返回 entry。"""
    rule = parse_remember_instruction(user_text)
    if not rule:
        return None
    return add_memory_entry(rule, source="user_instruction")
