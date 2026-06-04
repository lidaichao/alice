"""
Jira 搜索失败恢复 — 对齐 Baize jira_search_error_analysis（DeepSeek 替代 Claude Code）。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger("jira-search-recovery")

RECOVERABLE_CODES = frozenset({
    "JIRA_API_ERROR",
    "JIRA_REQUEST_TIMEOUT",
    "JIRA_INVALID_VALUE",
})


def classify_jira_search_error(error_msg: str, http_status: int = 0) -> str:
    """将异常归类为恢复策略可用的错误码。"""
    err = (error_msg or "").lower()
    if http_status == 408 or "timeout" in err or "timed out" in err:
        return "JIRA_REQUEST_TIMEOUT"
    if http_status in (400, 410) or "does not exist" in err or "not valid" in err:
        return "JIRA_INVALID_VALUE"
    if http_status in (401, 403) or "permission" in err:
        return "JIRA_PERMISSION_DENIED"
    if http_status >= 400 or "jira http" in err:
        return "JIRA_API_ERROR"
    return "JIRA_API_ERROR"


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.I)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def parse_jira_search_recovery_payload(data: dict) -> Optional[dict]:
    """校验并规范化 LLM 返回的 jira_search_recovery JSON。"""
    if not isinstance(data, dict):
        return None
    if data.get("kind") != "jira_search_recovery" or data.get("plugin") != "jira":
        return None
    status = (data.get("status") or "").strip()
    if status not in ("retry_available", "needs_user_input", "not_recoverable"):
        return None
    action = data.get("action") if isinstance(data.get("action"), dict) else {}
    action_id = (action.get("id") or "").strip()
    out = {
        "status": status,
        "summary": (data.get("summary") or "").strip() or "Jira 查询需要调整。",
        "reason": (data.get("reason") or "").strip(),
        "action": {
            "id": action_id,
            "label": (action.get("label") or action_id or "恢复").strip(),
        },
    }
    if status == "retry_available":
        retry = data.get("retry") if isinstance(data.get("retry"), dict) else {}
        jql = (retry.get("jql") or "").strip()
        if not jql:
            return None
        out["retry"] = {"jql": jql}
    if status == "needs_user_input":
        sup = data.get("supplement")
        if isinstance(sup, dict) and sup.get("prompt"):
            out["supplement"] = sup
        else:
            return None
    return out


def build_jira_search_recovery_prompt(
    user_question: str,
    failed_jql: str,
    error_code: str,
    error_message: str,
    project_keys: list,
) -> str:
    pk = ", ".join(project_keys[:5]) if project_keys else "CT"
    return f"""你是 Jira JQL 专家。上一次搜索失败，请输出**唯一** JSON 对象（不要 Markdown），格式如下之一：

1) 可自动重试（修正 JQL）:
{{"kind":"jira_search_recovery","plugin":"jira","status":"retry_available","summary":"中文说明","reason":"中文原因","action":{{"id":"retry_with_rewritten_jql","label":"重试"}},"retry":{{"jql":"修正后的完整 JQL"}}}}

2) 需用户补充（如状态值非法）:
{{"kind":"jira_search_recovery","plugin":"jira","status":"needs_user_input","summary":"中文说明","reason":"中文原因","action":{{"id":"ask_user_for_search_input","label":"请用户补充"}},"supplement":{{"prompt":"请选择","choices":[{{"value":"x","label":"显示名"}}]}}}}

3) 无法安全恢复:
{{"kind":"jira_search_recovery","plugin":"jira","status":"not_recoverable","summary":"中文说明","reason":"中文原因","action":{{"id":"not_recoverable","label":"无法恢复"}}}}

约束：
- JQL 只能 SELECT 搜索，禁止 UPDATE/DELETE/DROP
- 必须包含 project 或 key 约束；项目范围建议: {pk}
- retry 的 jql 必须与失败 JQL 不同且更可能成功
- 超时则缩小范围（更少 OR、更短日期窗、maxResults 语义上更小）

【用户问题】{user_question[:500]}
【失败 JQL】{failed_jql[:800]}
【错误类型】{error_code}
【错误信息】{error_message[:500]}"""


def llm_analyze_jira_search_recovery(
    user_question: str,
    failed_jql: str,
    error_code: str,
    error_message: str,
    project_keys: list,
    api_key: str = "",
    http_post=None,
) -> Optional[dict]:
    """调用 DeepSeek 分析搜索失败并返回 recovery 对象。"""
    key = api_key or os.getenv("DEEPSEEK_KEY", "")
    if not key or not http_post:
        return None
    prompt = build_jira_search_recovery_prompt(
        user_question, failed_jql, error_code, error_message, project_keys,
    )
    try:
        r = http_post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "messages": [
                    {"role": "system", "content": "只输出一个合法 JSON 对象，无其它文字。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
            },
            timeout=25,
        )
        if r.status_code != 200:
            logger.warning(f"[JiraRecovery] LLM HTTP {r.status_code}")
            return None
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json_object(content)
        return parse_jira_search_recovery_payload(parsed) if parsed else None
    except Exception as e:
        logger.warning(f"[JiraRecovery] LLM failed: {e}")
        return None
