"""
backend/agent/nodes.py — V2.0 Plan-and-Execute 核心节点
Planner → Executor → Synthesizer
"""
import os, sys, json, logging
import http.client as http_client

logger = logging.getLogger("agent-v2")

# ── 配置(由外部注入) ──
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
_deepseek_headers = {}
_user_cfg = {}
_http = None
_tools_registry = []
_tool_executors = {}

def init_agent(deepseek_key: str, model: str, tools: list, executors: dict, http_module=None):
    """初始化 V2.0 Agent 全局配置"""
    global _deepseek_headers, _user_cfg, _tools_registry, _tool_executors, _http
    _deepseek_headers = {
        "Authorization": f"Bearer {deepseek_key}",
        "Content-Type": "application/json",
    }
    _user_cfg = {"deepseek_model": model, "deepseek_key": deepseek_key}
    _tools_registry = tools
    _tool_executors = executors
    _http = http_module or http_client


def _call_llm(messages: list, temperature: float = 0.1, max_tokens: int = 800) -> str:
    """调用 DeepSeek, 返回纯文本"""
    resp = _http.request("POST", "/v1/chat/completions",
        body=json.dumps({
            "model": _user_cfg["deepseek_model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode(),
        headers=_deepseek_headers)
    data = json.loads(resp.data.decode())
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def planner_node(state: dict) -> dict:
    """Planner: 分析用户意图 → 生成执行计划"""
    messages = state.get("messages", [])
    past = state.get("past_steps", [])

    user_text = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            user_text = m.get("content", "")
            break

    tool_desc = "\n".join([f"- {t['function']['name']}: {t['function']['description']}"
                           for t in _tools_registry[:5]])

    prompt = f"""你是 Alice V2.0 的 Plan-and-Execute 大脑。

【用户最新请求】: {user_text}
【已执行步骤】: {json.dumps(past, ensure_ascii=False) if past else "无"}

【可用工具】:
{tool_desc}

请生成 JSON 格式的执行计划:
{{
  "plan": ["步骤1", "步骤2", ...],
  "reasoning": "简短推理"
}}

如果用户只是闲聊或打招呼，plan 可以为空数组 []。"""

    try:
        result = _call_llm([
            {"role": "system", "content": "你是精准的执行计划生成器。只输出 JSON。"},
            {"role": "user", "content": prompt},
        ], temperature=0.1, max_tokens=500)

        plan = []
        if "{" in result:
            plan_data = json.loads(result[result.index("{"):].split("```")[0].strip() if "```" in result else result.strip())
            plan = plan_data.get("plan", [])
        logger.info(f"[Planner] Generated plan: {plan}")
        return {"plan": plan}
    except Exception as e:
        logger.error(f"[Planner] Failed: {e}")
        return {"plan": []}


def executor_node(state: dict) -> dict:
    """Executor: 按 plan 逐步调用工具"""
    plan = state.get("plan", [])
    past_steps = list(state.get("past_steps", []))
    messages = list(state.get("messages", []))

    if not plan:
        return {"past_steps": past_steps}

    # 取第一个未执行步骤
    step_text = plan[0]
    remaining_plan = plan[1:]

    # 路由到合适工具
    step_lower = step_text.lower()
    tool_name = None
    tool_args = {"query": step_text}

    if "jira" in step_lower or "ct-" in step_lower or "任务" in step_text:
        tool_name = "query_jira_metadata"
        # 提取 issue key
        import re
        match = re.search(r'(CT-\d+)', step_text, re.I) or re.search(r'(CT-\d+)', str(messages[-1].get("content","") if messages else ""), re.I)
        if match:
            tool_args = {"issue_key": match.group(1)}
        else:
            tool_args = {"query": step_text[:50]}

    elif "svn" in step_lower or "提交" in step_text or "版本" in step_text:
        tool_name = "get_issue_commits"
        import re
        match = re.search(r'(CT-\d+)', step_text, re.I) or re.search(r'(CT-\d+)', str(messages[-1].get("content","") if messages else ""), re.I)
        if match:
            tool_args = {"issue_key": match.group(1)}

    elif "diff" in step_lower or "变更" in step_text:
        tool_name = "get_single_commit_diff"
        import re
        match = re.search(r'r(\d{4,6})', step_text)
        if match:
            tool_args = {"revision_id": match.group(1)}

    elif "文档" in step_text or "notion" in step_lower or "知识" in step_lower:
        tool_name = "search_docs_catalog"

    if tool_name and tool_name in _tool_executors:
        try:
            result = _tool_executors[tool_name](tool_args)
            past_steps.append({
                "step": len(past_steps) + 1,
                "plan_item": step_text,
                "tool": tool_name,
                "result": str(result)[:1000] if result else "无结果",
            })
            messages.append({"role": "tool", "name": tool_name, "content": str(result)[:1000] if result else ""})
            logger.info(f"[Executor] {tool_name}({tool_args}) → {len(str(result)) if result else 0} chars")
        except Exception as e:
            logger.error(f"[Executor] Tool failed: {e}")
            past_steps.append({"step": len(past_steps)+1, "plan_item": step_text, "tool": tool_name, "result": f"ERROR: {e}"})
    else:
        past_steps.append({"step": len(past_steps)+1, "plan_item": step_text, "tool": "llm", "result": "(跳过—无匹配工具)"})

    return {"plan": remaining_plan, "past_steps": past_steps, "messages": messages}


def synthesizer_node(state: dict) -> dict:
    """Synthesizer: 汇总 past_steps → 生成最终回答"""
    past_steps = state.get("past_steps", [])
    messages = state.get("messages", [])

    user_text = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            user_text = m.get("content", "")
            break

    steps_text = "\n".join([
        f"步骤{s['step']}: {s['plan_item']}\n  工具:{s.get('tool','?')}\n  结果:{str(s.get('result',''))[:400]}"
        for s in past_steps[-5:]
    ])

    prompt = f"""你是 Alice AI 助手。请基于以下工具执行结果，回答用户的问题。用自然的语言，结构清晰。

【用户问题】: {user_text}

【已获取的数据】:
{steps_text if steps_text else "(无数据)"}

请直接回答，不要提及你的内部流程。"""

    try:
        answer = _call_llm([
            {"role": "system", "content": "你是 Alice Jira AI 助手。基于真实数据回答，不要编造。"},
            {"role": "user", "content": prompt},
        ], temperature=0.1, max_tokens=1000)
        logger.info(f"[Synthesizer] Generated answer: {len(answer)} chars")
        return {"final_answer": answer}
    except Exception as e:
        logger.error(f"[Synthesizer] Failed: {e}")
        return {"final_answer": f"抱歉，分析过程遇到问题: {e}"}
