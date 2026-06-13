"""
agent_graph.py — Alice AI 编排层（LangGraph StateGraph）
v3.0 Phase 1：Agent Loop、意图路由、工具选择、草稿生成
参考：specs/langgraph_api.md（基于 LangGraph v1.2.4 真实源码）
约束：§八 #1 StateGraph 强制、#10 幂等 Key、#11 LLM Timeout 60s
"""

import json
import os
import uuid
import sqlite3
import concurrent.futures
from collections.abc import Sequence
from typing import Annotated, Literal, TypedDict

import requests
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver
from loguru import logger

from svn_proxy import svn_log
from jira_api import JiraClient


# ═══════════════════════════════════════════════════════════════
# 配置：从 global_config.json 读取 LLM 配置
# ═══════════════════════════════════════════════════════════════

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "global_config.json")


def _load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


_config = _load_config()
DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", _config.get("DEEPSEEK_URL", "https://api.deepseek.com/v1"))
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY", _config.get("DEEPSEEK_KEY", ""))
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", _config.get("DEEPSEEK_MODEL", "composer-2.5"))

# 确保 base_url 是纯 /v1 根路径（处理 global_config.json 中误带 /chat/completions 后缀的情况）
_DEEPSEEK_BASE = DEEPSEEK_URL.removesuffix("/chat/completions").rstrip("/")

# Dify RAG 配置（供工具节点使用）
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", _config.get("DIFY_BASE_URL", "http://localhost:5001"))
DIFY_API_KEY = os.getenv("DIFY_API_KEY", _config.get("DIFY_API_KEY", ""))
DIFY_DATASET_ID = os.getenv("DIFY_DATASET_ID", _config.get("DIFY_DATASET_ID", ""))
DIFY_DATASET_API_KEY = os.getenv("DIFY_DATASET_API_KEY", _config.get("DIFY_DATASET_API_KEY", ""))


def _agent_dify_key() -> str:
    """Agent 工具节点 Dify Key（v3.1 双模：dataset-* 优先 → app-* 降级）"""
    return DIFY_DATASET_API_KEY or DIFY_API_KEY

# n8n 配置
N8N_BASE_URL = os.getenv("N8N_BASE_URL", _config.get("N8N_BASE_URL", "http://localhost:5678"))
N8N_API_KEY = os.getenv("N8N_API_KEY", _config.get("N8N_API_KEY", ""))
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_BASE_URL", N8N_BASE_URL)


# ═══════════════════════════════════════════════════════════════
# 1. State 定义（约束#1：TypedDict + add_messages）
# ═══════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    """LangGraph Agent 状态：消息 + 草稿 + 确认 + 追踪 ID + KB 来源"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    draft: dict | None
    confirm_result: str | None
    trace_id: str
    kb_sources: list[dict] | None


# ═══════════════════════════════════════════════════════════════
# n8n Webhook 调用器（Phase 2.4 · 约束#6 超时+中文翻译）
#   Webhook 节点默认不要求认证头；X-N8N-API-KEY 仅用于 REST API。
# ═══════════════════════════════════════════════════════════════

_N8N_WEBHOOK_BASE = N8N_WEBHOOK_URL  # 复用顶层配置


def n8n_webhook_call(workflow_path: str, payload: dict, timeout: int = 3) -> dict:
    """
    调用 n8n Webhook 工作流，含超时 + 中文错误翻译。
    
    返回 dict: {"ok": True/False, "data": ... / "error": "中文错误信息"}
    """
    url = f"{_N8N_WEBHOOK_BASE}/webhook/{workflow_path}"
    trace_id = payload.get("trace_id", "unknown")
    logger.info(f"[{trace_id}] n8n Webhook 调用: {workflow_path}")
    try:
        # H7: Webhook 节点默认无认证，去掉 X-N8N-API-KEY（仅用于 REST API）
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"[{trace_id}] n8n Webhook 完成: {workflow_path} {resp.elapsed.total_seconds():.1f}s")
            return {"ok": True, "data": data}
        else:
            logger.error(f"[{trace_id}] n8n Webhook 失败: HTTP {resp.status_code} {resp.text[:200]}")
            error_msg = "外部服务异常，请联系管理员"
            if resp.status_code == 403:
                error_msg = "您没有该项目的创建权限"
            elif resp.status_code == 404:
                error_msg = "项目不存在，请检查项目 Key"
            return {"ok": False, "error": error_msg, "status_code": resp.status_code}
    except requests.exceptions.Timeout:
        logger.error(f"[{trace_id}] n8n Webhook 超时 >{timeout}s: {workflow_path}")
        return {"ok": False, "error": "创建超时 n8n 暂不可用 请稍后重试", "error_code": "N8N_TIMEOUT"}
    except requests.exceptions.ConnectionError:
        logger.error(f"[{trace_id}] n8n Webhook 连接失败: {workflow_path}")
        return {"ok": False, "error": "无法连接到 n8n 服务，请确认 n8n 已启动", "error_code": "N8N_UNREACHABLE"}
    except Exception as e:
        logger.error(f"[{trace_id}] n8n Webhook 异常: {e}")
        return {"ok": False, "error": "外部服务异常，请联系管理员"}


# ═══════════════════════════════════════════════════════════════
# 1.5 Jira 客户端（复用 jira_api.JiraClient，读 global_config）
# ═══════════════════════════════════════════════════════════════

_jira_client: JiraClient | None = None

def get_jira_client() -> JiraClient:
    global _jira_client
    if _jira_client is None:
        _jira_client = JiraClient(
            base_url=_config.get("jira_url", "http://ctjira1.lmdgame.com:8080"),
            email=os.getenv("JIRA_USERNAME", "admin"),
            password=os.getenv("JIRA_PASSWORD", ""),
            pat_token=_config.get("jira_pat") or None,
        )
    return _jira_client


# ═══════════════════════════════════════════════════════════════
# 2. 工具定义（Phase 1.2：Agent 工具节点）
# ═══════════════════════════════════════════════════════════════

@tool
def dify_rag_retrieval(query: str, trace_id: str = "unknown") -> str:
    """搜索 Alice 知识库。调用 Dify RAG API：POST /datasets/{id}/retrieve"""
    import httpx
    key = _agent_dify_key()
    if not key or not DIFY_DATASET_ID:
        logger.warning(f"[{trace_id}] Dify RAG 未配置（Key/DATASET_ID 为空），返回空结果")
        return "知识库未配置，请联系管理员。"

    url = f"{DIFY_BASE_URL}/v1/datasets/{DIFY_DATASET_ID}/retrieve"
    logger.info(f"[{trace_id}] 调用 Dify RAG 检索: query={query[:80]}...")
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "query": query,
                "retrieval_model": {
                    "search_method": "keyword_search",
                    "reranking_enable": False,
                    "top_k": 5,
                    "score_threshold_enabled": False,
                    "score_threshold": 0.0,
                },
            },
            timeout=10.0,
        )
        if resp.status_code == 401:
            _hint = "（Agent 工具节点 RAG 需 dataset-* 开头的 Key，当前仅 app-* Key）" if not DIFY_DATASET_API_KEY else ""
            logger.error(f"[{trace_id}] Dify RAG 401: Key 权限不足{_hint}")
            return "知识库 Key 权限不足（RAG 需 dataset-* 开头的 Key），请联系管理员配置 DIFY_DATASET_API_KEY。"
        if resp.status_code != 200:
            logger.error(f"[{trace_id}] Dify RAG 检索失败: HTTP {resp.status_code} {resp.text[:200]}")
            return f"[知识库检索失败: HTTP {resp.status_code}]"
        logger.info(f"[{trace_id}] Dify RAG 检索耗时 {resp.elapsed.total_seconds():.1f}s")
        data = resp.json()
        records = data.get("records", [])
        if not records:
            _last_kb_sources.clear()
            return "未找到相关知识库内容。"
        snippets = []
        sources = []
        for i, rec in enumerate(records[:3]):
            seg = rec.get("segment", {})
            content = seg.get("content", "")
            score = rec.get("score", 0)
            snippets.append(f"[片段{i+1}·得分{score:.2f}] {content}")
            doc = seg.get("document", {}) or {}
            src_name = doc.get("name", "")
            src_updated = doc.get("updated_at", "") or doc.get("updated", "")
            if src_name:
                sources.append({"source": src_name, "updated": src_updated, "chunk": f"L{i+1}"})
        _last_kb_sources[:] = sources
        logger.info(f"[{trace_id}] KB 来源 {len(sources)} 条已暂存: {[s['source'] for s in sources]}")
        return "\n\n".join(snippets)
    except Exception as e:
        logger.error(f"[{trace_id}] Dify RAG 检索异常: {e}")
        return f"[知识库服务暂时不可用，请稍后重试]"


@tool
def n8n_jira_query(jql: str, trace_id: str = "unknown") -> str:
    """通过 n8n Webhook 查询 Jira 任务。JQL 从 Agent 推理生成。"""
    logger.info(f"[{trace_id}] n8n Jira 查询: jql={jql[:80]}")
    result = n8n_webhook_call("alice-jira-search", {"jql": jql, "trace_id": trace_id}, timeout=3)
    if not result.get("ok"):
        return f"[Jira 查询失败: {result.get('error', '未知错误')}]"
    data = result.get("data", {})
    issues = data.get("issues", [])
    if not issues:
        return "未找到匹配的 Jira 任务。"
    lines = [f"共找到 {len(issues)} 条 Jira 任务："]
    for issue in issues[:10]:
        key = issue.get("key", "?")
        summary = issue.get("summary", "")[:80]
        status = issue.get("status", "?")
        lines.append(f"- {key} [{status}] {summary}")
    return "\n".join(lines)


@tool
def svn_query(path: str, trace_id: str = "unknown") -> str:
    """查询 SVN 代码仓库日志。路径必须先通过 workspace_manager 白名单校验。"""
    logger.info(f"[{trace_id}] SVN 查询: path={path[:80]}")
    entries = svn_log(path, limit=10, trace_id=trace_id)
    if not entries:
        return f"[SVN 查询无结果: 路径未授权或查询失败] path={path[:80]}"
    lines = [f"SVN 最近 {len(entries)} 条提交："]
    for entry in entries:
        lines.append(f"- {entry['revision']} {entry['author']} {entry['date']}: {entry['message'][:60]}")
    return "\n".join(lines)


@tool
def jira_create_issue(project_key: str, issue_type: str, summary: str, description: str, trace_id: str = "unknown") -> str:
    """在 Jira 中创建 Issue。project_key 必须是已存在的项目 Key（如 AL、CT），issue_type 必须是有效类型（如 任务、缺陷），summary 为标题，description 为描述。"""
    logger.info(f"[{trace_id}] Jira 创建 Issue: project={project_key} type={issue_type} summary={summary[:60]}")
    import uuid, re as _re2
    raw_id = str(uuid.uuid4())
    idempotency_key = f"alice-tx-{_re2.sub(r'[^a-zA-Z0-9\-]', '', raw_id)}"
    try:
        jira = get_jira_client()
        draft = {
            "projectKey": project_key,
            "summary": summary,
            "issueType": issue_type,
            "description": description,
            "labels": [idempotency_key],
        }
        created = jira.create_issue_from_draft(draft, default_issue_type="任务")
        issue_key = created.get("key", "?")
        logger.info(f"[{trace_id}] Jira 创建完成: {issue_key}")
        return f"Jira Issue 已创建成功: {issue_key}"
    except ValueError as e:
        logger.error(f"[{trace_id}] Jira 创建参数错误: {e}")
        return f"[Jira 创建失败: {e}]"
    except Exception as e:
        logger.error(f"[{trace_id}] Jira 创建异常: {e}")
        return f"[Jira 创建失败: {str(e)[:200]}]"


# 工具列表
tools = [dify_rag_retrieval, n8n_jira_query, svn_query, jira_create_issue]

# v3.1 波次2: 模块级 KB 来源暂存（供 ai_bridge SSE 透传）
_last_kb_sources: list[dict] = []


# ═══════════════════════════════════════════════════════════════
# 3. LLM 初始化（绑定工具）
# ═══════════════════════════════════════════════════════════════

def _create_llm():
    """创建 ChatOpenAI 实例，绑定 Alice 工具"""
    if not DEEPSEEK_KEY:
        logger.warning("DEEPSEEK_KEY 未配置，Agent 将无法调用 LLM")
    # v3.1 w3: 使用预处理过的 _DEEPSEEK_BASE（已去掉 /chat/completions 后缀）
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_KEY,
        base_url=_DEEPSEEK_BASE,
        temperature=0.0,
    ).bind_tools(tools)


llm = _create_llm()
tool_node = ToolNode(tools)


# ═══════════════════════════════════════════════════════════════
# 4. 节点函数
# ═══════════════════════════════════════════════════════════════

def agent_node(state: AgentState) -> dict:
    """Agent 推理节点：LLM 调用（含 Hard Timeout 60s，约束#11）"""
    trace_id = state.get("trace_id", "unknown")
    messages = state["messages"]
    logger.info(f"[{trace_id}] Agent 节点开始推理，消息数={len(messages)}")

    # C1: 显式 executor 管理——超时时 cancel_futures 防止僵尸线程堆积
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(llm.invoke, messages)
        response = future.result(timeout=60)
        logger.info(f"[{trace_id}] Agent 推理完成，输出 {len(str(response))} 字符")

        # v3.1 波次2: 透传 KB 来源到 State
        result: dict = {"messages": [response]}
        if _last_kb_sources:
            result["kb_sources"] = list(_last_kb_sources)
            _last_kb_sources.clear()
        return result
    except concurrent.futures.TimeoutError:
        logger.error(f"[{trace_id}] LLM 响应超时 >60s")
        executor.shutdown(wait=False, cancel_futures=True)
        raise TimeoutError("LLM 响应超时（>60s），请稍后重试")
    finally:
        executor.shutdown(wait=False)


def should_continue(state: AgentState) -> Literal["continue", "end"]:
    """条件边：agent 输出含 tool_calls → action，否则 → END（约束#1）"""
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    if last_message and last_message.tool_calls:
        logger.info(f"[{state.get('trace_id', '?')}] 路由 → 工具执行（{len(last_message.tool_calls)} 个调用）")
        return "continue"
    logger.info(f"[{state.get('trace_id', '?')}] 路由 → END（无需工具调用）")
    return "end"


# ═══════════════════════════════════════════════════════════════
# 5. Graph 构建 + SqliteSaver 持久化（约束#1 + §2.5.2）
# ═══════════════════════════════════════════════════════════════

def build_agent_graph(checkpointer=None):
    """构建 LangGraph Agent 编排图"""
    builder = StateGraph(AgentState)

    # 添加节点
    builder.add_node("agent", agent_node)
    builder.add_node("action", tool_node)

    # 入口
    builder.set_entry_point("agent")

    # 条件边：agent → action（有工具调用）或 END（无工具调用）
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "action",
            "end": END,
        },
    )

    # 工具执行后回到 agent
    builder.add_edge("action", "agent")

    # SqliteSaver 持久化 Checkpointer（§2.5.2 / C2: 显式绝对路径，避免 CWD 漂移）
    if checkpointer is None:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alice_agent.db")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    # HITL 中断：工具执行前暂停（interrupt_before=["action"]）
    graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["action"],
    )
    return graph


# ═══════════════════════════════════════════════════════════════
# 6. 全局 Graph 实例（模块加载时编译一次）
# ═══════════════════════════════════════════════════════════════

graph = build_agent_graph()
