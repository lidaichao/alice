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

CONFIDENCE_TOOL_FILTER_THRESHOLD = 0.8
DISAMBIGUATION_SSE_THRESHOLD = 0.8

INTENT_UI_LABELS: dict[str, str] = {
    "weekly_report": "写周报 / 工作总结",
    "week_deadline_tasks": "本周待完成任务",
    "code_commit_list": "查看 Issue 提交列表",
    "code_diff": "代码 Diff / Code Review",
    "revision_analysis": "分析 SVN revision 提交",
    "doc_search": "查文档 / 策划案",
    "doc_jira_cross": "文档 + Jira 关联",
    "jira_search": "Jira 任务筛选 / 统计",
    "jira_keyword_search": "Jira 关键词搜索",
    "jira_write": "Jira 创建 / 改状态",
    "issue_metadata": "单个 Issue 详情",
    "knowledge_query": "知识库泛查",
    "full_set": "通用助手（不收窄工具）",
}

_route_cache: dict[str, tuple[float, Optional[list[str]], str, dict]] = {}


def _cache_key(text: str) -> str:
    norm = re.sub(r"\s+", " ", (text or "").strip().lower())[:500]
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _cache_get(text: str) -> Optional[tuple[Optional[list[str]], str, dict]]:
    ck = _cache_key(text)
    hit = _route_cache.get(ck)
    if not hit:
        return None
    exp, tools, label, meta = hit
    if time.time() > exp:
        _route_cache.pop(ck, None)
        return None
    logger.info(f"[IntentRouter] cache hit → {label}")
    return tools, label, meta


def _cache_set(
    text: str,
    tools: Optional[list[str]],
    label: str,
    meta: Optional[dict] = None,
) -> None:
    _route_cache[_cache_key(text)] = (
        time.time() + CACHE_TTL_SEC,
        tools,
        label,
        meta or {},
    )


def _suggest_alternate_intents(user_text: str, primary: str) -> list[str]:
    t = user_text or ""
    alts: list[str] = []
    if re.search(r"周报|日报|月报", t):
        alts.append("weekly_report")
    if re.search(r"本周|这周|待办|交付", t):
        alts.append("week_deadline_tasks")
    if re.search(r"文档|策划|KB-|wiki", t, re.I):
        alts.append("doc_search")
    if re.search(r"[A-Z][A-Z0-9]*-\d+", t) and re.search(r"状态|流转|处理中", t):
        alts.append("jira_write")
    if re.search(r"Jira|任务|bug|缺陷", t, re.I):
        alts.append("jira_search")
    if re.search(r"r\d{4,6}|revision|提交内容|diff", t, re.I):
        alts.append("revision_analysis")
    out = []
    for a in alts:
        if a != primary and a not in out and a in INTENT_REGISTRY:
            out.append(a)
    if "full_set" not in out and primary != "full_set":
        out.append("full_set")
    return out[:3]


def build_disambiguation_payload(verdict: dict, user_text: str) -> Optional[dict]:
    """confidence < 0.8 时生成 intent_disambiguation SSE 载荷（E5.2）。"""
    conf = float(verdict.get("confidence", 1.0))
    if conf >= DISAMBIGUATION_SSE_THRESHOLD:
        return None
    intent_id = verdict.get("intent", "full_set")
    choices = [{"value": intent_id, "label": INTENT_UI_LABELS.get(intent_id, intent_id)}]
    for alt in _suggest_alternate_intents(user_text, intent_id):
        choices.append({"value": alt, "label": INTENT_UI_LABELS.get(alt, alt)})
    if len(choices) < 2:
        return None
    return {
        "prompt": "我不太确定您想用哪种方式处理，请选一个（可跳过，将按全功能助手继续）：",
        "confidence": conf,
        "suggested_intent": intent_id,
        "choices": choices[:4],
    }


def apply_route_meta_to_tools(
    tools: Optional[list[str]],
    verdict: dict,
) -> tuple[Optional[list[str]], dict]:
    """E5.1：<0.8 不静默收窄工具集。"""
    conf = float(verdict.get("confidence", 1.0))
    meta = {
        "confidence": conf,
        "intent_id": verdict.get("intent", "full_set"),
        "disambiguation": None,
    }
    if conf < CONFIDENCE_TOOL_FILTER_THRESHOLD:
        meta["tools_narrowed"] = False
        return None, meta
    meta["tools_narrowed"] = tools is not None
    return tools, meta


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
    try:
        from intent_classifier import is_smalltalk_greeting

        if is_smalltalk_greeting(t):
            return "full_set"
    except ImportError:
        pass
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
    Returns (tool_names, intent_label, route_meta).
    tool_names=None → 全量工具。
    route_meta 含 confidence、disambiguation（可选）。
    """
    if not user_text or not user_text.strip():
        return None, "EMPTY", {"confidence": 1.0}

    intent_override = re.match(r"^\[INTENT:([a-z_]+)\]\s*", user_text.strip(), re.I)
    if intent_override:
        intent_id = intent_override.group(1).lower()
        if intent_id in INTENT_REGISTRY:
            tools, label = INTENT_REGISTRY[intent_id]
            meta = {
                "confidence": 1.0,
                "intent_id": intent_id,
                "disambiguation": None,
                "tools_narrowed": tools is not None,
                "user_override": True,
            }
            logger.info(f"[IntentRouter] user override → {label}")
            return tools, label, meta

    cached = _cache_get(user_text)
    if cached is not None:
        return cached

    fp = _fast_path_intent(user_text)
    if fp:
        tools, label = INTENT_REGISTRY[fp]
        meta = {"confidence": 1.0, "intent_id": fp, "disambiguation": None, "tools_narrowed": True}
        _cache_set(user_text, tools, label, meta)
        logger.info(f"[IntentRouter] fast-path '{fp}' → {label}")
        return tools, label, meta

    verdict = classify_intent_llm(user_text, api_key)
    intent_id = verdict.get("intent", "full_set")
    tools, label = INTENT_REGISTRY.get(intent_id, INTENT_REGISTRY["full_set"])
    tools, meta = apply_route_meta_to_tools(tools, verdict)
    meta["disambiguation"] = build_disambiguation_payload(verdict, user_text)
    logger.info(
        f"[IntentRouter] LLM '{intent_id}' conf={verdict.get('confidence')} "
        f"narrowed={meta.get('tools_narrowed')} → {label} tools={tools}"
    )
    _cache_set(user_text, tools, label, meta)
    return tools, label, meta


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
