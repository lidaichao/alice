"""
backend/agent/state.py — V2.0 Plan-and-Execute Agent State
"""
from typing import TypedDict, Annotated, List, Sequence
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Plan-and-Execute 智能体状态"""
    # 对话历史 (自动合并消息)
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # 当前步骤规划
    plan: List[str]

    # 规划模式: "doc_only"(仅文档) / "cross_domain"(跨域) / "chat"(闲聊)
    plan_mode: str

    # 已执行的工具记录
    past_steps: List[dict]

    # 最终回答 (流式输出)
    final_answer: str
