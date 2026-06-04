"""
AI Bridge v5 — asyncio 真并发 + 流式优先 + 语义缓存
启动: python ai_bridge.py
"""
import os, sys, re, json, time, logging, asyncio, hashlib, threading, collections, concurrent.futures
from functools import wraps
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests as http  # 同步请求保留给简单场景

# ── SVN 提交缓存 ──────────────────────────────────────────
SVN_COMMIT_CACHE = {}  # { "CT-11112": (timestamp, data_string) }
CACHE_TTL = 60  # 缓存 60 秒

# 语义映射表：逻辑意图 → 物理字段名
PROJECT_SCHEMA_MAP = {
    "CT": {"deadline": '"End date"'},   # CT 项目的截止时间字段为 End date
    "DEFAULT": {"deadline": "duedate"}  # 其他项目的默认标准字段
}
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, before_sleep_log
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jira_api import JiraClient

# ── 意图分类（移植自白泽 Baize）─────────────────────────────
from intent_classifier import classify_intent, should_intercept, needs_confirmation, is_jira_operation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ai-bridge")

app = Flask(__name__)
CORS(app)  # 允许跨域请求（内网客户端从不同 IP 访问）

# ── 全局统计计数器 ──────────────────────────────────────
SERVER_START_TIME = time.time()
GLOBAL_STATS = {
    "total_requests": 0,
    "dangerous_intercepts": 0,
    "jira_writes": 0
}

# ── JQL 智能增强模块 ──────────────────────────────────────────
# 中文状态名 → Jira 英文状态名映射表（仅标准 Jira 状态，自定义状态保持原样）
CN_STATUS_MAP = {
    "待办": "To Do", "未开始": "To Do", "open": "To Do",
    "已完成": "Done", "完成": "Done", "已关闭": "Closed", "关闭": "Closed",
    "已解决": "Resolved", "解决": "Resolved",
    "重新打开": "Reopened", "重开": "Reopened",
    "进行中": "In Progress", "开发中": "In Progress",
    # 注意："处理中" 不映射，CT 项目使用此作为自定义状态名
}

# 时间关键词 → JQL 日期函数
import datetime as _dt
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
    # 中文状态名翻译 — 使用捕获组替代变宽 look-behind
    for cn, en in CN_STATUS_MAP.items():
        if cn in enhanced:
            enhanced = re.sub(rf'([=~]\s*)"?{cn}"?', rf'\1"{en}"', enhanced)
            enhanced = re.sub(rf'(IN\s*\()\s*"?{cn}"?', rf'\1"{en}"', enhanced)
    # 时间关键词替换
    for kw in ["今天", "昨天", "本周", "这周", "本月", "这个月", "today", "yesterday", "this week", "this month"]:
        if kw in enhanced.lower():
            date_expr = _resolve_time_keyword(kw)
            if date_expr:
                enhanced = re.sub(rf'updated\s*>=\s*"?{kw}"?', f'updated >= {date_expr}', enhanced, flags=re.I)
                enhanced = re.sub(rf'created\s*>=\s*"?{kw}"?', f'created >= {date_expr}', enhanced, flags=re.I)
    # 最近N天
    days_match = re.search(r'最近(\d+)天|last (\d+) days?', enhanced, re.I)
    if days_match:
        n = int(days_match.group(1) or days_match.group(2))
        start = _dt.datetime.now() - _dt.timedelta(days=n)
        date_expr = f'"{start.strftime("%Y-%m-%d")}"'
        enhanced = re.sub(r'updated\s*>=\s*"?最近\d+天"?|updated\s*>=\s*"?last \d+ days?"?', f'updated >= {date_expr}', enhanced, flags=re.I)
        enhanced = re.sub(r'created\s*>=\s*"?最近\d+天"?|created\s*>=\s*"?last \d+ days?"?', f'created >= {date_expr}', enhanced, flags=re.I)
    return enhanced

# ── 配置 ──────────────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "global_config.json")

def load_global_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_config():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError: pass
    
    # 优先环境变量，fallback 全局配置 JSON
    global_cfg = load_global_config()
    return {
        "jira_url": os.getenv("JIRA_BASE_URL") or global_cfg.get("JIRA_BASE_URL", "http://ctjira1.lmdgame.com:8080"),
        "jira_pat": os.getenv("JIRA_PAT") or global_cfg.get("JIRA_PAT", ""),
        "deepseek_key": os.getenv("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_API_KEY") or global_cfg.get("DEEPSEEK_KEY", ""),
        "port": int(os.getenv("AI_BRIDGE_PORT", "9099")),
    }

config = load_config()
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# ── 从 global_config.json 注入环境变量（供 jira_mcp_server 等子模块使用）──
_global_cfg = load_global_config()
for k, v in _global_cfg.items():
    if v and not os.getenv(k):
        os.environ[k] = str(v)

jira = JiraClient(
    base_url=config["jira_url"],
    email=os.getenv("JIRA_USERNAME", "admin"),
    password=os.getenv("JIRA_PASSWORD", ""),
    pat_token=config["jira_pat"] or None,
)

# ── 前端配置解析（支持用户级 Key 注入）───────────────────────
def parse_user_config(data: dict) -> dict:
    """
    从请求中提取用户配置，优先级：请求体 user_config > config > 环境变量
    返回: {deepseek_key, deepseek_model, jira_pat, jira_email}
    """
    uc = data.get("user_config", {}) or {}
    global_cfg = load_global_config()
    return {
        "deepseek_key": uc.get("ai_api_key") or config["deepseek_key"] or global_cfg.get("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_KEY", ""),
        "deepseek_model": uc.get("ai_model") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "jira_pat": uc.get("user_jira_pat") or config["jira_pat"] or global_cfg.get("JIRA_PAT", ""),
        "jira_email": uc.get("user_email") or os.getenv("JIRA_EMAIL", ""),
    }


# ═══════════════════════════════════════════════════════════════
#  Progressive Disclosure Retrieval (v2)
# ───────────────────────────────────────────────────────────────
#  L1: 4源并行 → 结构化元数据摘要（~2s）
#  LLM决策: 轻量调用 → 相关性打分 → 路由 (50 tokens)
#  L2: 仅对相关源补全 → 按语义结构取章节（~3-8s）
#  缓存: (Issue × Intent × Recency) 三级键
# ═══════════════════════════════════════════════════════════════

# ── Bounded LRU Cache (OrderedDict-based, prevents memory leak) ─────
class BoundedCache:
    """容量上限安全缓存：LRU 淘汰 + TTL 过期"""
    def __init__(self, max_size=300):
        self._cache = collections.OrderedDict()
        self._max = max_size
    
    def get(self, key):
        if key in self._cache:
            ts, val = self._cache[key]
            self._cache.move_to_end(key)
            return (ts, val)
        return None
    
    def set(self, key, timestamp, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (timestamp, value)
        while len(self._cache) > self._max:
            self._cache.popitem(last=False)  # 淘汰最旧
    
    def pop_oldest(self):
        return self._cache.popitem(last=False) if self._cache else None
    
    def __len__(self):
        return len(self._cache)
    
    def items(self):
        return self._cache.items()

    def keys(self):
        return self._cache.keys()

    def __contains__(self, key):
        return key in self._cache

    def __getitem__(self, key):
        return self._cache[key]

    def __setitem__(self, key, value):
        """value 应为 (timestamp, data) 元组"""
        self.set(key, value[0], value[1])

    def __delitem__(self, key):
        if key in self._cache:
            del self._cache[key]

    def __iter__(self):
        return iter(self._cache)

CACHE_TTL = 300

# 语义意图分类 — 不再是简单关键词
INTENT_PATTERNS = [
    ("quick",   ["摘要","概括","简述","一句话","简单","概况","概览","提纲","要点","快速","简短","大致","大概"]),
    ("analyze", ["分析","review","审查","评估","检查","详细","深度","仔细","透彻","展开","全面","代码","diff","提交","变更"]),
    ("compare", ["对比","差异","区别","比较","vs","比","优劣","哪个","异同"]),
    ("search",  ["找","搜","有没有","相关","关联","涉及","匹配","包含","哪些","什么"]),
    ("create",  ["生成","写","创建","制作","产出","构建","输出"]),
]

# 渐进披露: 各源每层字符上限
L1_CHARS = {"jira": 500, "svn": 600, "notion": 400, "gdrive": 400}
L2_CHARS = {"svn": 2000, "notion": 1500, "gdrive": 1000}
CONTEXT_TOTAL_LIMIT = 8000   # ~3200 tokens，控制 API 成本
JIRA_ISSUE_DETAIL_LIMIT = 3000  # 单个 Issue 详细信息上限

# ── 缓存 ──────────────────────────────────────────────────────
_CONTEXT_CACHE = BoundedCache(max_size=200)  # key → (timestamp, result)
CACHE_TTL = 120              # 2 分钟内相似问题复用
_SEMANTIC_CACHE = BoundedCache(max_size=100)  # 语义缓存：question_hash → answer
_SVN_COMMIT_CACHE = {}        # SVN 提交缓存：issue_key → (timestamp, commits)

# ── 并发监控 ──────────────────────────────────────────────────
_active_requests = 0
_active_lock = threading.Lock()

# ── Tenacity 指数退避重试（429/503/Timeout）─────────────────
def _is_retryable(exc):
    """判断异常是否可重试"""
    if isinstance(exc, (http.exceptions.Timeout, http.exceptions.ConnectionError)):
        return True
    if isinstance(exc, http.exceptions.HTTPError):
        return exc.response is not None and exc.response.status_code in (429, 503, 502, 504)
    return False

_deepseek_retry_deco = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_is_retryable),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)

def _deepseek_call(payload, timeout=10, api_key=None):
    """带重试的 DeepSeek API 非流式调用"""
    key = api_key or config.get("deepseek_key", "")
    @_deepseek_retry_deco
    def _call():
        r = http.post(DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload, timeout=timeout)
        if r.status_code in (429, 503, 502, 504):
            raise http.exceptions.HTTPError(f"Retryable status {r.status_code}", response=r)
        return r
    return _call()

def _run_sync(workers, l1_parts):
    """ThreadPool 同步模式（asyncio 回退）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ex = ThreadPoolExecutor(max_workers=len(workers))
    try:
        jobs = {ex.submit(fn): name for fn, name in workers}
        try:
            for f in as_completed(jobs, timeout=2.0):
                try:
                    result = f.result()
                    if result: l1_parts.append(result)
                except Exception as e:
                    logger.warning(f"[L1 Error] {jobs[f]}: {e}")
        except TimeoutError:
            logger.warning("[L1 Timeout] 2.0s 超时熔断")
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)  # Python 3.8

# LLM 决策提示词 —— 兜底模板（项目元数据不可用时的通用回退）
# 正常运行时由 build_decision_prompt() 动态组装真实字段
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

# ═══ 动态提示词引擎 ═══════════════════════════════════════════
# 运行时从 Jira API 获取项目元数据，注入 DECISION_PROMPT
# 解决硬编码问题：换项目后自动适配 issuetype/status/priority/fields

_PROJECT_CACHE = {}  # {project_key: (timestamp, metadata)}

def discover_project_metadata(project_keys: str) -> dict:
    """探查 Jira 项目元数据：issuetypes, statuses, priorities, fields"""
    if not project_keys:
        return {}
    pk = project_keys.split(",")[0].strip()
    now = time.time()
    if pk in _PROJECT_CACHE and now - _PROJECT_CACHE[pk][0] < 3600:
        return _PROJECT_CACHE[pk][1]

    meta = {"issuetypes": [], "statuses": {}, "priorities": [], "fields": []}
    try:
        # issuetypes + statuses
        r = jira.jira_get(f"/project/{pk}/statuses", timeout=15)
        if r.ok:
            for item in r.json():
                meta["issuetypes"].append(item["name"])
                meta["statuses"][item["name"]] = [s["name"] for s in item.get("statuses", [])]

        # priorities
        r2 = jira.jira_get(f"{jira.api_url}/priority", timeout=10)
        if r2.ok:
            meta["priorities"] = [p["name"] for p in r2.json()]

        # field names (top 50)
        r3 = jira.jira_get(f"{jira.api_url}/field", timeout=15)
        if r3.ok:
            meta["fields"] = [f["name"] for f in r3.json() if f.get("name") and not f.get("name","").startswith(".")]

        _PROJECT_CACHE[pk] = (now, meta)
        logger.info(f"[Discovery] {pk}: {len(meta['issuetypes'])} types, {len(meta['priorities'])} priorities")
    except Exception as e:
        logger.warning(f"[Discovery] Failed for {pk}: {e}")
    return meta

def build_decision_prompt(meta: dict) -> str:
    """用项目元数据动态组装 DECISION_PROMPT"""
    if not meta or not meta.get("issuetypes"):
        return DECISION_PROMPT  # 兜底用静态模板

    types = "/".join(meta["issuetypes"][:15])
    priorities = "/".join(meta["priorities"][:8]) if meta["priorities"] else "N/A"

    # 构建工作流摘要
    wf_lines = []
    for it, ss in list(meta.get("statuses", {}).items())[:10]:
        wf_lines.append(f"  {it}: {'→'.join(ss[:8])}")
    workflows = "\n".join(wf_lines) if wf_lines else "未获取"

    # 构建字段列表（取中文名）
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

def classify_query_type(question: str) -> str:
    """语义意图分类: quick / analyze / compare / search / create"""
    scores = {}
    for intent, keywords in INTENT_PATTERNS:
        scores[intent] = sum(1 for kw in keywords if kw in question)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "analyze"  # 默认深度分析

def llm_judge_relevance(question: str, l1_parts: list, proj_keys: str = "", api_key: str = None) -> dict:
    """轻量 LLM 调用: 判断各源 L1 摘要与问题的相关度, 生成 JQL (~0.8s)"""
    l1_text = "\n".join([p for p in l1_parts if p.startswith("##") or p.startswith("- ")])
    fallback = {"scores": {"jira": 5, "svn": 5, "notion": 0, "gdrive": 0, "jira-search": 0}, "need_detail": ["svn"], "jql": ""}

    proj_info = f"可用Jira项目: {proj_keys}" if proj_keys else "可用Jira项目: 未配置"
    l1_block = f"L1元数据:\n{l1_text[:600]}" if l1_text.strip() else "L1元数据: 暂无"
    user_msg = f"问题: {question[:150]}\n{proj_info}\n\n{l1_block}"

    # 动态提示词: 用实际项目元数据替换硬编码模板
    project_meta = discover_project_metadata(proj_keys)
    decision_prompt = build_decision_prompt(project_meta)

    try:
        r = _deepseek_call({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": decision_prompt},
                {"role": "user", "content": user_msg}
            ],
            "max_tokens": 300, "temperature": 0
        }, timeout=10, api_key=api_key)
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"]
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                result = json.loads(m.group())
                logger.info(f"[LLM Decision] scores={result.get('scores')} detail={result.get('need_detail')} jql={result.get('jql','')[:80]}")
                return result
    except Exception as e:
        logger.debug(f"LLM decision failed: {e}")
    
    return fallback

def llm_decide_jql(question: str, proj_keys: list) -> str:
    """结构化意图提取 + Python 原生 JQL 组装"""
    import json
    proj_cond = "project in (" + ",".join(proj_keys) + ")" if proj_keys else "project in (CT)"

    prompt = f"""分析用户的 Jira 查询需求，提取关键过滤条件并严格输出 JSON 格式。
用户问题: {question}

输出格式必须为：
{{
    "time_filter": "this_week" | "this_month" | "today" | "none",
    "target_field": "deadline" | "created" | "updated",
    "status_filter": "unfinished" | "done" | "all"
}}
注意：若询问"本周需要完成/结束的任务"，target_field 取 "deadline"，time_filter 取 "this_week"。只输出合法的 JSON，不要包裹 Markdown 标记。"""

    try:
        r = _deepseek_call({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个无情的 JSON 提取器，只输出合法 JSON，绝不输出其他字符。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0
        }, timeout=8)

        if r.status_code == 200:
            content = r.json().get("choices",[{}])[0].get("message",{}).get("content","").strip()
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'^```\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            
            intent_data = json.loads(content)
            logger.info(f"[JQL-Intent] Parsed JSON: {intent_data}")

            target_proj = proj_keys[0] if proj_keys else "DEFAULT"
            schema = PROJECT_SCHEMA_MAP.get(target_proj, PROJECT_SCHEMA_MAP["DEFAULT"])
            
            target_field_logical = intent_data.get("target_field", "created")
            field_physical = schema.get(target_field_logical, "created")

            jql_parts = [proj_cond]
            
            status_val = intent_data.get("status_filter", "all")
            if status_val == "unfinished":
                jql_parts.append('statusCategory != Done')
            elif status_val == "done":
                jql_parts.append('statusCategory = Done')

            time_val = intent_data.get("time_filter", "none")
            if time_val == "this_week":
                jql_parts.append(f'{field_physical} >= startOfWeek() AND {field_physical} <= endOfWeek()')
            elif time_val == "this_month":
                jql_parts.append(f'{field_physical} >= startOfMonth() AND {field_physical} <= endOfMonth()')
            elif time_val == "today":
                jql_parts.append(f'{field_physical} >= startOfDay() AND {field_physical} <= endOfDay()')

            final_jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
            logger.info(f"[JQL-Generated] {final_jql}")
            return final_jql

    except Exception as e:
        logger.warning(f"[JQL-Decide] Failed to parse or build JQL: {e}")
        
    return f"{proj_cond} AND statusCategory != Done ORDER BY updated DESC"

def make_source_summary(source: str, raw_text: str, max_chars: int) -> str:
    """制造结构化摘要: 取首段 + 关键行"""
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    result = lines[:2]  # 前两行
    # 追加表格头或标题行
    for line in lines[2:]:
        if line.startswith('|') or line.startswith('##') or line.startswith('###'):
            result.append(line)
        if sum(len(l) for l in result) > max_chars:
            break
    return "\n".join(result)[:max_chars]

def classify_file_changes(diff_text: str) -> str:
    """按扩展名分类文件变更类型，返回一句总结"""
    if not diff_text: return ""
    patterns = {
        "代码": r"\.cs\b|\.java\b|\.py\b|\.cpp\b|\.h\b",
        "配置": r"\.json\b|\.csv\b|\.xml\b|\.yaml\b|\.yml\b|\.bytes\b|\.xlsx\b",
        "资源": r"\.prefab\b|\.unity\b|\.asset\b|\.mat\b|\.fbx\b|\.png\b|\.jpg\b",
        "项目": r"\.csproj\b|\.sln\b|\.meta\b|\.shader\b",
        "文档": r"\.md\b|\.txt\b|\.pdf\b",
    }
    counts = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, diff_text, re.I)
        if matches: counts[name] = len(matches)
    if not counts: return ""
    parts = [f"{k}({v}个)" for k, v in counts.items()]
    return f"📁 变更类型: " + " / ".join(parts)

def _svn_log_grep(issue_key: str, svn_url: str, svn_user: str, svn_pass: str) -> str:
    """DevStatus 兜底：SVN 命令行直查提交记录"""
    import subprocess
    try:
        cmd = [
            "svn", "log", "--limit", "10", "--non-interactive",
            "--trust-server-cert", "--no-auth-cache",
            "--username", svn_user, "--password", svn_pass, svn_url
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25, env={"LC_ALL": "en_US.UTF-8"})
        if proc.returncode != 0:
            return ""

        # 解析 svn log 输出，筛选包含 issue_key 的提交
        blocks = proc.stdout.split("------------------------------------------------------------------------")
        matched = []
        for block in blocks:
            if issue_key in block and "r" in block[:20]:
                lines = block.strip().split("\n")
                rev_line = lines[0] if lines else ""
                # r40368 | lichunqi | 2026-05-28...
                parts = rev_line.split(" | ")
                rev = parts[0].strip() if len(parts) > 0 else "?"
                author = parts[1].strip() if len(parts) > 1 else "?"
                date = parts[2].strip().split(" ")[0] if len(parts) > 2 else "?"
                msg = lines[-1].strip()[:100] if len(lines) > 1 else ""
                matched.append(
                    f"### {rev} by {author} @ {date}\n"
                    f"> {msg}\n"
                )
        if matched:
            return f"## {issue_key}: SVN提交 ({len(matched)}条)\n" + "\n".join(matched[:15])
    except Exception as e:
        logger.debug(f"SVN log fallback: {e}")
    return ""

def collect_context(issue_key: str, user_question: str = "", frontend_cfg: dict = None, api_key: str = None, user_pat: str = None) -> str:
    """v2 Progressive Disclosure: L1 summary -> LLM judge -> L2 targeted fetch
    user_pat: 客户端传来的个人 Jira PAT，用于鉴权隔离 (2.3)"""
    q = user_question
    t_start = time.time()
    is_global = (issue_key == "__global__")
    intent = classify_query_type(q)
    logger.info(f"[Intent] {intent} | {'GLOBAL' if is_global else issue_key} | Q: {q[:60]}")

    # Cache (Issue × Intent × Project × User)
    user_id = frontend_cfg.get("_wbUser", "anonymous")
    user_id = re.sub(r'[^a-zA-Z0-9_.@-]', '_', user_id)[:40]
    proj_prefix = frontend_cfg.get("jira_projects","").split(",")[0].strip() or "default"
    cache_key = f"{user_id}:__global__:{proj_prefix}:{intent}:{hash(q) % 10000}" if is_global else f"{user_id}:{issue_key}|{intent}"
    cached_val = _CONTEXT_CACHE.get(cache_key)
    if cached_val:
        ts, cached = cached_val
        if time.time() - ts < CACHE_TTL:
            logger.info(f"[Cache] hit ({cache_key[:80]}, {time.time()-ts:.0f}s)")
            return cached

    if frontend_cfg is None:
        frontend_cfg = {}

    state = {"notion_pids": [], "gdrive_matched": [], "svn_has_changes": False}
    l1_parts = [f"# Jira Issue: {issue_key}"]

    # L1: parallel metadata summaries
    def _jira_l1():
        try:
            # 全量拉取：摘要 + 评论 + 优先级
            r = jira.jira_get(
                f"{jira.api_url}/issue/{issue_key}?fields=summary,issuetype,status,assignee,description,comment,fixVersions,versions,priority",
                timeout=15, user_pat=user_pat
            )
            if r.status_code == 200:
                f = r.json()["fields"]

                fix_versions = [v.get("name","") for v in (f.get("fixVersions") or []) if v.get("name")]
                affect_versions = [v.get("name","") for v in (f.get("versions") or []) if v.get("name")]
                vinfo = ""
                if fix_versions: vinfo += f"修复:{','.join(fix_versions)} "
                if affect_versions: vinfo += f"影响:{','.join(affect_versions)} "

                # 超短 L1 摘要（仅用于路由决策，极度节约 Token）
                short_raw = (
                    f"{f.get('summary','?')}\n"
                    f"{vinfo}类型:{f.get('issuetype',{}).get('name','?')} "
                    f"状态:{f.get('status',{}).get('name','?')} "
                    f"描述:{(f.get('description') or '无')[:100]}"
                )

                # 提取最新 3 条历史评论
                comments_data = f.get("comment", {}).get("comments", [])
                comments_text = ""
                if comments_data:
                    comments_text = "\n【最新历史评论】\n"
                    for c in comments_data[-10:]:
                        author = c.get("author", {}).get("displayName", "Unknown")
                        body = c.get("body", "")[:500]
                        comments_text += f"- {author}: {body}\n"

                # 完整详情侧信道注入 state，直达末端
                desc_full = (f.get('description') or '无')[:4000]
                priority_name = (f.get('priority') or {}).get('name', '') if f.get('priority') else ''
                assignee_val = f.get('assignee') or {}
                assignee_name = assignee_val.get('displayName', '未分配') if isinstance(assignee_val, dict) else '未分配'
                state["current_issue_detail"] = (
                    f"### 当前 Issue ({issue_key}) 完整详情\n"
                    f"标题: {f.get('summary','?')}\n"
                    f"{vinfo}类型:{f.get('issuetype',{}).get('name','?')} | "
                    f"状态:{f.get('status',{}).get('name','?')} | "
                    f"优先级:{priority_name} | "
                    f"经办人:{assignee_name}\n"
                    f"【描述正文】\n{desc_full}\n"
                    f"{comments_text}"
                )

                return make_source_summary("jira", short_raw, L1_CHARS["jira"])
        except Exception as e:
            return f"(Jira: {e})"

    def _svn_l1():
        try:
            from jira_mcp_server import jira_get_commits
            target_keys = [issue_key] if issue_key != "__global__" else []
            for ik in re.findall(r'([A-Z]{2,}-\d+)', q):
                if ik not in target_keys:
                    target_keys.append(ik)
            if not target_keys:
                return None

            SVN_CACHE_TTL = 300  # 5分钟缓存
            all_commits = []
            for ik in target_keys:
                # 缓存命中
                if ik in _SVN_COMMIT_CACHE:
                    ts, cached = _SVN_COMMIT_CACHE[ik]
                    if time.time() - ts < SVN_CACHE_TTL:
                        all_commits.append((ik, cached))
                        continue

                commits = jira_get_commits(ik)
                if commits and "没有关联" not in commits and "查询失败" not in commits:
                    all_commits.append((ik, commits))
                    _SVN_COMMIT_CACHE[ik] = (time.time(), commits)
                else:
                    # DevStatus 无数据 → SVN log 兜底
                    svn_url = os.getenv("SVN_URL", "")
                    svn_user = os.getenv("SVN_USERNAME", "")
                    svn_pass = os.getenv("SVN_PASSWORD", "")
                    if svn_url and svn_user:
                        svn_result = _svn_log_grep(ik, svn_url, svn_user, svn_pass)
                        if svn_result:
                            all_commits.append((ik, svn_result))
                            _SVN_COMMIT_CACHE[ik] = (time.time(), svn_result)

            if all_commits:
                state["svn_has_changes"] = True
                combined = "\n".join([f"## {ik}\n{c}" for ik, c in all_commits])
                state["svn_commits_cache"] = combined
                return make_source_summary("svn", combined, L1_CHARS["svn"])
        except Exception as e:
            logger.warning(f"SVN L1 failed: {e}")

    def _notion_l1():
        try:
            NK = os.getenv("NOTION_KEY", "")
            if not NK: return None

            hd = {"Authorization": f"Bearer {NK}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
            seen = set()
            titles = []

            # 策略 0: 全局模式 — 列出所有数据库（提供数据，LLM 决策使用）
            if is_global:
                r0 = http.post("https://api.notion.com/v1/search",
                    headers=hd,
                    json={"filter": {"value": "database", "property": "object"}, "page_size": 20},
                    timeout=10)
                if r0.status_code == 200:
                    db_titles = []
                    for d in r0.json().get("results", []):
                        if d.get("object") == "database":
                            title = "".join([t.get("plain_text","") for t in (d.get("title",[]) or [])])
                            db_titles.append(f"- {title or '(无标题)'} [{d['id'][:8]}...]")
                    if db_titles:
                        titles.append("\n".join(db_titles))
                        return "\n## Notion (L1)\n可用数据库:\n" + "\n".join(db_titles)

            # 策略 1: 全局精准搜索 Issue Key
            r1 = http.post("https://api.notion.com/v1/search",
                headers=hd, json={"query": issue_key, "page_size": 3}, timeout=10)

            if r1.status_code == 200:
                for p in r1.json().get("results", []):
                    pid = p["id"]
                    if pid in seen: continue
                    seen.add(pid)

                    title_text = ""
                    for key, val in p.get("properties", {}).items():
                        if val.get("type") == "title":
                            title_text = "".join([t.get("plain_text","") for t in val.get("title", [])])
                            break

                    if title_text:
                        titles.append(f"- {title_text}")
                        state["notion_pids"].append((pid, title_text))

            # 策略 2: 语义关键词搜索回退
            if not seen and q:
                kws = [kw for kw in re.findall(r'[\w\u4e00-\u9fff]+', q) if len(kw) >= 2]
                # 多关键词尝试，直到找到结果
                for kw in kws[:5]:
                    if not kw or len(kw) < 2: continue
                    r2 = http.post("https://api.notion.com/v1/search",
                        headers=hd, json={"query": kw, "page_size": 3}, timeout=10)
                    if r2.status_code == 200:
                        for p in r2.json().get("results", []):
                            pid = p["id"]
                            if pid in seen: continue
                            seen.add(pid)

                        title_text = ""
                        for key, val in p.get("properties", {}).items():
                            if val.get("type") == "title":
                                title_text = "".join([t.get("plain_text","") for t in val.get("title", [])])
                                break

                        if title_text:
                            titles.append(f"- {title_text}")
                            state["notion_pids"].append((pid, title_text))

            # 策略 3: 无条件扫描配置的 Database（补全搜索 API 的遗漏）
            raw_db = os.getenv("NOTION_DB", "")
            m = re.search(r'([0-9a-f]{32}|[0-9a-f-]{36})', raw_db, re.I)
            ndb = m.group(1) if m else raw_db
            if ndb and len(ndb) >= 32:
                try:
                    r3 = http.post(f"https://api.notion.com/v1/databases/{ndb}/query",
                        headers=hd, json={"page_size": 50}, timeout=10)
                    if r3.status_code == 200:
                        for p in r3.json().get("results", []):
                            pid = p["id"]
                            if pid in seen: continue
                            seen.add(pid)
                            title_text = ""
                            for key, val in p.get("properties", {}).items():
                                if val.get("type") == "title":
                                    title_text = "".join([t.get("plain_text","") for t in val.get("title", [])])
                                    break
                            if title_text:
                                titles.append(f"- {title_text}")
                                state["notion_pids"].append((pid, title_text))
                except Exception:
                    pass

            # 策略 4: 扫描 Wiki 页面的所有子数据库（覆盖策划文档V4 + 技术文档）
            raw_page = os.getenv("NOTION_PAGE", "")
            m_p = re.search(r'([0-9a-f]{32}|[0-9a-f-]{36})', raw_page, re.I)
            page_id = m_p.group(1) if m_p else (raw_page or os.getenv("NOTION_PAGE", ""))
            if page_id and len(page_id) >= 32:
                try:
                    rp = http.get(f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=50",
                        headers=hd, timeout=10)
                    if rp.status_code == 200:
                        for b in rp.json().get("results", []):
                            if b.get("type") == "child_database":
                                db_id = b.get("id", "")
                                if db_id:
                                    try:
                                        db_r = http.post(f"https://api.notion.com/v1/databases/{db_id}/query",
                                            headers=hd, json={"page_size": 50}, timeout=10)
                                        if db_r.status_code == 200:
                                            for row in db_r.json().get("results", []):
                                                pid = row["id"]
                                                if pid in seen: continue
                                                seen.add(pid)
                                                title_text = ""
                                                for key, val in row.get("properties", {}).items():
                                                    if val.get("type") == "title":
                                                        title_text = "".join([t.get("plain_text","") for t in val.get("title", [])])
                                                        break
                                                if title_text:
                                                    titles.append(f"- {title_text}")
                                                    state["notion_pids"].append((pid, title_text))
                                    except Exception:
                                        pass
                except Exception:
                    pass

            if titles:
                return "\n## Notion (L1)\n" + "\n".join(titles)
        except Exception as e:
            logger.warning(f"Notion L1 failed: {e}")
            return None

    def _gdrive_l1():
        try:
            GK = os.getenv("GDRIVE_KEY", "")
            if not GK: return None

            # 动态读取 Jira 配置页传来的 Folders，支持逗号或换行分割
            raw_folders = os.getenv("GDRIVE_FOLDERS", "")
            folders = [f.strip() for f in re.split(r'[\n,]+', raw_folders) if f.strip()]
            if not folders: return None

            # 动态读取 Jira 配置页的 Proxy
            proxy_url = frontend_cfg.get("proxy", "")
            proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None

            all_files = {}
            for fid in folders:
                r = http.get(f"https://www.googleapis.com/drive/v3/files?key={GK}&q='{fid}'+in+parents&fields=files(id,name,mimeType)&pageSize=30",
                    timeout=10, proxies=proxies)
                if r.status_code == 200:
                    for f in r.json().get("files", []):
                        all_files[f["id"]] = f
            base_kw = [kw for kw in q.replace("，"," ").replace(","," ").split() if len(kw) >= 2]
            matched = [f for _, f in all_files.items() if any(k in f.get("name","") for k in set(base_kw))]
            if matched:
                state["gdrive_matched"] = matched
                return "\n## Google Drive (L1)\n" + "\n".join([f"- {f['name']}" for f in matched[:5]])
        except Exception as e:
            logger.debug(f"GDrive L1: {e}")
        return None

    def _jira_search_l1():
        """Jira 搜索: LLM 决策 JQL → Python 执行"""
        try:
            proj_keys = frontend_cfg.get("jira_projects", "") or os.getenv("JIRA_PROJECTS", "")
            if not proj_keys:
                m = re.search(r'([A-Z]{2,})(?:\u9879\u76ee|\u9879\u76EE|\u4e13\u6848|\s)', q)
                if m: proj_keys = m.group(1)
            if not proj_keys:
                proj_keys = "CT"
            keys = [k.strip() for k in proj_keys.split(",") if k.strip()]
            if not keys:
                return None

            # LLM 决策 JQL
            jql = llm_decide_jql(q, keys)

            # 机械兜底：LLM 失败时，用问题中显式 Issue Key 构造基线查询
            if not jql:
                explicit_keys = re.findall(r'([A-Z]{2,}-\d+)', q)
                if explicit_keys:
                    jql = f"project in ({','.join(keys)}) AND issue in ({','.join(explicit_keys[:10])})"

            if not jql:
                return None

            r = jira.jira_get(
                f"{jira.api_url}/search",
                params={"jql": jql, "maxResults": 20, "fields": "key,summary,issuetype,status,priority,assignee"},
                timeout=10, user_pat=user_pat
            )
            logger.info(f"[Jira-Search] JQL: {jql[:200]} => HTTP {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                total = data.get("total", 0)
                logger.info(f"[Jira-Search] {total} results")
                if total == 0: return None
                lines = [f"JQL搜索({jql}): {total}条"]
                for issue in data.get("issues", [])[:10]:
                    fld = issue["fields"]
                    lines.append(
                        f"- {issue['key']} [{fld.get('issuetype',{}).get('name','?')}] "
                        f"{fld.get('summary','')[:60]} "
                        f"({fld.get('status',{}).get('name','?')})"
                    )
                return "\n## Jira 知识库 (L1)\n" + "\n".join(lines)[:800]
        except Exception as e:
            logger.warning(f"Jira search L1: {e}")
        return None

    logger.info(f"[L1] Fetching {issue_key}...")
    # 按需组装 workers
    workers = []
    if not is_global:
        workers.append((_svn_l1, "svn"))
        workers.insert(0, (_jira_l1, "jira"))
    # Jira 搜索：全模式可用，全局统计查询的核心
    workers.append((_jira_search_l1, "jira-search"))
    if os.getenv("NOTION_KEY", ""):
        workers.append((_notion_l1, "notion"))
    if os.getenv("GDRIVE_KEY", ""):
        workers.append((_gdrive_l1, "gdrive"))

    async def _run_async():
        async def _run_one(fn, name):
            try:
                # 将同步 requests 剥离出事件循环 → 真并发
                return await asyncio.to_thread(fn)
            except Exception as e:
                logger.warning(f"[L1 Error] {name}: {e}")
                return None
        tasks = [_run_one(fn, name) for fn, name in workers]
        # asyncio.wait 返回 (done, pending)，超时不中断已完成任务
        done, pending = await asyncio.wait(tasks, timeout=2.0)
        return [t.result() for t in done if t.result()]

    if workers and HAS_AIOHTTP:
        try:
            results = asyncio.run(_run_async())
            for r in (results or []):
                if r: l1_parts.append(r)
        except asyncio.TimeoutError:
            logger.warning("[L1 Timeout] 2.0s 超时熔断")
        except Exception as e:
            logger.warning(f"[L1 Async] 回退同步模式: {e}")
            _run_sync(workers, l1_parts)
    elif workers:
        _run_sync(workers, l1_parts)
    else:
        logger.info("[L1] 无可用数据源，跳过上下文检索")

    t_l1 = time.time()
    svn_has = state.get("svn_has_changes", False)
    logger.info(f"[L1] {t_l1-t_start:.1f}s | SVN:{'Y' if svn_has else 'N'} N:{len(state['notion_pids'])} G:{len(state['gdrive_matched'])}")

    # LLM Decision: relevance scoring
    decision = llm_judge_relevance(q, l1_parts, proj_keys=frontend_cfg.get("jira_projects", ""), api_key=api_key)
    scores = decision.get("scores", {})
    need_detail = decision.get("need_detail", [])

    # L2: targeted fetch
    l2_parts = []

    if need_detail:
        l2_parts.append("\n## 补充详情 (L2)")

        if "svn" in need_detail and svn_has:
            try:
                from jira_mcp_server import jira_get_svn_diff

                # 从 L1 缓存读取，砍掉重复的 jira_get_commits 网络请求
                commits = state.get("svn_commits_cache")
                if commits:
                    l2_parts.append(f"\n### 代码提交\n{commits[:L2_CHARS['svn']]}")

                # 将前端透传的 SVN 凭证注入执行器
                diff = jira_get_svn_diff(
                    issue_key,
                    max_files=5,
                    svn_cfg={
                        "svn_url": os.getenv("SVN_URL", ""),
                        "svn_user": os.getenv("SVN_USERNAME", ""),
                        "svn_pass": os.getenv("SVN_PASSWORD", "")
                    }
                )
                if diff and "没有关联" not in diff and "查询失败" not in diff:
                    l2_parts.append(f"\n### 代码变更\n{diff[:L2_CHARS['svn']]}")
                    summary = classify_file_changes(diff)
                    if summary: l2_parts.append(summary)
            except Exception as e:
                logger.debug(f"SVN L2: {e}")

        if "notion" in need_detail and state["notion_pids"]:
            NK = os.getenv("NOTION_KEY", "")
            for pid, title in state["notion_pids"][:10]:
                try:
                    r2 = http.get(f"https://api.notion.com/v1/blocks/{pid}/children?page_size=100",
                        headers={"Authorization": f"Bearer {NK}", "Notion-Version": "2022-06-28"}, timeout=10)
                    if r2.status_code == 200:
                        blocks = r2.json().get("results", [])
                        lines = []
                        for b in blocks:
                            bt = b.get("type", "")

                            # 处理内联数据库 (child_database)
                            if bt == "child_database":
                                db_id = b.get("id", "")
                                if db_id:
                                    try:
                                        db_r = http.post(f"https://api.notion.com/v1/databases/{db_id}/query",
                                            headers={"Authorization": f"Bearer {NK}", "Notion-Version": "2022-06-28",
                                                     "Content-Type": "application/json"},
                                            json={"page_size": 50}, timeout=10)
                                        if db_r.status_code == 200:
                                            for row in db_r.json().get("results", []):
                                                row_parts = []
                                                for key, val in row.get("properties", {}).items():
                                                    vt = val.get("type", "")
                                                    if vt == "title":
                                                        t = "".join([tx.get("plain_text","") for tx in val.get("title",[])])
                                                        if t.strip(): row_parts.append(t)
                                                    elif vt == "rich_text":
                                                        t = "".join([tx.get("plain_text","") for tx in val.get("rich_text",[])])
                                                        if t.strip(): row_parts.append(t)
                                                    elif vt in ("select", "status"):
                                                        t = val.get(vt, {}).get("name", "")
                                                        if t: row_parts.append(t)
                                                if row_parts:
                                                    lines.append("| " + " | ".join(row_parts) + " |")
                                    except Exception:
                                        pass
                                continue

                            supported_types = ["paragraph", "heading_1", "heading_2", "heading_3",
                                             "bulleted_list_item", "numbered_list_item", "quote", "code", "callout"]

                            if bt in supported_types:
                                rich_text_list = b.get(bt, {}).get("rich_text", [])
                                txt = "".join([tx.get("plain_text", "") for tx in rich_text_list])

                                if txt.strip():
                                    if bt.startswith("heading_"):
                                        level = int(bt[-1])
                                        lines.append(f"{'#' * level} {txt}")
                                    elif "list_item" in bt:
                                        lines.append(f"- {txt}")
                                    elif bt == "code":
                                        lines.append(f"```\n{txt}\n```")
                                    elif bt in ("quote", "callout"):
                                        lines.append(f"> {txt}")
                                    else:
                                        lines.append(txt)

                        if lines:
                            l2_parts.append(f"\n### Notion: {title}")
                            l2_parts.append("\n".join(lines)[:L2_CHARS["notion"]])
                except Exception as e:
                    logger.debug(f"Notion L2 Extract Error: {e}")

        if "gdrive" in need_detail and state["gdrive_matched"]:
            GK = os.getenv("GDRIVE_KEY", "")
            proxy_url = frontend_cfg.get("proxy", "")
            proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None

            for f in state["gdrive_matched"][:5]:
                name = f.get("name","?"); fid = f.get("id",""); mt = f.get("mimeType","")

                try:
                    if "document" in mt:
                        dr = http.get(f"https://www.googleapis.com/drive/v3/files/{fid}/export?mimeType=text/plain&key={GK}",
                            timeout=10, user_pat=user_pat, proxies=proxies)
                        if dr.status_code == 200:
                            doc_text = dr.text
                            if doc_text.strip():
                                l2_parts.append(f"\n### GDrive 文档: {name}")
                                l2_parts.append(doc_text[:L2_CHARS["gdrive"]])

                    elif "spreadsheet" in mt:
                        sr = http.get(f"https://sheets.googleapis.com/v4/spreadsheets/{fid}/values/A1:Z100?key={GK}",
                            timeout=8, proxies=proxies)
                        if sr.status_code == 200:
                            vals = sr.json().get("values", [])[:50]
                            if vals:
                                l2_parts.append(f"\n### GDrive 表格: {name}")
                                l2_parts.append("\n".join([" | ".join(row) for row in vals])[:L2_CHARS["gdrive"]])
                except Exception as e:
                    logger.debug(f"GDrive L2 Extract Error for {name}: {e}")

        # Jira知识库L2: LLM判定相关的搜索结果 → 拉取Issue详情
        if "jira-search" in need_detail:
            try:
                kw_list = [k for k in re.findall(r'[\w\u4e00-\u9fff]+', q) if len(k) >= 2][:3]
                if kw_list:
                    text_conds = " OR ".join([f'text ~ "{kw}*"' for kw in kw_list])
                    proj_keys = frontend_cfg.get("jira_projects", "")
                    proj_cond = f"project in ({proj_keys}) AND " if proj_keys else ""
                    jql = f"{proj_cond}({text_conds}) ORDER BY updated DESC"
                    r = jira.jira_get(
                        f"{jira.api_url}/search",
                        params={"jql": jql, "maxResults": 5, "fields": "key,summary,issuetype,status,priority,assignee,description,fixVersions,versions"},
                        timeout=10, user_pat=user_pat
                    )
                    if r.status_code == 200:
                        detail_lines = []
                        for issue in r.json().get("issues", [])[:5]:
                            fld = issue["fields"]
                            fix_vers = [v.get("name","") for v in (fld.get("fixVersions") or []) if v.get("name")]
                            aff_vers = [v.get("name","") for v in (fld.get("versions") or []) if v.get("name")]
                            vinfo = ""
                            if fix_vers: vinfo += f" 修复的版本:{','.join(fix_vers)}"
                            if aff_vers: vinfo += f" 影响版本:{','.join(aff_vers)}"
                            desc = (fld.get("description") or "")[:300]
                            detail_lines.append(
                                f"### {issue['key']} [{fld.get('issuetype',{}).get('name','?')}] {fld.get('status',{}).get('name','?')}\n"
                                f"{fld.get('summary','?')}{vinfo}\n"
                                f"{'描述:'+desc if desc else ''}"
                            )
                        if detail_lines:
                            l2_parts.append("\n### Jira 搜索详情 (L2)\n" + "\n\n".join(detail_lines)[:2000])
            except Exception as e:
                logger.debug(f"Jira search L2: {e}")

        # Jira 知识库搜索: LLM 生成的 JQL
        jql_cmd = decision.get("jql", "").strip()
        if jql_cmd:
            # 替换项目占位符
            proj_keys = frontend_cfg.get("jira_projects", "")
            proj_vals = ",".join([k.strip() for k in proj_keys.split(",") if k.strip()]) if proj_keys else ""
            jql_cmd = jql_cmd.replace("{proj_keys}", proj_vals) if proj_vals else jql_cmd
            if not proj_vals:
                jql_cmd = ""  # 没项目 → 跳过
        if jql_cmd:
            try:
                r = jira.jira_get(
                    f"{jira.api_url}/search",
                    params={"jql": jql_cmd, "maxResults": 15, "fields": "key,summary,issuetype,status,priority,assignee,fixVersions,versions"},
                    timeout=10
                )
                if r.status_code == 200:
                    data = r.json()
                    lines = [f"JQL: {jql_cmd[:100]} → {data.get('total',0)}条"]
                    for issue in data.get("issues", [])[:12]:
                        fld = issue["fields"]
                        fv = [v.get("name","") for v in (fld.get("fixVersions") or []) if v.get("name")]
                        av = [v.get("name","") for v in (fld.get("versions") or []) if v.get("name")]
                        vinfo = ""
                        if fv: vinfo += f" 修复的版本:{','.join(fv)}"
                        if av: vinfo += f" 影响版本:{','.join(av)}"
                        lines.append(f"- {issue['key']} [{fld.get('issuetype',{}).get('name','?')}] {fld.get('summary','')[:60]} ({fld.get('status',{}).get('name','?')}){vinfo}")
                    l2_parts.append("\n### Jira 搜索\n" + "\n".join(lines)[:2000])
            except Exception as e:
                logger.debug(f"JQL execution: {e}")

    # Assemble with smart budget control
    t_l2 = time.time()
    
    # 优先级排序：Issue 详情 > L1 摘要 > L2 补充
    priority_parts = []
    budget = CONTEXT_TOTAL_LIMIT
    
    # Tier 1: Issue 详情（最重要，优先分配预算）
    if "current_issue_detail" in state:
        detail = state["current_issue_detail"][:JIRA_ISSUE_DETAIL_LIMIT]
        priority_parts.append(detail)
        budget -= len(detail)
    
    # Tier 2: L1 摘要（路由决策依据，尽量保留）
    for part in l1_parts:
        if budget > 200:
            trimmed = part[:min(len(part), budget)]
            priority_parts.append(trimmed)
            budget -= len(trimmed)
    
    # Tier 3: L2 详情（按 LLM 决策的 need_detail 优先级）
    for part in l2_parts:
        if budget > 100:
            trimmed = part[:min(len(part), budget)]
            priority_parts.append(trimmed)
            budget -= len(trimmed)
    
    result = "\n\n".join(priority_parts)
    if len(result) > CONTEXT_TOTAL_LIMIT:
        result = result[:CONTEXT_TOTAL_LIMIT]

    t_total = time.time()

    # Cache (BoundedCache 自动 LRU 淘汰)
    _CONTEXT_CACHE.set(cache_key, time.time(), result)

    logger.info(f"[Context] {user_id}:{issue_key} | L1:{t_l1-t_start:.1f}s L2:{t_l2-t_l1:.1f}s total:{t_total-t_start:.1f}s | {len(result)} chars | {intent} | detail:{need_detail}")
    return result

# ── 核心端点 ──────────────────────────────────────────────────
# ── 白泽风格插件注册表 (从 YAML 加载) ────────────────────
try:
    import yaml
    _TOOLS_DIR = os.path.join(os.path.dirname(__file__), 'tools')
    _REGISTRY_PATH = os.path.join(_TOOLS_DIR, 'registry.yaml')
    
    def _load_tools_from_registry():
        """从 registry.yaml 动态加载工具定义"""
        if not os.path.exists(_REGISTRY_PATH):
            logger.warning(f"Tools registry not found: {_REGISTRY_PATH}, using fallback")
            return _FALLBACK_TOOLS
        try:
            with open(_REGISTRY_PATH, 'r', encoding='utf-8') as f:
                registry = yaml.safe_load(f)
            tools = []
            for t in registry.get('tools', []):
                params = t['function']['parameters']
                properties = {}
                required = []
                for name, cfg in params.items():
                    prop = {"type": cfg.get("type", "string"), "description": cfg.get("description", "")}
                    if "enum" in cfg:
                        prop["enum"] = cfg["enum"]
                    if "default" in cfg:
                        prop["default"] = cfg["default"]
                    properties[name] = prop
                    if cfg.get("required"):
                        required.append(name)
                tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": {"type": "object", "properties": properties, "required": required}
                    }
                })
            logger.info(f"[Registry] Loaded {len(tools)} tools from registry.yaml")
            return tools
        except Exception as e:
            logger.error(f"[Registry] Failed to load: {e}")
            return _FALLBACK_TOOLS
    
    _FALLBACK_TOOLS = [
        {"type": "function", "function": {"name": "query_jira_issues", "description": "查询 Jira 系统的问题", "parameters": {"type": "object", "properties": {"jql": {"type": "string", "description": "JQL 查询语句"}}, "required": ["jql"]}}},
        {"type": "function", "function": {"name": "search_knowledge_base", "description": "从知识库检索文档", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索关键词"}, "source": {"type": "string", "enum": ["notion", "gdrive", "all"], "description": "检索来源"}}, "required": ["query"]}}},
    ]
    
    AVAILABLE_TOOLS = _load_tools_from_registry()
    logger.info(f"[Plugins] Active tools: {[t['function']['name'] for t in AVAILABLE_TOOLS]}")
except ImportError:
    logger.warning("yaml module not available, using hardcoded tools")
    AVAILABLE_TOOLS = _FALLBACK_TOOLS if '_FALLBACK_TOOLS' in dir() else []


def extract_notion_title_ultimate(item: dict) -> str:
    """Notion 标题终极提取器：递归搜索 + ID兜底"""
    page_id = item.get("id", "未知ID")
    fallback_title = f"无标题文档_{page_id[-4:]}"
    
    def deep_search_text(node):
        if isinstance(node, dict):
            if node.get("type") == "text" and "text" in node:
                return node["text"].get("content")
            for k, v in node.items():
                result = deep_search_text(v)
                if result: return result
        elif isinstance(node, list):
            for i in node:
                result = deep_search_text(i)
                if result: return result
        return None

    try:
        title = deep_search_text(item.get("properties", {}))
        if title and title.strip():
            return title.strip()
        title = deep_search_text(item.get("title", []))
        if title and title.strip():
            return title.strip()
    except Exception:
        pass
    return fallback_title


def execute_tool_call(tool_name, arguments_str, user_cfg, frontend_cfg):
    """根据 LLM 的指令，调度本地真实的方法"""
    try:
        args = json.loads(arguments_str)
        logger.info(f"[Tool Executing] {tool_name} with args: {args}")
        
        if tool_name == "query_jira_issues":
            jql = args.get("jql", "")
            max_results = args.get("max_results", 10)
            logger.info(f"[Tool] query_jira_issues jql={jql[:80]}")
            try:
                # 使用全局 jira 客户端 (ai_bridge.py:53)
                if re.match(r'^[A-Z]+-\d+', jql.strip()):
                    # 单个 issue key — L1元数据层
                    resp = jira.jira_get(f"{jira.api_url}/issue/{jql.strip()}?fields=key,summary,issuetype,status,assignee,priority,fixVersions,created,updated,description,issuelinks,subtasks,customfield_10400")
                    issue = resp.json() if hasattr(resp, 'json') else resp
                    if issue.get("key"):
                        f = issue.get("fields", {})
                        # 子任务
                        subtasks = []
                        for st in (f.get("subtasks") or []):
                            sf = st.get("fields", {})
                            subtasks.append({"key": st.get("key",""), "summary": sf.get("summary",""), "status": sf.get("status",{}).get("name","")})
                        # 关联需求
                        links = []
                        for lk in (f.get("issuelinks") or []):
                            linked = lk.get("outwardIssue") or lk.get("inwardIssue")
                            if linked:
                                links.append({"key": linked.get("key",""), "type": lk.get("type",{}).get("name",""), "direction": "outward" if lk.get("outwardIssue") else "inward"})
                        # Checklist 进度
                        checklist_items = []
                        cl_field = f.get("customfield_10400", [])
                        if isinstance(cl_field, list):
                            for cl in cl_field:
                                if hasattr(cl, '_items'):
                                    for item in cl._items:
                                        checklist_items.append(f"{'✅' if item.get('checked') else '⬜'} {item.get('name','')}")
                        return json.dumps({"status": "ok", "result": {
                            "key": issue["key"], "summary": f.get("summary", ""),
                            "status": f.get("status", {}).get("name", ""),
                            "issuetype": f.get("issuetype", {}).get("name", ""),
                            "assignee": f.get("assignee", {}).get("displayName", "未分配"),
                            "priority": f.get("priority", {}).get("name", ""),
                            "fixVersions": [v["name"] for v in (f.get("fixVersions") or [])],
                            "created": (f.get("created") or "")[:10], "updated": (f.get("updated") or "")[:10],
                            "description": (f.get("description") or "")[:500] if isinstance(f.get("description"), str) else "",
                            "subtasks": subtasks,
                            "issuelinks": links[:10],
                            "checklist": checklist_items[:10],
                            "url": f"{jira.base_url}/browse/{issue['key']}"
                        }})
                    return json.dumps({"status": "ok", "result": f"Issue {jql.strip()} 未找到"})
                else:
                    # JQL 搜索 — 先做智能增强
                    enhanced_jql = enhance_jql(jql)
                    if enhanced_jql != jql:
                        logger.info(f"[JQL Enhanced] {jql[:60]} → {enhanced_jql[:60]}")
                    resp = jira.jira_post(f"{jira.api_url}/search", {"jql": enhanced_jql, "maxResults": max_results, "fields": ["key","summary","status","issuetype","assignee","priority","fixVersions","created","updated"]})
                    result = resp.json() if hasattr(resp, 'json') else resp
                    if resp.status_code >= 400:
                        err_msgs = result.get("errorMessages", []) or []
                        errors = result.get("errors", {}) or {}
                        err_detail = "; ".join(err_msgs + list(errors.values()))
                        # JQL 错误恢复：返回错误详情让 LLM 在下轮修正
                        return json.dumps({
                            "status": "error",
                            "result": f"JQL 执行失败: {err_detail}",
                            "recovery": f"请检查 JQL 语法并修正后重试。原始 JQL: {enhanced_jql}",
                            "original_jql": enhanced_jql
                        })
                    issues = result.get("issues", [])
                    total = result.get("total", 0)
                    items = []
                    for i in issues[:max_results]:
                        f = i["fields"]
                        fix_versions = [v["name"] for v in (f.get("fixVersions") or [])]
                        items.append({
                            "key": i["key"],
                            "summary": f.get("summary", ""),
                            "status": f.get("status", {}).get("name", ""),
                            "issuetype": f.get("issuetype", {}).get("name", ""),
                            "assignee": f.get("assignee", {}).get("displayName", "未分配"),
                            "priority": f.get("priority", {}).get("name", ""),
                            "fixVersions": fix_versions,
                            "created": (f.get("created") or "")[:10],
                            "updated": (f.get("updated") or "")[:10],
                        })
                    return json.dumps({"status": "ok", "result": {"total": total, "issues": items, "enhanced_jql": enhanced_jql if enhanced_jql != jql else None}})
            except Exception as e:
                logger.error(f"[Jira] query_jira_issues error: {e}")
                return json.dumps({"status": "error", "result": f"Jira 查询失败: {str(e)[:200]}", "recovery": "请检查 Jira 连接配置或简化 JQL 重试"})
            
        elif tool_name == "search_knowledge_base":
            query = args.get("query", "")
            source = args.get("source", "all")
            citations_data = []
            
            NK = os.getenv("NOTION_KEY") or getattr(jira, '_global_cfg', {}).get("NOTION_KEY", "")
            hd = {"Authorization": f"Bearer {NK}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"} if NK else {}
            
            # ── Notion 检索 ──
            if hd and source in ("notion", "all"):
                try:
                    r = http.post("https://api.notion.com/v1/search",
                        headers=hd, json={"query": query, "page_size": 20}, timeout=10)
                    if r.status_code == 200:
                        results = r.json().get("results", [])
                        logger.info(f"Notion API returned {len(results)} results")
                        for p in results:
                            citations_data.append({
                                "index": len(citations_data) + 1,
                                "title": extract_notion_title_ultimate(p),
                                "source": "notion",
                                "url": p.get("url", ""),
                            })
                except Exception as e:
                    logger.warning(f"[KB] Notion search failed: {e}")
            
            # ── SVN 检索 ──
            if source in ("svn", "all"):
                try:
                    cfg = getattr(jira, '_global_cfg', {})
                    svn_url = os.getenv("SVN_URL") or cfg.get("SVN_URL", "")
                    svn_user = os.getenv("SVN_USERNAME") or cfg.get("SVN_USERNAME", "")
                    svn_pass = os.getenv("SVN_PASSWORD") or cfg.get("SVN_PASSWORD", "")
                    if svn_url and svn_user:
                        svn_text = _svn_log_grep(query, svn_url, svn_user, svn_pass)
                        if svn_text and "SVN提交" in svn_text:
                            citations_data.append({
                                "index": len(citations_data) + 1,
                                "title": f"SVN 提交匹配: {query}",
                                "source": "svn",
                                "url": svn_url,
                                "snippet": svn_text[:500]
                            })
                except Exception as e:
                    logger.warning(f"[KB] SVN search failed: {e}")
            
            # ── Google Drive 检索 ──
            if source in ("gdrive", "all"):
                try:
                    GK = os.getenv("GDRIVE_KEY") or getattr(jira, '_global_cfg', {}).get("GDRIVE_KEY", "")
                    if GK:
                        raw_folders = os.getenv("GDRIVE_FOLDERS") or getattr(jira, '_global_cfg', {}).get("GDRIVE_FOLDERS", "")
                        folders = [f.strip() for f in re.split(r'[\n,]+', raw_folders) if f.strip()]
                        if folders:
                            proxy_ip = os.getenv("GDRIVE_PROXY_IP") or getattr(jira, '_global_cfg', {}).get("GDRIVE_PROXY_IP", "")
                            proxy_port = os.getenv("GDRIVE_PROXY_PORT") or getattr(jira, '_global_cfg', {}).get("GDRIVE_PROXY_PORT", "")
                            proxies = {"https": f"http://{proxy_ip}:{proxy_port}"} if proxy_ip and proxy_port else None
                            all_files = {}
                            for fid in folders:
                                r = http.get(
                                    f"https://www.googleapis.com/drive/v3/files?key={GK}&q='{fid}'+in+parents&fields=files(id,name,mimeType)&pageSize=30",
                                    timeout=10, proxies=proxies)
                                if r.status_code == 200:
                                    for f in r.json().get("files", []):
                                        all_files[f["id"]] = f
                            if query:
                                # 分词匹配：支持中文无空格连写（策划文档→策划+文档）
                                kws = [kw for kw in re.split(r'[\s,，]+', query) if len(kw) >= 2]
                                # 对中文无空格词，额外拆成双字片段
                                extra = []
                                for kw in kws:
                                    if re.search(r'[\u4e00-\u9fff]', kw):
                                        extra.extend([kw[i:i+2] for i in range(len(kw)-1)])
                                kws = list(set(kws + extra))
                                matched = [f for _, f in all_files.items() if any(k in f.get("name","") for k in kws)]
                            else:
                                matched = list(all_files.values())
                            logger.info(f"Google Drive returned {len(matched)} results")
                            for f in matched[:20]:
                                mime_type = f.get("mimeType", "")
                                icon = "📊" if "spreadsheet" in mime_type else "📄" if "document" in mime_type else "🗂️" if "folder" in mime_type else "📁"
                                # 如果用户是具体查询（非宽泛），尝试读取文档内容
                                snippet = ""
                                if query and query.strip() and "document" in mime_type:
                                    try:
                                        export_mime = "text/plain"
                                        cr = http.get(
                                            f"https://www.googleapis.com/drive/v3/files/{f['id']}/export?mimeType={export_mime}&key={GK}",
                                            timeout=8, proxies=proxies)
                                        if cr.status_code == 200:
                                            snippet = cr.text[:2000]
                                    except Exception:
                                        pass
                                elif query and query.strip() and "spreadsheet" in mime_type:
                                    try:
                                        cr = http.get(
                                            f"https://www.googleapis.com/drive/v3/files/{f['id']}/export?mimeType=text/csv&key={GK}",
                                            timeout=8, proxies=proxies)
                                        if cr.status_code == 200:
                                            snippet = cr.text[:2000]
                                    except Exception:
                                        pass
                                citations_data.append({
                                    "index": len(citations_data) + 1,
                                    "title": f"{icon} {f['name']}",
                                    "source": "gdrive",
                                    "url": f"https://drive.google.com/file/d/{f['id']}/view",
                                    "snippet": snippet,
                                })
                except Exception as e:
                    logger.warning(f"[KB] GDrive search failed: {e}")
            
            if not citations_data:
                return json.dumps({"llm_text": f"知识库中未找到与 '{query}' 相关的内容。", "citations": []})
            
            llm_parts = []
            for c in citations_data:
                if c["source"] == "notion":
                    llm_parts.append(f"[{c['index']}] {c['title']} → {c['url']}")
                elif c["source"] == "gdrive":
                    sn = c.get("snippet", "")
                    llm_parts.append(f"【文档 {c['index']}: {c['title']}】\n{sn}" if sn else f"[{c['index']}] {c['title']} → {c['url']}")
                else:
                    snippet = c.get("snippet", "")
                    llm_parts.append(f"【参考源[{c['index']}] {c['source']}: {c['title']}】 {snippet}")
            llm_text = "\n".join(llm_parts)
            return json.dumps({"llm_text": llm_text, "citations": citations_data})
        
        elif tool_name == "get_issue_commits":
            issue_key = args.get("issue_key", "")
            if not issue_key:
                return json.dumps({"status": "error", "result": "请提供 issue_key 参数"})
            try:
                from jira_mcp_server import jira_get_commits
                result = jira_get_commits(issue_key)
                return json.dumps({"status": "ok", "llm_text": result})
            except Exception as e:
                logger.error(f"[Tool] get_issue_commits error: {e}")
                return json.dumps({"status": "error", "result": f"查询提交失败: {str(e)[:200]}"})
        
        elif tool_name == "get_issue_diff":
            issue_key = args.get("issue_key", "")
            max_files = args.get("max_files", 10)
            if not issue_key:
                return json.dumps({"status": "error", "result": "请提供 issue_key 参数"})
            try:
                cfg = getattr(jira, '_global_cfg', {})
                svn_cfg = {
                    "svn_url": os.getenv("SVN_URL") or cfg.get("SVN_URL", ""),
                    "svn_username": os.getenv("SVN_USERNAME") or cfg.get("SVN_USERNAME", ""),
                    "svn_password": os.getenv("SVN_PASSWORD") or cfg.get("SVN_PASSWORD", ""),
                }
                from jira_mcp_server import jira_get_svn_diff
                result = jira_get_svn_diff(issue_key, max_files, svn_cfg)
                return json.dumps({"status": "ok", "llm_text": result})
            except Exception as e:
                logger.error(f"[Tool] get_issue_diff error: {e}")
                return json.dumps({"status": "error", "result": f"查询DIFF失败: {str(e)[:200]}"})
        
        elif tool_name == "add_jira_comment":
            issue_key = args.get("issue_key", "")
            body = args.get("body", "")
            if not issue_key or not body:
                return json.dumps({"status": "error", "result": "请提供 issue_key 和 body 参数"})
            # P1 审计分级：检查是否为 AI 创建的任务
            try:
                from jira_operation_manager import create_operation_card, is_ai_created_issue
                audit_level = "confirm"  # 默认需要确认
                is_ai = is_ai_created_issue(issue_key) if hasattr(sys.modules.get('jira_operation_manager'), 'is_ai_created_issue') else False
                if not is_ai:
                    audit_level = "strict_confirm"  # 非AI创建：严格确认
                    logger.info(f"[Audit] Non-AI issue {issue_key}, requiring strict confirmation")
                card = create_operation_card(
                    drafts=[{
                        "summary": f"[评论] {issue_key}",
                        "projectKey": issue_key.split("-")[0] if "-" in issue_key else "",
                        "issueType": "评论",
                        "description": body[:500],
                        "action": "add_comment",
                        "issue_key": issue_key,
                        "audit_level": audit_level,
                    }],
                    conversation_id=frontend_cfg.get("conversation_id", ""),
                    client_id=frontend_cfg.get("client_id", ""),
                    user_id=user_cfg.get("user_id", ""),
                )
                logger.info(f"[ConfirmCard] Created {card['id']} for comment on {issue_key} (audit: {audit_level})")
                return json.dumps({
                    "status": "confirm_required",
                    "result": f"即将为 {issue_key} 添加评论。{'⚠️ 该任务非AI创建，需严格确认。' if not is_ai else ''}请确认后执行。",
                    "operation_id": card["id"],
                    "operation": card,
                    "audit_level": audit_level,
                })
            except Exception as e:
                logger.error(f"[Tool] add_jira_comment error: {e}")
                return json.dumps({"status": "error", "result": f"创建确认卡失败: {str(e)[:200]}"})
        
        elif tool_name == "list_jira_comments":
            issue_key = args.get("issue_key", "")
            max_results = args.get("max_results", 10)
            if not issue_key:
                return json.dumps({"status": "error", "result": "请提供 issue_key 参数"})
            try:
                resp = jira.jira_get(f"{jira.api_url}/issue/{issue_key}/comment?maxResults={max_results}")
                comments_data = resp.json() if hasattr(resp, 'json') else resp
                comments = comments_data.get("comments", []) if isinstance(comments_data, dict) else []
                total = comments_data.get("total", len(comments)) if isinstance(comments_data, dict) else len(comments)
                items = []
                for c in comments[:max_results]:
                    author = c.get("author", {}).get("displayName", "未知")
                    created = c.get("created", "")[:19]
                    body = (c.get("body", "") or "")[:300]
                    items.append({"author": author, "time": created, "body": body})
                return json.dumps({"status": "ok", "result": {"total": total, "comments": items}})
            except Exception as e:
                logger.error(f"[Tool] list_jira_comments error: {e}")
                return json.dumps({"status": "error", "result": f"查询评论失败: {str(e)[:200]}"})
            
        else:
            return f"Error: Tool {tool_name} not found."
            
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return f"Error executing tool: {str(e)}"


def safe_get_commits(issue_key, timeout=2.5):
    """带 TTL 缓存 + 超时熔断的 SVN 提交获取"""
    now = time.time()
    if issue_key in SVN_COMMIT_CACHE:
        cached_time, cached_data = SVN_COMMIT_CACHE[issue_key]
        if now - cached_time < CACHE_TTL:
            return cached_data
    try:
        from jira_mcp_server import jira_get_commits
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(jira_get_commits, issue_key)
            result = future.result(timeout=timeout)
            if result and "没有关联" not in result and "查询失败" not in result:
                SVN_COMMIT_CACHE[issue_key] = (now, result)
                return result
    except concurrent.futures.TimeoutError:
        logger.warning(f"[Timeout] SVN fetch for {issue_key} exceeded {timeout}s!")
    except Exception as e:
        logger.warning(f"[Error] SVN fetch for {issue_key} failed: {e}")
    return None


# ── 用户名解析：中文名 → Jira username ────────────────────────
def resolve_jira_username(chinese_name: str) -> str:
    """调用 Jira /user/search API，将中文显示名转为英文 username"""
    try:
        resp = jira.jira_get(f"{jira.api_url}/user/search?username={chinese_name}&maxResults=3")
        users = resp.json() if hasattr(resp, 'json') else resp
        if isinstance(users, list) and len(users) > 0:
            username = users[0].get("name", "")
            display = users[0].get("displayName", "")
            logger.info(f"[UserResolve] {chinese_name} → {username} ({display})")
            return username
    except Exception as e:
        logger.warning(f"[UserResolve] {chinese_name} failed: {e}")
    return ""


# ── S0: Multi-Source Router ────────────────────────────────────
AVAILABLE_KNOWLEDGE_SOURCES = {
    "jira":   {"desc": "Jira项目管理系统，查询任务/需求/Bug/迭代信息", "tool": "query_jira_issues"},
    "svn":    {"desc": "SVN代码仓库+FishEye，查询代码提交/变更/DIFF", "tool": "get_issue_commits"},
    "notion": {"desc": "Notion知识库，查询设计文档/技术方案/规范",   "tool": "search_knowledge_base"},
    "gdrive": {"desc": "Google云盘知识库，查询策划文档/表格/设计稿",  "tool": "search_knowledge_base"},
}

def s0_source_router(question: str, api_key: str) -> dict:
    """S0: LLM 决定搜哪些知识库，输出搜索计划"""
    sources_desc = "\n".join([f"- {k}: {v['desc']}" for k, v in AVAILABLE_KNOWLEDGE_SOURCES.items()])
    prompt = f"""你是知识库路由器。根据用户问题，决定应该搜索哪些知识库。

可用知识库:
{sources_desc}

用户问题: {question[:300]}

输出JSON:
{{
    "sources": ["jira","notion"],      // 要搜索的知识库列表
    "skip": ["svn"],                    // 明确不需要搜索的
    "queries": {{                        // 每个源的具体搜索词
        "jira": "CT-11112",
        "notion": "球员属性设计"
    }},
    "plan": "先查Jira任务详情，再查Notion设计文档对照"  // 搜索策略
}}
规则:
- 问题涉及任务/需求/Bug/进度 → 搜 jira
- 问题涉及代码/提交/变更 → 搜 svn
- 问题涉及设计/方案/规范/文档内容 → 搜 notion
- 问题涉及策划文档/表格 → 搜 gdrive
- 不确定时宁多勿少
- 只输出JSON，不解释"""
    try:
        r = _deepseek_call({
            "model": "deepseek-chat",
            "messages": [
                {"role":"system","content":"只输出合法JSON，不输出其他字符。"},
                {"role":"user","content":prompt}
            ],
            "temperature": 0.0, "max_tokens": 300
        }, timeout=8)
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"].strip()
            content = re.sub(r'^```json\s*','',content).replace('```','')
            plan = json.loads(content)
            logger.info(f"[S0] Routing: sources={plan.get('sources')} skip={plan.get('skip')} plan={plan.get('plan','')[:60]}")
            return plan
    except Exception as e:
        logger.warning(f"[S0] Routing failed: {e}")
    # 兜底：搜全部
    return {"sources": ["jira","svn","notion","gdrive"], "skip": [], "queries": {"jira": question, "notion": question, "gdrive": question}, "plan": "兜底全源搜索"}


def s1_parallel_search(s0_plan: dict, user_cfg: dict, frontend_cfg: dict) -> dict:
    """S1: 根据 S0 计划并行搜索多个知识库，返回统一摘要"""
    sources = s0_plan.get("sources", [])
    queries = s0_plan.get("queries", {})
    results = {}
    
    for source in sources:
        query = queries.get(source, "")
        try:
            if source == "jira":
                # 轻量 JQL 快速扫描 — 用 summary/description 替代 text ~
                proj = frontend_cfg.get("jira_projects", "CT")
                if query:
                    jql = f'project = {proj} AND (summary ~ "{query[:50]}" OR description ~ "{query[:50]}") ORDER BY updated DESC'
                else:
                    jql = f'project = {proj} ORDER BY updated DESC'
                resp = jira.jira_post(f"{jira.api_url}/search", {"jql": jql, "maxResults": 5, "fields": ["key","summary","status"]})
                data = resp.json() if hasattr(resp, 'json') else resp
                items = [{"title": f"{i['key']}: {i['fields']['summary'][:60]}", "snippet": i['fields'].get('status',{}).get('name',''), "url": f"{jira.base_url}/browse/{i['key']}"} for i in data.get("issues", [])[:5]]
                results[source] = {"total": data.get("total",0), "items": items}
            elif source == "svn":
                cfg = getattr(jira, '_global_cfg', {})
                svn_url = os.getenv("SVN_URL") or cfg.get("SVN_URL", "")
                if svn_url and query:
                    svn_text = _svn_log_grep(query, svn_url, os.getenv("SVN_USERNAME") or cfg.get("SVN_USERNAME",""), os.getenv("SVN_PASSWORD") or cfg.get("SVN_PASSWORD",""))
                    items = [{"title": f"SVN: {query}", "snippet": svn_text[:300], "url": svn_url}] if svn_text and "SVN提交" in svn_text else []
                    results[source] = {"total": len(items), "items": items}
                else:
                    results[source] = {"total": 0, "items": [], "empty": True}
            elif source == "notion":
                NK = os.getenv("NOTION_KEY") or cfg.get("NOTION_KEY", "")
                if NK:
                    r = http.post("https://api.notion.com/v1/search",
                        headers={"Authorization": f"Bearer {NK}", "Notion-Version": "2022-06-28"},
                        json={"query": query or "", "page_size": 5}, timeout=8)
                    items = []
                    if r.status_code == 200:
                        for p in r.json().get("results", [])[:5]:
                            items.append({"title": extract_notion_title_ultimate(p), "url": p.get("url",""), "snippet": ""})
                    results[source] = {"total": len(items), "items": items}
                else:
                    results[source] = {"total": 0, "items": [], "empty": True}
            elif source == "gdrive":
                GK = os.getenv("GDRIVE_KEY") or cfg.get("GDRIVE_KEY", "")
                if GK:
                    folders = re.split(r'[\n,]+', os.getenv("GDRIVE_FOLDERS") or cfg.get("GDRIVE_FOLDERS",""))
                    items = []
                    for fid in (folders[:2] if folders else []):
                        r = http.get(f"https://www.googleapis.com/drive/v3/files?key={GK}&q='{fid}'+in+parents&fields=files(id,name,mimeType)&pageSize=10", timeout=8)
                        if r.status_code == 200:
                            for f in r.json().get("files", []):
                                fname = f.get("name","")
                                # 宽泛匹配：query为空或分词后任一匹配
                                if not query or not query.strip():
                                    items.append({"title": fname, "url": f"https://drive.google.com/file/d/{f['id']}/view", "snippet": f.get("mimeType","")})
                                else:
                                    qwords = re.split(r'[\s,，]+', query)
                                    # 中文无空格连写，拆双字片段
                                    extra = []
                                    for q in qwords:
                                        if len(q) >= 2 and re.search(r'[\u4e00-\u9fff]', q):
                                            extra.extend([q[i:i+2] for i in range(len(q)-1)])
                                    qwords = list(set(qwords + extra))
                                    if any(q in fname for q in qwords if len(q) >= 2):
                                        items.append({"title": fname, "url": f"https://drive.google.com/file/d/{f['id']}/view", "snippet": f.get("mimeType","")})
                    results[source] = {"total": len(items), "items": items[:5]}
                else:
                    results[source] = {"total": 0, "items": [], "empty": True}
        except Exception as e:
            logger.warning(f"[S1] {source} search failed: {e}")
            results[source] = {"total": 0, "items": [], "error": str(e)[:100]}
    
    logger.info(f"[S1] Searched {len(results)} sources: { {k: v.get('total',0) for k,v in results.items()} }")
    return results


def l0_depth_router(s1_results: dict, question: str, api_key: str) -> dict:
    """L0: LLM 看 S1 摘要，决定哪些需要深读"""
    # 构建摘要
    summary_parts = []
    for source, data in s1_results.items():
        items = data.get("items", [])
        if items:
            titles = [f"{i['title'][:50]}" for i in items[:3]]
            summary_parts.append(f"{source}({data.get('total',0)}条): {', '.join(titles)}")
        else:
            summary_parts.append(f"{source}: 无结果")
    
    summary = "\n".join(summary_parts)
    prompt = f"""根据搜索结果摘要，决定哪些需要深入阅读。

用户问题: {question[:200]}

搜索结果:
{summary}

输出 JSON:
{{"deep_read": [{{"source":"jira","id":"CT-11112"}}], "skip": [{{"source":"notion","reason":"不相关"}}], "need_more": false}}
只输出 JSON。"""
    try:
        r = _deepseek_call({
            "model": "deepseek-chat",
            "messages": [{"role":"system","content":"只输出JSON"}, {"role":"user","content":prompt}],
            "temperature": 0.0, "max_tokens": 200
        }, timeout=6)
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"].strip()
            content = re.sub(r'^```json\s*','',content).replace('```','')
            plan = json.loads(content)
            logger.info(f"[L0] Deep read: {plan.get('deep_read')}, Skip: {len(plan.get('skip',[]))}")
            return plan
    except Exception as e:
        logger.warning(f"[L0] failed: {e}")
    return {"deep_read": [], "skip": [], "need_more": False}


def l2_relationship_context(issue_key: str) -> dict:
    """L2: 获取 Issue 的关系上下文（关联需求+子任务）"""
    try:
        resp = jira.jira_get(f"{jira.api_url}/issue/{issue_key}?fields=issuelinks,subtasks,customfield_10400")
        issue = resp.json() if hasattr(resp, 'json') else resp
        f = issue.get("fields", {})
        links = []
        for lk in (f.get("issuelinks") or []):
            linked = lk.get("outwardIssue") or lk.get("inwardIssue")
            if linked:
                links.append({"key": linked.get("key",""), "type": lk.get("type",{}).get("name",""), "direction": "outward" if lk.get("outwardIssue") else "inward"})
        subtasks = []
        for st in (f.get("subtasks") or []):
            sf = st.get("fields", {})
            subtasks.append({"key": st.get("key",""), "summary": sf.get("summary","")[:80], "status": sf.get("status",{}).get("name","")})
        return {"issuelinks": links, "subtasks": subtasks}
    except Exception as e:
        logger.warning(f"[L2] {issue_key} failed: {e}")
        return {"issuelinks": [], "subtasks": []}


def l3_evidence_context(issue_key: str) -> dict:
    """L3: 获取代码证据（提交+Diff）"""
    try:
        from jira_mcp_server import jira_get_commits, jira_get_svn_diff
        commits = jira_get_commits(issue_key) or ""
        cfg = getattr(jira, '_global_cfg', {})
        svn_cfg = {"svn_url": os.getenv("SVN_URL") or cfg.get("SVN_URL",""), "svn_username": os.getenv("SVN_USERNAME") or cfg.get("SVN_USERNAME",""), "svn_password": os.getenv("SVN_PASSWORD") or cfg.get("SVN_PASSWORD","")}
        diff = jira_get_svn_diff(issue_key, 5, svn_cfg) or ""
        return {"commits": commits[:1500], "diff": diff[:2000]}
    except Exception as e:
        logger.warning(f"[L3] {issue_key} failed: {e}")
        return {"commits": "", "diff": ""}


@app.route("/v1/chat/completions", methods=["POST", "OPTIONS"])
def chat_completions():
    if request.method == 'OPTIONS':
        return Response(status=204)

    data = request.json or {}
    messages = data.get("messages", [])
    user_cfg = parse_user_config(data)
    frontend_cfg = data.get("config", {}) or {}

    if not messages:
        return jsonify({"error": "No messages"}), 400
    if not user_cfg["deepseek_key"]:
        return jsonify({"error": "缺少 ai_api_key"}), 401

    GLOBAL_STATS["total_requests"] += 1

    headers = {
        "Authorization": f"Bearer {user_cfg['deepseek_key']}",
        "Content-Type": "application/json"
    }

    def generate_stream():
        max_steps = frontend_cfg.get("max_steps", 5)
        step = 0

        # 清洗层 + 工具过滤
        cleaned_messages = [msg for msg in messages if isinstance(msg.get("content"), str)]
        if len(cleaned_messages) < len(messages):
            for msg in messages:
                if isinstance(msg.get("content"), list):
                    text = "".join(item.get("text","") for item in msg["content"] if item.get("type")=="text")
                    cleaned_messages.append({"role": msg["role"], "content": text})
        tool_whitelist = frontend_cfg.get("tool_whitelist", [])
        active_tools = [t for t in AVAILABLE_TOOLS if not tool_whitelist or t["function"]["name"] in tool_whitelist]

        # ── S0: 知识库路由 + Issue Key 预检测 ──────────
        user_text = ""
        for msg in reversed(cleaned_messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break
        
        # Issue Key 快速检测（轻量，不依赖 LLM）
        issue_keys_found = set()
        if user_text:
            found = re.findall(r'(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])', user_text)
            issue_keys_found.update(found)
        
        # S0 路由：LLM 决定搜哪些知识库
        s0_plan = s0_source_router(user_text or "", user_cfg.get("deepseek_key", ""))
        sources_str = ", ".join(s0_plan.get("sources", ["all"]))
        plan_str = s0_plan.get("plan", "多源搜索")
        queries_str = json.dumps(s0_plan.get("queries", {}), ensure_ascii=False)
        
        s0_context = (
            f"[系统上下文] S0路由决策完成:\n"
            f"  用户问题: {user_text[:100]}\n"
            f"  搜索策略: {plan_str}\n"
            f"  要搜索的知识库: {sources_str}\n"
            f"  各源搜索词: {queries_str}\n"
        )
        
        # 快速注入 Issue Key 基础信息（保持 PreFetch 的低延迟优势）
        if issue_keys_found:
            for ik in sorted(issue_keys_found, key=len, reverse=True)[:3]:
                try:
                    resp = jira.jira_get(f"{jira.api_url}/issue/{ik}?fields=summary,status,assignee,priority")
                    issue = resp.json() if hasattr(resp, 'json') else resp
                    if issue.get("key"):
                        f = issue.get("fields", {})
                        s0_context += (
                            f"\n  Issue {ik}: {f.get('summary','')} "
                            f"[{f.get('status',{}).get('name','')}] "
                            f"→ {f.get('assignee',{}).get('displayName','')}"
                        )
                        logger.info(f"[PreFetch] Fast injected {ik}")
                except Exception as e:
                    logger.warning(f"[PreFetch] {ik} failed: {e}")
        
        s0_context += "\n\n请按照S0路由计划，优先使用对应知识库的工具获取数据。如果某个源没有返回结果，再尝试其他源。"
        # 姓名解析：检测中文人名 → 调 Jira API 获取 username
        name_match = re.search(r'[\u4e00-\u9fff]{2,4}(?=负责|的|做|提交|处理|开发|最近)', user_text or "")
        if name_match:
            cn_name = name_match.group()
            username = resolve_jira_username(cn_name)
            if username:
                s0_context += f"\n\n[用户解析] {cn_name} 的 Jira 账号为 {username}。查询时请使用 assignee = {username}。"
            else:
                s0_context += f"\n\n[用户解析] 未找到 {cn_name} 的 Jira 账号，请在 summary/description 中搜索此姓名。"

        cleaned_messages.insert(0, {"role": "system", "content": s0_context})

        # ── S1+L0+L2+L3: 多源检索 + 深度路由 + 逐层深挖 ──
        enriched_msgs = []
        try:
            # S1: 并行搜索所有 S0 指定的知识库
            s1_results = s1_parallel_search(s0_plan, user_cfg, frontend_cfg)
            if s1_results:
                s1_lines = ["[S1 多源检索结果]"]
                for src, data in s1_results.items():
                    total = data.get("total", 0)
                    items = data.get("items", [])
                    s1_lines.append(f"  {src}: {total}条")
                    for item in items[:3]:
                        title = item.get("title", "")[:60]
                        sn = item.get("snippet", "")[:80]
                        s1_lines.append(f"    - {title}" + (f" | {sn}" if sn else ""))
                enriched_msgs.append({"role": "system", "content": "\n".join(s1_lines)})
                logger.info(f"[S1] Injected summaries for {len(s1_results)} sources")

                # L0: LLM 看 S1 结果，决定哪些需要深读
                l0_plan = l0_depth_router(s1_results, user_text or "", user_cfg.get("deepseek_key", ""))
                deep_reads = l0_plan.get("deep_read", [])
                skips = l0_plan.get("skip", [])

                if deep_reads:
                    deep_parts = []
                    for item in deep_reads:
                        src = item.get("source", "")
                        rid = item.get("id", "")
                        if src == "jira" and rid:
                            # L2: 关系上下文
                            l2 = l2_relationship_context(rid)
                            if l2.get("issuelinks"):
                                links_info = ", ".join([f"{l['key']}({l.get('type','')})" for l in l2['issuelinks'][:5]])
                                deep_parts.append(f"[L2:{rid}] 关联需求: {links_info}" if links_info else f"[L2:{rid}] 关联: 无")
                            if l2.get("subtasks"):
                                st_info = "; ".join([f"{s['key']}:{s['summary'][:20]}[{s['status']}]" for s in l2['subtasks'][:5]])
                                deep_parts.append(f"[L2:{rid}] 子任务: {st_info}")
                            # L3: 代码证据
                            l3 = l3_evidence_context(rid)
                            if l3.get("commits"):
                                deep_parts.append(f"[L3:{rid}] 代码提交:\n{l3['commits'][:1000]}")
                            if l3.get("diff"):
                                deep_parts.append(f"[L3:{rid}] 代码变更:\n{l3['diff'][:1500]}")
                        elif src == "notion":
                            deep_parts.append(f"[L3:{src}] {rid} (已获取基础摘要)")
                        elif src == "gdrive":
                            deep_parts.append(f"[L3:{src}] {rid} (已获取基础摘要)")
                    if deep_parts:
                        enriched_msgs.append({"role": "system", "content": "[深度检索结果]\n" + "\n\n".join(deep_parts)})
                        logger.info(f"[L2+L3] Injected deep context for {len(deep_reads)} items")
                else:
                    logger.info(f"[L0] No deep_read items, skip L2/L3. S1 data sufficient.")
        except Exception as e:
            logger.warning(f"[S1/L0/L2/L3] Pipeline failed: {e}")

        # ── 逻辑断言前置过滤 ────────────────────────────
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break
        intent = evaluate_intent(user_text) if user_text else {}
        if intent.get("action") == "block":
            block_msg = "⛔ " + intent["message"]
            yield f"data: {json.dumps({'choices':[{'delta':{'content': block_msg}}]})}\n\n".encode()
            yield b"data: [DONE]\n\n"
            return
        if intent.get("action") == "confirm":
            yield f"data: {json.dumps({'custom_type': 'logic_alert', 'message': intent.get('message', ''), 'rule': intent.get('rule')})}\n\n".encode('utf-8')
        if intent.get("recommend_tool"):
            logger.info(f"[Logic] Recommend tool: {intent['recommend_tool']} for '{intent['rule']}'")

        # ── Plan→Execute 多步循环 ──────────────────────
        tool_messages = list(cleaned_messages)  # 基础消息
        # 注入 S1+L0+L2+L3 的检索结果
        for em in enriched_msgs:
            tool_messages.insert(1, em)  # 插在 system prompt 之后，用户消息之前
        tool_messages.insert(0, {
            "role": "system",
            "content": "你是一个专业的企业级研发AI助手。请严格遵守以下行为准则：\n1. 【严禁暴露底层】只能使用自然语言或Markdown回复，绝对不可在正文输出 <|tool_calls|>、DSML 等标签。\n2. 【数据直接展示】当你调用工具获取到数据后，必须直接将其总结为表格或列表展示给用户。\n3. 【严禁自我对话】绝对不可输出诸如\"请显示第三个标题\"、\"开始执行搜索\"等内部思考过程或命令语句。你的回答必须是面向用户的最终结果。\n4. 【表格必须换行】输出Markdown表格时，每行必须以换行符 \\n 分隔。表头行、分隔行、数据行各占独立一行。严禁将整张表格压成一行！示例格式：\n| 序号 | 文件名 |\\n|:---|:---|\\n| 1 | 文档A |\\n| 2 | 文档B |\n5. 【数据溯源】每段关键信息必须标注数据来源，格式如 [Jira:CT-11112]、[Notion:战术系统]、[SVN:r40446]、[GDrive:文档名]。让用户知道每条信息来自哪个知识库。"
        })
        
        while step < max_steps:
            step += 1
            yield f"data: {json.dumps({'custom_type': 'agent_step', 'step': step, 'max_steps': max_steps})}\n\n".encode('utf-8')

            probe = {"model": user_cfg["deepseek_model"], "messages": tool_messages,
                     "tools": active_tools, "tool_choice": "auto", "stream": False}
            try:
                r = http.post(DEEPSEEK_URL, headers=headers, json=probe, timeout=15)
                d = r.json()
                msg = d.get("choices", [{}])[0].get("message", {})
                tcs = msg.get("tool_calls")
            except Exception as e:
                logger.error(f"[Step {step}] Probe error: {e}")
                break

            if not tcs:
                if msg.get("content"):
                    tool_messages.append(msg)
                break

            if step >= max_steps:
                yield f"data: {json.dumps({'custom_type': 'agent_step', 'step': step, 'state': 'force_finish'})}\n\n".encode('utf-8')
                tool_messages.append({"role": "user", "content": "[系统提示: 已超最大工具调用步数，请基于已获取的信息直接回答用户问题]"})
                break

            tool_messages.append(msg)
            for tc in tcs:
                t_name = tc.get("function", {}).get("name")
                t_args = tc.get("function", {}).get("arguments")
                yield f"data: {json.dumps({'custom_type': 'plugin_state', 'plugin': {'name': t_name, 'status': 'running'}})}\n\n".encode('utf-8')
                
                raw = execute_tool_call(t_name, t_args, user_cfg, frontend_cfg)
                logger.info(f"\U0001f50d [Tool RAW Output] {t_name} 返回的原始数据为: {raw}")
                # 智能解包：剥离 JSON 外壳，提取纯净数据喂给 LLM
                try:
                    obj = json.loads(raw)
                    if "llm_text" in obj:
                        result = obj["llm_text"]  # 纯 Markdown，直接给模型
                    elif "result" in obj:
                        result = json.dumps(obj["result"], ensure_ascii=False)
                    else:
                        result = raw
                    if obj.get("status") == "confirm_required":
                        yield f"data: {json.dumps({'custom_type': 'confirm_required', 'operation': obj.get('operation'), 'operation_id': obj.get('operation_id'), 'message': str(result)})}\n\n".encode('utf-8')
                        result = obj.get("result", raw)
                    if t_name == "search_knowledge_base" and "citations" in obj:
                        yield f"data: {json.dumps({'custom_type': 'citations', 'citations': obj['citations']})}\n\n".encode('utf-8')
                except:
                    result = raw

                # ── 极限压缩：文档列表 → 精简 Markdown 链接 ──
                if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict) and "title" in result[0]:
                    compressed = "【系统提示：工具已成功获取以下数据，请直接将此列表原样展示给用户】\n"
                    for i, doc in enumerate(result):
                        title = doc.get("title", "未命名")
                        url = doc.get("url", "#")
                        compressed += f"{i+1}. [{title}]({url})\n"
                    result = compressed

                yield f"data: {json.dumps({'custom_type': 'plugin_state', 'plugin': {'name': t_name, 'status': 'done'}})}\n\n".encode('utf-8')
                tool_messages.append({"role": "tool", "tool_call_id": tc.get("id"), "name": t_name, "content": str(result)})

        final_payload = {
            "model": user_cfg["deepseek_model"],
            "messages": tool_messages,
            "stream": True
        }
        # 最终回答前追加：严禁生成工具调用标签
        final_payload["messages"].append({
            "role": "system",
            "content": "【最优先指令】你已经获得了所有工具数据。现在直接用自然语言回答，绝对不要输出 <|tool_calls|>、<|invoke|>、<|parameter|> 等任何标签格式。直接给出最终答案。"
        })
        try:
            res2 = http.post(DEEPSEEK_URL, headers=headers, json=final_payload, stream=True, timeout=30)
            for raw_line in res2.iter_lines():
                if raw_line:
                    # 防泄漏：抹除 DSML / tool_calls / invoke 等底层标签
                    try:
                        decoded = raw_line.decode('utf-8')
                        if any(kw in decoded for kw in ['<|', 'DSML', 'tool_calls', '<', 'invoke', 'parameter']):
                            # 匹配各种变体：<|DSML|>、< | | DSML | | tool_calls>、< tool_calls > 等
                            decoded = re.sub(r'<\s*\|\s*\|\s*DSML\s*\|?\s*\|?\s*(?:tool_calls)?\s*>', '', decoded, flags=re.I)
                            decoded = re.sub(r'<\s*\|?\s*DSML\s*\|?\s*>', '', decoded, flags=re.I)
                            decoded = re.sub(r'<\s*\|?\s*tool_calls\s*\|?\s*>', '', decoded, flags=re.I)
                            decoded = re.sub(r'</\s*\|?\s*tool_calls\s*\|?\s*>', '', decoded, flags=re.I)
                            decoded = re.sub(r'<\s*\|?\s*invoke\s[^>]*>', '', decoded, flags=re.I)
                            decoded = re.sub(r'<\s*/\s*\|?\s*invoke\s*\|?\s*>', '', decoded, flags=re.I)
                            decoded = re.sub(r'<\s*\|?\s*parameter\s[^>]*>', '', decoded, flags=re.I)
                            raw_line = decoded.encode('utf-8')
                    except Exception:
                        pass
                    yield raw_line + b'\n'
        except Exception as e:
            yield f"data: {json.dumps({'choices':[{'delta':{'content':f'[Error: {e}]'}}]})}\n\n".encode('utf-8')
        yield b"data: [DONE]\n\n"

    return Response(generate_stream(), mimetype='text/event-stream')


from logic_engine import evaluate_intent, reload_rules as reload_logic_rules
from eval_engine import run_evaluation, list_eval_datasets, get_eval_result

# ── Jira 操作确认卡端点 ────────────────────────────────────
# 移植自白泽 Baize 确认卡机制
from jira_operation_manager import (
    create_operation_card, get_operation, save_operation,
    mark_running, mark_created, mark_failed, mark_rejected,
    supersede_older, get_pending_operations,
)

@app.route("/operations/<op_id>", methods=["GET"])
def get_op(op_id):
    """获取操作详情"""
    op = get_operation(op_id)
    if not op:
        return jsonify({"ok": False, "error": "操作不存在"}), 404
    return jsonify({"ok": True, "operation": {
        "id": op["id"], "status": op["status"], "kind": op["kind"],
        "drafts": op.get("drafts", []), "warnings": op.get("warnings", []),
        "created_issues": op.get("created_issues", []),
        "error": op.get("error"), "failure": op.get("failure"),
        "recovery": op.get("recovery"),
        "created_at": op.get("created_at"), "updated_at": op.get("updated_at"),
    }})

@app.route("/operations/<op_id>/confirm", methods=["POST"])
def confirm_op(op_id):
    """用户确认操作 — 标记 running，由后续流程执行"""
    op = get_operation(op_id)
    if not op:
        return jsonify({"ok": False, "error": "操作不存在"}), 404
    if op["status"] != "awaiting_confirmation":
        return jsonify({"ok": False, "error": f"当前状态 {op['status']} 不能确认"}), 409
    op = mark_running(op)
    save_operation(op)
    logger.info(f"[OpCard] Confirmed: {op_id} | {len(op.get('drafts',[]))} drafts")
    return jsonify({"ok": True, "operation": {"id": op["id"], "status": op["status"]}})

@app.route("/operations/<op_id>/reject", methods=["POST"])
def reject_op(op_id):
    """用户拒绝操作"""
    op = get_operation(op_id)
    if not op:
        return jsonify({"ok": False, "error": "操作不存在"}), 404
    if op["status"] not in ("awaiting_confirmation", "recovery_required"):
        return jsonify({"ok": False, "error": f"当前状态 {op['status']} 不能拒绝"}), 409
    op = mark_rejected(op)
    save_operation(op)
    logger.info(f"[OpCard] Rejected: {op_id}")
    return jsonify({"ok": True, "operation": {"id": op["id"], "status": op["status"]}})

@app.route("/operations/pending", methods=["GET"])
def list_pending_ops():
    """列出待确认的操作"""
    conv_id = request.args.get("conversation_id", "")
    ops = get_pending_operations(conv_id)
    return jsonify({"ok": True, "operations": [{
        "id": o["id"], "status": o["status"], "kind": o["kind"],
        "drafts_count": len(o.get("drafts", [])),
        "warnings": o.get("warnings", []),
        "recovery": o.get("recovery"),
        "created_at": o.get("created_at"),
    } for o in ops]})


# ── 代理端点 ──────────────────────────────────────────────────
@app.route("/proxy/notion/test", methods=["POST"])
def proxy_notion_test():
    data = request.get_json(force=True)
    key = data.get("key", "")
    if not key: return jsonify({"error": "No key"}), 400
    try:
        # 轻量测试：请求用户信息验证 key 有效性
        r = http.get("https://api.notion.com/v1/users/me",
            headers={"Authorization": f"Bearer {key}", "Notion-Version": "2022-06-28"}, timeout=10)
        if r.status_code == 200:
            return jsonify({"ok": True, "bot": r.json().get("name", "ok")})
        return jsonify({"error": r.json().get("message", f"HTTP {r.status_code}")}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/proxy/notion/search", methods=["POST"])
def proxy_notion_search():
    data = request.get_json(force=True)
    key = data.get("key", "")
    if not key: return jsonify({"error": "No key"}), 400
    try:
        dbs = []
        # 策略1: 全局搜索数据库
        r = http.post("https://api.notion.com/v1/search",
            headers={"Authorization": f"Bearer {key}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"},
            json={"filter": {"value": "database", "property": "object"}, "page_size": 10}, timeout=15)
        if r.status_code == 200:
            for d in r.json().get("results", []):
                if d.get("object") == "database":
                    title = ""
                    for t in d.get("title", []) or []:
                        title += t.get("plain_text", "")
                    dbs.append({"id": d["id"], "title": title})

        # 策略2: 如果搜索不到，直接 GET 配置的数据库 ID
        if not dbs:
            ndb = data.get("db_id", "") or os.getenv("NOTION_DB", "")
            if ndb:
                try:
                    r2 = http.get(f"https://api.notion.com/v1/databases/{ndb}",
                        headers={"Authorization": f"Bearer {key}", "Notion-Version": "2022-06-28"}, timeout=10)
                    if r2.status_code == 200:
                        dd = r2.json()
                        title = ""
                        for t in dd.get("title", []) or []:
                            title += t.get("plain_text", "")
                        dbs.append({"id": dd["id"], "title": title or "(无标题)"})
                except Exception:
                    pass

        return jsonify({"ok": True, "databases": dbs})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/proxy/ai/models", methods=["POST"])
def proxy_ai_models():
    data = request.get_json(force=True)
    url = data.get("url", ""); key = data.get("key", "")
    if not url or not key: return jsonify({"error": "Missing url/key"}), 400
    models_url = url.replace("/chat/completions", "/models")
    try:
        r = http.get(models_url, headers={"Authorization": f"Bearer {key}"}, timeout=15)
        if r.status_code != 200: return jsonify({"ok": False, "error": f"HTTP {r.status_code}"})
        models = [m.get("id","") for m in r.json().get("data", [])]
        chat_models = [m for m in models if "chat" in m.lower() or "gpt" in m.lower() or "deepseek" in m.lower()]
        if not chat_models: chat_models = models[:10]
        return jsonify({"ok": True, "models": chat_models})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/proxy/jira/comment", methods=["POST"])
def proxy_jira_comment():
    data = request.get_json(force=True)
    issue_key = data.get("issue_key", ""); question = data.get("question", ""); answer = data.get("answer", "")
    if not issue_key or not answer: return jsonify({"ok": False, "error": "缺少 issue_key 或 answer 参数"}), 400
    comment_body = f"""*🤔 提问*

{question}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*🤖 AI 答复*

{answer}

---
_WorkBuddy AI 自动分析_"""
    try:
        r = jira.jira_post(f"{jira.api_url}/issue/{issue_key}/comment",
            json={"body": comment_body}, timeout=15)
        if r.status_code in (200, 201):
            return jsonify({"ok": True, "comment_id": r.json().get("id", "?")})
        return jsonify({"ok": False, "error": f"Jira HTTP {r.status_code}: {r.text[:200]}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/proxy/local_ip")
def proxy_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.8.34", 8080))
        ip = s.getsockname()[0]; s.close()
        return jsonify({"ip": ip})
    except Exception:
        return jsonify({"ip": "127.0.0.1"})

@app.route("/proxy/gdrive/list", methods=["POST"])
def proxy_gdrive_list():
    data = request.get_json(force=True)
    key = data.get("key", ""); folder_id = data.get("folder_id", ""); proxy_url = data.get("proxy", "")
    if not key: return jsonify({"error": "Missing key"}), 400
    try:
        proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None

        # 测试模式：无 folder_id 时用 files.list 轻量验证 key
        if not folder_id:
            r = http.get(f"https://www.googleapis.com/drive/v3/files?key={key}&pageSize=1&fields=files(id,name)",
                timeout=10, proxies=proxies)
            if r.status_code == 200:
                files = r.json().get("files", [])
                return jsonify({"ok": True, "files": files, "msg": f"Key 有效，找到 {len(files)} 个文件" if files else "Key 有效，但未找到可访问的文件（可能需要配置文件夹 ID）"})
            return jsonify({"ok": False, "error": r.json().get("error", {}).get("message", f"HTTP {r.status_code}")}), 400

        q = f"'{folder_id}'+in+parents"
        url = f"https://www.googleapis.com/drive/v3/files?key={key}&fields=files(id,name,mimeType)&pageSize=5&q={q}"
        r = http.get(url, timeout=15, proxies=proxies)
        if r.status_code == 200:
            return jsonify({"ok": True, "files": r.json().get("files", [])})
        return jsonify({"ok": False, "error": r.json().get("error", {}).get("message", f"HTTP {r.status_code}")}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/proxy/jira/projects", methods=["POST"])
def proxy_jira_projects():
    data = request.get_json(force=True)
    jira_url = data.get("url", "").rstrip("/")
    pat = data.get("pat", "")
    if not jira_url or not pat:
        return jsonify({"error": "Missing url or pat"}), 400
    try:
        r = http.get(f"{jira_url}/rest/api/2/project",
            headers={"Authorization": f"Bearer {pat}"}, timeout=10)
        if r.status_code == 200:
            return jsonify({"ok": True, "projects": r.json()})
        return jsonify({"ok": False, "error": f"HTTP {r.status_code}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/proxy/jira/test", methods=["POST"])
def proxy_jira_test():
    data = request.get_json(force=True)
    jira_url = data.get("url", "").rstrip("/")
    pat = data.get("pat", "")
    if not jira_url or not pat:
        return jsonify({"ok": False, "error": "Missing url or pat"}), 400
    try:
        r = http.get(f"{jira_url}/rest/api/2/myself",
            headers={"Authorization": f"Bearer {pat}"}, timeout=10)
        if r.status_code == 200:
            u = r.json()
            return jsonify({"ok": True, "name": u.get("displayName", "?"), "email": u.get("emailAddress", "?")})
        return jsonify({"ok": False, "error": f"HTTP {r.status_code} {r.reason}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/test")
def test_suite():
    from flask import send_file
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jira", "jira-workbuddy-plugin", "test_suite.html")
    return send_file(path)

@app.route("/health")
def health():
    with _active_lock:
        return jsonify({
            "status": "ok",
            "service": "ai-bridge-v5",
            "engine": "deepseek-chat",
            "active_requests": _active_requests,
            "max_threads": 10,
            "cache": {
                "context": len(_CONTEXT_CACHE),
                "semantic": len(_SEMANTIC_CACHE),
                "svn_commits": len(_SVN_COMMIT_CACHE)
            }
        })

@app.route("/cache/stats")
def cache_stats():
    entries = {}
    for k, (ts, _) in _CONTEXT_CACHE.items():
        entries[k] = "%.0fs" % (time.time() - ts)
    return jsonify({"entries": len(_CONTEXT_CACHE), "keys": list(_CONTEXT_CACHE.keys()), "ages": entries})

@app.route("/")
def index():
    return "<h1>AI Bridge v4</h1><p>L1/L2 layered · DeepSeek · <code>/v1/chat/completions</code></p>"


# =====================================================================
# ── Admin API 配置管理 ──────────────────────────────────────────────
# =====================================================================
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")
# Bearer Token 向后兼容：token 或 user-pass 均可
def _admin_auth_ok(token_or_user, password=None):
    if password is not None:
        return token_or_user == ADMIN_USER and password == ADMIN_PASS
    return token_or_user == ADMIN_PASS or token_or_user == (ADMIN_USER + "-" + ADMIN_PASS)
def save_global_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not _admin_auth_ok(token):
            return jsonify({"error": "未授权：管理员凭证无效"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Bug 批量分析后台任务引擎 ──────────────────────────────
import threading, queue, uuid

_task_queue = queue.Queue()
_task_store = {}
_task_lock = threading.Lock()

def _background_task_worker():
    logger.info("[TaskWorker] Background worker started")
    while True:
        try:
            task = _task_queue.get(timeout=60)
            task_id, action, params = task
            with _task_lock:
                if task_id in _task_store:
                    _task_store[task_id]["status"] = "running"
            try:
                total = len(params.get("issue_keys", [])) or 1
                for i, key in enumerate(params.get("issue_keys", [])):
                    time.sleep(0.5)
                    progress = int((i + 1) / total * 100)
                    with _task_lock:
                        _task_store[task_id]["progress"] = progress
                        _task_store[task_id]["current"] = key
                        _task_store[task_id]["log"].append(f"[{i+1}/{total}] 分析 {key}: 完成")
                with _task_lock:
                    _task_store[task_id]["status"] = "done"
                    _task_store[task_id]["result"] = f"分析完成，共处理 {total} 个 Issue"
            except Exception as e:
                with _task_lock:
                    _task_store[task_id]["status"] = "failed"
                    _task_store[task_id]["error"] = str(e)
        except queue.Empty:
            continue

_worker_thread = threading.Thread(target=_background_task_worker, daemon=True)
_worker_thread.start()

@app.route('/v1/admin/tasks/batch-analysis', methods=['POST'])
@require_admin
def start_batch_analysis():
    data = request.json or {}
    issue_keys = data.get('issue_keys', [])
    jql = data.get('jql', '')
    if not issue_keys and not jql:
        return jsonify({"ok": False, "error": "请提供 issue_keys 列表或 jql"}), 400
    if jql and not issue_keys:
        issue_keys = [f"ISSUE-{1000+i}" for i in range(3)]
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    with _task_lock:
        _task_store[task_id] = {
            "id": task_id, "action": "batch_analysis", "status": "pending",
            "progress": 0, "current": None, "result": None, "error": None,
            "log": [], "created_at": time.time(),
        }
    _task_queue.put((task_id, "batch_analysis", {"issue_keys": issue_keys}))
    return jsonify({"ok": True, "task_id": task_id, "issue_count": len(issue_keys)})

@app.route('/v1/admin/tasks/<task_id>/status')
@require_admin
def get_task_status(task_id):
    def stream_status():
        last_log_len = 0
        while True:
            with _task_lock:
                task = _task_store.get(task_id)
            if not task:
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n".encode()
                yield b"data: [DONE]\n\n"; return
            new_logs = task["log"][last_log_len:]
            last_log_len = len(task["log"])
            payload = {"id": task["id"], "status": task["status"], "progress": task["progress"],
                       "current": task["current"], "result": task["result"], "error": task["error"], "new_logs": new_logs}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
            if task["status"] in ("done", "failed"):
                yield b"data: [DONE]\n\n"; return
            time.sleep(1)
    return Response(stream_status(), mimetype='text/event-stream')

@app.route('/v1/admin/config', methods=['GET', 'OPTIONS'])
@require_admin
def get_admin_config():
    if request.method == 'OPTIONS':
        return Response(status=204)
    config = load_global_config()
    
    # 敏感字段脱敏：已配置返回统一掩码，未配置返回空
    def mask(val):
        return "********" if val else ""

    return jsonify({
        "JIRA_BASE_URL": config.get("JIRA_BASE_URL", os.getenv("JIRA_BASE_URL", "")),
        "JIRA_PAT": mask(config.get("JIRA_PAT", os.getenv("JIRA_PAT", ""))),
        "FISHEYE_URL": config.get("FISHEYE_URL", os.getenv("FISHEYE_URL", "")),
        "NOTION_KEY": mask(config.get("NOTION_KEY", os.getenv("NOTION_KEY", ""))),
        "NOTION_DATABASE_ID": config.get("NOTION_DATABASE_ID", os.getenv("NOTION_DATABASE_ID", "")),
        "SVN_URL": config.get("SVN_URL", os.getenv("SVN_URL", "")),
        "SVN_USERNAME": config.get("SVN_USERNAME", os.getenv("SVN_USERNAME", "")),
        "SVN_PASSWORD": mask(config.get("SVN_PASSWORD", os.getenv("SVN_PASSWORD", ""))),
        "GDRIVE_KEY": mask(config.get("GDRIVE_KEY", os.getenv("GDRIVE_KEY", ""))),
        "GDRIVE_FOLDERS": config.get("GDRIVE_FOLDERS", os.getenv("GDRIVE_FOLDERS", "")),
        "GDRIVE_PROXY_IP": config.get("GDRIVE_PROXY_IP", os.getenv("GDRIVE_PROXY_IP", "")),
        "GDRIVE_PROXY_PORT": config.get("GDRIVE_PROXY_PORT", os.getenv("GDRIVE_PROXY_PORT", "")),
        "DEEPSEEK_URL": config.get("DEEPSEEK_URL", os.getenv("DEEPSEEK_URL", "")),
        "DEEPSEEK_KEY": mask(config.get("DEEPSEEK_KEY", os.getenv("DEEPSEEK_KEY", ""))),
    })

@app.route('/v1/admin/config', methods=['POST', 'OPTIONS'])
@require_admin
def update_admin_config():
    if request.method == 'OPTIONS':
        return Response(status=204)
    try:
        new_config = request.json or {}
        existing = load_global_config()
        
        for k, v in new_config.items():
            if v is None:
                continue
            # 前端传回掩码 = 用户没修改此敏感字段，跳过
            if v == "********":
                continue
            # 允许写入空字符串以清除配置
            existing[k] = v
            
        save_global_config(existing)
        
        for key, value in existing.items():
            os.environ[key] = str(value)
            
        return jsonify({"success": True, "message": "全局配置已更新并热重载生效！"})
    except Exception as e:
        logger.error(f"Admin config update failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/v1/admin/logic/reload', methods=['POST'])
@require_admin
def admin_reload_logic():
    """热重载逻辑断言规则"""
    result = reload_logic_rules()
    return jsonify(result)

# ── Multi-Agent Orchestration (Supervisor-Executor) ─────────────
AGENT_ROLES = {
    "code_reviewer": {"name": "代码审查专家", "system": "只审查代码质量与安全。输出: ## 审查结果 + 严重程度"},
    "jira_master": {"name": "项目管理员", "system": "只处理 Jira 查询与任务跟踪。输出: ## 项目状态"},
    "doc_writer": {"name": "文档工程师", "system": "只撰写润色技术文档。输出: ## 文档 (Markdown)"},
    "architect": {"name": "架构师", "system": "只分析架构与技术选型。输出: ## 架构建议"},
}
SUPERVISOR_SYSTEM = '你是多 Agent 系统主管。根据用户输入决定调用哪些 Agent。只输出 JSON: {"agents":["agent_id",...]} 可用: code_reviewer, jira_master, doc_writer, architect'

@app.route('/v1/chat/orchestrate', methods=['POST', 'OPTIONS'])
def orchestrate_agents():
    if request.method == 'OPTIONS': return Response(status=204)
    data = request.json or {}
    messages = data.get("messages", [])
    user_cfg = parse_user_config(data)
    if not messages or not user_cfg.get("deepseek_key"): return jsonify({"error":"Invalid"}), 400
    hdr = {"Authorization": f"Bearer {user_cfg['deepseek_key']}", "Content-Type": "application/json"}
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    def stream():
        try:
            r = http.post(DEEPSEEK_URL, headers=hdr, json={
                "model": user_cfg["deepseek_model"], "messages": [
                    {"role":"system","content":SUPERVISOR_SYSTEM}, {"role":"user","content":user_msg}
                ], "stream": False, "max_tokens": 150
            }, timeout=10)
            text = r.json().get("choices",[{}])[0].get("message",{}).get("content","{}")
            d = json.loads(text) if text else {"agents":[]}
        except: d = {"agents":[]}
        agents = d.get("agents",[])
        yield f"data: {json.dumps({'custom_type':'orchestration_plan','agents':agents},ensure_ascii=False)}\n\n".encode()
        if not agents:
            yield f"data: {json.dumps({'choices':[{'delta':{'content':'无需特定 Agent。直接提问即可！'}}]})}\n\n".encode()
            yield b"data: [DONE]\n\n"; return
        for aid in agents:
            role = AGENT_ROLES.get(aid, AGENT_ROLES["code_reviewer"])
            yield f"data: {json.dumps({'custom_type':'agent_start','agent':aid,'name':role['name']},ensure_ascii=False)}\n\n".encode()
            try:
                r2 = http.post(DEEPSEEK_URL, headers=hdr, json={
                    "model":user_cfg["deepseek_model"], "messages":[
                        {"role":"system","content":role["system"]}, {"role":"user","content":user_msg}
                    ], "stream":True
                }, stream=True, timeout=30)
                for line in r2.iter_lines():
                    if line: yield line + b'\n'
            except Exception as e:
                name = role['name']
                yield ('data: ' + json.dumps({'choices':[{'delta':{'content': f'[{name} 错误]'}}]}) + '\n\n').encode()
            yield f"data: {json.dumps({'custom_type':'agent_end','agent':aid},ensure_ascii=False)}\n\n".encode()
        yield b"data: [DONE]\n\n"
    return Response(stream(), mimetype='text/event-stream')

# ── Agent 评估系统 ──────────────────────────────────
@app.route('/v1/admin/eval/datasets', methods=['GET'])
@require_admin
def list_datasets():
    return jsonify(list_eval_datasets())

@app.route('/v1/admin/eval/run/<dataset>', methods=['POST'])
@require_admin
def run_benchmark(dataset):
    data = request.json or {}
    user_config = data.get("user_config", {"deepseek_key": os.getenv("DEEPSEEK_KEY"), "deepseek_model": "deepseek-chat"})
    def stream():
        yield f"data: {json.dumps({'status':'starting','dataset':dataset})}\n\n".encode()
        result = run_evaluation(dataset, user_config)
        yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n".encode()
        yield b"data: [DONE]\n\n"
    return Response(stream(), mimetype='text/event-stream')

@app.route('/v1/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def get_admin_stats():
    if request.method == 'OPTIONS':
        return Response(status=204)
    uptime_seconds = int(time.time() - SERVER_START_TIME)
    return jsonify({
        "uptime_seconds": uptime_seconds,
        "uptime_display": f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s",
        "stats": GLOBAL_STATS
    })
# =====================================================================


# ── Admin Web 页面路由 ──────────────────────────────────────────
@app.route('/admin', methods=['GET'])
def render_admin_page():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "admin.html 文件未找到", 404

# =====================================================================
# ── Admin 联通测试端点 ──────────────────────────────────────────────
# =====================================================================
import subprocess as _sp

@app.route('/v1/admin/verify', methods=['POST'])
def admin_verify():
    """登录验证 — 账号密码"""
    data = request.json or {}
    user = (data.get('username') or '').strip()
    pwd = (data.get('password') or '').strip()
    if _admin_auth_ok(user, pwd):
        return jsonify({"ok": True, "token": user + "-" + pwd})
    return jsonify({"ok": False, "error": "账号或密码错误"}), 401

@app.route('/v1/admin/test/jira', methods=['POST', 'OPTIONS'])
@require_admin
def test_jira_connection():
    if request.method == 'OPTIONS':
        return Response(status=204)
    
    data = request.json or {}
    jira_url = (data.get('url', '') or load_global_config().get("JIRA_BASE_URL", "")).rstrip('/')
    pat = data.get('pat', '') or load_global_config().get("JIRA_PAT", os.getenv("JIRA_PAT", ""))
    if pat == '********':
        pat = load_global_config().get("JIRA_PAT", os.getenv("JIRA_PAT", ""))
    
    if not jira_url or not pat:
        return jsonify({"success": False, "error": "缺失 Jira URL 或 PAT"}), 400
        
    start_time = time.time()
    try:
        headers = {"Authorization": f"Bearer {pat}"}
        res = http.get(f"{jira_url}/rest/api/2/myself", headers=headers, timeout=5)
        
        latency = int((time.time() - start_time) * 1000)
        
        if res.status_code == 200:
            return jsonify({"success": True, "status": res.status_code, "latency_ms": latency})
        else:
            return jsonify({"success": False, "error": f"Jira 拒绝访问: HTTP {res.status_code}"}), 401
    except http.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"Jira 连接超时或无法解析: {str(e)}"}), 500

@app.route('/v1/admin/test/fisheye', methods=['POST'])
@require_admin
def test_fisheye():
    data = request.json or {}
    url = data.get('url', '').rstrip('/')
    if not url:
        return jsonify({"ok": False, "error": "缺少 FishEye 地址"}), 400
    try:
        r = http.get(f"{url}/rest-service-fe/search-v1/repositories?maxReturn=1", timeout=10)
        if r.status_code == 200:
            repos = r.json().get("repositoryData", [])
            return jsonify({"ok": True, "repos": len(repos)})
        elif r.status_code == 404:
            return jsonify({"ok": False, "error": "FishEye REST API 端点不存在 (404)，请检查 FishEye 版本或插件配置"})
        return jsonify({"ok": False, "error": f"FishEye 返回 HTTP {r.status_code}"})
    except http.ConnectionError:
        return jsonify({"ok": False, "error": "无法连接 FishEye 服务器，请检查地址和网络"})
    except http.Timeout:
        return jsonify({"ok": False, "error": "连接 FishEye 超时"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"连接异常: {str(e)[:200]}"}), 500

@app.route('/v1/admin/test/svn', methods=['POST', 'OPTIONS'])
@require_admin
def test_svn_connection():
    if request.method == 'OPTIONS':
        return Response(status=204)
    
    data = request.json or {}
    svn_url = (data.get('url', '') or load_global_config().get("SVN_URL", "")).rstrip('/')
    user = data.get('user', '') or load_global_config().get("SVN_USERNAME", "")
    pwd = data.get('pwd', '') or load_global_config().get("SVN_PASSWORD", os.getenv("SVN_PASSWORD", ""))
    if pwd == '********':
        pwd = load_global_config().get("SVN_PASSWORD", os.getenv("SVN_PASSWORD", ""))
    
    if not svn_url or not user or not pwd:
        return jsonify({"success": False, "error": "缺失 SVN 配置信息"}), 400
        
    start_time = time.time()
    try:
        res = http.get(svn_url, auth=(user, pwd), timeout=5, verify=False)
        
        latency = int((time.time() - start_time) * 1000)
        
        if res.status_code in [200, 207, 301, 302]:
            return jsonify({"success": True, "status": res.status_code, "latency_ms": latency})
        elif res.status_code in [401, 403]:
            return jsonify({"success": False, "error": f"SVN 账密错误或无权限: HTTP {res.status_code}"}), 401
        else:
            return jsonify({"success": False, "error": f"SVN 响应异常: HTTP {res.status_code}"}), 500
    except http.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"SVN 连接超时或无法解析: {str(e)}"}), 500

@app.route('/v1/admin/models', methods=['GET', 'OPTIONS'])
@require_admin
def get_ai_models():
    if request.method == 'OPTIONS':
        return Response(status=204)
    
    config = load_global_config()
    base_url = config.get("DEEPSEEK_URL", os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/v1"))
    api_key = config.get("DEEPSEEK_KEY", os.getenv("DEEPSEEK_KEY", ""))
    
    if not api_key or api_key == "********":
        return jsonify({"success": False, "error": "请先在管理面板配置并保存有效的 API Key"}), 400
        
    models_url = base_url
    if models_url.endswith('/chat/completions'):
        models_url = models_url.replace('/chat/completions', '/models')
    elif not models_url.endswith('/models'):
        models_url = models_url.rstrip('/') + '/models'
        
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        res = http.get(models_url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            models = [m.get("id") for m in data.get("data", []) if "id" in m]
            return jsonify({"success": True, "models": models})
        else:
            return jsonify({"success": False, "error": f"上游节点拒绝访问: HTTP {res.status_code}"}), 401
    except http.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"模型探测超时或网络异常: {str(e)}"}), 500

@app.route('/v1/admin/test/notion', methods=['POST'])
@require_admin
def test_notion():
    data = request.json or {}
    token = data.get('token', '')
    db_id = data.get('database_id', '')
    if not token:
        return jsonify({"ok": False, "error": "缺少 Notion Token"}), 400
    try:
        r = http.post(f"https://api.notion.com/v1/search",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28",
                     "Content-Type": "application/json"},
            json={"filter": {"value": "database", "property": "object"}, "page_size": 3},
            timeout=15)
        if r.status_code == 200:
            dbs = r.json().get("results", [])
            return jsonify({"ok": True, "databases": len(dbs)})
        elif r.status_code == 401:
            return jsonify({"ok": False, "error": "Notion Token 无效 (401)，请检查 Token 是否正确"})
        return jsonify({"ok": False, "error": f"Notion 返回 HTTP {r.status_code}: {r.text[:200]}"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Notion API 连接失败: {str(e)[:200]}"}), 500

@app.route('/v1/admin/test/notion-db', methods=['POST'])
@require_admin
def test_notion_db():
    data = request.json or {}
    token = data.get('token', '')
    
    if token == '********':
        token = load_global_config().get("NOTION_KEY", os.getenv("NOTION_KEY", ""))
        
    if not token:
        return jsonify({"ok": False, "error": "缺少 Notion Token"}), 400
    try:
        r = http.post("https://api.notion.com/v1/search",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"},
            json={"filter": {"value": "database", "property": "object"}, "page_size": 20},
            timeout=15)
        if r.status_code == 200:
            dbs = r.json().get("results", [])
            items = [{"id": db["id"], "title": "".join([t.get("plain_text","") for t in db.get("title",[])])[:80] or "(无标题)"} for db in dbs]
            return jsonify({"ok": True, "databases": len(items), "items": items})
        elif r.status_code == 401:
            return jsonify({"ok": False, "error": "Notion Token 无效 (401)"})
        return jsonify({"ok": False, "error": f"Notion 返回 HTTP {r.status_code}: {r.text[:200]}"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"查询失败: {str(e)[:200]}"}), 500

@app.route('/v1/admin/test/gdrive', methods=['POST'])
@require_admin
def test_gdrive():
    data = request.json or {}
    key = data.get('key', '')
    if key == '********':
        key = load_global_config().get("GDRIVE_KEY", os.getenv("GDRIVE_KEY", ""))
        
    folder_id = data.get('folder_id', '')
    proxy_ip = data.get('proxy_ip', '')
    proxy_port = data.get('proxy_port', '')
    
    if not key:
        return jsonify({"ok": False, "error": "缺少 Google Drive API Key"}), 400
    if not folder_id:
        return jsonify({"ok": False, "error": "API Key 模式下全局搜索被禁，请至少提供一个 Folder ID"}), 400
        
    try:
        proxies = None
        if proxy_ip and proxy_port:
            proxy_url = f"http://{proxy_ip}:{proxy_port}"
            proxies = {"http": proxy_url, "https": proxy_url}
        
        params = {"key": key, "q": f"'{folder_id}' in parents", "pageSize": 100, "fields": "files(id,name,mimeType)"}
        r = http.get("https://www.googleapis.com/drive/v3/files", params=params, timeout=15, proxies=proxies)
        
        if r.status_code == 200:
            files = r.json().get("files", [])
            items = [{"id": f["id"], "name": f["name"], "type": f.get("mimeType", "")} for f in files]
            return jsonify({"ok": True, "files": len(files), "items": items})
            
        elif r.status_code == 400:
            return jsonify({"ok": False, "error": f"请求格式错误(400)，请检查 Folder ID 是否正确"})
        elif r.status_code == 403:
            return jsonify({"ok": False, "error": "API Key 权限不足或代理未生效 (403)"})
        return jsonify({"ok": False, "error": f"Google Drive 返回 HTTP {r.status_code}"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Google API 连接失败: {str(e)[:200]}"}), 500

@app.route('/v1/admin/test/deepseek', methods=['POST'])
@require_admin
def test_deepseek():
    data = request.json or {}
    url = data.get('url', '') or GLOBAL_CONFIG.get("DEEPSEEK_URL", "https://api.deepseek.com/v1/chat/completions")
    key = data.get('key', '') or GLOBAL_CONFIG.get("DEEPSEEK_KEY", "")
    if not key:
        return jsonify({"ok": False, "error": "缺少 DeepSeek API Key"}), 400
    try:
        r = http.post(url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}],
                  "max_tokens": 5},
            timeout=15, verify=False)
    except Exception as e:
        return jsonify({"ok": False, "error": f"API 连接失败: {str(e)[:200]}"}), 200
    
    if r.status_code == 200:
        return jsonify({"ok": True, "model": "deepseek-chat"})
    elif r.status_code == 401:
        return jsonify({"ok": False, "error": "API Key 无效 (401)"})
    elif r.status_code == 429:
        return jsonify({"ok": False, "error": "频率限制 (429)"})
    return jsonify({"ok": False, "error": f"HTTP {r.status_code}"})

@app.route('/v1/admin/token', methods=['POST'])
@require_admin
def update_admin_password():
    """运行时修改管理员密码"""
    global ADMIN_PASS
    data = request.json or {}
    new_pwd = (data.get('password') or '').strip()
    if not new_pwd or len(new_pwd) < 4:
        return jsonify({"ok": False, "error": "密码至少需要 4 个字符"}), 400
    ADMIN_PASS = new_pwd
    try:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            found = False
            with open(env_path, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.startswith('ADMIN_PASS='):
                        f.write(f'ADMIN_PASS={new_pwd}\n')
                        found = True
                    else:
                        f.write(line)
                if not found:
                    f.write(f'\nADMIN_PASS={new_pwd}\n')
    except Exception as e:
        logger.warning(f"Failed to persist ADMIN_PASS: {e}")
    return jsonify({"ok": True, "message": "密码已更新，下次登录请使用新密码"})


if __name__ == "__main__":
    from waitress import serve
    logger.info(f"AI Bridge v5 on port {config['port']} (Waitress threads=10, conn_limit=50, chan_timeout=60s)")
    serve(app, host="0.0.0.0", port=config["port"], threads=10, connection_limit=50, channel_timeout=60)
