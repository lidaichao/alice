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

# Jira /field 自动发现时的截止时间字段别名（按优先级）
DEADLINE_FIELD_ALIASES = [
    "end date",
    "结束时间",
    "截止日期",
    "计划结束",
    "due date",
    "duedate",
]


def _normalize_field_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _parse_schema_deadline(raw: str) -> tuple:
    """PROJECT_SCHEMA_MAP 中的 deadline 值 → (display_name, jql_fragment)"""
    raw = (raw or "duedate").strip()
    if raw.startswith('"') and raw.endswith('"'):
        inner = raw[1:-1]
        return inner, f'"{inner}"'
    return raw, raw


def _meta_from_field(display_name: str, rest_id: str, source: str) -> dict:
    disp = display_name or "duedate"
    if _normalize_field_name(disp) == "duedate":
        return {
            "jql_name": "duedate",
            "rest_id": "duedate",
            "display_name": "duedate",
            "source": source,
        }
    return {
        "jql_name": f'"{disp}"',
        "rest_id": rest_id or "duedate",
        "display_name": disp,
        "source": source,
    }


def discover_deadline_from_jira_fields(all_fields: list) -> dict | None:
    """从 Jira /field 列表按别名匹配截止时间字段"""
    if not all_fields:
        return None
    by_norm = {}
    for f in all_fields:
        name = f.get("name") or ""
        if name:
            by_norm[_normalize_field_name(name)] = f
    for alias in DEADLINE_FIELD_ALIASES:
        hit = by_norm.get(_normalize_field_name(alias))
        if hit:
            return _meta_from_field(hit.get("name", alias), hit.get("id", ""), "discovered")
    return None


def resolve_deadline_field(
    project_key: str,
    config_map: dict | None = None,
    all_fields: list | None = None,
) -> dict:
    """
    多项目截止时间字段解析（配置 > 静态表 > /field 发现 > duedate）
    config_map: global_config JIRA_DEADLINE_FIELD_BY_PROJECT
    all_fields: Jira GET /field 返回的数组
    """
    pk = (project_key or "DEFAULT").strip().upper()
    cfg = config_map or {}

    if pk in cfg and cfg[pk]:
        name = str(cfg[pk]).strip()
        rest_id = "duedate"
        if all_fields:
            for f in all_fields:
                if (f.get("name") or "").strip() == name or _normalize_field_name(f.get("name")) == _normalize_field_name(name):
                    rest_id = f.get("id") or rest_id
                    name = f.get("name") or name
                    break
        return _meta_from_field(name, rest_id, "config")

    schema = PROJECT_SCHEMA_MAP.get(pk) or PROJECT_SCHEMA_MAP.get("DEFAULT", {})
    if schema.get("deadline"):
        disp, jql = _parse_schema_deadline(schema["deadline"])
        rest_id = "duedate"
        if all_fields:
            for f in all_fields:
                if _normalize_field_name(f.get("name")) == _normalize_field_name(disp):
                    rest_id = f.get("id") or rest_id
                    disp = f.get("name") or disp
                    break
        meta = _meta_from_field(disp, rest_id, "schema")
        meta["jql_name"] = jql
        return meta

    discovered = discover_deadline_from_jira_fields(all_fields or [])
    if discovered:
        return discovered

    return _meta_from_field("duedate", "duedate", "duedate")


def parse_date_range_from_text(text: str, anchor: _dt.datetime | None = None) -> tuple:
    """
    解析用户问题中的日期区间。
    返回 (start_iso, end_iso, range_label, use_jql_functions)
    use_jql_functions=True 时用 startOfWeek()/endOfWeek() 而非字面日期
    """
    anchor = anchor or _dt.datetime.now()
    text = text or ""

    m_iso = re.search(
        r"(\d{4})-(\d{1,2})-(\d{1,2})\s*[-–—至到~]\s*(\d{4})-(\d{1,2})-(\d{1,2})",
        text,
    )
    if m_iso:
        s = f"{m_iso.group(1)}-{int(m_iso.group(2)):02d}-{int(m_iso.group(3)):02d}"
        e = f"{m_iso.group(4)}-{int(m_iso.group(5)):02d}-{int(m_iso.group(6)):02d}"
        return s, e, f"{s} 至 {e}", False

    m_cn = re.search(
        r"(\d{1,2})月(\d{1,2})日\s*[-–—至到~]\s*(\d{1,2})月(\d{1,2})日",
        text,
    )
    if m_cn:
        year = anchor.year
        s = f"{year}-{int(m_cn.group(1)):02d}-{int(m_cn.group(2)):02d}"
        e = f"{year}-{int(m_cn.group(3)):02d}-{int(m_cn.group(4)):02d}"
        return s, e, f"{s} 至 {e}", False

    if re.search(r"本周|这周|this\s*week", text, re.I):
        monday = anchor - _dt.timedelta(days=anchor.weekday())
        sunday = monday + _dt.timedelta(days=6)
        s, e = monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
        return s, e, f"日历本周（{s} 至 {e}）", True

    if re.search(r"本月|这个月|this\s*month", text, re.I):
        start = anchor.replace(day=1)
        return start.strftime("%Y-%m-%d"), anchor.strftime("%Y-%m-%d"), "本月", True

    # 周报/日报默认：日历本周
    if re.search(r"周报|日报|月报", text):
        monday = anchor - _dt.timedelta(days=anchor.weekday())
        sunday = monday + _dt.timedelta(days=6)
        s, e = monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
        return s, e, f"日历本周（{s} 至 {e}）", True

    monday = anchor - _dt.timedelta(days=anchor.weekday())
    sunday = monday + _dt.timedelta(days=6)
    s, e = monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
    return s, e, f"日历本周（{s} 至 {e}）", True


def build_weekly_report_jql(
    project_key: str,
    deadline_meta: dict,
    date_range: tuple,
) -> str:
    """组装周报 JQL（项目 + 动态截止时间字段 + 日期区间）"""
    pk = (project_key or "CT").strip().upper()
    jql_field = deadline_meta.get("jql_name") or "duedate"
    start, end, _label, use_fn = date_range
    if use_fn:
        if "本月" in (_label or ""):
            time_clause = f"{jql_field} >= startOfMonth() AND {jql_field} <= endOfMonth()"
        else:
            time_clause = f"{jql_field} >= startOfWeek() AND {jql_field} <= endOfWeek()"
    else:
        time_clause = f'{jql_field} >= "{start}" AND {jql_field} <= "{end}"'
    return f"project = {pk} AND {time_clause} ORDER BY {jql_field} ASC"


def extract_deadline_display(fields: dict, deadline_meta: dict) -> str:
    """从 issue fields 取出截止时间显示值"""
    if not fields:
        return "—"
    rest_id = deadline_meta.get("rest_id") or "duedate"
    if rest_id == "duedate":
        return (fields.get("duedate") or "—")[:10]
    val = fields.get(rest_id)
    if val is None:
        return "—"
    if isinstance(val, str):
        return val[:10] if val else "—"
    return str(val)[:20]

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
    "2. 【禁止口头模拟工具】绝对禁止用纯文本回复\"我正在搜索...\"、\"我已经读取了...\"！如果你需要获取数据，必须且只能通过标准的 JSON tool_calls 触发工具！\n"
    "3. 【数据直接展示】当你调用工具获取到数据后，必须直接将其总结为表格或列表展示给用户。\n"
    "4. 【禁止知识库幻觉】所有涉及项目业务、机制、数值的回答，必须 100% 来源于工具调用的返回结果。如果没有搜到，直接回答\"未找到相关文档\"，绝不允许动用通用参数知识进行编造！\n"
    "5. 【上下文缺失必须反问】如果用户使用了\"这个\"、\"这份\"等代词且无上下文指代，你必须直接反问具体指的是什么，禁止基于猜测捏造数据！\n"
    "6. 【表格必须换行】输出Markdown表格时，每行必须以换行符 \\n 分隔。\n"
    "7. 【代码检索铁律】查询代码提交/变更/DIFF时必须使用 get_issue_commits，严禁用 search_knowledge_base 搜索代码！\n"
    "8. 【致命警告】一次只能调用 ONE 个工具！绝对禁止并发调用多个工具！"
)
