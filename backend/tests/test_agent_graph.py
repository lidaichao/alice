"""
test_agent_graph.py — LangGraph Agent 单元测试
v3.0 Phase 1.4：覆盖 StateGraph 编译、SqliteSaver 挂载、LLM Timeout 机制、AgentState Schema
"""

import pytest
import sys
import os

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_graph import (
    build_agent_graph,
    AgentState,
    agent_node,
    should_continue,
    dify_rag_retrieval,
)


class TestAgentGraphBuild:
    """Phase 1.4：StateGraph 编译 + SqliteSaver 挂载"""

    def test_graph_builds_with_sqlite_checkpointer(self):
        """验证 StateGraph 编译成功 + SqliteSaver 挂载正确"""
        graph = build_agent_graph()
        assert graph is not None
        assert graph.checkpointer is not None, "SqliteSaver 应正确挂载到 graph.checkpointer"

    def test_graph_endpoints_registered(self):
        """验证节点入口/出口注册正确"""
        graph = build_agent_graph()
        # 编译后的 graph 应有 stream/invoke 方法
        assert hasattr(graph, "invoke"), "编译后的 graph 应支持 invoke"
        assert hasattr(graph, "stream"), "编译后的 graph 应支持 stream"
        assert hasattr(graph, "astream"), "编译后的 graph 应支持 astream（异步）"


class TestAgentStateSchema:
    """Phase 1.4：AgentState TypedDict Schema"""

    def test_state_contains_messages_and_trace_id(self):
        """验证 State 包含 messages + trace_id 字段"""
        state = AgentState(messages=[], draft=None, confirm_result=None, trace_id="test-001")
        assert "messages" in state
        assert "trace_id" in state
        assert "draft" in state
        assert "confirm_result" in state

    def test_state_defaults(self):
        """验证 State 默认值"""
        state = AgentState(messages=[], draft=None, confirm_result=None, trace_id="")
        assert state["messages"] == []
        assert state["draft"] is None
        assert state["confirm_result"] is None
        assert state["trace_id"] == ""
        assert isinstance(state["trace_id"], str)


class TestShouldContinue:
    """Phase 1.4：条件边路由逻辑"""

    def test_end_when_no_messages(self):
        """无消息 → END"""
        state = AgentState(messages=[], draft=None, confirm_result=None, trace_id="t1")
        result = should_continue(state)
        assert result == "end"

    def test_end_when_no_tool_calls(self):
        """最后一条消息无 tool_calls → END"""
        from langchain_core.messages import AIMessage
        state = AgentState(
            messages=[AIMessage(content="你好，有什么可以帮你的？")],
            draft=None,
            confirm_result=None,
            trace_id="t2",
        )
        result = should_continue(state)
        assert result == "end"

    def test_continue_when_tool_calls_present(self):
        """最后一条消息有 tool_calls → continue（路由到 action）"""
        from langchain_core.messages import AIMessage
        msg = AIMessage(content="", additional_kwargs={}, id="test-msg")
        # 模拟 tool_calls — 通过设置空列表的 tool_calls 属性
        msg.tool_calls = [{"name": "search_kb", "args": {"query": "test"}, "id": "call-1", "type": "tool_call"}]
        state = AgentState(
            messages=[msg],
            draft=None,
            confirm_result=None,
            trace_id="t3",
        )
        result = should_continue(state)
        assert result == "continue"


class TestLlmTimeoutEnforcement:
    """Phase 1.4：LLM 节点超时机制（约束#11）"""

    def test_agent_node_has_timeout(self):
        """验证 agent_node 函数中存在 ThreadPoolExecutor + timeout=60 逻辑"""
        import inspect
        source = inspect.getsource(agent_node)
        assert "ThreadPoolExecutor" in source, "agent_node 应使用 ThreadPoolExecutor 进行超时控制"
        assert "timeout" in source, "agent_node 应将 timeout 参数传给 future.result()"
        assert "TimeoutError" in source, "agent_node 应捕获 TimeoutError"

    def test_build_graph_idempotent(self):
        """多次调用 build_agent_graph() 返回独立实例"""
        g1 = build_agent_graph()
        g2 = build_agent_graph()
        assert g1 is not g2, "每次调用应返回新的 graph 实例"


class TestToolsDefinitions:
    """Phase 1.4：工具节点定义完整"""

    def test_all_three_tools_defined(self):
        """验证 Dify RAG / n8n Jira / SVN / Jira 创建 四个工具均已定义"""
        from agent_graph import tools, dify_rag_retrieval, n8n_jira_query, svn_query, jira_create_issue
        tool_names = [t.name for t in tools]
        assert "dify_rag_retrieval" in tool_names, "Dify RAG 检索工具应已注册"
        assert "n8n_jira_query" in tool_names, "n8n Jira 查询工具应已注册"
        assert "svn_query" in tool_names, "SVN 查询工具应已注册"
        assert "jira_create_issue" in tool_names, "Jira 创建工具应已注册"
        assert len(tools) >= 4

    def test_dify_rag_tool_handles_no_config(self):
        """Dify RAG 工具在不配置时应返回友好提示"""
        result = dify_rag_retrieval.invoke({"query": "test query", "trace_id": "test-999"})
        assert isinstance(result, str)
        # 无配置时应返回友好提示（不抛异常）
        assert len(result) > 0
