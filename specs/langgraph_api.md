# LangGraph Agent API · Alice v3.0 集成参考

> 来源：`alice/specs/langgraph/`（完整仓库克隆自 https://github.com/langchain-ai/langgraph）
> 版本：LangGraph v1.2.4 · LangChain Core v1.4.0+ · Python ≥ 3.10
> 用途：杰尼龟编写 `agent_graph.py`——Alice 的 AI 编排层。
>       所有 API 签名均提取自仓库中的真实源码和示例文件。

---

## 零、安装与导入（来自仓库 pyproject.toml）

```bash
pip install langgraph langchain-core langchain-openai langgraph-checkpoint
```

```python
# === 来自仓库 libs/cli/examples/graphs/agent.py（官方示例） ===
from collections.abc import Sequence
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph, add_messages
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
```

---

## 一、StateGraph 构建（来自 `agent.py` 完整示例）

### 1.1 定义 State

```python
class AgentState(TypedDict):
    """消息列表使用 add_messages reducer 实现追加而非覆盖。"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

**关键规则：**
- State 必须是 `TypedDict`
- 消息列表用 `Annotated[Sequence[BaseMessage], add_messages]`（不是 `list`）
- 自定义字段不加 Annotated 则默认覆盖（写时覆盖，读时取最新值）

### 1.2 创建 Graph（来自 `agent.py` L57-96）

```python
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("agent", call_model)    # LLM 推理
workflow.add_node("action", tool_node)    # 工具执行

# 设置入口
workflow.set_entry_point("agent")

# 条件边：agent 输出含 tool_calls → action，否则 → END
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "action",
        "end": END,
    },
)

# 普通边：工具执行后回到 agent
workflow.add_edge("action", "agent")

# 编译
graph = workflow.compile()
```

### 1.3 should_continue（来自 `agent.py` L29-38）

```python
def should_continue(state: AgentState) -> Literal["continue", "end"]:
    last_message = state["messages"][-1]
    # 注意：不是 hasattr，直接检查 tool_calls 是否为真值
    if not last_message.tool_calls:
        return "end"
    return "continue"
```

---

## 二、HITL 人机回环（来自仓库 tests/test_pregel_async.py L5594-5680）

### 2.1 编译时设置中断点

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()

# interrupt_before=["action"]  → Agent 推理完成、准备执行工具前自动暂停
graph = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["action"],
)
```

### 2.2 中断→恢复流程（来自 tests/test_pregel_async.py L2923-3020）

```python
config = {"configurable": {"thread_id": "user-session-123"}}

# === 第一段：推理到工具前自动中断 ===
result = await graph.ainvoke(
    {"messages": [HumanMessage(content="帮我创建 3 个 Jira")]},
    config,
)
# result["messages"][-1] 是 AIMessage，含 tool_calls 草稿
# 此时 graph 已暂停，工具尚未执行

# === 提取草稿，推送 ConfirmCard 给前端 ===
last_msg = result["messages"][-1]
draft = last_msg.tool_calls  # 草稿数据

# === 第二段：用户确认后恢复执行 ===
await graph.ainvoke(None, config)
# 继续执行 tool_node，实际调用创建 Jira 的工具
```

### 2.3 状态检查（来自 tests L2963-2988）

```python
# 查看当前状态（不执行任何节点）
state = await graph.aget_state(config)
# state.values → 当前 State 内容
# state.next → 下一个待执行节点（如 ("action",)）

# 更新状态（外部注入确认结果）
await graph.aupdate_state(config, {"confirm_result": "approved"})
```

---

## 三、工具定义（来自 `agent.py` L11-18）

```python
from langgraph.prebuilt import ToolNode

# 定义工具函数（@tool 装饰器）
from langchain_core.tools import tool

@tool
def search_knowledge_base(query: str) -> str:
    """搜索 Alice 知识库。"""
    # 实际调 Dify RAG API：POST /datasets/{id}/retrieve
    ...

@tool
def create_jira_draft(summary: str, project: str, issue_type: str) -> str:
    """生成 Jira 创建草稿（不直接执行）。"""
    return f"DRAFT: {summary} @ {project} [{issue_type}]"

tools = [search_knowledge_base, create_jira_draft]

# LLM 绑定工具
from langchain_openai import ChatOpenAI
model = ChatOpenAI(model="deepseek-chat").bind_tools(tools)

# 工具执行节点
tool_node = ToolNode(tools)
```

---

## 四、节点函数（来自 `agent.py` L41-50）

```python
def call_model(state: AgentState) -> dict:
    """调用 LLM，返回 AI 消息。"""
    messages = state["messages"]
    response = model.invoke(messages)
    # 返回值是 dict，会被 add_messages reducer 追加到 messages 列表
    return {"messages": [response]}
```

---

## 五、流式输出（来自仓库 SDK astream 方法）

```python
# stream_mode="updates" — 每节点完成时推送增量（Alice SSE 推荐）
async for chunk in graph.astream(
    {"messages": [HumanMessage(content="查一下 CT 项目 bug")]},
    config,
    stream_mode="updates",
):
    node_name = list(chunk.keys())[0]
    node_output = chunk[node_name]
    # Hub 将 node_name/node_output 封装为 SSE 事件推给前端
```

| stream_mode | 粒度 | Alice 用途 |
|-------------|------|-----------|
| `"values"` | 每步推送完整 State | 前端显示完整对话历史 |
| `"updates"` | 每节点完成后推送增量 | 显示"检索中…"→"分析中…" |
| `"messages"` | 逐 token 推送 LLM 输出 | 打字机效果 |

---

## 六、agent_graph.py 完整模板（基于仓库示例）

```python
"""agent_graph.py — Alice AI 编排层（LangGraph StateGraph）"""
from collections.abc import Sequence
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph, add_messages
from langgraph.prebuilt import ToolNode


# ============ 1. State ============
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    draft: dict | None
    confirm_result: str | None


# ============ 2. 工具 ============
@tool
def search_kb(query: str) -> str:
    """搜索 Alice 知识库。调 Dify RAG API：POST /datasets/{id}/retrieve"""
    pass

@tool
def create_jira(summary: str, project_key: str, issue_type: str) -> str:
    """生成 Jira 创建草稿。"""
    return f"DRAFT:{summary}|{project_key}|{issue_type}"

tools = [search_kb, create_jira]
model = ChatOpenAI(model="deepseek-chat").bind_tools(tools)
tool_node = ToolNode(tools)


# ============ 3. 节点 ============
def agent_node(state: AgentState) -> dict:
    response = model.invoke(state["messages"])
    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["continue", "end"]:
    last = state["messages"][-1]
    return "continue" if last.tool_calls else "end"


# ============ 4. Graph ============
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("action", tool_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "continue": "action",
    "end": END,
})
workflow.add_edge("action", "agent")

graph = workflow.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["action"],  # ← HITL 中断：工具执行前暂停
)
```

---

## 七、硬约束：禁止编造的 API 对照表

> 以下对照表基于 LangGraph v1.2.4 真实源码。

| ❌ 错误（杰尼龟可能乱写） | ✅ 正确（仓库真实用法） |
|---|---|
| `from langgraph.graph.message import add_messages` | `from langgraph.graph import add_messages` |
| `Annotated[list, add_messages]` | `Annotated[Sequence[BaseMessage], add_messages]` |
| `hasattr(last_message, "tool_calls")` | `last_message.tool_calls`（直接真值判断） |
| `graph.invoke(None)` 同步恢复 | `await graph.ainvoke(None, config)`（异步，复用 config） |
| ~~`interrupt_before=["agent"]`~~ | `interrupt_before=["action"]`（HITL 在工具执行前中断） |
| State 用 `dataclass` | State 必须是 `TypedDict` |
| `add_node()` 返回新 graph | `add_node()` 返回 `None`（原地修改 builder） |

---

## 八、仓库路径索引

> 所有路径相对于 `alice/specs/langgraph/`

| 内容 | 路径 |
|------|------|
| 官方 StateGraph Agent 示例 | `libs/cli/examples/graphs/agent.py` |
| 多节点复杂 Agent 示例 | `libs/cli/examples/graphs/storm.py` |
| HITL interrupt 测试 | `libs/langgraph/tests/test_pregel_async.py` (L2923-3020, L5594-5680) |
| ToolNode 完整源码 | `libs/prebuilt/langgraph/prebuilt/tool_node.py` |
| 流式 astream 实现 | `libs/langgraph/langgraph/pregel/remote.py` |
| pyproject.toml（依赖） | `libs/langgraph/pyproject.toml` |

## 九、外部参考

| 资源 | URL |
|------|-----|
| LangGraph GitHub | https://github.com/langchain-ai/langgraph |
| LangGraph 官方文档 | https://docs.langchain.com/oss/python/langgraph/overview |
| HITL 中断指南 | https://docs.langchain.com/oss/python/langgraph/interrupts |
| 流式输出指南 | https://docs.langchain.com/oss/python/langgraph/streaming |
