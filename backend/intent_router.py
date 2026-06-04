"""
Alice V2.0 Intent Router — LLM 语义分发 + TTL 缓存
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Optional

import requests

logger = logging.getLogger("intent_router")

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
CACHE_TTL_SEC = 300

# intent id → (tool_subset, legacy label for VIP / logs)
INTENT_REGISTRY: dict[str, tuple[Optional[list[str]], str]] = {
    "weekly_report": (["search_jira_issues"], "WEEKLY_REPORT"),
    "week_deadline_tasks": (["search_jira_issues"], "WEEK_DEADLINE_TASKS"),
    "code_commit_list": (["query_jira_metadata", "get_issue_commits"], "CODE_COMMIT_LIST"),
    "code_diff": (
        [
            "get_issue_commits",
            "get_single_commit_diff",
            "query_jira_metadata",
            "search_docs_catalog",
            "read_specific_doc",
        ],
        "CODE_COMMIT_DIFF",
    ),
    "revision_analysis": (
        ["get_single_commit_diff", "get_issue_commits", "query_jira_metadata"],
        "CODE_COMMIT_DIFF",
    ),
    "doc_search": (["search_docs_catalog", "read_specific_doc"], "DOC_SEARCH"),
    "doc_jira_cross": (
        [
            "search_docs_catalog",
            "read_specific_doc",
            "search_jira_issues",
            "query_jira_metadata",
        ],
        "DOC_JIRA_CROSS",
    ),
    "jira_search": (["search_jira_issues"], "JIRA_STRUCTURED_SEARCH"),
    "jira_keyword_search": (["search_jira_issues"], "JIRA_KEYWORD_SEARCH"),
    "jira_write": (["search_jira_issues"], "JIRA_WRITE"),
    "issue_metadata": (["query_jira_metadata"], "ISSUE_METADATA"),
    "knowledge_query": (["search_docs_catalog", "read_specific_doc"], "KNOWLEDGE_QUERY"),
    "full_set": (None, "FULL_SET"),
}

ROUTER_SYSTEM = """你是 Alice 的意图分类器。根据用户最后一句话，输出唯一意图 JSON。

可选 intent（必须从中选一个）：
- week_deadline_tasks: 本周/这周需要完成、待交付的任务列表（含按角色如策划筛选）
- weekly_report: 写周报/日报/月报、本周工作总结
- revision_analysis: 分析某个 SVN revision（如 r40759）的提交内容/diff，常带 Issue Key
- code_diff: 代码 diff 审查、Code Review、分析代码变更
- code_commit_list: 查看某 Issue 有哪些提交、提交列表（不要 diff 深度分析）
- doc_search: 查文档内容、摘要、云盘/Notion 设计文档
- doc_jira_cross: 同时要文档和 Jira 任务关联
- jira_search: Jira 任务统计、筛选、列表（非单 Issue 详情）
- jira_keyword_search: 按关键词找任务
- jira_write: 创建/改状态/流转 Jira（含「改成处理中」）— 系统会弹确认卡，不是无权限
- issue_metadata: 单个 CT-123 的状态、详情、评论
- knowledge_query: 知识库/策划案/wiki 泛查询
- full_set: 闲聊或无法判断（宁可用 full_set）

规则提示：
- 「简要分析 r40759 提交内容」→ revision_analysis（不是 code_commit_list）
- 「球员系统…设计 讲讲文档」→ doc_search
- 「本周需要完成的任务」「策划负责」→ week_deadline_tasks
- 仅「最近两天提交了什么」→ code_commit_list

只输出 JSON：{"intent": "<id>", "confidence": <0.0-1.0>}"""

_route_cache: dict[str, tuple[float, Optional[list[str]], str]] = {}


def _cache_key(text: str) -> str:
    norm = re.sub(r"\s+", " ", (text or "").strip().lower())[:500]
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _cache_get(text: str) -> Optional[tuple[Optional[list[str]], str]]:
    ck = _cache_key(text)
    hit = _route_cache.get(ck)
    if not hit:
        return None
    exp, tools, label = hit
    if time.time() > exp:
        _route_cache.pop(ck, None)
        return None
    logger.info(f"[IntentRouter] cache hit → {label}")
    return tools, label


def _cache_set(text: str, tools: Optional[list[str]], label: str) -> None:
    _route_cache[_cache_key(text)] = (time.time() + CACHE_TTL_SEC, tools, label)


def _resolve_api_key(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit.strip()
    key = os.getenv("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    if key:
        return key.strip()
    try:
        path = os.path.join(os.path.dirname(__file__), "global_config.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return (json.load(f).get("DEEPSEEK_KEY") or "").strip()
    except Exception:
        pass
    return ""


def _parse_router_json(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def classify_intent_llm(user_text: str, api_key: Optional[str] = None) -> dict:
    """DeepSeek temperature=0 → {intent, confidence}"""
    key = _resolve_api_key(api_key)
    if not key:
        return {"intent": "full_set", "confidence": 0.0, "reason": "no_api_key"}

    prompt = f"用户输入：\n{(user_text or '')[:800]}"
    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("DEEPSEEK_MODEL") or "deepseek-chat",
                "messages": [
                    {"role": "system", "content": ROUTER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 80,
            },
            timeout=12,
        )
        resp.raise_for_status()
        content = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _parse_router_json(content)
        intent = (parsed.get("intent") or "full_set").strip().lower()
        if intent not in INTENT_REGISTRY:
            intent = "full_set"
        conf = float(parsed.get("confidence", 0.8))
        return {"intent": intent, "confidence": max(0.0, min(1.0, conf))}
    except Exception as e:
        logger.warning(f"[IntentRouter] LLM classify failed: {e}")
        return {"intent": "full_set", "confidence": 0.0, "reason": str(e)}


def _fast_path_intent(user_text: str) -> Optional[str]:
    """零成本确定性分流（非正则森林，仅极高置信短路径）"""
    t = user_text or ""
    if re.search(r"KB-[\w-]+", t, re.I):
        return "doc_search"
    if re.search(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])", t) and re.search(
        r"(?:改成|改为|状态|流转)", t, re.I
    ) and re.search(r"处理中|完成|关闭|进行中|待办", t, re.I):
        return "jira_write"
    if re.search(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])", t) and re.search(
        r"(?:r|版本)\s*\d{4,6}", t, re.I
    ) and re.search(r"分析|审查|diff|提交内容", t, re.I):
        return "revision_analysis"
    if re.search(r"技术文档", t, re.I) and re.search(
        r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])", t
    ) and re.search(r"提交|commit|代码", t, re.I):
        return "doc_jira_cross"
    return None


def route_intent(user_text: str, api_key: Optional[str] = None) -> tuple:
    """
    Returns (tool_names, intent_label).
    tool_names=None → 全量工具。
    """
    if not user_text or not user_text.strip():
        return None, "EMPTY"

    cached = _cache_get(user_text)
    if cached is not None:
        return cached

    fp = _fast_path_intent(user_text)
    if fp:
        tools, label = INTENT_REGISTRY[fp]
        _cache_set(user_text, tools, label)
        logger.info(f"[IntentRouter] fast-path '{fp}' → {label}")
        return tools, label

    verdict = classify_intent_llm(user_text, api_key)
    intent_id = verdict.get("intent", "full_set")
    tools, label = INTENT_REGISTRY.get(intent_id, INTENT_REGISTRY["full_set"])
    logger.info(
        f"[IntentRouter] LLM '{intent_id}' conf={verdict.get('confidence')} → {label} tools={tools}"
    )
    _cache_set(user_text, tools, label)
    return tools, label


def get_filtered_tools(active_tools: list, tool_names: list) -> list:
    if tool_names is None:
        return active_tools
    filtered = [
        t
        for t in active_tools
        if t.get("function", {}).get("name") in tool_names or t.get("type") != "function"
    ]
    if not filtered:
        return active_tools
    logger.info(
        f"[IntentRouter] Filtered tools: {len(active_tools)} → {len(filtered)}"
    )
    return filtered
