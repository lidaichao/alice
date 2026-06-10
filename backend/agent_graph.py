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

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver
from loguru import logger


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
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", _config.get("DEEPSEEK_MODEL", "deepseek-chat"))

# Dify RAG 配置（供工具节点使用）
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", _config.get("DIFY_BASE_URL", "http://localhost:5001"))
DIFY_API_KEY = os.getenv("DIFY_API_KEY", _config.get("DIFY_API_KEY", ""))
DIFY_DATASET_ID = os.getenv("DIFY_DATASET_ID", _config.get("DIFY_DATASET_ID", ""))

# n8n 配置（Phase 2 占位）
N8N_BASE_URL = os.getenv("N8N_BASE_URL", _config.get("N8N_BASE_URL", "http://localhost:5678"))
N8N_API_KEY = os.getenv("N8N_API_KEY", _config.get("N8N_API_KEY", ""))
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", _config.get("N8N_WEBHOOK_URL", ""))


# ═══════════════════════════════════════════════════════════════
# 1. State 定义（约束#1：TypedDict + add_messages）
# ═══════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    """LangGraph Agent 状态：消息 + 草稿 + 确认 + 追踪 ID"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    draft: dict | None
    confirm_result: str | None
    trace_id: str


# ═══════════════════════════════════════════════════════════════
# 2. 工具定义（Phase 1.2：Agent 工具节点）
# ═══════════════════════════════════════════════════════════════

@tool
def dify_rag_retrieval(query: str, trace_id: str = "unknown") -> str:
    """搜索 Alice 知识库。调用 Dify RAG API：POST /datasets/{id}/retrieve"""
    import httpx
    if not DIFY_API_KEY or not DIFY_DATASET_ID:
        logger.warning(f"[{trace_id}] Dify RAG 未配置（DIFY_API_KEY/DIFY_DATASET_ID 为空），返回空结果")
        return "知识库未配置，请联系管理员。"

    url = f"{DIFY_BASE_URL}/v1/datasets/{DIFY_DATASET_ID}/retrieve"
    logger.info(f"[{trace_id}] 调用 Dify RAG 检索: query={query[:80]}...")
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {DIFY_API_KEY}"},
            json={
                "query": query,
                "retrieval_model": {
                    "search_method": "hybrid_search",
                    "reranking_enable": True,
                    "top_k": 5,
                },
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.error(f"[{trace_id}] Dify RAG 检索失败: HTTP {resp.status_code} {resp.text[:200]}")
            return f"[知识库检索失败: HTTP {resp.status_code}]"
        logger.info(f"[{trace_id}] Dify RAG 检索耗时 {resp.elapsed.total_seconds():.1f}s")
        data = resp.json()
        records = data.get("records", [])
        if not records:
            return "未找到相关知识库内容。"
        snippets = []
        for i, rec in enumerate(records[:3]):
            seg = rec.get("segment", {})
            content = seg.get("content", "")
            score = rec.get("score", 0)
            snippets.append(f"[片段{i+1}·得分{score:.2f}] {content}")
        return "\n\n".join(snippets)
    except Exception as e:
        logger.error(f"[{trace_id}] Dify RAG 检索异常: {e}")
        return f"[知识库服务暂时不可用，请稍后重试]"


@tool
def n8n_jira_query(jql: str, trace_id: str = "unknown") -> str:
    """通过 n8n Webhook 查询 Jira 任务。Phase 2 实现，当前为占位。"""
    logger.info(f"[{trace_id}] n8n Jira 查询（占位）: jql={jql[:80]}")
    return "[Jira 查询功能待 Phase 2 实现]"


@tool
def svn_query(path: str, trace_id: str = "unknown") -> str:
    """查询 SVN 代码仓库。Phase 2 实现，当前为占位。"""
    logger.info(f"[{trace_id}] SVN 查询（占位）: path={path[:80]}")
    return "[SVN 查询功能待 Phase 2 实现]"


# 工具列表
tools = [dify_rag_retrieval, n8n_jira_query, svn_query]


# ═══════════════════════════════════════════════════════════════
# 3. LLM 初始化（绑定工具）
# ═══════════════════════════════════════════════════════════════

def _create_llm():
    """创建 ChatOpenAI 实例，绑定 Alice 工具"""
    if not DEEPSEEK_KEY:
        logger.warning("DEEPSEEK_KEY 未配置，Agent 将无法调用 LLM")
    base_url = DEEPSEEK_URL.rstrip("/") if DEEPSEEK_URL.endswith("/chat/completions") else DEEPSEEK_URL
    if not base_url.endswith("/v1"):
        base_url = DEEPSEEK_URL
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_KEY,
        base_url=base_url,
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.invoke, messages)
        try:
            response = future.result(timeout=60)
            logger.info(f"[{trace_id}] Agent 推理完成，输出 {len(str(response))} 字符")
            return {"messages": [response]}
        except concurrent.futures.TimeoutError:
            logger.error(f"[{trace_id}] LLM 响应超时 >60s")
            raise TimeoutError("LLM 响应超时（>60s），请稍后重试")


def should_continue(state: AgentState) -> Literal["continue", "end"]:
    """条件边：agent 输出含 tool_calls → action，否则 → END（约束#1）"""
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    if last_message and hasattr(last_message, "tool_calls") and last_message.tool_calls:
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

    # SqliteSaver 持久化 Checkpointer（§2.5.2）
    if checkpointer is None:
        conn = sqlite3.connect("alice_agent.db", check_same_thread=False)
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
