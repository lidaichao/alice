"""
backend/agent/graph.py — V2.0 Plan-and-Execute 图状智能体
拓扑: Planner → [plan非空→Executor, plan空→Synthesizer]
       Executor → Planner (循环直到 plan 空)
       Synthesizer → END
"""
from langgraph.graph import StateGraph, END
from backend.agent.state import AgentState
from backend.agent.nodes import planner_node, executor_node, synthesizer_node


def should_execute(state: AgentState) -> str:
    """条件边: 有计划 → 执行, 无计划 → 合成"""
    plan = state.get("plan", [])
    if plan:
        return "executor"
    return "synthesizer"


def build_graph() -> StateGraph:
    """构建 V2.0 Plan-and-Execute 图"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("synthesizer", synthesizer_node)

    # 入口
    workflow.set_entry_point("planner")

    # 边
    workflow.add_conditional_edges("planner", should_execute, {
        "executor": "executor",
        "synthesizer": "synthesizer",
    })

    workflow.add_edge("executor", "planner")  # 执行后回到 planner 检查
    workflow.add_edge("synthesizer", END)

    return workflow


# 全局编译实例
graph = build_graph().compile()
