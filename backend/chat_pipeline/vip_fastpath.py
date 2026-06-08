"""
VIP / Pre-flight RAG fastpaths — extracted from chat_completions generate_stream.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional, Set

logger = logging.getLogger(__name__)

# Q8 单点穿透：仅 CT 项目 Issue Key（对齐 Baize 确定性检索）
_CT_ISSUE_KEY_RE = re.compile(r"(CT-\d+)", re.I)


def extract_ct_issue_key(text: str, fallback_keys: Optional[Set[str]] = None) -> str:
    """从用户句或上下文严格提取 CT-xxxxx；失败时从 fallback_keys 取 CT 前缀 key。"""
    m = _CT_ISSUE_KEY_RE.search(text or "")
    if m:
        return m.group(1).upper()
    for k in sorted(fallback_keys or (), key=len, reverse=True):
        ku = (k or "").upper()
        if _CT_ISSUE_KEY_RE.fullmatch(ku) or ku.startswith("CT-"):
            return ku
    return ""


def summarize_commit_block_deterministic(commit_block: str) -> str:
    """Baize analyzeIssues 风格：提交表预聚合，降低 LLM 数数/归纳幻觉。"""
    if not (commit_block or "").strip():
        return ""
    authors: dict[str, int] = {}
    revs: list[str] = []
    dates: list[str] = []
    for line in (commit_block or "").splitlines():
        if "|" not in line or "r" not in line.lower():
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 4:
            continue
        rev_cell = parts[0]
        if not re.match(r"r\d+", rev_cell, re.I):
            continue
        revs.append(rev_cell)
        author = parts[1] if len(parts) > 1 else "未知"
        authors[author] = authors.get(author, 0) + 1
        if len(parts) > 2 and parts[2]:
            dates.append(parts[2][:10])
    if not revs:
        m_total = re.search(r"共\s*(\d+)\s*条提交", commit_block)
        if m_total:
            return (
                "【确定性统计 · 提交预聚合】\n"
                f"- 提交条数（文本解析）: {m_total.group(1)}\n"
            )
        return ""
    by_author = "; ".join(f"{k}×{v}" for k, v in sorted(authors.items(), key=lambda x: -x[1]))
    date_span = ""
    if dates:
        date_span = f"- 时间跨度: {min(dates)} ~ {max(dates)}\n"
    return (
        "【确定性统计 · 提交预聚合】\n"
        f"- 提交条数: {len(revs)}\n"
        f"- 版本号: {', '.join(revs[:12])}\n"
        f"- 按作者: {by_author}\n"
        f"{date_span}".rstrip()
    )


@dataclass
class VipFastpathContext:
    user_text: str
    issue_keys_found: Set[str]
    intent_label: str
    intent_route: str
    user_cfg: dict
    frontend_cfg: dict
    vip_stream: Callable[[str, str], Iterator[bytes]]
    exec_search_docs_catalog: Callable[[dict], str]
    exec_read_specific_doc: Callable[[dict], str]
    build_weekly_jira_snapshot: Callable[[str, dict, str], tuple]
    iter_jira_structured_read_lane: Callable[..., Iterator[bytes]]
    jira_http: Any = None


def _title_score(title: str, query: str) -> float:
    t = (title or "").strip().lower()
    q = (query or "").strip().lower()
    if not t or not q:
        return 0.0
    if t == q or q in t or t in q:
        return 1.0
    q_chars = [c for c in q if len(c.strip())]
    if not q_chars:
        return 0.0
    hit = sum(1 for c in q_chars if c in t)
    return hit / max(len(q_chars), 1)


def _pick_catalog_prefer_source(items: list, query: str, prefer: str = "notion") -> dict:
    """Pick best title match, boosting preferred source (e.g. notion for tech docs)."""
    if not items:
        return {}
    best = items[0]
    best_score = -1.0
    for it in items:
        score = _title_score(it.get("title") or "", query)
        if (it.get("source") or "").lower() == prefer:
            score += 0.35
        if score > best_score:
            best_score = score
            best = it
    return best


def _pick_catalog_item(items: list, query: str, user_text: str = "") -> dict:
    """Prefer best title match; boost Google Drive when query matches design doc titles."""
    if not items:
        return {}
    prefer_gdrive = bool(re.search(r"云盘|gdrive|google", user_text or "", re.I))
    best = items[0]
    best_score = -1.0
    for it in items:
        title = it.get("title") or ""
        score = _title_score(title, query)
        src = (it.get("source") or "").lower()
        if src == "gdrive":
            score += 0.15
        if prefer_gdrive and src == "gdrive":
            score += 0.25
        if score > best_score:
            best_score = score
            best = it
    return best


def _plugin_sse(name: str, status: str) -> bytes:
    payload = {"custom_type": "plugin_state", "plugin": {"name": name, "status": status}}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def _run_knowledge_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    from knowledge_express_lane import should_use_knowledge_express_lane, extract_catalog_query

    _early_commit_signal = bool(ctx.issue_keys_found) and bool(
        re.search(
            r"提交|commit|diff|代码变更|改了什么代码|变更了哪些|改了哪些文件|提交记录|提交内容|改了.*什么",
            ctx.user_text or "",
            re.I,
        )
    )
    if not should_use_knowledge_express_lane(
        ctx.user_text or "", ctx.intent_label, has_commit_intent=_early_commit_signal,
    ):
        return

    _kq = extract_catalog_query(ctx.user_text or "")
    logger.info(f"[VIP] Knowledge express lane (early): '{_kq[:80]}'")
    yield _plugin_sse("search_docs_catalog", "running")
    _catalog_raw = ctx.exec_search_docs_catalog({"query": _kq, "source": "all"})
    yield _plugin_sse("search_docs_catalog", "done")

    _catalog_items = []
    try:
        _catalog_items = json.loads(_catalog_raw).get("result") or []
    except Exception:
        pass

    _doc_block = ""
    if _catalog_items:
        _pick = _pick_catalog_item(_catalog_items, _kq, ctx.user_text or "")
        _doc_id = _pick.get("doc_id", "")
        _doc_src = _pick.get("source", "notion")
        _doc_title = _pick.get("title", "")
        yield _plugin_sse("read_specific_doc", "running")
        _read_raw = ctx.exec_read_specific_doc({"doc_id": _doc_id, "source": _doc_src})
        yield _plugin_sse("read_specific_doc", "done")
        try:
            _read_j = json.loads(_read_raw)
            _doc_block = _read_j.get("llm_text") or str(_read_j.get("result", ""))[:12000]
        except Exception:
            _doc_block = str(_read_raw)[:12000]
        if _doc_title:
            _doc_block = f"【{_doc_src}】{_doc_title}\n\n{_doc_block}"
    else:
        _doc_block = (
            f"知识库目录检索「{_kq}」在 Notion / Google 云盘中未找到匹配文档。\n"
            "请用户确认文档标题或是否已完成同步。"
        )

    _know_prompt = (
        "你是 Alice。请仅根据下方【真实文档数据】回答用户当前问题。\n"
        "禁止编造文档中不存在的人名、字段或规则；无数据时必须明确说明未找到。\n"
        "当文档数据包含名单、表格行或明确条目（如人名、角色名、配置项）时，"
        "必须在回答中逐项完整列出具体名称，绝对禁止用「等」「若干」「部分」概括或省略任何一条。\n\n"
        f"【文档数据】\n{_doc_block[:12000]}\n\n"
        f"【用户问题】\n{ctx.user_text}"
    )
    yield from ctx.vip_stream(_know_prompt, _doc_block or "（无文档数据）")


def _run_revision_analysis_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    """Q2: Issue + revision → SVN diff → 分析（优先于仅提交列表）"""
    _diff_rev = re.search(r"(?:r|版本\s*)\s*(\d{4,6})", ctx.user_text or "", re.I)
    if not _diff_rev:
        return
    if ctx.intent_label not in ("CODE_COMMIT_DIFF", "revision_analysis", "CODE_COMMIT_LIST") and not re.search(
        r"分析|审查|diff|提交内容", ctx.user_text or "", re.I
    ):
        return
    if re.search(r"有哪些.*提交|提交列表|最近.*天.*提交", ctx.user_text or "", re.I) and not re.search(
        r"分析|审查|提交内容", ctx.user_text or "", re.I
    ):
        return

    _rev_id = _diff_rev.group(1)
    logger.info(f"[VIP] Revision analysis lane r{_rev_id}")

    yield _plugin_sse("get_single_commit_diff", "running")
    raw_diff = ""
    try:
        from knowledge_retriever import get_single_commit_diff

        _d = get_single_commit_diff(_rev_id)
        raw_diff = str(_d)[:8000] if _d and len(str(_d)) > 20 else ""
    except Exception as e:
        raw_diff = f"[Diff r{_rev_id} 获取失败: {e}]"
    yield _plugin_sse("get_single_commit_diff", "done")

    _issue_ctx = ""
    _ik_list = list(ctx.issue_keys_found)
    if _ik_list:
        _ik = _ik_list[0]
        yield _plugin_sse("get_issue_commits", "running")
        try:
            from knowledge_retriever import fetch_precise_commits_via_fisheye

            _issue_ctx = (fetch_precise_commits_via_fisheye(_ik) or "")[:3000]
        except Exception as e:
            _issue_ctx = f"Issue {_ik} 提交上下文获取失败: {e}"
        yield _plugin_sse("get_issue_commits", "done")

    _prompt = (
        f"你是 Alice 资深主程。请基于下方【真实 SVN Diff】分析 revision r{_rev_id} 的提交内容。\n"
        "必须引用 diff 中的具体文件/逻辑变化；若 diff 为空，明确说明无法获取 diff，禁止编造。\n\n"
        f"【SVN Diff r{_rev_id}】\n{raw_diff[:8000]}\n\n"
    )
    if _issue_ctx:
        _prompt += f"【关联 Issue 提交记录】\n{_issue_ctx}\n\n"
    _prompt += f"【用户问题】\n{ctx.user_text}"
    yield from ctx.vip_stream(_prompt, raw_diff[:4000] or "（无 Diff 数据）")


def _run_week_deadline_tasks_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    """Q3: 本周截止字段（End date）+ 策划分列"""
    t = ctx.user_text or ""
    if ctx.intent_label != "WEEK_DEADLINE_TASKS" and not re.search(
        r"本周.*(?:需要完成|要完成)|需要完成.*任务", t, re.I
    ):
        return

    logger.info("[VIP] Week deadline tasks lane")
    yield _plugin_sse("search_jira_issues", "running")
    table_text = ""
    jql = ""
    dl_meta = {"display_name": "截止时间"}
    range_label = ""
    try:
        table_text, jql, dl_meta, date_range = ctx.build_weekly_jira_snapshot(
            t, ctx.frontend_cfg, ctx.user_cfg.get("jira_pat", ""),
        )
        range_label = date_range[2]
    except Exception as e:
        table_text = f"Jira 查询失败: {str(e)[:200]}"
    yield _plugin_sse("search_jira_issues", "done")

    disp = dl_meta.get("display_name", "截止时间")
    planner_note = ""
    if "策划" in t:
        planner_note = (
            "\n【策划分列】从表格中筛选 labels/标题/经办人角色与「策划」相关的行单独成表；"
            "若表格无明确策划列，据经办人与标题合理推断并说明依据。\n"
        )

    _prompt = (
        "你是 Alice PM 助理。根据下方【真实 Jira 数据】回答，禁止编造 Issue。\n\n"
        f"【数据依据】筛选字段「{disp}」；时间：{range_label}；JQL：{jql}\n"
        "（JQL 必须基于截止时间/End date 字段，禁止仅用 updated 或 assignee=currentUser）\n\n"
        f"{table_text}\n{planner_note}\n"
        "【输出要求】\n"
        "1. 先列出本周需要完成的全部任务（表格）\n"
        "2. 若用户要求策划负责，单独一节「策划负责」\n"
        "3. 开头写明数据依据（字段名 + JQL）\n\n"
        f"【用户问题】\n{t}"
    )
    yield from ctx.vip_stream(_prompt, table_text or "（无数据）")


def _run_diff_rag_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    _diff_rev = re.search(r"(?:r|版本\s*)\s*(\d{4,6})", ctx.user_text or "")
    _diff_intent = bool(
        re.search(
            r"diff|分析.*代码|代码.*分析|代码.*审查|变更|改了.*什么|提交内容",
            ctx.user_text or "",
            re.I,
        )
    )
    if not (_diff_rev and _diff_intent):
        return

    _rev_id = _diff_rev.group(1)
    logger.info(f"[VIP] Pre-flight RAG for r{_rev_id}")

    raw_diff = ""
    try:
        from knowledge_retriever import get_single_commit_diff

        _d = get_single_commit_diff(_rev_id)
        raw_diff = str(_d)[:3000] if _d and len(str(_d)) > 20 else ""
    except Exception as e:
        logger.error(f"[VIP] Diff fetch failed: {e}")
        raw_diff = f"[Diff r{_rev_id} 获取失败]"

    _ik_list = list(ctx.issue_keys_found)[:1]
    _ik_str = _ik_list[0] if _ik_list else ""
    try:
        from knowledge_retriever import extract_dynamic_keywords

        _search_kw = extract_dynamic_keywords(ctx.user_text or "", _ik_str)
    except Exception:
        _search_kw = _ik_str or (ctx.user_text or "")[:30]

    doc_content = ""
    _doc_title = ""
    _doc_source_label = "知识库"
    try:
        _search_result = ctx.exec_search_docs_catalog({"query": _search_kw, "source": "all"})
        _sr_obj = json.loads(_search_result)
        if _sr_obj.get("status") == "ok":
            catalog = _sr_obj.get("result", [])
            if isinstance(catalog, list) and catalog:
                _first = _pick_catalog_item(catalog, _search_kw, ctx.user_text or "")
                _doc_id = _first.get("doc_id", "")
                _doc_source = _first.get("source", "notion")
                _doc_title = _first.get("title", "未知文档")
                _doc_source_label = _doc_source.upper()
                if _doc_id:
                    _read_result = ctx.exec_read_specific_doc({"doc_id": _doc_id, "source": _doc_source})
                    _rr_obj = json.loads(_read_result)
                    doc_content = str(_rr_obj.get("llm_text", _rr_obj.get("result", "")))[:2000]
    except Exception as e:
        logger.error(f"[VIP] Knowledge fetch failed: {e}")

    _anti = (
        f"【强制指令】：如果用户后续追问业务逻辑来源于哪里，或者有哪些相关文档，"
        f"你必须如实回答来源于{_doc_source_label}真实文档《{_doc_title}》。"
        f"绝对禁止编造任何不存在的文档名称！"
    ) if _doc_title else ""

    if doc_content:
        final_prompt = (
            f"请作为一个资深主程，对以下 SVN 代码变更进行 Code Review。\n\n"
            f"【业务背景参考】（来自系统自动检索的 {_doc_source_label} 真实文档：《{_doc_title}》）：\n{doc_content}\n\n"
            f"【代码 Diff】：\n{raw_diff}\n\n"
            f"请结合背景，指出代码核心修改意图和潜在风险。不要罗列代码，直接输出分析。\n\n"
            f"{_anti}\n\n"
            f"【用户的真实特定诉求】：{ctx.user_text}\n"
            f"（请在审查或输出时特别关注用户的上述诉求）"
        )
    else:
        final_prompt = (
            f"请作为一个资深主程，对以下 SVN 代码变更进行 Code Review。\n\n"
            f"（未能自动检索到相关业务文档，请基于代码本身进行分析）\n\n"
            f"【代码 Diff】：\n{raw_diff}\n\n"
            f"请指出代码核心修改意图和潜在风险。不要罗列代码，直接输出分析。\n\n"
            f"【用户的真实特定诉求】：{ctx.user_text}\n"
            f"（请在审查或输出时特别关注用户的上述诉求）"
        )

    yield from ctx.vip_stream(
        final_prompt,
        "【VIP 直通车】LLM 未能生成分析，以下是原始 Diff：\n\n" + raw_diff[:4000],
    )


def _run_weekly_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    if not re.search(
        r"周报|日报|月报|本周.{0,10}(?:总结|汇总|进度|情况|报告)|写.{0,8}(?:周报|月报|日报)",
        ctx.user_text or "",
    ):
        return

    logger.info("[VIP] Weekly report express lane")
    yield _plugin_sse("search_jira_issues", "running")
    _weekly_table = ""
    _weekly_jql = ""
    _dl_meta = {"display_name": "截止时间", "source": "?"}
    _range_label = ""
    try:
        _weekly_table, _weekly_jql, _dl_meta, _date_range = ctx.build_weekly_jira_snapshot(
            ctx.user_text, ctx.frontend_cfg, ctx.user_cfg.get("jira_pat", ""),
        )
        _range_label = _date_range[2]
    except Exception as e:
        logger.error(f"[VIP] Weekly Jira fetch failed: {e}")
        _weekly_table = f"Jira 周报数据拉取失败: {str(e)[:200]}"
    yield _plugin_sse("search_jira_issues", "done")

    _disp_field = _dl_meta.get("display_name", "截止时间")
    _weekly_prompt = (
        "你是一名游戏研发项目的 PM 助理。请基于下方【真实 Jira 数据】撰写一份结构化的项目周报。\n\n"
        "【数据筛选依据 — 必须在周报开头第一段写明，禁止省略】\n"
        f"- 筛选字段: Jira「{_disp_field}」\n"
        f"- 时间范围: {_range_label}\n"
        f"- 查询 JQL: {_weekly_jql}\n"
        "- 禁止根据任务状态猜测「本周」；只能使用表格中的任务\n\n"
        "【输出结构 — 必须包含】\n"
        "1. 数据依据说明（字段 + 时间范围 + JQL，见上）\n"
        "2. 本周概览（1-2 句）\n"
        "3. 任务列表（表格，须含编号、标题、经办人、状态、截止时间列）\n"
        "4. 本周更新/完成亮点\n"
        "5. 风险与阻塞（若无则写「暂无」）\n"
        "6. 下周建议关注\n\n"
        "【铁律】\n"
        "- 只能使用下方表格中的 Issue，禁止编造 Issue Key 或人员\n"
        "- 禁止输出「让我先读取文档」「第一步」等过程话术\n"
        "- 若数据为空，如实写「该时间范围内 Jira 未返回匹配任务」\n\n"
        f"【真实 Jira 数据】\n{_weekly_table}\n\n"
        f"【用户原始需求】\n{ctx.user_text}"
    )
    yield from ctx.vip_stream(_weekly_prompt, _weekly_table or "【无 Jira 数据】")


def _run_issue_detail_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    _issue_detail_intent = bool(ctx.issue_keys_found) and bool(
        re.search(
            r"详情|内容|描述|评论|状态|什么情况|怎么样|是谁|什么问题|备注",
            ctx.user_text or "",
        )
    ) and not bool(
        re.search(r"提交|commit|diff|代码变更|改了什么|改成|改为|流转", ctx.user_text or "", re.I)
    )

    if not (_issue_detail_intent and len(ctx.issue_keys_found) == 1):
        return

    _ik = list(ctx.issue_keys_found)[0]
    logger.info(f"[VIP] Issue detail express lane: {_ik}")
    yield _plugin_sse("query_jira_metadata", "running")
    _detail_block = ""
    jira = ctx.jira_http
    try:
        _pat = ctx.user_cfg.get("jira_pat", "")
        _r = jira.jira_get(
            f"/issue/{_ik}",
            params={
                "fields": "summary,description,status,assignee,reporter,issuetype,priority,created,updated,duedate,labels,comment",
            },
            timeout=15,
            user_pat=_pat or None,
        )
        if _r.status_code == 200:
            _f = _r.json().get("fields", {})
            _comments = (_f.get("comment") or {}).get("comments") or []
            _clines = [
                f"- {_c.get('author', {}).get('displayName', '?')}: {(str(_c.get('body', '')) or '')[:200]}"
                for _c in _comments[-5:]
            ]
            _detail_block = (
                f"【Issue {_ik}】\n"
                f"- 标题: {_f.get('summary', '')}\n"
                f"- 类型: {_f.get('issuetype', {}).get('name', '')}\n"
                f"- 状态: {_f.get('status', {}).get('name', '')}\n"
                f"- 经办人: {(_f.get('assignee') or {}).get('displayName', '未分配')}\n"
                f"- 优先级: {(_f.get('priority') or {}).get('name', '')}\n"
                f"- 截止: {_f.get('duedate', '无')}\n"
                f"- 标签: {_f.get('labels', [])}\n"
                f"- 描述摘要: {(str(_f.get('description', '')) or '')[:800]}\n"
                f"- 最近评论:\n" + ("\n".join(_clines) if _clines else "（无）")
            )
        else:
            _detail_block = f"Issue {_ik} 查询失败 HTTP {_r.status_code}"
    except Exception as e:
        _detail_block = f"Issue 详情拉取异常: {str(e)[:200]}"
    yield _plugin_sse("query_jira_metadata", "done")
    _detail_prompt = (
        "请根据下方【真实 Jira Issue 数据】回答用户，禁止编造字段或评论。\n\n"
        f"{_detail_block}\n\n【用户问题】\n{ctx.user_text}"
    )
    yield from ctx.vip_stream(_detail_prompt, _detail_block)


def _run_tech_doc_commit_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    """Q8: Notion 技术文档预取 + Issue 提交 → 设计意图 vs 代码对比（单点穿透 CT Key）"""
    t = ctx.user_text or ""
    _ik = extract_ct_issue_key(t, ctx.issue_keys_found)
    if not _ik:
        return
    if not re.search(r"技术文档|设计文档|PRD|notion", t, re.I):
        return
    if not re.search(r"提交|commit|代码|分析", t, re.I):
        return

    # 单点穿透：仅用 Issue Key 检索知识库，禁止 summary 拼接噪声
    _search_kw = _ik
    logger.info(f"[VIP] Tech-doc + commit lane (pierce): {_ik} kw={_search_kw}")

    notion_block = ""
    yield _plugin_sse("search_docs_catalog", "running")
    _cat_raw = ctx.exec_search_docs_catalog({"query": _search_kw, "source": "all"})
    yield _plugin_sse("search_docs_catalog", "done")
    try:
        _items = json.loads(_cat_raw).get("result") or []
    except Exception:
        _items = []
    if _items:
        _pick = _pick_catalog_prefer_source(_items, _search_kw, prefer="notion")
        if not _pick:
            _pick = _items[0]
        _doc_id = _pick.get("doc_id", "")
        _doc_src = _pick.get("source", "notion")
        _doc_title = _pick.get("title", "")
        yield _plugin_sse("read_specific_doc", "running")
        _read_raw = ctx.exec_read_specific_doc({"doc_id": _doc_id, "source": _doc_src})
        yield _plugin_sse("read_specific_doc", "done")
        try:
            _rj = json.loads(_read_raw)
            notion_block = _rj.get("llm_text") or str(_rj.get("result", ""))[:6000]
            if _doc_title:
                notion_block = f"【{_doc_src}】《{_doc_title}》\n\n{notion_block}"
        except Exception:
            notion_block = str(_read_raw)[:6000]

    commit_block = ""
    yield _plugin_sse("get_issue_commits", "running")
    try:
        from knowledge_retriever import fetch_precise_commits_via_fisheye

        commit_block = fetch_precise_commits_via_fisheye(_ik) or ""
    except Exception as e:
        commit_block = f"提交记录获取失败: {e}"
    yield _plugin_sse("get_issue_commits", "done")

    _commit_stats = summarize_commit_block_deterministic(commit_block)
    if _commit_stats:
        commit_block = f"{_commit_stats}\n\n{commit_block}"

    _diff_block = ""
    _rev_m = re.search(r"(?:r|版本\s*)\s*(\d{4,6})", t, re.I)
    if _rev_m:
        _rid = _rev_m.group(1)
        yield _plugin_sse("get_single_commit_diff", "running")
        try:
            from knowledge_retriever import get_single_commit_diff

            _d = get_single_commit_diff(_rid)
            _diff_block = str(_d)[:4000] if _d else ""
        except Exception as e:
            _diff_block = f"Diff r{_rid} 获取失败: {e}"
        yield _plugin_sse("get_single_commit_diff", "done")

    _prompt = (
        "你是 Alice 资深主程。必须结合【Notion/知识库技术文档】与【真实提交数据】分析任务代码。\n"
        "输出须包含：\n"
        "1. 根据 Notion 技术文档，该任务的设计意图是什么\n"
        "2. 提交代码实际改了什么（可引用 diff）\n"
        "3. 实现与设计是否一致；不一致处逐条说明\n"
        "禁止编造文档或提交中不存在的内容。\n\n"
        f"【技术文档】\n{notion_block[:6000] or '（未检索到 Notion 技术文档，请说明）'}\n\n"
        f"【{_ik} 提交记录】\n{commit_block[:6000]}\n\n"
    )
    if _diff_block:
        _prompt += f"【代码 Diff】\n{_diff_block}\n\n"
    _prompt += f"【用户问题】\n{t}"
    yield from ctx.vip_stream(_prompt, notion_block or commit_block or "（无数据）")


def _run_commit_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    _commit_intent = bool(ctx.issue_keys_found) and bool(
        re.search(
            r"提交|commit|diff|代码变更|改了什么代码|变更了哪些|改了哪些文件|提交记录|提交内容|改了.*什么",
            ctx.user_text or "",
            re.I,
        )
    )
    if not _commit_intent:
        return

    _keys_in_msg = re.findall(
        r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])",
        ctx.user_text or "",
    )
    _ik = (
        _keys_in_msg[0]
        if _keys_in_msg
        else sorted(ctx.issue_keys_found, key=len, reverse=True)[0]
    )
    logger.info(f"[VIP] Issue commit express lane: {_ik}")
    yield _plugin_sse("get_issue_commits", "running")
    _commit_block = ""
    try:
        from knowledge_retriever import fetch_precise_commits_via_fisheye

        _commit_block = fetch_precise_commits_via_fisheye(_ik) or ""
    except Exception as e:
        _commit_block = f"提交记录拉取异常: {str(e)[:200]}"
    yield _plugin_sse("get_issue_commits", "done")
    _commit_stats = summarize_commit_block_deterministic(_commit_block)
    if _commit_stats:
        _commit_block = f"{_commit_stats}\n\n{_commit_block}"
    _commit_prompt = (
        f"你是 Alice。用户只关心【当前这一条消息】里 Issue {_ik} 的程序提交情况。\n"
        "禁止引用本会话中其它轮次的 Jira 列表查询、JQL 或 「50 条任务」等上下文。\n"
        "若下方无提交数据，明确说明「未查到该任务的 SVN/FishEye 提交记录」，不要编造。\n"
        "须优先引用【确定性统计】中的条数与作者分布，勿自行重数表格行。\n\n"
        f"【{_ik} 提交数据】\n{_commit_block[:8000]}\n\n"
        f"【用户当前问题】\n{ctx.user_text}"
    )
    yield from ctx.vip_stream(_commit_prompt, _commit_block or "（无提交数据）")


def _run_jira_structured_lane(ctx: VipFastpathContext) -> Iterator[bytes]:
    from jira_search_engine import should_force_jira_structured_read

    if not (
        ctx.user_text
        and should_force_jira_structured_read(
            ctx.user_text, ctx.intent_route or "", ctx.intent_label,
        )
    ):
        return

    logger.info(f"[JiraLane] structured_search express (label={ctx.intent_label})")
    try:
        yield from ctx.iter_jira_structured_read_lane(
            ctx.user_text, ctx.frontend_cfg, ctx.user_cfg, ctx.vip_stream,
        )
    except Exception as lane_err:
        logger.warning(f"[JiraLane] structured_search failed: {lane_err}")
        try:
            from jira_runtime_config import load_jira_runtime_config
            from jira_search_engine import (
                parse_query_from_natural_language,
                build_resolved_jql,
                format_search_result_for_llm,
            )

            _rt_cfg = load_jira_runtime_config(ctx.frontend_cfg)
            _q = parse_query_from_natural_language(ctx.user_text, _rt_cfg)
            _jql = build_resolved_jql(_q, _rt_cfg).get("jql", "")
            _fb = format_search_result_for_llm(
                {
                    "jql": _jql,
                    "issues": [],
                    "total": 0,
                    "analysis": {"summary": "结构化查询未完成，以下为 JQL 依据"},
                },
                ctx.user_text,
            )
            yield (
                f"data: {json.dumps({'custom_type': 'plugin_state', 'plugin': {'name': 'jira_structured_search', 'status': 'error', 'error': str(lane_err)[:200], 'jql': _jql}}, ensure_ascii=False)}\n\n"
            ).encode("utf-8")
            _err_intro = f"【Alice】Jira 结构化查询遇到问题：{str(lane_err)[:120]}\n\n"
            yield from ctx.vip_stream(_err_intro + _fb, _fb)
        except Exception:
            _plain = f"【Alice】Jira 查询失败：{str(lane_err)[:200]}"
            yield (
                f"data: {json.dumps({'choices': [{'delta': {'content': _plain}}]}, ensure_ascii=False)}\n\n"
            ).encode("utf-8")


def iter_vip_fastpath(ctx: VipFastpathContext) -> Iterator[bytes]:
    """
    Try VIP lanes in order. Yields SSE chunks; return True if a lane handled the request.
    Usage:
        gen = iter_vip_fastpath(ctx)
        while True:
            try:
                yield next(gen)
            except StopIteration as stop:
                if stop.value:
                    yield b"data: [DONE]\\n\\n"
                break
    """
    lanes = (
        _run_knowledge_lane,
        _run_week_deadline_tasks_lane,
        _run_revision_analysis_lane,
        _run_diff_rag_lane,
        _run_tech_doc_commit_lane,
        _run_weekly_lane,
        _run_issue_detail_lane,
        _run_commit_lane,
        _run_jira_structured_lane,
    )
    for lane in lanes:
        gen = lane(ctx)
        if gen is None:
            continue
        yielded = False
        for chunk in gen:
            yielded = True
            yield chunk
        if yielded:
            return True
    return False
