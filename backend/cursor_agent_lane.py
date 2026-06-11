"""P2-2: Cursor SDK Lane — 自定义工具 + 通用复杂执行引擎入口。

将所有需要多步编排、代码分析、Jira 批量操作的任务，
从 DeepSeek ReAct 手搓工具迁移至 Cursor SDK 代理执行。
"""
from __future__ import annotations

import json
import logging
import os
import selectors
import sys
import time as _time
from typing import Any, Callable, Dict, Iterator, List, Optional


# ═══════════════════════════════════════════════════════════════
#  cursor-sdk 0.1.7 + Windows 兼容性补丁 (v1.0.30)
#
#  背景：cursor-sdk _bridge.py:_read_discovery() 使用
#  selectors.DefaultSelector() 监听子进程 stderr pipe。
#  Windows 的 select.select() 仅支持 socket，不支持 pipe
#  handle → OSError WinError 10038。
#
#  此补丁用轮询选择器替代 DefaultSelector，绕过该限制。
#  待 cursor-sdk 上游修复后移除此补丁。
# ═══════════════════════════════════════════════════════════════

class _PollingSelector(selectors._BaseSelectorImpl):
    """轮询选择器：用 os.read(fd, 0) + sleep 替代 select.select()。

    仅用于 cursor-sdk 桥进程 stderr 监听，不适用于高性能 I/O。
    """
    _POLL_S = 0.02  # 20ms poll interval

    def register(self, fileobj, events, data=None):
        key = super().register(fileobj, events, data)
        return key

    def unregister(self, fileobj):
        return super().unregister(fileobj)

    def select(self, timeout=None):
        deadline = (_time.monotonic() + timeout) if timeout is not None else None
        while True:
            ready = []
            for fd in list(self._fd_to_key):
                key = self._fd_to_key[fd]
                if key.events & selectors.EVENT_READ:
                    try:
                        os.read(fd, 0)
                    except (BlockingIOError, OSError):
                        continue
                    ready.append((key, selectors.EVENT_READ))
            if ready or (deadline is not None and _time.monotonic() >= deadline):
                return ready
            _time.sleep(min(timeout or self._POLL_S, self._POLL_S))


# 在 cursor_sdk import 前应用补丁
selectors.DefaultSelector = _PollingSelector  # type: ignore[assignment]

from cursor_sdk import Agent, CursorAgentError, CustomTool, LocalAgentOptions

logger = logging.getLogger("cursor-agent-lane")

SSE_DONE = b"data: [DONE]\n\n"


# ═══════════════════════════════════════════════════════════════
#  工具 input_schema 辅助
# ═══════════════════════════════════════════════════════════════

def _obj(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props.keys())}

def _str_param(desc: str) -> dict:
    return {"type": "string", "description": desc}

def _int_param(desc: str) -> dict:
    return {"type": "integer", "description": desc}


# ═══════════════════════════════════════════════════════════════
#  只读工具 handlers
# ═══════════════════════════════════════════════════════════════

def _handle_jira_search_issues(args: dict, _ctx) -> str:
    """只读：Jira 关键词搜索"""
    keyword = (args.get("keyword") or args.get("query") or "").strip()
    if not keyword:
        return json.dumps({"status": "error", "result": "缺少 keyword 参数"})
    try:
        from jira_search_engine import (
            JiraSearchQuery,
            format_search_result_for_llm,
            parse_query_from_natural_language,
            search_and_analyze,
        )
        from jira_runtime_config import load_jira_runtime_config
        from ai_bridge import jira

        rt_cfg = load_jira_runtime_config({})
        query = None
        try:
            from jira_query_builder import parse_query_llm
            structured = parse_query_llm(keyword)
            if structured:
                query = JiraSearchQuery(max_results=rt_cfg.max_search_results)
                if structured.get("assignee"):
                    query.assignees = [structured["assignee"]]
                if structured.get("status"):
                    query.statuses = [structured["status"]]
                if structured.get("projectKey"):
                    query.project_key = structured["projectKey"]
                if structured.get("issueType"):
                    query.issue_types = [structured["issueType"]]
                if structured.get("text"):
                    query.text = structured["text"]
                if structured.get("updatedAfter"):
                    query.updated_after = structured["updatedAfter"]
                if structured.get("updatedBefore"):
                    query.updated_before = structured["updatedBefore"]
                if structured.get("maxResults"):
                    query.max_results = int(structured["maxResults"])
        except Exception as _ql_e:
            logger.warning("[cursor-lane] jira_search LLM builder failed: %s", _ql_e)

        if query is None:
            query = parse_query_from_natural_language(keyword, rt_cfg)
        if not query.text and not query.assignees:
            query.text = keyword

        result = search_and_analyze(jira, query, config=rt_cfg)
        llm_text = format_search_result_for_llm(result, keyword)
        items = result.get("issues") or []
        return json.dumps({
            "status": "ok",
            "result": {
                "total": result.get("total", 0),
                "issues": items,
                "jql": result.get("jql"),
                "analysis": result.get("analysis"),
            },
            "llm_text": llm_text,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "result": f"Jira 搜索异常: {str(e)[:200]}"})


def _handle_jira_read_issue_detail(args: dict, _ctx) -> str:
    """只读：获取单个 Jira Issue 的完整详情"""
    issue_key = args.get("issue_key", "").strip()
    if not issue_key:
        return json.dumps({"status": "error", "result": "缺少 issue_key 参数"})
    try:
        from ai_bridge import jira, _strip_html
        from jira_search_engine import simplify_issue

        resp = jira.jira_get(
            f"{jira.api_url}/issue/{issue_key}"
            "?fields=summary,issuetype,status,assignee,priority,created,updated,duedate,description,project,comment"
            "&expand=renderedFields",
            timeout=10,
        )
        if resp.status_code != 200:
            return json.dumps({"status": "error", "result": f"Jira 返回 {resp.status_code}"})

        data = resp.json()
        simplified = simplify_issue(data)
        fields = data.get("fields", {})

        desc = ""
        rendered = data.get("renderedFields", {})
        if rendered.get("description"):
            desc = _strip_html(rendered["description"])[:500]
        elif fields.get("description"):
            desc = _strip_html(str(fields.get("description", "")))[:500]

        comments_list = []
        comment_data = fields.get("comment", {})
        for c in (comment_data.get("comments") or [])[-3:]:
            body = _strip_html(c.get("body", ""))[:200]
            comments_list.append({
                "author": c.get("author", {}).get("displayName", "?"),
                "created": c.get("created", ""),
                "body": body,
            })

        return json.dumps({
            "status": "ok",
            "result": {
                **simplified,
                "description_summary": desc,
                "comments": comments_list,
            }
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "result": f"获取 Issue 详情失败: {str(e)[:200]}"})


def _handle_list_issuetypes(args: dict, _ctx) -> str:
    """只读：查询 Jira 项目的可用 Issue 类型"""
    project_key = (args.get("project_key") or "").strip()
    if not project_key:
        return json.dumps({"status": "error", "result": "缺少 project_key 参数"})
    try:
        from ai_bridge import jira
        types = jira.get_project_issuetypes(project_key)
        simple = [{"name": t.get("name", ""), "id": t.get("id", ""), "subtask": bool(t.get("subtask"))} for t in types]
        return json.dumps({"status": "ok", "result": {"project_key": project_key, "issuetypes": simple, "total": len(simple)}}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "result": str(e)})


def _handle_read_file(args: dict, _ctx) -> str:
    """只读：读取工作区文件"""
    from workspace_tools import _exec_read_file
    return _exec_read_file(args)


def _handle_search_code(args: dict, _ctx) -> str:
    """只读：ripgrep 代码搜索"""
    from workspace_tools import _exec_search_code
    return _exec_search_code(args)


def _handle_svn_log(args: dict, _ctx) -> str:
    """只读：SVN 提交日志"""
    from workspace_tools import _exec_svn_log
    return _exec_svn_log(args)


def _handle_list_directory(args: dict, _ctx) -> str:
    """只读：列出目录结构"""
    from workspace_tools import _exec_list_directory
    return _exec_list_directory(args)


# ── KB / SVN 只读（复用 ai_bridge 现有实现）─────────────

def _handle_get_issue_commits(args: dict, _ctx) -> str:
    """只读：查询 Issue 关联的 SVN 提交文件列表"""
    from ai_bridge import _exec_get_issue_commits
    return _exec_get_issue_commits(args)


def _handle_get_single_commit_diff(args: dict, _ctx) -> str:
    """只读：查询单次 SVN 提交的 Diff 内容"""
    from ai_bridge import _exec_get_single_commit_diff
    return _exec_get_single_commit_diff(args)


def _handle_search_docs_catalog(args: dict, _ctx) -> str:
    """只读：搜索 Notion/GDrive 文档目录（返回标题+摘要）"""
    from ai_bridge import _exec_search_docs_catalog
    return _exec_search_docs_catalog(args, user_text=(args.get("query") or ""))


def _handle_read_specific_doc(args: dict, _ctx) -> str:
    """只读：读取指定文档全文（Notion/GDrive）"""
    from ai_bridge import _exec_read_specific_doc
    return _exec_read_specific_doc(args, user_text=(args.get("doc_id") or ""))


# ═══════════════════════════════════════════════════════════════
#  写操作工具 handlers（经审计闸门）
# ═══════════════════════════════════════════════════════════════

def _make_write_handler(
    kind: str,
    *,
    conversation_id: str = "",
    user_id: str = "",
) -> Callable[[dict, Any], str]:
    """创建带审计闸门的写操作 handler 闭包。"""

    def _handler(args: dict, _ctx) -> str:
        from jira_operation_manager import create_operation_card_with_audit

        drafts: list = []

        if kind == "jira_bulk_create":
            summaries = args.get("summaries") or args.get("issues_list") or []
            if isinstance(summaries, list):
                project_key = args.get("project_key") or args.get("projectKey") or ""
                issue_type = args.get("issue_type") or args.get("issueType") or "Task"
                parent_key = args.get("parent_key") or args.get("parentKey") or ""
                for s in summaries:
                    summary = s if isinstance(s, str) else s.get("summary", str(s))
                    draft = {
                        "summary": summary,
                        "projectKey": project_key,
                        "issueType": issue_type,
                        "description": s.get("description", "") if isinstance(s, dict) else "",
                    }
                    if parent_key:
                        draft["parentKey"] = parent_key
                    drafts.append(draft)
            else:
                return json.dumps({"status": "error", "result": "summaries 必须是数组"})

        elif kind == "jira_transition":
            issue_key = args.get("issue_key") or args.get("issueKey") or ""
            target_status = args.get("target_status") or args.get("targetStatus") or ""
            if not issue_key:
                return json.dumps({"status": "error", "result": "缺少 issue_key 参数"})
            drafts.append({
                "summary": f"变更 {issue_key} 状态 → {target_status}",
                "projectKey": issue_key.split("-")[0] if "-" in issue_key else "",
                "issueType": "Task",
                "description": f"目标状态: {target_status}",
                "operation": "transition",
                "issue_key": issue_key,
                "target_status": target_status,
            })

        elif kind == "jira_add_comment":
            issue_key = args.get("issue_key") or args.get("issueKey") or ""
            comment_body = args.get("body") or args.get("comment") or ""
            if not issue_key:
                return json.dumps({"status": "error", "result": "缺少 issue_key 参数"})
            if not comment_body:
                return json.dumps({"status": "error", "result": "缺少 body（评论内容）"})
            drafts.append({
                "summary": f"评论 {issue_key}: {comment_body[:80]}",
                "projectKey": issue_key.split("-")[0] if "-" in issue_key else "",
                "issueType": "Task",
                "description": comment_body,
                "operation": "comment",
                "issue_key": issue_key,
                "comment_body": comment_body,
            })

        logger.info("[CursorTool] jira_write invoked kind=%s user_id=%s conv_id=%s drafts_count=%d",
                   kind, user_id, conversation_id, len(drafts))

        audit_result = create_operation_card_with_audit(
            drafts=drafts,
            conversation_id=conversation_id,
            user_id=user_id,
            kind=kind,
            trigger_source="cursor_sdk",
            ai_created=True,
        )
        logger.info("[CursorTool] audit_result status=%s op_id=%s",
                   audit_result.get("status"), audit_result.get("operation", {}).get("id", "NONE"))
        if audit_result.get("status") == "awaiting_confirmation":
            op = audit_result.get("operation", {})
            logger.info("[CursorTool] operation detail: id=%s kind=%s status=%s drafts=%s",
                       op.get("id"), op.get("kind"), op.get("status"), len(op.get("drafts", [])))

        op = audit_result.get("operation")
        if op and op.get("id"):
            from jira_operation_manager import save_operation
            save_operation(op)
            logger.info("[CursorTool] save_operation done op_id=%s", op["id"])

        return json.dumps({"status": audit_result.get("status", "unknown"), "detail": audit_result}, ensure_ascii=False)

    return _handler


# ═══════════════════════════════════════════════════════════════
#  工具构建
# ═══════════════════════════════════════════════════════════════

def _build_custom_tools(
    conversation_id: str = "",
    user_id: str = "",
    *,
    mode: str = "agent",
) -> Dict[str, CustomTool]:
    """构建 Cursor SDK 自定义工具。mode=ask 时仅注入只读工具（10 个），agent/plan 全量（13 个）。"""

    tools: Dict[str, CustomTool] = {}

    # ── 只读工具 ─────────────────────────────────────────

    tools["jira_search_issues"] = CustomTool(
        execute=_handle_jira_search_issues,
        description="在 Jira 中按关键词搜索相关任务。返回匹配的任务列表（key、标题、状态、经办人）。",
        input_schema=_obj({"keyword": _str_param("搜索关键词（1-2 个核心业务术语）")}),
    )

    tools["jira_read_issue_detail"] = CustomTool(
        execute=_handle_jira_read_issue_detail,
        description="获取指定 Jira Issue 的完整详情——标题、状态、经办人、优先级、描述摘要、最近评论。",
        input_schema=_obj({"issue_key": _str_param("Jira Issue Key，例如 CT-11112")}),
    )

    tools["list_jira_issuetypes"] = CustomTool(
        execute=_handle_list_issuetypes,
        description="查询指定 Jira 项目的可用问题类型列表（名称+ID）。用于在创建 Issue 前确认合法的 issuetype 名称。只读。",
        input_schema=_obj({"project_key": _str_param("Jira 项目 Key，如 CT、GM")}),
    )

    tools["read_file"] = CustomTool(
        execute=_handle_read_file,
        description="读取工作区内指定文件的内容（只读）。路径必须在已授权工作区内。",
        input_schema=_obj({
            "path": _str_param("文件路径（相对或绝对）"),
            "max_lines": _int_param("最大读取行数，默认 200"),
        }, required=["path"]),
    )

    tools["search_code"] = CustomTool(
        execute=_handle_search_code,
        description="使用 ripgrep 在工作区内搜索代码内容。支持正则表达式和文件类型过滤。只读。",
        input_schema=_obj({
            "pattern": _str_param("搜索的正则表达式或关键词"),
            "path": _str_param("搜索路径（默认当前工作区）"),
            "glob": _str_param("文件类型过滤，如 '*.py' 或 '*.{js,ts}'"),
        }, required=["pattern"]),
    )

    tools["svn_log"] = CustomTool(
        execute=_handle_svn_log,
        description="查看工作区内 SVN 仓库的提交历史（只读）。",
        input_schema=_obj({
            "path": _str_param("文件或目录路径"),
            "limit": _int_param("返回最近 N 条提交，默认 20"),
        }, required=["path"]),
    )

    tools["list_directory"] = CustomTool(
        execute=_handle_list_directory,
        description="列出工作区内的目录结构（只读）。",
        input_schema=_obj({"path": _str_param("目录路径（必须在已授权工作区内）")}),
    )

    # ── KB / SVN 只读工具 ────────────────────────────────

    tools["get_issue_commits"] = CustomTool(
        execute=_handle_get_issue_commits,
        description="查询指定 Jira Issue 关联的 SVN 提交列表（文件路径、版本号、作者、时间）。只读。",
        input_schema=_obj({"issue_key": _str_param("Jira Issue Key，如 CT-11112")}),
    )

    tools["get_single_commit_diff"] = CustomTool(
        execute=_handle_get_single_commit_diff,
        description="获取指定 SVN 版本号的代码 Diff 内容。只读。",
        input_schema=_obj({"revision_id": _str_param("SVN 版本号，如 40538 或 r40538")}),
    )

    tools["search_docs_catalog"] = CustomTool(
        execute=_handle_search_docs_catalog,
        description="搜索 Notion/Google Drive 文档目录，返回标题+摘要候选列表。不返回全文。只读。",
        input_schema=_obj({
            "query": _str_param("搜索关键词"),
            "source": _str_param("文档来源：notion / gdrive / all（默认 all）"),
        }, required=["query"]),
    )

    tools["read_specific_doc"] = CustomTool(
        execute=_handle_read_specific_doc,
        description="读取指定文档的全文内容。需先通过 search_docs_catalog 获取 doc_id。只读。",
        input_schema=_obj({"doc_id": _str_param("文档 ID（从 search_docs_catalog 返回结果获取）")}),
    )

    # ── 写操作工具（经审计闸门）─────────────────────────
    # ask 模式不注入写工具

    if mode != "ask":
        tools["jira_create_subtasks"] = CustomTool(
            execute=_make_write_handler("jira_bulk_create", conversation_id=conversation_id, user_id=user_id),
            description=(
                "在 Jira 中批量创建子任务。所有写操作需经审计闸门审批，"
                "不会直接调用 Jira API。参数 summaries 为子任务标题数组，"
                "可提供 project_key 和 issue_type。"
            ),
            input_schema=_obj({
                "summaries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "子任务标题数组",
                },
                "project_key": _str_param("Jira 项目 Key（如 CT、GM）"),
                "issue_type": _str_param("Issue 类型，默认 Task"),
                "parent_key": _str_param("父 Issue Key（子任务必填，如 CT-11152）"),
            }, required=["summaries"]),
        )

        tools["jira_update_status"] = CustomTool(
            execute=_make_write_handler("jira_transition", conversation_id=conversation_id, user_id=user_id),
            description="更新指定 Jira Issue 的状态。需经审计闸门审批。",
            input_schema=_obj({
                "issue_key": _str_param("Jira Issue Key，如 CT-11112"),
                "target_status": _str_param("目标状态名称"),
            }),
        )

        tools["jira_add_comment"] = CustomTool(
            execute=_make_write_handler("jira_add_comment", conversation_id=conversation_id, user_id=user_id),
            description="在指定 Jira Issue 中添加评论。需经审计闸门审批。",
            input_schema=_obj({
                "issue_key": _str_param("Jira Issue Key，如 CT-11112"),
                "body": _str_param("评论内容"),
            }),
        )

    return tools


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

def iter_cursor_sdk_lane(
    user_text: str,
    user_cfg: dict,
    frontend_cfg: dict,
    conversation_id: str = "",
) -> Iterator[bytes]:
    """
    Cursor SDK 道 —— 通用复杂执行引擎入口。

    从 chat_orchestrator 预检链末尾调用，仅在 engine 参数以 "cursor-" 开头时分流。
    engine 值约定: cursor-plan / cursor-agent / cursor-ask（模式标签→前端显示用，SDK 全走 agent 模式）。
    """
    if not user_text:
        yield _sse_error("user_text 为空")
        yield SSE_DONE
        return

    # ── 解析 engine 参数 ──────────────────────────────────
    engine = (user_cfg.get("engine") or "").strip()
    if not engine.startswith("cursor-"):
        yield _sse_error("engine 参数非 cursor- 前缀，应走 ReAct")
        yield SSE_DONE
        return

    cursor_mode = engine[len("cursor-"):]  # plan / agent / ask
    logger.info("[CursorLane] engine=%s mode=%s", engine, cursor_mode)

    # ── 取 SDK 配置 ───────────────────────────────────────
    api_key = (
        (frontend_cfg or {}).get("cursor_api_key")
        or user_cfg.get("cursor_api_key")
        or os.environ.get("CURSOR_API_KEY", "")
    ).strip()
    model = (
        (frontend_cfg or {}).get("cursor_sdk_model")
        or user_cfg.get("cursor_sdk_model")
        or os.environ.get("CURSOR_SDK_MODEL", "composer-2.5")
    ).strip()

    if not api_key:
        yield _sse_error(
            "Cursor SDK 未配置 API Key。"
            "请在客户端 ⚙ 配置中填入 CURSOR_API_KEY，或设置环境变量 CURSOR_API_KEY。"
        )
        yield SSE_DONE
        return

    # ── 取 workspace ───────────────────────────────────────
    try:
        from workspace_manager import list_workspaces
        workspaces = list_workspaces()
        if not workspaces:
            yield _sse_error(
                "未找到已授权的工作区。请先在 Admin 后台授权至少一个工作区目录。"
            )
            yield SSE_DONE
            return
        workspace_cwd = workspaces[0].get("root_path") or os.getcwd()
    except ImportError:
        workspace_cwd = os.getcwd()
        logger.warning("[CursorLane] workspace_manager 不可用，fallback 到 cwd")

    # ── 取 user_id ────────────────────────────────────────
    user_id = (
        (user_cfg or {}).get("user_id")
        or (frontend_cfg or {}).get("user_id")
        or ""
    )

    # ── 构建自定义工具 ─────────────────────────────────────
    custom_tools = _build_custom_tools(
        conversation_id=conversation_id,
        user_id=user_id,
        mode=cursor_mode,
    )
    logger.info("[CursorLane] registered %d custom tools: %s", len(custom_tools), list(custom_tools.keys()))

    # ── 模式专用 system prompt ─────────────────────────────
    MODE_PROMPTS: dict[str, str] = {
        "ask": (
            "你是只读问答模式，仅能使用只读工具查询信息。"
            "不得调用任何写操作工具（jira_create_subtasks / jira_update_status / jira_add_comment）。"
            "直接回答用户问题，不生成计划、不创建 Issue、不修改状态。"
        ),
        "plan": (
            "你先分析用户意图，生成一个执行计划（步骤清单），不要直接执行写操作。"
            "在回复中输出「📋 执行计划」标题 + 编号步骤列表（每条一行，格式：1. 步骤描述）。"
            "在用户回复'开始执行'或'执行计划'或'确认执行'之前，不得调用 jira_create_subtasks / jira_update_status / jira_add_comment。"
            "用户确认后，逐步骤调用对应工具完成执行。"
        ),
    }
    mode_sys = MODE_PROMPTS.get(cursor_mode, "")

    # ── Agent.create + send ────────────────────────────────
    mode_label = {"plan": "📋 规划模式", "agent": "🔬 分析模式", "ask": "💬 问答模式"}.get(cursor_mode, f"cursor-{cursor_mode}")
    yield _sse_content(f"【Cursor {mode_label}】正在启动分析引擎…\n\n")

    try:
        with Agent.create(
            model=model,
            api_key=api_key,
            local=LocalAgentOptions(cwd=workspace_cwd, custom_tools=custom_tools),
        ) as agent:
            prefixed = (
                "[系统指令] 你是 Alice 研发助手。"
                + (f"\n{mode_sys}\n" if mode_sys else "")
                + "\n当用户要求创建/修改 Jira Issue 时，必须调用 jira_create_subtasks 等工具。"
                "禁止说「我无法操作 Jira」——工具已提供给你。"
                "禁止编造操作 ID 或虚构执行结果。"
                "创建 Jira Issue 前，若不确定 issuetype 名称是否合法，先调用 list_jira_issuetypes 查询。\n---\n"
                + user_text
            )
            run = agent.send(prefixed)
            text = (run.text() or "").strip()
            logger.info("[CursorLane] agent=%s run complete, text_len=%d", agent.agent_id, len(text))

            # ── 工具调用校验 ─────────────────────────────────
            tool_calls = []
            try:
                for msg in (run.messages() or []):
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        tool_calls.append(msg.tool_calls)
            except Exception:
                pass

            logger.info("[CursorLane] tool_calls: %s", tool_calls)

            # 〃 注释：tool_calls 检查因 SDK API 兼容性问题目前不可靠，已禁用伪阳性提示
            # jira_keywords = ['创建', '新建', '修改', '添加', '删除', 'jira', 'issue', '任务', '子任务', 'create', 'transition']
            # wants_write = any(kw in (user_text or '').lower() for kw in jira_keywords)
            # if wants_write and not tool_calls and text:
            #     text += "\n\n⚠️ 未检测到工具调用。已记录的回复可能未真正执行操作。请重新描述你的需求。"

            if text:
                for chunk in _sse_text_chunks(text, source="cursor"):
                    yield chunk
            else:
                yield _sse_content("（Cursor SDK 返回空内容，已回退）", source="cursor")
    except CursorAgentError as err:
        logger.error("[CursorLane] CursorAgentError: %s (retryable=%s)", err.message, err.is_retryable)
        yield _sse_error(f"Cursor SDK 启动失败：{err.message[:300]}")
    except Exception as exc:
        logger.error("[CursorLane] unexpected error: %s", exc)
        yield _sse_error(f"Cursor SDK 执行异常：{str(exc)[:300]}")
    finally:
        yield SSE_DONE


# ═══════════════════════════════════════════════════════════════
#  SSE 辅助
# ═══════════════════════════════════════════════════════════════

def _sse_content(text: str, *, source: str = "cursor") -> bytes:
    payload = json.dumps({
        "choices": [{"delta": {"content": text}}],
        "source": source,
    }, ensure_ascii=False)
    return f"data: {payload}\n\n".encode("utf-8")


def _sse_error(text: str) -> bytes:
    return _sse_content(f"❌ {text}")


def _sse_text_chunks(text: str, *, source: str = "cursor", chunk_size: int = 200) -> Iterator[bytes]:
    """将文本按字符边界切分为流式 SSE chunk，模拟打字效果。"""
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        yield _sse_content(chunk, source=source)
