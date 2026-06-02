"""
Alice V2.0 Intent Router — 意图路由层
═══════════════════════════════════════════════════════════
设计原理 (Industry-validated pattern, 2025-2026):
  "不要让模型一边理解人话，一边挑工具，一边还要组织答案"
  → 路由层负责"用户要什么工具"，LLM 负责"数据怎么回答"

与 LlamaIndex 的关系:
  LlamaIndex 管检索完成后 LLM 的摘要选择与回答合成
  Intent Router 管检索开始前 LLM 应该拿到哪些工具
  互补，不冲突

关键设计:
  1. 模式匹配 (非关键词匹配) — 基于用户意图的语义模式
  2. 路由输出是工具子集，不是固定调用链 — LLM 仍自主决策调用顺序
  3. 不确定时回退到全量工具 — 宁可多给，不可少给
═══════════════════════════════════════════════════════════
"""
import re
import logging

logger = logging.getLogger('intent_router')

# ── 意图模式定义 ─────────────────────────────────────────
# 每个模式: (pattern_regex, tool_subset, label)
# pattern 匹配用户问法，tool_subset 是该意图下应暴露的工具

INTENT_PATTERNS = [

    # P0: 代码提交/Diff 查询 — 最容易出错的场景
    # LLM 会因为任务状态"规划中/待PO分转"而预判没提交
    # 路由层直接给 get_issue_commits，跳过 LLM 的状态推理
    (
        r"提交|commit|改了什么代码|代码变更|diff|变更了哪些|改了哪些文件|提交记录|提交内容",
        ["query_jira_metadata", "get_issue_commits"],
        "CODE_COMMIT"
    ),

    # P1: 文档内容查询 — 只需要知识库检索
    (
        r"文档.*写了|写了什么|文档.*内容|文档.*摘要|这份.*文档|说明.*这份|讲.*什么|说了什么",
        ["search_docs_catalog", "read_specific_doc"],
        "DOC_SEARCH"
    ),

    # P2: 文档+Jira 关联查询 — 跨工具关联检索
    (
        r"文档.*(?:jira|任务|关联|相关.*任务)|(?:jira|任务|关联).*文档",
        ["search_docs_catalog", "read_specific_doc", "search_jira_issues", "query_jira_metadata"],
        "DOC_JIRA_CROSS"
    ),

    # P3: 关键词搜索 Jira (无具体 Issue Key)
    (
        r"找.*(?:任务|bug|需求|故事|缺陷)|搜索|查找.*jira|和.*有关的.*任务|相关.*任务",
        ["search_jira_issues", "query_jira_metadata"],
        "JIRA_KEYWORD_SEARCH"
    ),

    # P4: 具体任务状态查询 — 轻量
    (
        r"状态|谁在负责|经办人|怎么样|是什么|详细信息",
        ["query_jira_metadata"],
        "ISSUE_METADATA"
    ),
]

# ── 路由函数 ──────────────────────────────────────────────

def route_intent(user_text: str) -> tuple:
    """
    根据用户输入，返回应暴露的工具子集。

    Args:
        user_text: 用户原始输入文本

    Returns:
        (tool_names, intent_label)
        - tool_names: 推荐的工具名称列表
        - intent_label: 匹配到的意图标签 (用于日志)
        - 如果无匹配，返回 None (走全量工具)
    """
    if not user_text or not user_text.strip():
        return None, "EMPTY"

    text = user_text.lower().strip()

    for pattern, tools, label in INTENT_PATTERNS:
        if re.search(pattern, text):
            logger.info(f"[IntentRouter] Matched '{label}' → tools: {tools}")
            return tools, label

    # 无匹配 → 全量工具 (宁可多给，不可少给)
    logger.info(f"[IntentRouter] No match → full toolset")
    return None, "FULL_SET"


def get_filtered_tools(active_tools: list, tool_names: list) -> list:
    """
    从全量工具列表中，按名称筛选出匹配的工具。

    Args:
        active_tools: 当前可用的全部工具 (DeepSeek API JSON Schema 格式)
        tool_names: 需要保留的工具名称列表

    Returns:
        筛选后的工具列表
    """
    if tool_names is None:
        return active_tools  # 全量

    filtered = [
        t for t in active_tools
        if t.get("function", {}).get("name") in tool_names or t.get("type") != "function"
    ]
    if not filtered:
        return active_tools  # 安全兜底

    logger.info(f"[IntentRouter] Filtered tools: {len(active_tools)} → {len(filtered)} "
                f"({[t['function']['name'] for t in filtered if t.get('type') == 'function']})")
    return filtered
