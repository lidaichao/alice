"""
General knowledge / document express lane (catalog → read → summarize).
Not tied to specific coordinator test questions.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# Jira status change / create — not document intent
_WRITE_STATUS = re.compile(
    r"(?:改成|改为|修改为|设为|设置为|更新为).*(?:状态|为)"
    r"|(?:创建|新建|删除).*(?:jira|任务|issue|bug)",
    re.I,
)

_KNOWLEDGE_SIGNAL = re.compile(
    r"文档|知识库|wiki|云盘|策划案|设计案|KB-|Google\s*云盘|技术文档|设计规则|展示规则",
    re.I,
)

_SKIP_LABELS = frozenset({
    "JIRA_STRUCTURED_SEARCH",
    "WEEK_DEADLINE_TASKS",
    "JIRA_WRITE",
    "JIRA_KEYWORD_SEARCH",
    "CODE_COMMIT_LIST",
    "WEEKLY_REPORT",
    "ISSUE_METADATA",
})


def should_use_knowledge_express_lane(
    user_text: str,
    intent_label: str,
    *,
    has_commit_intent: bool,
) -> bool:
    if has_commit_intent:
        return False
    if _WRITE_STATUS.search(user_text or ""):
        return False
    if intent_label in _SKIP_LABELS:
        return False
    if intent_label in ("KNOWLEDGE_QUERY", "DOC_SEARCH", "DOC_JIRA_CROSS"):
        return True
    return bool(_KNOWLEDGE_SIGNAL.search(user_text or ""))


def extract_catalog_query(user_text: str) -> str:
    t = (user_text or "").strip()
    for prefix in ("请", "帮我", "麻烦", "我想"):
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
    m = re.search(r"[《「]([^》」]+)[》」]", t)
    if m:
        return m.group(1).strip()[:80]
    m = re.search(r"KB-[\w-]+", t, re.I)
    if m:
        return m.group(0)
    # Drop trailing instruction verbs, keep title-like head
    t = re.sub(r"(简单|简要)?(分析|讲讲|说明|介绍|列给?我).*$", "", t).strip()
    return (t[:80] if t else user_text[:80]).strip()
