"""
prompt_manager.py — 提示词管理模块
职责：组装和返回 LLM 上下文 Prompt，纯函数无运行时依赖
"""
import re
import datetime as _dt

# ── 项目字段映射 ──────────────────────────────────────────
PROJECT_SCHEMA_MAP = {
    "CT": {"deadline": '"End date"'},   # CT 项目的截止时间字段为 End date
    "DEFAULT": {"deadline": "duedate"}  # 其他项目的默认标准字段
}

# ── JQL 中文状态名 → 英文映射 ─────────────────────────────
CN_STATUS_MAP = {
    "待办": "To Do", "未开始": "To Do", "open": "To Do",
    "已完成": "Done", "完成": "Done", "已关闭": "Closed", "关闭": "Closed",
    "已解决": "Resolved", "解决": "Resolved",
    "重新打开": "Reopened", "重开": "Reopened",
    "进行中": "In Progress", "开发中": "In Progress",
    # 注意："处理中" 不映射，CT 项目使用此作为自定义状态名
}

# ── 时间关键词 → JQL 日期函数 ─────────────────────────────
def _resolve_time_keyword(keyword: str) -> str:
    """将中文时间关键词转为 JQL 日期表达式"""
    now = _dt.datetime.now()
    kw = keyword.strip().lower()
    if kw in ("今天", "today"):
        return f'"{now.strftime("%Y-%m-%d")}"'
    if kw in ("昨天", "yesterday"):
        yesterday = now - _dt.timedelta(days=1)
        return f'"{yesterday.strftime("%Y-%m-%d")}"'
    if kw in ("本周", "这周", "this week"):
        monday = now - _dt.timedelta(days=now.weekday())
        return f'"{monday.strftime("%Y-%m-%d")}"'
    if kw in ("本月", "这个月", "this month"):
        return f'"{now.strftime("%Y-%m")}-01"'
    m = re.match(r'最近(\d+)天', kw) or re.match(r'last (\d+) days?', kw)
    if m:
        start = now - _dt.timedelta(days=int(m.group(1)))
        return f'"{start.strftime("%Y-%m-%d")}"'
    return None

def enhance_jql(jql: str) -> str:
    """预处理 JQL：翻译中文状态名 + 替换时间关键词"""
    enhanced = jql
    for cn, en in CN_STATUS_MAP.items():
        if cn in enhanced:
            enhanced = re.sub(rf'([=~]\s*)"?{cn}"?', rf'\1"{en}"', enhanced)
            enhanced = re.sub(rf'(IN\s*\()\s*"?{cn}"?', rf'\1"{en}"', enhanced)
    for kw in ["今天", "昨天", "本周", "这周", "本月", "这个月", "today", "yesterday", "this week", "this month"]:
        if kw in enhanced.lower():
            date_expr = _resolve_time_keyword(kw)
            if date_expr:
                enhanced = re.sub(rf'updated\s*>=\s*"?{kw}"?', f'updated >= {date_expr}', enhanced, flags=re.I)
                enhanced = re.sub(rf'created\s*>=\s*"?{kw}"?', f'created >= {date_expr}', enhanced, flags=re.I)
    days_match = re.search(r'最近(\d+)天|last (\d+) days?', enhanced, re.I)
    if days_match:
        n = int(days_match.group(1) or days_match.group(2))
        start = _dt.datetime.now() - _dt.timedelta(days=n)
        date_expr = f'"{start.strftime("%Y-%m-%d")}"'
        enhanced = re.sub(r'updated\s*>=\s*"?最近\d+天"?|updated\s*>=\s*"?last \d+ days?"?', f'updated >= {date_expr}', enhanced, flags=re.I)
        enhanced = re.sub(r'created\s*>=\s*"?最近\d+天"?|created\s*>=\s*"?last \d+ days?"?', f'created >= {date_expr}', enhanced, flags=re.I)
    return enhanced

# ── 语义意图分类 ──────────────────────────────────────────
INTENT_PATTERNS = [
    ("quick",   ["摘要","概括","简述","一句话","简单","概况","概览","提纲","要点","快速","简短","大致","大概"]),
    ("analyze", ["分析","review","审查","评估","检查","详细","深度","仔细","透彻","展开","全面","代码","diff","提交","变更"]),
    ("compare", ["对比","差异","区别","比较","vs","比","优劣","哪个","异同"]),
    ("search",  ["找","搜","有没有","相关","关联","涉及","匹配","包含","哪些","什么"]),
    ("create",  ["生成","写","创建","制作","产出","构建","输出"]),
]

def classify_query_type(question: str) -> str:
    """语义意图分类: quick / analyze / compare / search / create"""
    scores = {}
    for intent, keywords in INTENT_PATTERNS:
        scores[intent] = sum(1 for kw in keywords if kw in question)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "analyze"

# ── 渐进披露字符上限 ──────────────────────────────────────
L1_CHARS = {"jira": 500, "svn": 600, "notion": 400, "gdrive": 400}
L2_CHARS = {"svn": 2000, "notion": 1500, "gdrive": 1000}
CONTEXT_TOTAL_LIMIT = 8000
JIRA_ISSUE_DETAIL_LIMIT = 3000

# ── LLM 决策提示词（静态兜底模板）─────────────────────────
DECISION_PROMPT = """你是Jira数据检索决策器。分析用户问题与L1元数据，输出JSON:
{"scores":{"jira":0,"svn":0,"notion":0,"gdrive":0,"jira-search":0},"need_detail":[],"jql":""}

规则:
- scores: 0-10, 各数据源语义相关度
- need_detail: 分数>=6的源需补全
- jql: 如果用户的问题需要搜索Jira, 生成完整JQL查询语句。否则留空""
- JQL中项目名用 project in ({proj_keys}) 占位
- JQL必须使用英文字段名(fixVersion, affectedVersion, assignee, status, priority, issuetype, summary等)
- 不要用中文字段名，不要用LIMIT

Jira标准字段:
- issuetype: 问题类型(Bug/Story/Task/Epic/Sub-task等)
- status: 状态(Open/In Progress/Done/Closed等)
- priority: 优先级(High/Medium/Low等)
- assignee: 经办人
- reporter: 报告人
- fixVersion: 修复的版本
- affectedVersion: 影响版本
- summary, description, created, updated
- Sprint, labels, components

JQL示例(通用):
- "XX版本的缺陷" → "project in ({proj_keys}) AND issuetype = \"Bug\" AND affectedVersion = \"XX\" ORDER BY updated DESC"
- "某人负责的未完成任务" → "project in ({proj_keys}) AND assignee = \"userid\" AND status != \"Closed\" ORDER BY updated DESC"
- "XX类型的工作" → "project in ({proj_keys}) AND issuetype = \"XX\" ORDER BY updated DESC"
- "关键词搜索" → "project in ({proj_keys}) AND summary ~ \"关键词*\" ORDER BY updated DESC"

重要: 只要用户问题涉及Jira数据查询,即使L1元数据为空也必须生成jql。只输出JSON,不要解释。"""

# ── 动态提示词引擎 ────────────────────────────────────────
def build_decision_prompt(meta: dict) -> str:
    """用项目元数据动态组装 DECISION_PROMPT"""
    if not meta or not meta.get("issuetypes"):
        return DECISION_PROMPT

    types = "/".join(meta["issuetypes"][:15])
    priorities = "/".join(meta["priorities"][:8]) if meta["priorities"] else "N/A"

    wf_lines = []
    for it, ss in list(meta.get("statuses", {}).items())[:10]:
        wf_lines.append(f"  {it}: {'→'.join(ss[:8])}")
    workflows = "\n".join(wf_lines) if wf_lines else "未获取"

    field_names = [f for f in meta.get("fields", []) if f and any('\u4e00' <= c <= '\u9fff' for c in f)][:20]
    fields_str = ", ".join(field_names) if field_names else "summary,description"

    return f"""你是Jira数据检索决策器。分析用户问题与L1元数据，输出JSON:
{{"scores":{{"jira":0,"svn":0,"notion":0,"gdrive":0,"jira-search":0}},"need_detail":[],"jql":""}}

规则:
- scores: 0-10, 各数据源语义相关度
- need_detail: 分数>=6的源需补全
- jql: 用户问题涉及Jira数据查询时生成完整JQL。项目占位符用 {{proj_keys}}, 否则留空""

当前Jira项目信息:
- issuetype({len(meta.get('issuetypes',[]))}种): {types}
- priority: {priorities}
- 工作流(状态流转):
{workflows}
- 常用字段(中文名→JQL名): {fields_str}
- **JQL字段映射**: 修复的版本→fixVersion, 影响版本→affectedVersion, 经办人→assignee, 报告人→reporter, 优先级→priority, 状态→status, 摘要→summary, 描述→description, 创建时间→created, 更新时间→updated, Sprint→Sprint
- **注意**: JQL中必须使用英文字段名(fixVersion/affectedVersion), NOT中文显示名

JQL示例(注意: JQL不支持LIMIT, 数量由Python控制):
- "XX版本的缺陷" → "project in ({{proj_keys}}) AND issuetype = \\"缺陷\\" AND affectedVersion = \\"XX\\" ORDER BY updated DESC"
- "某人负责的未完成任务" → "project in ({{proj_keys}}) AND assignee = \\"ID\\" AND status not in (完成状态) ORDER BY updated DESC"
- "XX类型的工作" → "project in ({{proj_keys}}) AND issuetype = \\"XX\\" ORDER BY updated DESC"
- "关键词搜索" → "project in ({{proj_keys}}) AND summary ~ \\"关键词*\\" ORDER BY updated DESC"

重要: JQL字段必须用英文(fixVersion, affectedVersion, assignee), 不用中文。不用LIMIT。只要用户问题涉及Jira数据查询,即使L1元数据为空也必须生成jql。只输出JSON。"""

# ── 知识源路由定义 ────────────────────────────────────────
AVAILABLE_KNOWLEDGE_SOURCES = {
    "jira":   {"desc": "Jira项目管理系统，查询任务/需求/Bug/迭代信息", "tool": "query_jira_issues"},
    "svn":    {"desc": "SVN代码仓库+FishEye，查询代码提交/变更/DIFF", "tool": "get_issue_commits"},
    "notion": {"desc": "Notion知识库，查询设计文档/技术方案/规范",   "tool": "search_knowledge_base"},
    "gdrive": {"desc": "Google云盘知识库，查询策划文档/表格/设计稿",  "tool": "search_knowledge_base"},
}

# ── 核心系统提示词 ────────────────────────────────────────
CORE_AGENT_SYSTEM_PROMPT = (
    "你是一个专业的企业级研发AI助手。请严格遵守以下行为准则：\n"
    "1. 【严禁暴露底层】只能使用自然语言或Markdown回复，绝对不可在正文输出 <|tool_calls|>、DSML 等标签。\n"
    "2. 【数据直接展示】当你调用工具获取到数据后，必须直接将其总结为表格或列表展示给用户。\n"
    "3. 【严禁自我对话】绝对不可输出诸如\"请显示第三个标题\"、\"开始执行搜索\"等内部思考过程或命令语句。你的回答必须是面向用户的最终结果。\n"
    "4. 【表格必须换行】输出Markdown表格时，每行必须以换行符 \\n 分隔。表头行、分隔行、数据行各占独立一行。严禁将整张表格压成一行！示例格式：\n"
    "| 序号 | 文件名 |\\n|:---|:---|\\n| 1 | 文档A |\\n| 2 | 文档B |\n"
    "5. 【数据溯源】每段关键信息必须标注数据来源，格式如 [Jira:CT-11112]、[Notion:战术系统]、[SVN:r40446]、[GDrive:文档名]。让用户知道每条信息来自哪个知识库。\n"
    "6. 【代码检索铁律】查询代码提交记录/变更/DIFF时，必须且只能使用 get_issue_commits 或 get_issue_diff 工具，传入 Issue Key 即可。严禁使用 search_knowledge_base 搜索代码！search_knowledge_base 仅用于 Notion/GDrive 文档检索。\n"
    "7. 【致命警告】你一次只能调用 ONE 个工具！绝对禁止并发调用多个工具！绝对禁止在回复内容中手写 <|DSML|> 或 tool_calls 标签！如果你需要查资料，请通过标准 API 格式调用一次工具，等拿到结果后再进行下一步。"
)
