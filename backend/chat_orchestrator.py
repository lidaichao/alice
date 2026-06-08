"""
ChatOrchestrator — 对话编排入口（E1 绞杀者）。

编排顺序：危险拦截 → 记忆捕获 → 闲聊道 → Plugin-Gateway → VIP 快车道 →（交还 ai_bridge ReAct/Graph）
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, List, Optional, Set

from intent_classifier import classify_intent, should_use_chat_only_lane
from chat_pipeline.vip_fastpath import VipFastpathContext, iter_vip_fastpath
from chat_pipeline.dsml_cleaner import sse_line_has_dsml_leak
import plugin_gateway

logger = logging.getLogger(__name__)

CHAT_ONLY_SYSTEM = """你是 Alice，团队内的 Jira 与知识库 AI 工作助理。

当前为闲聊模式：用户没有提出具体的查任务、搜文档或代码提交类需求。
- 用自然、简短的中文回复（通常 2～4 句），像同事打招呼，不要机械罗列功能清单。
- 禁止调用任何工具，禁止编造 Jira Issue、文档或提交记录。
- 若用户顺便问你能做什么，可轻描淡写提一句可查任务/文档，不要展开成固定模板。"""

SSE_DONE = b"data: [DONE]\n\n"

# ── O2 KB 上下文缓存（v1.0.22）──
# 会话级缓存：上一轮 FAISS 检索结果暂存，下一轮若话题连续则直接复用
# key = conversation_id；value = {"last_doc_id": str, "last_chunk_ids": list, "last_query": str, "cached_at": float}
_kb_context_cache: dict[str, dict] = {}

# ── O2 对比查询信号词（v1.0.22）──
_CONTRAST_SIGNALS = ("对比", "差异", "vs", "不同", "区别", "比较", "VS", "有什么区别", "有什么不同")

def _simple_keywords(text: str) -> set:
    """提取简单关键词：中文用 bigram 滑动窗口，英文用空格拆分，≥2 字，去停用词。"""
    stop = frozenset({"的", "了", "是", "在", "和", "有", "我", "你", "他", "她", "它", "们", "这", "那", "不", "也", "就", "都", "个",
                       "把", "被", "对", "从", "到", "上", "下", "中", "与", "或", "等", "哪些", "怎么", "什么", "哪个", "如何",
                       "为什么", "多少", "吗", "呢", "吧", "啊", "哦", "嗯", "一个", "一种", "一下", "能", "可", "要", "会", "可以",
                       "还", "没", "很", "太", "更", "最", "只", "刚", "才", "已经", "正", "将", "着", "过", "得"})
    text = text.lower()
    # 移除标点
    cleaned = re.sub(r"[，。！？、；：（）【】\"\'\-/\\,\.!\?;:\(\)\[\]]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    tokens: set[str] = set()
    # 中文 bigram
    for i in range(len(cleaned) - 1):
        bigram = cleaned[i:i + 2]
        if re.search(r"[\u4e00-\u9fff]", bigram) and bigram not in stop:
            tokens.add(bigram)
    # 英文单词
    for word in cleaned.split():
        if len(word) >= 2 and word not in stop:
            tokens.add(word)
    return tokens

def set_kb_cache(conversation_id: str, query: str, doc_id: str, chunk_ids: list) -> None:
    """写入 KB 上下文缓存（O2）。"""
    if not conversation_id:
        return
    _kb_context_cache[conversation_id] = {
        "last_doc_id": doc_id,
        "last_chunk_ids": list(chunk_ids or []),
        "last_query": query,
        "cached_at": __import__("time").time(),
    }

def get_kb_cache(conversation_id: str, current_query: str) -> dict | None:
    """读取 KB 上下文缓存；关键词重叠 < 2 则清缓存返回 None（O2）。"""
    entry = _kb_context_cache.get(conversation_id)
    if not entry:
        return None
    last_kw = _simple_keywords(entry["last_query"])
    cur_kw = _simple_keywords(current_query)
    overlap = last_kw & cur_kw
    if len(overlap) < 2:
        del _kb_context_cache[conversation_id]
        return None
    return entry

def detect_contrast_query(user_text: str) -> bool:
    """检测是否为对比类查询（O2）。"""
    return any(sig in user_text for sig in _CONTRAST_SIGNALS)

def format_kb_cache_context(entry: dict) -> str:
    """将缓存条目格式化为注入 Prompt 的上下文（O2）。"""
    doc_id = entry.get("last_doc_id", "")
    query = entry.get("last_query", "")
    chunk_ids = entry.get("last_chunk_ids", [])
    return (
        "【KB 上下文缓存 · O2】\n"
        f"上一轮用户查询了「{query}」，检索到的文档为 {doc_id}（chunk_ids: {', '.join(chunk_ids[:5])}）。\n"
        "当前问题可能与该文档相关，请优先基于上一轮的 KB 检索结果回答。"
    )


@dataclass
class OrchestratorContext:
    """单次 /v1/chat/completions 流式请求的编排上下文。"""

    messages: list
    user_cfg: dict
    frontend_cfg: dict
    headers: dict
    conversation_id: str = ""
    intent_label: str = "FULL_SET"
    active_tools: list = field(default_factory=list)
    cleaned_msgs: list = field(default_factory=list)
    user_text: str = ""
    intent_info: dict = field(default_factory=dict)
    issue_keys_found: Set[str] = field(default_factory=set)
    terminated: bool = False
    # VIP / 结构化读依赖（由 ai_bridge 注入，避免循环 import）
    deepseek_url: str = ""
    http_post: Any = None
    jira_client: Any = None
    exec_search_docs_catalog: Callable = lambda _a: ""
    exec_read_specific_doc: Callable = lambda _a: ""
    build_weekly_jira_snapshot: Callable = lambda *_a: ("", "")
    iter_jira_structured_read_lane: Callable = lambda *_a: iter(())


def clean_chat_messages(messages: list) -> list:
    cleaned = []
    for msg in messages:
        if isinstance(msg.get("content"), str):
            cleaned.append(msg)
        elif isinstance(msg.get("content"), list):
            text = "".join(
                item.get("text", "")
                for item in msg["content"]
                if item.get("type") == "text"
            )
            cleaned.append({"role": msg["role"], "content": text})
    return cleaned


def format_job_channel_context(
    user_text: str,
    issue_keys: Set[str],
    *,
    max_chars: int = 8000,
) -> str:
    """作业通道摘要：保留 Issue Key + 用户诉求（E6.4）。"""
    parts: List[str] = []
    if issue_keys:
        parts.append("【作业上下文 · Issue Keys】 " + ", ".join(sorted(issue_keys)[:30]))
    if user_text:
        parts.append("【用户诉求】\n" + user_text.strip()[:4000])
    block = "\n\n".join(parts)
    return block[:max_chars] if len(block) > max_chars else block


def last_user_message_text(messages: list) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            c = msg.get("content", "")
            return c if isinstance(c, str) else str(c)
    return ""


def build_chat_only_messages(user_text: str) -> list:
    system = CHAT_ONLY_SYSTEM
    try:
        from memory_manager import format_memory_for_prompt

        mem = format_memory_for_prompt(intent_label="CHAT_ONLY")
        if mem:
            system += f"\n\n{mem}"
    except Exception:
        pass
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]


def make_vip_stream_factory(
    *,
    deepseek_url: str,
    headers: dict,
    user_cfg: dict,
    http_post: Callable,
) -> Callable[[str, str], Iterator[bytes]]:
    """VIP 直通车：纯 prompt → LLM stream（无 tools）。"""

    def _vip_stream(prompt: str, fallback_text: str = "") -> Iterator[bytes]:
        _msgs = [{"role": "user", "content": prompt}]
        logger.info("[VIP] Direct stream (%d chars), no tools, no ReAct", len(prompt))
        try:
            vip_resp = http_post(
                deepseek_url,
                headers=headers,
                json={
                    "model": user_cfg["deepseek_model"],
                    "messages": _msgs,
                    "stream": True,
                    "temperature": 0.1,
                },
                stream=True,
                timeout=90,
            )
            _yielded = False
            for raw_line in vip_resp.iter_lines():
                if raw_line:
                    decoded = raw_line.decode("utf-8", errors="replace")
                    if sse_line_has_dsml_leak(decoded):
                        continue
                    _yielded = True
                    yield raw_line + b"\n"
            if not _yielded and fallback_text:
                yield (
                    f"data: {json.dumps({'choices': [{'delta': {'content': fallback_text}}]}, ensure_ascii=False)}\n\n".encode(
                        "utf-8"
                    )
                )
        except Exception as exc:
            logger.error("[VIP] Stream failed: %s", exc)
            err = "⚠️ 系统底层数据服务暂不可用（SVN或知识库异常），请联系管理员或稍后重试。"
            yield (
                f"data: {json.dumps({'choices': [{'delta': {'content': err}}]}, ensure_ascii=False)}\n\n".encode(
                    "utf-8"
                )
            )

    return _vip_stream


def iter_llm_sse_messages(
    messages: list,
    user_cfg: dict,
    headers: dict,
    *,
    deepseek_url: str,
    http_post: Callable,
    temperature: float = 0.65,
) -> Iterator[bytes]:
    """无 tools 的流式 LLM（闲聊道）。"""
    try:
        vip_resp = http_post(
            deepseek_url,
            headers=headers,
            json={
                "model": user_cfg["deepseek_model"],
                "messages": messages,
                "stream": True,
                "temperature": temperature,
            },
            stream=True,
            timeout=90,
        )
        _yielded = False
        for raw_line in vip_resp.iter_lines():
            if raw_line:
                decoded = raw_line.decode("utf-8", errors="replace")
                if sse_line_has_dsml_leak(decoded):
                    continue
                _yielded = True
                yield raw_line + b"\n"
        if not _yielded:
            fallback = "你好，我是 Alice。有需要查任务或文档时，直接告诉我就好。"
            yield (
                f"data: {json.dumps({'choices': [{'delta': {'content': fallback}}]}, ensure_ascii=False)}\n\n".encode(
                    "utf-8"
                )
            )
    except Exception as exc:
        logger.error("[ChatOnly] Stream failed: %s", exc)
        err = "⚠️ 闲聊回复暂时不可用，请稍后重试。"
        yield (
            f"data: {json.dumps({'choices': [{'delta': {'content': err}}]}, ensure_ascii=False)}\n\n".encode(
                "utf-8"
            )
        )


def extract_issue_keys(user_text: str) -> Set[str]:
    if not user_text:
        return set()
    found = re.findall(
        r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])",
        user_text,
    )
    return set(found)


def prepare_orchestrator_context(
    messages: list,
    user_cfg: dict,
    frontend_cfg: dict,
    headers: dict,
    conversation_id: str,
    intent_label: str,
    active_tools: list,
    *,
    deepseek_url: str,
    http_post: Callable,
    jira_client: Any,
    exec_search_docs_catalog: Callable,
    exec_read_specific_doc: Callable,
    build_weekly_jira_snapshot: Callable,
    iter_jira_structured_read_lane: Callable,
) -> OrchestratorContext:
    cleaned = clean_chat_messages(messages)
    user_text = last_user_message_text(cleaned)
    intent_info = (
        classify_intent(user_text)
        if user_text
        else {"route": "ordinary_chat", "reason": "empty_text"}
    )
    return OrchestratorContext(
        messages=messages,
        user_cfg=user_cfg,
        frontend_cfg=frontend_cfg,
        headers=headers,
        conversation_id=conversation_id,
        intent_label=intent_label,
        active_tools=active_tools,
        cleaned_msgs=cleaned,
        user_text=user_text,
        intent_info=intent_info,
        issue_keys_found=extract_issue_keys(user_text),
        deepseek_url=deepseek_url,
        http_post=http_post,
        jira_client=jira_client,
        exec_search_docs_catalog=exec_search_docs_catalog,
        exec_read_specific_doc=exec_read_specific_doc,
        build_weekly_jira_snapshot=build_weekly_jira_snapshot,
        iter_jira_structured_read_lane=iter_jira_structured_read_lane,
    )


def iter_preflight_sse(ctx: OrchestratorContext) -> Iterator[bytes]:
    """
    预检编排：若本请求已由快车道/闲聊等处理完毕，设置 ctx.terminated 并 yield 含 [DONE]。
    """
    user_text = ctx.user_text
    intent_info = ctx.intent_info

    if user_text and intent_info.get("route") == "dangerous":
        block_msg = (
            "【Alice】检测到高风险操作请求，已拦截。"
            f"（{intent_info.get('reason', 'dangerous')}）"
        )
        ctx.terminated = True
        yield f"data: {json.dumps({'choices': [{'delta': {'content': block_msg}}]}, ensure_ascii=False)}\n\n".encode(
            "utf-8"
        )
        yield SSE_DONE
        return

    if user_text:
        try:
            from memory_manager import try_capture_memory_from_message

            mem_entry = try_capture_memory_from_message(user_text)
            if mem_entry:
                mem_ack = (
                    f"【已记住】{mem_entry.get('text', '')}\n"
                    "该规则已写入团队浅层记忆，后续对话将自动注入上下文。"
                )
                ctx.terminated = True
                yield f"data: {json.dumps({'choices': [{'delta': {'content': mem_ack}}]}, ensure_ascii=False)}\n\n".encode(
                    "utf-8"
                )
                yield SSE_DONE
                return
        except Exception as mem_e:
            logger.warning("[Memory] capture failed: %s", mem_e)

    if user_text and should_use_chat_only_lane(user_text, intent_info, ctx.intent_label):
        logger.info("[ChatOnly] ordinary_chat → LLM stream (no tools, single-turn)")
        ctx.terminated = True
        yield from iter_llm_sse_messages(
            build_chat_only_messages(user_text),
            ctx.user_cfg,
            ctx.headers,
            deepseek_url=ctx.deepseek_url,
            http_post=ctx.http_post,
        )
        yield SSE_DONE
        return

    # Plugin-Gateway: 草稿 / Jira 写
    try:
        express = plugin_gateway.try_express_lanes(
            user_text,
            intent_info,
            ctx.user_cfg,
            conversation_id=ctx.conversation_id,
            user_id=(ctx.user_cfg or {}).get("user_id", ""),
        )
        if express:
            ctx.terminated = True
            for chunk in express:
                yield chunk
            logger.info("[Plugin-Gateway] express lane handled, stream terminated")
            yield SSE_DONE
            return
    except Exception as exc:
        logger.warning("[Plugin-Gateway] express lane error: %s", exc)
        if plugin_gateway.is_jira_write_request(
            user_text, intent_info.get("route", "")
        ):
            ctx.terminated = True
            werr = f"【Alice】Jira 写操作处理失败：{str(exc)[:150]}"
            yield f"data: {json.dumps({'choices': [{'delta': {'content': werr}}]}, ensure_ascii=False)}\n\n".encode(
                "utf-8"
            )
            yield SSE_DONE
            return

    # VIP 快车道
    try:
        vip_stream = make_vip_stream_factory(
            deepseek_url=ctx.deepseek_url,
            headers=ctx.headers,
            user_cfg=ctx.user_cfg,
            http_post=ctx.http_post,
        )
        vip_ctx = VipFastpathContext(
            user_text=user_text or "",
            issue_keys_found=ctx.issue_keys_found,
            intent_label=ctx.intent_label,
            intent_route=intent_info.get("route", ""),
            user_cfg=ctx.user_cfg,
            frontend_cfg=ctx.frontend_cfg,
            vip_stream=vip_stream,
            exec_search_docs_catalog=ctx.exec_search_docs_catalog,
            exec_read_specific_doc=ctx.exec_read_specific_doc,
            build_weekly_jira_snapshot=ctx.build_weekly_jira_snapshot,
            iter_jira_structured_read_lane=ctx.iter_jira_structured_read_lane,
            jira_http=ctx.jira_client,
        )
        vip_gen = iter_vip_fastpath(vip_ctx)
        vip_handled = False
        while True:
            try:
                yield next(vip_gen)
            except StopIteration as vip_stop:
                vip_handled = bool(vip_stop.value)
                break
        if vip_handled:
            ctx.terminated = True
            yield SSE_DONE
            return
    except Exception as vip_err:
        logger.warning("[VIP] Fastpath pipeline skipped: %s", vip_err)

    # ═══════════════════════════════════════════════════════
    #  M5.4 — [WORKFLOW:xxx] 工作流模板执行道
    #  匹配格式: [WORKFLOW:version-day-check] 或 [WORKFLOW:design-to-subtasks]
    #  直接调 execute_template，跳过 ReAct 大循环。
    # ═══════════════════════════════════════════════════════
    if user_text:
        wf_match = re.match(r"^\s*\[WORKFLOW:([a-z0-9_-]+)\]\s*", user_text, re.I)
        if wf_match:
            template_id = wf_match.group(1).lower()
            logger.info("[Workflow] trigger detected: %s", template_id)
            try:
                from workflow_engine import execute_template as _exec_wf, list_template_ids as _list_ids
                available = _list_ids()
                stashed = user_text[:120]
                ctx.terminated = True

                if template_id in available:
                    result = _exec_wf(template_id, context={})
                    if result.get("ok"):
                        steps = result.get("execution_log") or []
                        lines = [f"## ⚙️ 工作流执行完成：{result.get('template_name', template_id)}\n"]
                        for s in steps:
                            icon = "✅" if s.get("status") == "done" else "❌"
                            sid = s.get("step_id", "?")
                            tool = s.get("tool", "")
                            lines.append(f"- {icon} **{sid}**（`{tool}`）")
                            out = (s.get("output") or "")[:200]
                            if out:
                                lines.append(f"  {out}")
                        lines.append(f"\n> 共 {len(steps)} 步执行完毕。")
                        final_msg = "\n".join(lines)
                    else:
                        final_msg = f"**工作流 `{template_id}` 执行失败**\n\n步驟 `{result.get('failed_step', '?')}` 出错：{result.get('error', '?')[:300]}"
                else:
                    avail_list = ", ".join(available) if available else "（无可用模板）"
                    final_msg = f"未找到工作流模板 `{template_id}`。\n\n可用模板：{avail_list}"

                payload = json.dumps(
                    {"choices": [{"delta": {"content": final_msg}}]}, ensure_ascii=False
                )
                yield f"data: {payload}\n\n".encode("utf-8")
                yield SSE_DONE
            except Exception as wf_err:
                logger.warning("[Workflow] trigger failed: %s", wf_err)
                ctx.terminated = True
                err_payload = json.dumps(
                    {"choices": [{"delta": {"content": f"工作流执行异常：{str(wf_err)[:200]}"}}]}, ensure_ascii=False
                )
                yield f"data: {err_payload}\n\n".encode("utf-8")
                yield SSE_DONE
            return
