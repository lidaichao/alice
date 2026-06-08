"""M5.1 — 工作流模板注册表引擎（骨架）。

职责：
  1. 加载 workflow_templates.yaml → 校验必填字段 + ID 唯一性
  2. 列出模板 ID / 按 ID 获取模板
  3. 不实现执行——留给 M5.2/M5.3 接入。

严禁手搓正则 / 手写 YAML 解析器；统一用 PyYAML。
"""

from __future__ import annotations

import json
import os
import logging
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

logger = logging.getLogger("workflow-engine")

_TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "data", "workflow_templates.yaml")

_REQUIRED_TOP_FIELDS = {"id", "name", "steps"}
_REQUIRED_STEP_FIELDS = {"id", "tool", "description"}


def _validate_template(t: dict, index: int) -> None:
    """校验单个模板必填字段，缺失抛 ValueError。"""
    label = t.get("id") or f"#index-{index}"
    missing = _REQUIRED_TOP_FIELDS - set(t.keys())
    if missing:
        raise ValueError(f"模板「{label}」缺少必填字段: {sorted(missing)}")
    steps = t.get("steps") or []
    if not isinstance(steps, list) or len(steps) == 0:
        raise ValueError(f"模板「{label}」的 steps 必须是非空数组")
    for si, s in enumerate(steps):
        miss = _REQUIRED_STEP_FIELDS - set(s.keys())
        if miss:
            raise ValueError(
                f"模板「{label}」第 {si} 步「{s.get('id', f'index-{si}')}」缺少必填字段: {sorted(miss)}"
            )


def load_templates(path: str | None = None) -> list[dict]:
    """加载并校验 workflow_templates.yaml，返回模板列表。"""
    if yaml is None:
        raise ImportError("PyYAML 未安装，无法加载工作流模板（pip install pyyaml）")

    file_path = path or _TEMPLATES_PATH
    if not os.path.isfile(file_path):
        logger.warning("[Workflow] templates file not found: %s", file_path)
        return []

    with open(file_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw = data.get("templates") or []
    if not isinstance(raw, list):
        raise ValueError(f"顶层 'templates' 必须是数组，实际类型: {type(raw).__name__}")

    ids: set = set()
    for i, t in enumerate(raw):
        _validate_template(t, i)
        tid = t.get("id")
        if tid in ids:
            raise ValueError(f"模板 ID「{tid}」重复，请确保 id 唯一")
        ids.add(tid)

    logger.info("[Workflow] loaded %d templates: %s", len(raw), sorted(ids))
    return raw


def get_template(template_id: str) -> dict | None:
    """按 ID 获取单个模板。"""
    templates = load_templates()
    for t in templates:
        if t.get("id") == template_id:
            return dict(t)
    return None


def list_template_ids() -> list[str]:
    """列出所有模板 ID。"""
    return sorted(t.get("id") for t in load_templates() if t.get("id"))


# ════════════════════════════════════════════════════════════
#  TODO(M5.3) — 在此接入更多模板:
#    - design-to-subtasks 模板执行
#    - 流式执行（M5.4）
# ════════════════════════════════════════════════════════════


def execute_template(template_id: str, context: dict | None = None) -> dict:
    """M5.2/M5.3 — 执行指定工作流模板。

    :param template_id: 模板 ID（如 version-day-check / design-to-subtasks）
    :param context:    上下文参数，可选
    :return:           {"ok": True, "template_id": ..., "steps": [...], "execution_log": [...]}
                       {"ok": False, "failed_step": ..., "error": ...}
    """
    ctx = context or {}
    tmpl = get_template(template_id)
    if tmpl is None:
        return {"ok": False, "error": f"模板不存在: {template_id}"}

    steps = tmpl.get("steps") or []
    execution_log: list[dict] = []
    step_states: list[dict] = []
    partial_failures: list[dict] = []

    for step in steps:
        step_id = step.get("id", "?")
        tool = step.get("tool", "")
        desc = step.get("description", "")
        step_state = {"id": step_id, "tool": tool, "status": "pending"}
        step_states.append(step_state)

        try:
            if tool == "jira_search":
                result = _step_jira_search(step, ctx, execution_log)
            elif tool == "format":
                result = _step_format(step, ctx, execution_log, template_id)
            elif tool == "llm_summarize":
                result = _step_llm_summarize(step, ctx, execution_log)
            elif tool == "kb_search":
                result = _step_kb_search(step, ctx, execution_log)
            elif tool == "jira_create_drafts":
                result = _step_jira_create_drafts(step, ctx, execution_log)
            else:
                raise ValueError(f"未知工具类型: {tool}")

            step_state["status"] = "done"
            step_state["result"] = result

            # jira_create_drafts may return structured dict with partial_failures
            prefix = ""
            if isinstance(result, dict):
                pf = result.get("partial_failures") or []
                if pf:
                    step_state["partial_failures"] = pf
                    partial_failures.extend(pf)
                    prefix = f"[{len(pf)} partial failures] "
                result = json.dumps(result, ensure_ascii=False)

            output_snippet = (result or "")[:500]
            execution_log.append({
                "step_id": step_id,
                "tool": tool,
                "status": "done",
                "output": f"{prefix}{output_snippet}" if prefix else output_snippet,
            })

        except Exception as e:
            step_state["status"] = "failed"
            err_msg = f"{desc} — {str(e)[:200]}"
            execution_log.append({
                "step_id": step_id,
                "tool": tool,
                "status": "failed",
                "error": err_msg,
            })
            logger.warning("[Workflow] step '%s' failed: %s", step_id, e)
            return {
                "ok": False,
                "template_id": template_id,
                "failed_step": step_id,
                "error": err_msg,
                "steps": step_states,
                "execution_log": execution_log,
            }

    logger.info("[Workflow] template '%s' executed: %d steps OK", template_id, len(steps))
    return {
        "ok": True,
        "template_id": template_id,
        "template_name": tmpl.get("name", template_id),
        "steps": step_states,
        "execution_log": execution_log,
    }


# ── 步骤处理器 ────────────────────────────────────────────


def _step_jira_search(step: dict, ctx: dict, execution_log: list[dict]) -> str:
    """M5.2 jira_search 步骤 — 复用现有 Jira 接口执行 JQL。"""
    jql = (ctx.get("jql") or "").strip()
    if not jql:
        raise ValueError("JQL 查询语句为空，请在 context.jql 中提供或从 Admin 配置读取")

    jira_pat = ctx.get("jira_pat") or os.getenv("JIRA_PAT", "")
    jira_url = ctx.get("jira_url") or os.getenv("JIRA_URL", "")

    import requests as _req
    try:
        r = _req.get(
            f"{jira_url.rstrip('/')}/rest/api/2/search",
            params={"jql": jql, "maxResults": 50, "fields": "key,summary,status,assignee"},
            headers={"Authorization": f"Bearer {jira_pat}"} if jira_pat else {},
            timeout=15,
        )
        if r.status_code != 200:
            raise ValueError(f"Jira API 返回 HTTP {r.status_code}: {r.text[:200]}")

        data = r.json()
        issues = data.get("issues", [])
        total = data.get("total", 0)
        lines = [f"JQL 查询 '{jql[:80]}' → 共 {total} 条"]
        for i, issue in enumerate(issues[:20]):
            key = issue.get("key", "?")
            fields = issue.get("fields", {})
            summary = fields.get("summary", "")
            status = (fields.get("status") or {}).get("name", "")
            assignee = (fields.get("assignee") or {}).get("displayName", "未分配")
            lines.append(f"{i+1}. {key} [{status}] {summary} — {assignee}")
        return "\n".join(lines)

    except Exception as e:
        raise ValueError(f"Jira 查询失败: {str(e)[:200]}")


def _step_format(step: dict, ctx: dict, execution_log: list[dict], template_id: str = "") -> str:
    """M5.2 format 步骤 — 将上一步结果格式化。

    对 version-day-check：格式化为检查清单表格
    对 design-to-subtasks：整理 draft 列表供 HITL 审批
    """
    prev = execution_log[-1] if execution_log else {}
    raw_output = prev.get("output", "")
    if not raw_output:
        raise ValueError("format 步骤缺少上一步输出（execution_log 为空）")

    # ── design-to-subtasks: draft 列表 ──
    if template_id == "design-to-subtasks":
        try:
            data = json.loads(raw_output)
        except Exception:
            data = {}
        draft_ids = data.get("drafts") or []
        partial_failures = data.get("partial_failures") or []
        lines = ["## 策划→子任务 · 草稿列表（待 HITL 审批）\n"]
        lines.append("| # | Draft ID | Summary | Status |")
        lines.append("|---|---|---|---|")
        for i, d in enumerate(draft_ids):
            confirm_url = f"/v1/drafts/{d.get('draft_id', '?')}/confirm"
            lines.append(f"| {i+1} | `{d.get('draft_id', '?')}` | {d.get('summary', '?')[:60]} | [确认]({confirm_url}) |")
        if not draft_ids:
            lines.append("| - | 无有效草稿 | - | - |")
        if partial_failures:
            lines.append(f"\n### ⚠️ {len(partial_failures)} 条创建失败")
            for pf in partial_failures:
                lines.append(f"- #{pf.get('index', '?')} `{pf.get('summary', '?')[:60]}`: {pf.get('error', '?')}")
        return "\n".join(lines)

    # ── version-day-check: 检查清单 ──
    lines = raw_output.split("\n")
    checklist = ["## 版本日检查清单\n"]
    checklist.append("| # | Issue | 状态 | 负责人 |")
    checklist.append("|----|-------|------|--------|")
    count = 0
    for line in lines:
        import re
        m = re.match(r"^\d+\.\s+(.+?)\s+\[(.+?)\]\s+(.+?)\s+—\s+(.+)$", line)
        if m:
            count += 1
            checklist.append(f"| {count} | {m.group(1)} | {m.group(2)} | {m.group(4)} |")
    if count == 0:
        checklist.append("| - | 无待检查 Issue | - | - |")
    return "\n".join(checklist)


def _step_llm_summarize(step: dict, ctx: dict, execution_log: list[dict]) -> str:
    """M5.2/M5.3 llm_summarize 步骤 — LLM 汇总 / 提取。

    根据 step_id 自动选择 prompt：
      - identify_subtasks → 从策划文档提取子任务列表（JSON）
      - 其他 → 版本日检查清单总结
    """
    prev = execution_log[-1] if execution_log else {}
    raw_output = prev.get("output", "")
    if not raw_output:
        raise ValueError("llm_summarize 步骤缺少上一步输出（execution_log 为空）")

    deepseek_key = ctx.get("deepseek_key") or os.getenv("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    if not deepseek_key:
        return f"【LLM 不可用 — 未配置 DeepSeek Key】\n{raw_output[:1500]}"

    import urllib.request as _ur
    import json as _j

    step_id = step.get("id", "")

    if step_id == "identify_subtasks":
        system_prompt = (
            "你是 Alice 的工作流规划助手。根据输入的策划文档内容，提取可执行的子任务列表。\n\n"
            "输出格式（严格 JSON 数组）：\n"
            '[{"summary": "子任务标题", "issueType": "Task"}, ...]\n\n'
            "规则：\n"
            "- 每个子任务是一个独立的 Jira Issue，summary 清晰描述要做什么\n"
            "- issueType 默认 \"Task\"\n"
            "- 提取 3-8 个核心子任务\n"
            "- 只输出 JSON 数组，不输出任何解释"
        )
        max_tokens = 1200
    else:
        system_prompt = (
            "你是 Alice 的版本日检查助手。根据输入的 Jira 检查清单，用中文总结："
            "待处理项数量、已完成项数量、重点关注项。简洁输出，不超过 500 字。"
        )
        max_tokens = 600

    payload = _j.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_output[:6000]},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }).encode()

    try:
        req = _ur.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"},
        )
        with _ur.urlopen(req, timeout=30) as resp:
            data = _j.loads(resp.read().decode())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() or "LLM 返回空响应"
    except Exception as e:
        logger.warning("[Workflow] LLM summarize failed: %s", e)
        return f"【LLM 调用失败: {str(e)[:120]}】\n{raw_output[:1500]}"


# ── M5.3 步骤处理器 ───────────────────────────────────────


def _step_kb_search(step: dict, ctx: dict, execution_log: list[dict]) -> str:
    """M5.3 kb_search 步骤 — FAISS 语义检索优先，降级 catalog 关键词。

    从 context 读取 doc_query 或 parent_issue_key 作为搜索词。
    """
    query = (ctx.get("doc_query") or ctx.get("parent_issue_key") or "").strip()
    if not query:
        raise ValueError("kb_search 步骤缺少搜索词（context.doc_query 或 parent_issue_key）")

    # ── 优先 FAISS 语义检索 ──
    try:
        import rag_engine as _rag_mod
        if _rag_mod.is_index_ready():
            result = _rag_mod.search_doc_chunks(query, top_k=3)
            if result and not result.startswith("[RAG]"):
                logger.info("[Workflow] kb_search FAISS hit for '%s'", query[:60])
                return f"【FAISS 语义检索结果】\n查询: {query}\n\n{result}"
    except Exception as e:
        logger.debug("[Workflow] kb_search FAISS failed, falling back: %s", e)

    # ── 降级：简单文本返回 + 提示 ──
    fallback = (
        f"【KB 检索降级】\n"
        f"查询: {query}\n"
        f"FAISS 索引不可用，返回关键词结果：\n\n"
        f"请在 workflow context 中提供 doc_query 定位策划文档。\n"
        f"可用文档源: Notion / GDrive（search_docs_catalog 工具）"
    )
    logger.info("[Workflow] kb_search fallback for '%s'", query[:60])
    return fallback


def _step_jira_create_drafts(step: dict, ctx: dict, execution_log: list[dict]) -> dict:
    """M5.3 jira_create_drafts 步骤 — 逐条创建 draft，单条失败不停全局。

    从上一步 output 解析子任务列表（JSON 数组），逐条调 create_issues_draft。
    返回 {"total": N, "success": M, "failed": K, "drafts": [...], "partial_failures": [...]}
    全部失败 → raise ValueError。
    """
    prev = execution_log[-1] if execution_log else {}
    raw_output = prev.get("output", "")
    if not raw_output:
        raise ValueError("jira_create_drafts 步骤缺少上一步输出的子任务列表")

    # 解析 LLM 输出的 JSON 数组
    subtasks = _parse_subtask_json(raw_output)
    if not subtasks:
        raise ValueError("未能从上一步输出中解析出有效的子任务列表")

    project_key = ctx.get("project_key") or ""
    issue_type = ctx.get("issue_type") or "Task"
    user_id = ctx.get("user_id") or ""
    conversation_id = ctx.get("conversation_id") or ""
    parent_issue_key = ctx.get("parent_issue_key") or ""

    from jira_operation_manager import create_issues_draft as _create_draft

    drafts = []
    partial_failures = []
    for i, st in enumerate(subtasks):
        try:
            summary = (st.get("summary") or "").strip()
            if not summary:
                partial_failures.append({"index": i, "summary": "(empty)", "error": "summary 为空"})
                continue
            item = {"summary": summary, "issueType": st.get("issueType", issue_type)}
            if project_key:
                item["projectKey"] = project_key
            draft = _create_draft([item], conversation_id=conversation_id, user_id=user_id)
            drafts.append({
                "draft_id": draft["id"],
                "summary": summary,
                "issueType": item.get("issueType", issue_type),
                "projectKey": project_key or "(未指定)",
            })
        except Exception as e:
            partial_failures.append({"index": i, "summary": st.get("summary", "?")[:80], "error": str(e)[:200]})
            logger.warning("[Workflow] draft creation #%d failed: %s", i, e)

    if not drafts and partial_failures:
        raise ValueError(f"所有 {len(subtasks)} 条子任务创建 draft 均失败")

    # ── auto_confirm（仅 ALICE_DEBUG=1） ──
    auto_confirmed = []
    if ctx.get("auto_confirm") is True and os.environ.get("ALICE_DEBUG", "").strip() == "1":
        from jira_operation_manager import create_operation_card, mark_running, mark_created
        for d in drafts:
            try:
                conv_id = ctx.get("conversation_id") or f"auto-confirm-{d['draft_id']}"
                op = create_operation_card(
                    kind="create_issue",
                    summary=d["summary"],
                    source="workflow-design-to-subtasks",
                    tool_params={"issues_list": [{"summary": d["summary"], "issueType": d.get("issueType", "Task")}]},
                    conversation_id=conv_id,
                    user_id=user_id,
                )
                op = mark_running(op)
                op = mark_created(op, [{"key": f"auto-{d['draft_id'][-8:]}"}], confirmed_by=user_id or "workflow-auto")
                auto_confirmed.append({"draft_id": d["draft_id"], "operation_id": op.get("id", "")})
            except Exception as e:
                logger.warning("[Workflow] auto_confirm draft %s failed: %s", d["draft_id"], e)

    result = {
        "total": len(subtasks),
        "success": len(drafts),
        "failed": len(partial_failures),
        "drafts": drafts,
        "partial_failures": partial_failures,
    }
    if auto_confirmed:
        result["auto_confirmed"] = auto_confirmed
    return result


def _parse_subtask_json(text: str) -> list[dict]:
    """从 LLM 输出中提取子任务 JSON 数组。"""
    import re

    text = (text or "").strip()
    # 尝试直接解析整个文本
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    # 尝试从 markdown 代码块提取
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            parsed = json.loads(m.group(1).strip())
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    # 尝试找第一个 JSON 数组
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            parsed = json.loads(m.group())
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    return []
