"""
Jira Query Builder — DeepSeek NL → 结构化查询 JSON（P1-1 Jira 聪明度第一弹）
将自然语言转成结构化 params，交给 jira_search_engine.build_resolved_jql() 确定性建 JQL。
不直接让 LLM 拼 JQL，避免注入与幻觉。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

import requests

logger = logging.getLogger("jira-query-builder")

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

QUERY_BUILDER_SYSTEM = """你是 Jira 查询参数解析器。根据用户的自然语言描述，输出严格 JSON，不输出任何其它文字、注释或 Markdown。

输出格式：
{{"action":"search","params":{{"assignee":"...","status":"...","projectKey":"...","issueType":"...","text":"...","updatedAfter":"...","updatedBefore":"...","maxResults":50,"orderBy":"updated DESC"}}}}

params 字段说明（全部可选，空字段不输出）：
- assignee: 经办人中文姓名（如"张锡涛"），如果用户提到"我/我的/本人"不要输出 assignee（留给调用方用 currentUser 处理）
- status: 状态（如"进行中""待办""完成""已解决""已关闭"）
- projectKey: 项目 Key（如"CT""BUG"），大写
- issueType: 类型（Bug/Story/Task/Epic）
- text: 自由文本关键词（用于 summary ~ 模糊匹配 text ~），不要放人名、时间词
- updatedAfter: ISO 日期 "YYYY-MM-DD"
- updatedBefore: ISO 日期 "YYYY-MM-DD"
- maxResults: 返回数量（默认 50）
- orderBy: 排序（默认 "updated DESC"）

时间语义解析规则（基于「今天」= {today}）：
- "本周" → updatedAfter = 本周一, updatedBefore = 今天
- "上周" → updatedAfter = 上周一, updatedBefore = 上周日
- "最近两周" / "近两周" → updatedAfter = 14天前, updatedBefore = 今天
- "最近一周" / "近一周" → updatedAfter = 7天前, updatedBefore = 今天
- "上个月" → updatedAfter = 上月1日, updatedBefore = 上月最后一天
- "今天" → updatedAfter = 今天, updatedBefore = 今天
- "最近三天" → updatedAfter = 3天前, updatedBefore = 今天
- "最近一个月" / "近一个月" → updatedAfter = 30天前, updatedBefore = 今天

状态别名映射（输出正规状态名，不要用别名）：
- "进行中/处理中/开发中/in progress" → "进行中"
- "待办/未开始/todo/to do/open" → "待办"
- "完成/已解决/已关闭/done/resolved/closed" → "完成"
- "阻塞/blocked" → 不填 status，改为 text 中包含"阻塞"

重要规则：
1. 用户说"我的"+"任务" → 不要填 assignee（调用方知道当前用户），配合 status 或 updatedAfter 等条件
2. 用户说"张三的Bug" → assignee="张三", issueType="Bug"
3. 用户说"CT 项目进行中的任务" → projectKey="CT", status="进行中"
4. 用户说"最近两周已解决的" → status="完成", updatedAfter=(14天前), updatedBefore=(今天)
5. 用户说"张锡涛上周做了什么" → assignee="张锡涛", updatedAfter=(上周一), updatedBefore=(上周日)
6. 只输出 JSON，不输出解释"""


def _resolve_api_key(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit.strip()
    key = os.getenv("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    if key:
        return key.strip()
    try:
        path = os.path.join(os.path.dirname(__file__), "global_config.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return (json.load(f).get("DEEPSEEK_KEY") or "").strip()
    except Exception:
        pass
    return ""


def build_jira_search_prompt(user_text: str) -> str:
    """构造 system prompt，注入「今天」的日期计算基准"""
    today = date.today()
    return QUERY_BUILDER_SYSTEM.format(today=today.isoformat())


def _compute_date_examples() -> dict:
    """返回供 prompt 示例的时间基准 dict（用于 prompt 构造时的模板填充）"""
    today = date.today()
    # 本周一
    weekday = today.weekday()  # 0=Monday
    this_monday = today - timedelta(days=weekday)
    # 上周一 ~ 上周日
    last_monday = this_monday - timedelta(days=7)
    last_sunday = last_monday + timedelta(days=6)
    # 上月
    first_of_this_month = today.replace(day=1)
    last_of_last_month = first_of_this_month - timedelta(days=1)
    first_of_last_month = last_of_last_month.replace(day=1)

    return {
        "today": today.isoformat(),
        "this_monday": this_monday.isoformat(),
        "14_days_ago": (today - timedelta(days=14)).isoformat(),
        "7_days_ago": (today - timedelta(days=7)).isoformat(),
        "last_monday": last_monday.isoformat(),
        "last_sunday": last_sunday.isoformat(),
        "first_of_last_month": first_of_last_month.isoformat(),
        "last_of_last_month": last_of_last_month.isoformat(),
    }


def parse_query_llm(user_text: str, api_key: Optional[str] = None) -> Optional[dict]:
    """调 DeepSeek API 解析自然语言 → 结构化查询 params。

    Returns:
        dict {"assignee":..., "status":..., ...} 或 None（失败时降级到 regex fallback）
    """
    key = _resolve_api_key(api_key)
    if not key:
        logger.warning("[JiraQueryBuilder] No API key available, fallback to regex")
        return None

    text = (user_text or "").strip()
    if not text or len(text) < 2:
        return None

    prompt = f"用户查询：\n{text[:800]}"
    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("DEEPSEEK_MODEL") or "deepseek-chat",
                "messages": [
                    {"role": "system", "content": build_jira_search_prompt(text)},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 300,
            },
            timeout=10,
        )
        resp.raise_for_status()
        content = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not content:
            logger.warning("[JiraQueryBuilder] Empty LLM response")
            return None

        parsed = _parse_llm_json(content)
        if not parsed:
            return None

        action = parsed.get("action", "")
        if action != "search":
            logger.warning(f"[JiraQueryBuilder] Unexpected action: {action}")
            return None

        params = parsed.get("params") or {}
        if not isinstance(params, dict):
            return None

        # 清除空值字段
        clean = {}
        for k, v in params.items():
            if isinstance(v, str) and v.strip():
                clean[k] = v.strip()
            elif isinstance(v, (int, float)):
                clean[k] = v
            elif isinstance(v, list) and len(v) > 0:
                clean[k] = v

        if not clean:
            logger.info("[JiraQueryBuilder] All params empty after cleaning")
            return None

        logger.info(f"[JiraQueryBuilder] Parsed: {json.dumps(clean, ensure_ascii=False)}")
        return clean

    except requests.exceptions.Timeout:
        logger.warning("[JiraQueryBuilder] DeepSeek timeout (10s), fallback to regex")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"[JiraQueryBuilder] DeepSeek request failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"[JiraQueryBuilder] Unexpected error: {e}")
        return None


def _parse_llm_json(content: str) -> Optional[dict]:
    """从 LLM 返回文本中提取 JSON 对象"""
    text = (content or "").strip()
    # 去除可能的 markdown 代码块包裹
    if text.startswith("```"):
        import re
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取第一个 JSON 对象
        import re
        m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        logger.warning(f"[JiraQueryBuilder] Invalid JSON: {text[:200]}")
        return None
