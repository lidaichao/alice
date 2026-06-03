"""
backend/agent/state.py — V2.0 Plan-and-Execute Agent State
"""
from typing import TypedDict, Annotated, List
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Plan-and-Execute 智能体状态"""
    # 对话历史 (自动合并消息)
    messages: Annotated[list, add_messages]

    # 当前步骤规划: ["1. 查询 CT-10888 状态", "2. 获取 SVN 提交", "3. 汇总分析"]
    plan: List[str]

    # 已执行的工具记录: [{"step": 1, "tool": "query_jira_metadata", "result": "..."}]
    past_steps: List[dict]

    # 最终回答 (流式输出)
    final_answer: str
