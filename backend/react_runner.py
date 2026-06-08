"""
ReAct runner — LangGraph fallback + ReAct loop + final stream (E1.3).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Set

from chat_pipeline.dsml_cleaner import clean_dsml_leak

logger = logging.getLogger(__name__)
SSE_DONE = b"data: [DONE]\n\n"


class ReactFallback(Exception):
    pass


@dataclass
class ReactRunContext:
    cleaned_msgs: list
    user_text: str
    issue_keys_found: set
    intent_info: dict
    user_cfg: dict
    frontend_cfg: dict
    headers: dict
    active_tools: list
    tool_names: list = field(default_factory=list)
    jira_client: Any = None
    deepseek_url: str = ""
    http_post: Callable = None
    execute_tool_call: Callable = None
    core_system_prompt: str = ""
    resolve_jira_username: Callable = None
    tool_executors: dict = field(default_factory=dict)

    @property
    def max_steps(self) -> int:
        return int(self.frontend_cfg.get("max_steps", 5) or 5)


def iter_v2_graph_stream(ctx: ReactRunContext) -> Iterator[bytes]:
    if ctx.user_cfg.get("engine") != "v2-graph" and os.environ.get("ALICE_ENGINE") != "v2":
        raise ReactFallback()
    logger.info("[V2 Graph] Invoking LangGraph Plan-and-Execute agent")
    _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from backend.agent.graph import graph as _v2_graph
    from backend.agent.nodes import init_agent as _v2_init
    import requests as _http
    _v2_init(
        deepseek_key=ctx.user_cfg["deepseek_key"],
        model=ctx.user_cfg["deepseek_model"],
        tools=ctx.active_tools[:5],
        executors=ctx.tool_executors,
        http_module=_http,
    )
    _v2_msgs = [m for m in ctx.cleaned_msgs if m.get("role") != "system"]
    if ctx.user_text:
        _v2_msgs.append({"role": "user", "content": ctx.user_text})
    final_state = _v2_graph.invoke({
        "messages": _v2_msgs,
        "plan": [],
        "plan_mode": "cross_domain",
        "past_steps": [],
        "final_answer": "",
    })
    answer = final_state.get("final_answer", "")
    if answer:
        payload = json.dumps({"choices": [{"delta": {"content": answer}}]}, ensure_ascii=False)
        yield f"data: {payload}\n\n".encode("utf-8")
    else:
        payload = json.dumps(
            {"choices": [{"delta": {"content": "[V2 Agent] 分析完成，但未生成回答。"}}]},
            ensure_ascii=False,
        )
        yield f"data: {payload}\n\n".encode("utf-8")
    yield SSE_DONE


def iter_react_pipeline(ctx: ReactRunContext) -> Iterator[bytes]:
    step = 0
    max_steps = ctx.max_steps
    user_text = ctx.user_text
    issue_keys_found = ctx.issue_keys_found
    user_cfg = ctx.user_cfg
    frontend_cfg = ctx.frontend_cfg
    headers = ctx.headers
    active_tools = ctx.active_tools
    tool_names = ctx.tool_names
    # ── 构建初始消息列表 (旧 ReAct)
    system_context = ctx.core_system_prompt
    try:
        from memory_manager import format_memory_for_prompt
        _intent_lbl = (
            str(ctx.intent_info.get("intent_label") or "")
            if isinstance(ctx.intent_info, dict)
            else ""
        )
        _mem_block = format_memory_for_prompt(intent_label=_intent_lbl)
        try:
            from chat_orchestrator import format_job_channel_context

            _job_ctx = format_job_channel_context(ctx.user_text, ctx.issue_keys_found)
            if _job_ctx:
                _mem_block = (_mem_block + "\n\n" + _job_ctx) if _mem_block else _job_ctx
        except Exception:
            pass
        if _mem_block:
            system_context += f"\n\n{_mem_block}"
    except Exception as _mem_inj:
        logger.warning(f"[Memory] prompt inject failed: {_mem_inj}")

    # 预注入 Issue Key 基本信息
    if issue_keys_found:
        pre_context = ""
        for ik in sorted(issue_keys_found, key=len, reverse=True)[:3]:
            try:
                resp = ctx.jira_client.jira_get(
                    f"{ctx.jira_client.api_url}/issue/{ik}?fields=summary,status,assignee")
                if resp.status_code == 200:
                    issue = resp.json()
                    f = issue.get("fields", {})
                    pre_context += (
                        f"\n[已检测到 Issue] {ik}: {f.get('summary','')} "
                        f"[{f.get('status',{}).get('name','')}] "
                        f"经办人: {f.get('assignee',{}).get('displayName','未分配')}"
                    )
            except Exception:
                pass
        if pre_context:
            system_context += f"\n\n## 当前会话上下文{pre_context}"

    # ── O2 KB 上下文缓存注入（v1.0.22）──
    try:
        from chat_orchestrator import get_kb_cache, detect_contrast_query, format_kb_cache_context
        _conv_id = ctx.conversation_id or ""
        _user_t = ctx.user_text or ""
        # 对比查询检测
        if detect_contrast_query(_user_t):
            system_context += (
                "\n\n【O2 对比查询模式】\n"
                "用户正在进行对比查询。请尽可能从知识库中检索多个相关文档片段，"
                "以结构化格式（表格或分点）对比两者的差异。若仅找到一侧的信息，"
                "请明确指出并给出已有的完整内容，同时说明另一侧缺失。top-k 已扩大到 5。"
            )
        # KB 上下文缓存
        _cached = get_kb_cache(_conv_id, _user_t)
        if _cached:
            system_context += f"\n\n{format_kb_cache_context(_cached)}"
            logger.info("[O2] KB cache hit for conv %s", _conv_id)
    except Exception as _o2e:
        pass

    # 人名解析 (Jira username 查询)
    name_match = re.search(
        r'[\u4e00-\u9fff]{2,4}(?=负责|的|做|提交|处理|开发|最近)', user_text or "")
    if name_match:
        cn_name = name_match.group()
        try:
            username = ctx.resolve_jira_username(ctx.jira_client, cn_name)
            if username:
                system_context += (
                    f"\n\n[用户解析] {cn_name} 的 Jira 账号为 {username}。"
                    f"查询时请使用 assignee = {username}。"
                )
        except Exception:
            pass

    # ── 构建 messages ────────────────────────────
    tool_messages = [{"role": "system", "content": system_context}]
    # 保留历史消息（跳过已有的 system prompt）
    for msg in ctx.cleaned_msgs:
        if msg.get("role") != "system":
            tool_messages.append(msg)

    # ══════════════════════════════════════════════
    #  ReAct 主循环
    # ══════════════════════════════════════════════
    while step < max_steps:
        step += 1
        yield f"data: {json.dumps({'custom_type': 'agent_step', 'step': step, 'max_steps': max_steps})}\n\n".encode('utf-8')

        # Phase 1: LLM 决策 (非流式, 带 tools)
        logger.info(f"[ReAct] Step {step}/{max_steps} — asking LLM with {len(active_tools)} tools")
        try:
            probe_resp = ctx.http_post(ctx.deepseek_url, headers=headers, json={
                "model": user_cfg["deepseek_model"],
                "messages": tool_messages,
                "tools": active_tools,
                "tool_choice": "required" if tool_names else "auto",
                "stream": False
            }, timeout=30)
            probe_data = probe_resp.json()
            choice = probe_data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")
            logger.error(f"[ReAct-TRACE] Step {step}: finish_reason={finish_reason} | has_tool_calls={bool(msg.get('tool_calls'))} | content_first_100={str(msg.get('content',''))[:100]}")
            
            # ▸ 检测 tool_calls / DSML 文本泄漏: 如果 finish=stop 但 content 是 tool_calls 文本
            # 兼容 deepseek-v4-flash 的 <|DSML|>tool_calls> 变体
            # 注入禁止指令后不加 tools 重试一次
            _content_str = str(msg.get("content", ""))
            _has_leak = ("<|tool_calls|>" in _content_str or 
                        "<|DSML|>" in _content_str or
                        "<|invoke|>" in _content_str)
            if finish_reason == "stop" and _has_leak:
                logger.warning(f"[ReAct] Tool_calls text leak detected in probe, retrying without tools")
                
                # 清理 tool_calls 历史 + 发起纯文本 retry
                for _m in tool_messages:
                    if _m.get("role") == "assistant" and "tool_calls" in _m:
                        del _m["tool_calls"]
                
                tool_messages.append({
                    "role": "system",
                    "content": "你现在是纯文本回答模式。禁止输出任何 XML/DSML/tool_calls 标记。直接基于上文数据回答。"
                })
                probe_resp2 = ctx.http_post(ctx.deepseek_url, headers=headers, json={
                    "model": user_cfg["deepseek_model"],
                    "messages": tool_messages,
                    "stream": False
                }, timeout=30)
                probe_data2 = probe_resp2.json()
                choice2 = probe_data2.get("choices", [{}])[0]
                msg = choice2.get("message", {})
                finish_reason = choice2.get("finish_reason", "")
                
                # 清洗 retry 响应中的 DSML 标签
                _retry_content = str(msg.get("content", "")).strip()
                if finish_reason == "stop" and _retry_content:
                    _retry_content = clean_dsml_leak(_retry_content)
                    if _retry_content:
                        logger.info(f"[ReAct] DSML retry success, direct-output {len(_retry_content)} chars")
                        yield f"data: {json.dumps({'choices':[{'delta':{'content':_retry_content}}]})}\n\n".encode('utf-8')
                        yield b"data: [DONE]\n\n"
                        return
                
                logger.error(f"[ReAct] DSML retry still has tool_calls after cleaning")
        except Exception as e:
            logger.error(f"[ReAct] LLM probe failed at step {step}: {e}")
            break

        # ── 分支 A: LLM 决定调用工具 ──
        if finish_reason == "tool_calls" and msg.get("tool_calls"):
            tcs = msg["tool_calls"]
            logger.info(f"[ReAct] Step {step}: {len(tcs)} tool call(s) — {[tc['function']['name'] for tc in tcs]}")

            # 追加 assistant message (含 tool_calls)
            tool_messages.append(msg)

            # ── 并发执行所有工具 (asyncio.gather) ──
            def _run_one_tool(tc):
                """同步执行单个工具，返回 (tool_call_id, name, result, error)"""
                t_name = tc.get("function", {}).get("name", "unknown")
                t_args = tc.get("function", {}).get("arguments", "{}")
                tc_id = tc.get("id", "")

                # 发送 SSE: plugin_state running
                return {
                    "tc_id": tc_id,
                    "name": t_name,
                    "sse_running": json.dumps({
                        "custom_type": "plugin_state",
                        "plugin": {"name": t_name, "status": "running"}
                    }, ensure_ascii=False),
                    "result": ctx.execute_tool_call(
                        t_name,
                        t_args,
                        user_cfg,
                        frontend_cfg,
                        ctx.user_text or "",
                        request_user_id=(user_cfg or {}).get("user_id", ""),
                    ),
                    "sse_done": json.dumps({
                        "custom_type": "plugin_state",
                        "plugin": {"name": t_name, "status": "done"}
                    }, ensure_ascii=False)
                }

            # Alice V2.0 P0 Fix: 统一 ThreadPool 并发执行工具
            # 避免 asyncio.run() 在 Waitress 线程内嵌套事件循环
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=len(tcs)) as pool:
                futures = {pool.submit(_run_one_tool, tc): tc for tc in tcs}
                results = []
                for f in as_completed(futures, timeout=30):
                    try:
                        results.append(f.result())
                    except Exception as e:
                        logger.error(f"[ReAct] Tool thread failed: {e}")

            # 按顺序发送 SSE 事件 + 追加 tool messages（写操作确认卡 → 网关终止）
            _plugin_gateway_terminal = False
            _confirm_preview = ""
            _draft_gateway_terminal = False
            for r in results:
                yield f"data: {r['sse_running']}\n\n".encode('utf-8')
                yield f"data: {r['sse_done']}\n\n".encode('utf-8')

                # 检查确认卡（统一 confirm_card 事件，兼容旧 custom_type）
                try:
                    obj = json.loads(r['result'])
                    if obj.get("status") == "confirm_required":
                        _plugin_gateway_terminal = True
                        op_id = obj.get("operation_id", "")
                        ui_op = obj.get("operation") or {}
                        _confirm_preview = str(obj.get("result") or _confirm_preview)
                        card_evt = {
                            "_event": "confirm_card",
                            "op_id": op_id,
                            "operation": ui_op,
                            "message": _confirm_preview,
                            "preview": _confirm_preview,
                        }
                        yield f"data: {json.dumps(card_evt, ensure_ascii=False)}\n\n".encode('utf-8')
                        yield f"data: {json.dumps({'custom_type': 'confirm_required', 'operation': ui_op, 'operation_id': op_id, 'message': _confirm_preview}, ensure_ascii=False)}\n\n".encode('utf-8')
                        if _confirm_preview:
                            yield f"data: {json.dumps({'choices': [{'delta': {'content': _confirm_preview}}]}, ensure_ascii=False)}\n\n".encode('utf-8')
                    if obj.get("status") == "draft_required":
                        _draft_gateway_terminal = True
                        _plugin_gateway_terminal = True
                        draft_id = obj.get("draft_id", "")
                        items_ui = obj.get("items") or []
                        preview_d = str(obj.get("result") or "")
                        draft_evt = {
                            "_event": "draft_card",
                            "draft_id": draft_id,
                            "items": items_ui,
                            "warnings": obj.get("warnings") or [],
                            "preview": preview_d,
                        }
                        yield f"data: {json.dumps(draft_evt, ensure_ascii=False)}\n\n".encode('utf-8')
                        if preview_d:
                            yield f"data: {json.dumps({'choices': [{'delta': {'content': preview_d}}]}, ensure_ascii=False)}\n\n".encode('utf-8')
                        logger.info(
                            f"[Plugin-Gateway] draft_card emitted — draft_id={draft_id} items={len(items_ui)}"
                        )
                except Exception:
                    pass

                # ── O2 KB 上下文缓存写入（v1.0.22）──
                if r.get("name") == "search_doc_chunks":
                    try:
                        _result_text = str(r.get("result", ""))
                        # 从结果文本提取匹配文档 ID
                        _doc_match = re.search(r"【匹配文档:\s*([^】]+)】", _result_text)
                        _doc_id = _doc_match.group(1).strip() if _doc_match else ""
                        _query = ctx.user_text or ""
                        if _doc_id and _query:
                            from chat_orchestrator import set_kb_cache
                            _conv_id = ctx.conversation_id or ""
                            set_kb_cache(_conv_id, _query, _doc_id, [])
                            logger.info("[O2] KB cache written for conv %s doc=%s", _conv_id, _doc_id)
                    except Exception as _o2w:
                        logger.debug("[O2] KB cache write skipped: %s", _o2w)

                if _plugin_gateway_terminal:
                    continue

                # Alice V2.0 fix: 剥离 JSON 外壳，LLM 只看到纯文本
                tool_content = r["result"]
                try:
                    obj = json.loads(tool_content)
                    if isinstance(obj, dict):
                        tool_content = obj.get("llm_text") or obj.get("result") or tool_content
                except (json.JSONDecodeError, TypeError):
                    pass

                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": r["tc_id"],
                    "name": r["name"],
                    "content": str(tool_content)
                })

            if _plugin_gateway_terminal:
                if _draft_gateway_terminal:
                    logger.info("[Plugin-Gateway] draft_card — breaking ReAct loop, stream [DONE]")
                else:
                    logger.info("[Plugin-Gateway] confirm_card emitted — breaking ReAct loop, stream [DONE]")
                yield b"data: [DONE]\n\n"
                return

            # ══ Rabbit 核选项: 工具执行后直接输出数据，跳过后续 ReAct 步骤 ══
            # deepseek-v4-flash 在后续轮次中持续输出 tool_calls 文本而非事实回答
            # ⚠️ 如果调用了 get_single_commit_diff 或处于 Inception 模式 → 不拦截！
            _has_diff_in_step = any(
                r.get("name") == "get_single_commit_diff"
                for r in results
            )
            if not _has_diff_in_step:
                _nuke_results = []
                for _nm in reversed(tool_messages):
                    if _nm.get("role") == "tool":
                        _nuke_results.insert(0, str(_nm.get("content", "")))
                    elif _nm.get("role") == "assistant":
                        break
                if _nuke_results:
                    _nuke_text = "\n\n---\n\n".join(_nuke_results)[:6000]
                    # 数据已收集在 tool_messages 中, 交由 Final Stream LLM 合成
                    logger.info(f"[ReAct] Collected {len(_nuke_text)} chars from tool data — passing to Final Stream (nuclear yield removed)")
            else:
                logger.info(f"[ReAct] [NUCLEAR-SKIP] get_single_commit_diff detected, bypassing nuclear — let LLM analyze diff")

            continue  # 继续循环让 LLM 处理工具结果
        # ── 分支 B: LLM 决定输出最终回答 ──
        elif finish_reason == "stop":
            # ══ Stop Interceptor: 第一轮话痨拦截 ══
            # LLM 说"好的我来查"但不调工具 → 踹回循环
            _weekly_in_query = bool(re.search(
                r'周报|日报|月报|本周.{0,10}(?:总结|汇总|进度|情况|报告)',
                user_text or ""))
            _has_jira_search = any(
                m.get("role") == "tool" and m.get("name") == "search_jira_issues"
                for m in tool_messages
            )
            if step == 1 and _weekly_in_query and not _has_jira_search:
                _chatter = str(msg.get("content", ""))[:100]
                logger.warning(f"[ReAct] Stop Interceptor (weekly): no search_jira_issues, content='{_chatter}'")
                tool_messages.append(msg)
                tool_messages.append({
                    "role": "user",
                    "content": (
                        "【系统强制指令】用户要的是项目周报/汇总，禁止只回复「我来读取文档」！"
                        "必须立刻调用 search_jira_issues（keyword 可用「本周」或项目名 CT），"
                        "拿到任务列表后再写周报。禁止编造 CT-xxxx Issue Key。"
                    )
                })
                continue

            if step == 1 and issue_keys_found and not any(
                "tool_calls" in m for m in tool_messages if m.get("role") == "assistant"
            ):
                _chatter = str(msg.get("content", ""))[:100]
                logger.warning(f"[ReAct] Stop Interceptor: step={step} with {issue_keys_found} but no tool_calls! Content='{_chatter}'")
                tool_messages.append(msg)
                tool_messages.append({
                    "role": "user",
                    "content": f"【系统强制指令】请勿只回复文本！用户提到了 Jira 任务 {list(issue_keys_found)[:3]}，你必须立刻调用工具查询这些任务的具体数据（如状态、负责人、提交记录），然后再总结回答！"
                })
                continue  # 不 break，强制进入下一轮

            # 过滤 msg 中的 tool_calls / DSML 文本泄漏
            if msg.get("content"):
                import re as _re
                cleaned = str(msg["content"])
                # ── 行级过滤: 仅删除含 DSML/tool_calls 的行, 不跨行吞噬 ──
                lines = cleaned.split('\n')
                keep_lines = []
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        keep_lines.append(line)
                        continue
                    if _re.match(r'\s*<\s*\|?\s*(?:tool_calls|DSML|invoke|parameter)\s*\|?\s*>', stripped, _re.I):
                        continue
                    if _re.match(r'\s*<\s*\|?\s*/\s*(?:tool_calls|DSML)\s*\|?\s*>', stripped, _re.I):
                        continue
                    keep_lines.append(line)
                cleaned = '\n'.join(keep_lines)
                if cleaned.strip():
                    msg["content"] = cleaned.strip()
                else:
                    msg.pop("content", None)  # 全是 tool_calls 文本 → 去掉
            tool_messages.append(msg)
            logger.info(f"[ReAct] LLM finished after {step} step(s), streaming final answer")
            break

        # ── 分支 C: 其他情况 (length/content_filter) ──
        else:
            if msg.get("content"):
                # 同样清理可能的 tool_calls 文本 (含 DSML 变体)
                c2 = clean_dsml_leak(str(msg["content"]))
                if c2.strip():
                    msg["content"] = c2.strip()
            tool_messages.append(msg)
            logger.warning(f"[ReAct] unexpected finish_reason: {finish_reason}")
            break

    # ── 达到最大步数: 强制收尾 ──
    if step >= max_steps:
        yield f"data: {json.dumps({'custom_type': 'agent_step', 'step': step, 'state': 'force_finish'})}\n\n".encode('utf-8')
        if tool_messages and tool_messages[-1].get("role") != "user":
            tool_messages.append({
                "role": "user",
                "content": "[系统提示: 已超最大工具调用步数，请基于已获取的信息直接回答用户问题]"
            })

    # ══════════════════════════════════════════════
    #  Alice V2.0: 空值熔断检查 (仿白泽占位符模式)
    #  扫描本轮 tool messages，若有关键工具返回空结果→注入强制提醒
    # ══════════════════════════════════════════════
    empty_tools = set()
    empty_signals = [
        "搜索无结果", "0 条结果", "未找到匹配", "暂无关联",
        "没有找到", "暂无", "not found", "返回 0 条",
        "共 0 条", "total\": 0", "\"total\":0",
    ]
    for msg in tool_messages:
        if msg.get("role") == "tool":
            content = str(msg.get("content", ""))
            if any(sig in content for sig in empty_signals):
                name = msg.get("name", "unknown")
                empty_tools.add(name)
    if empty_tools:
        tool_messages.append({
            "role": "system",
            "content": (
                f"【数据熔断警告 — 最高优先级，必须遵守】\n"
                f"以下工具返回了空结果: {', '.join(sorted(empty_tools))}。\n"
                f"用户的原始问题是: {user_text[:100]}\n"
                f"你必须明确告诉用户: 这些数据源当前未返回匹配数据。\n"
                f"绝对禁止虚构任何 Issue Key（如 GAME-1234、CT-99999 等格式）！\n"
                f"绝对禁止虚构文档标题或业务数据！\n"
                f"如果没有足够的事实数据，直接回答'当前未查到相关数据，建议尝试其他关键词'。"
            )
        })
        logger.info(f"[ReAct] Empty-check injected for: {empty_tools}")

    # ══════════════════════════════════════════════
    #  Rabbit Nuclear Intercept V2: 最终防线
    #  不管 ReAct 如何退出（tool_calls/stop/DSML/预注入元数据）,
    #  只要用户问了提交相关的问题且有 Issue Key，强制调工具输出
    # ══════════════════════════════════════════════
    _has_diff_tool = any(
        m.get("role") == "tool" and m.get("name") == "get_single_commit_diff"
        for m in tool_messages
    )
    
    # ▸ Prompt Inception 检测: 如果用户消息中包含预置 diff 数据 → 全放行
    import sys as _sys4
    _sys4.stderr.write(f"[NUCLEAR-DEBUG] has_diff_tool={_has_diff_tool} tool_count={sum(1 for m in tool_messages if m.get('role')=='tool')}\n")
    _sys4.stderr.flush()
    
    if _has_diff_tool:
        logger.info(f"[NUCLEAR-V2] get_single_commit_diff detected, bypassing nuclear — let LLM analyze diff")
    else:
        _has_commit_tool = any(
            m.get("role") == "tool" and m.get("name") == "get_issue_commits"
            for m in tool_messages
        )
        _user_asks_commit = bool(re.search(
            r'提交|commit|改了什么代码|代码变更|diff|变更了哪些|改了哪些文件|提交记录|提交内容|改了.*什么',
            user_text or ""
        ))
        _has_issue_key = bool(issue_keys_found)
        
        if _user_asks_commit and _has_issue_key and not _has_commit_tool:
            logger.error(f"[NUCLEAR-V2] Commit query detected — force-executing get_issue_commits for {issue_keys_found}")
            try:
                from knowledge_retriever import fetch_precise_commits_via_fisheye
                for ik in sorted(issue_keys_found, key=len, reverse=True)[:1]:
                    commit_data = fetch_precise_commits_via_fisheye(ik)
                    if commit_data and len(str(commit_data)) > 20:
                        # 将工具结果注入 tool_messages, 交由 Final Stream LLM 合成
                        tool_messages.append({"role": "tool", "content": str(commit_data)[:6000]})
                        logger.info(f"[NUCLEAR-V2] Force-fetched commit data — passing to Final Stream")
            except Exception as _nuke_err:
                logger.error(f"[NUCLEAR-V2] Force-execute failed: {_nuke_err}")

    # 如果已有 tool 结果，确保数据在 tool_messages 中供 Final Stream 使用
    _all_tool_results = []
    for _tm in tool_messages:
        if _tm.get("role") == "tool":
            _all_tool_results.append(str(_tm.get("content", "")))
    if _all_tool_results and not _has_diff_tool:
        logger.info(f"[NUCLEAR-V2] Collected {sum(len(r) for r in _all_tool_results)} total chars from tool data — passing to Final Stream")

    # ══════════════════════════════════════════════
    #  最终回答: 流式 SSE 输出 (只有核拦截未触发时才到达这里)
    # ══════════════════════════════════════════════
    logger.info(f"[ReAct] Streaming final answer with {len(tool_messages)} messages")

    # ▸ Debug: 打印最后一条 tool message 的原始内容
    last_tool_msg = None
    for msg in reversed(tool_messages):
        if msg.get("role") == "tool":
            last_tool_msg = msg
            break
    if last_tool_msg:
        content = str(last_tool_msg.get("content", ""))
        # 检查是否有 Unicode 转义
        has_unicode_escape = "\\u" in content
        logger.error(f"[DEBUG-FINAL] Last tool msg: {len(content)} chars | "
                     f"Unicode escape: {has_unicode_escape} | "
                     f"Starts with: {repr(content[:120])}")
    else:
        logger.error(f"[DEBUG-FINAL] NO tool message in {len(tool_messages)} messages!")
        
    # 追加 system message — 软化容错版

    # 追加 system message 告诉模型现在是纯文本回答模式
    # 软化版：允许模型诚实地回复"未查到"而非恐慌性编造
    tool_messages.append({
        "role": "system",
        "content": (
            "【数据提取指令】请严格且仅从上方 tool 角色的返回结果中提取并作答。"
            "当 tool 返回了名单、表格行或明确条目（人名、角色名、配置项、SVN 版本号等）时，"
            "必须逐项完整列出具体名称与数值，绝对禁止用「等」「若干」「部分」概括或省略任何一条。"
            "如果 tool 返回内容为空或无法解析，请明确回复未查询到相关记录。"
            "绝不允许基于自身知识库或先验概率编造、拼凑任何数据！"
            "直接输出纯文本，禁止输出 <|tool_calls|> / <|DSML|> 标记。"
        )
    })
    # ══════════════════════════════════════════════
    #  Rabbit Debug Interceptor: 检查最终消息完整性
    # ══════════════════════════════════════════════
    import json as _json_dbg, sys as _sys
    _dbg_lines = [
        "=================== RABBIT DEBUG INTERCEPTOR ===================",
        f"Total messages count: {len(tool_messages)}",
    ]
    for idx, msg in enumerate(tool_messages[-3:]):
        content_raw = str(msg.get('content', ''))
        _dbg_lines.append(f"MSG [-{3-idx}]: Role: {msg.get('role')} | Content: {_json_dbg.dumps(content_raw, ensure_ascii=False)[:300]}...")
    _dbg_lines.append("================================================================")
    _dbg_text = "\n".join(_dbg_lines)
    _sys.stderr.write(_dbg_text + "\n")
    _sys.stderr.flush()
    logger.error(f"[RABBIT] Interceptor fired: {len(tool_messages)} msgs, last role={tool_messages[-1].get('role') if tool_messages else 'NONE'}")

    # ▸ 清理 tool_messages: 移除 assistant 消息中的 tool_calls 字段
    # 防止 LLM 被历史中的 function calling 格式诱导继续输出 tool_calls 文本
    for _msg in tool_messages:
        if _msg.get("role") == "assistant" and "tool_calls" in _msg:
            del _msg["tool_calls"]

    # ▸ 转换 tool 消息为 user 消息 (DeepSeek API 要求 tool 必须关联 tool_calls)
    _converted_messages = []
    for _msg in tool_messages:
        if _msg.get("role") == "tool":
            _converted_messages.append({
                "role": "user",
                "content": f"[工具返回数据 — 请基于此回答]\n{_msg.get('content', '')}"
            })
        else:
            _converted_messages.append(_msg)
    tool_messages = _converted_messages
    logger.info(f"[ReAct] Cleaned tool_calls from assistant msgs, converted tool→user, {len(tool_messages)} msgs for Final Stream")

    try:
        _final_content_yielded = False
        final_resp = ctx.http_post(ctx.deepseek_url, headers=headers, json={
            "model": user_cfg["deepseek_model"],
            "messages": tool_messages,
            "stream": True,
            "temperature": 0.1
        }, stream=True, timeout=60)

        consecutive_filtered = 0
        for raw_line in final_resp.iter_lines():
            if raw_line:
                decoded = raw_line.decode('utf-8', errors='replace')
                # ── 过滤 DSML/tool_calls 文本, 保留自然语言 ──
                cleaned = clean_dsml_leak(decoded)
                # 只有当整行都被清空时才跳过
                if not cleaned.strip():
                    consecutive_filtered += 1
                    if consecutive_filtered > 20:
                        logger.error("[ReAct] Too many filtered lines, LLM stuck in tool_calls mode")
                        yield f"data: {json.dumps({'choices':[{'delta':{'content':'[系统提示] AI 模型输出异常，请刷新页面重试。'}}]})}\n\n".encode('utf-8')
                        break
                    continue
                consecutive_filtered = 0
                _final_content_yielded = True
                # 直接输出清洗后的 SSE 行 (已含 data: 前缀)
                yield cleaned.encode('utf-8') + b"\n"
    except Exception as e:
        yield f"data: {json.dumps({'choices':[{'delta':{'content':f'[Error: {e}]'}}]})}\n\n".encode('utf-8')

    # ══ Final Stream 安全网: LLM 无有效输出 → 回退已检索的工具数据 ══
    if not _final_content_yielded:
        if _has_diff_tool:
            logger.error("[FINAL-SAFETY] LLM output filtered — fallback to raw diff")
            _raw_diff = []
            for _tm in tool_messages:
                if _tm.get("role") == "tool" and _tm.get("name") == "get_single_commit_diff":
                    _raw_diff.append(str(_tm.get("content", ""))[:4000])
            if _raw_diff:
                _safe_text = "【Alice】LLM 分析未成功生成，以下是原始代码 Diff 数据：\n\n" + "\n\n---\n\n".join(_raw_diff)
                yield f"data: {json.dumps({'choices':[{'delta':{'content':_safe_text}}]}, ensure_ascii=False)}\n\n".encode('utf-8')
        elif _all_tool_results:
            logger.error("[FINAL-SAFETY] LLM output empty — fallback to tool results (%d chunks)", len(_all_tool_results))
            _safe_text = (
                "【Alice】模型未生成完整回答，以下是已检索到的数据摘要：\n\n"
                + "\n\n---\n\n".join(_all_tool_results)[:6000]
            )
            yield f"data: {json.dumps({'choices':[{'delta':{'content':_safe_text}}]}, ensure_ascii=False)}\n\n".encode('utf-8')
        else:
            _hint = "【Alice】未能生成回答。请重试，或检查后端日志；周报类问题建议包含项目名（如 CT）。"
            yield f"data: {json.dumps({'choices':[{'delta':{'content':_hint}}]}, ensure_ascii=False)}\n\n".encode('utf-8')

    yield b"data: [DONE]\n\n"
