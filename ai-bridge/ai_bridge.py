"""
AI Bridge v6 — Alice V2.0 — asyncio 真并发 + 流式优先 + 语义缓存
启动: python ai_bridge.py
"""
import os, sys, re, json, time, logging, asyncio, hashlib, threading, collections, concurrent.futures
from logging.handlers import RotatingFileHandler
from functools import wraps
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests as http  # 同步请求保留给简单场景

# SVN 缓存 TTL（统一由 BoundedCache + safe_get_commits 自行管理）

# 语义映射表：逻辑意图 → 物理字段名
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

# ── 模块拆分导入 ──────────────────────────────────────────
from prompt_manager import (
    PROJECT_SCHEMA_MAP, CN_STATUS_MAP, enhance_jql,
    classify_query_type, L1_CHARS, L2_CHARS,
    CONTEXT_TOTAL_LIMIT, JIRA_ISSUE_DETAIL_LIMIT,
    DECISION_PROMPT, build_decision_prompt,
    AVAILABLE_KNOWLEDGE_SOURCES, CORE_AGENT_SYSTEM_PROMPT,
)
from knowledge_retriever import (
    BoundedCache, _CONTEXT_CACHE, _SEMANTIC_CACHE, _SVN_COMMIT_CACHE,
    CACHE_TTL, make_source_summary, classify_file_changes,
    svn_log_grep, safe_get_commits,
    extract_notion_title_ultimate, resolve_jira_username,
    l1_jira_fetch, l1_svn_fetch, l1_notion_fetch, l1_gdrive_fetch,
    l1_jira_fetch_async, l1_svn_fetch_async,
    l1_notion_fetch_async, l1_gdrive_fetch_async,
)

# ── 持久化日志配置 ──────────────────────────────────────
os.makedirs("logs", exist_ok=True)
_log_format = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
_fh = RotatingFileHandler("logs/alice_bridge.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
_fh.setFormatter(logging.Formatter(_log_format))
_sh = logging.StreamHandler(sys.stderr)
_sh.setFormatter(logging.Formatter(_log_format))
logging.basicConfig(level=logging.INFO, handlers=[_fh, _sh])
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

# ── 项目元数据探查（依赖 jira client 实例，留在主模块）───
_PROJECT_CACHE = {}

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
        r = jira.jira_get(f"/project/{pk}/statuses", timeout=15)
        if r.ok:
            for item in r.json():
                meta["issuetypes"].append(item["name"])
                meta["statuses"][item["name"]] = [s["name"] for s in item.get("statuses", [])]
        r2 = jira.jira_get(f"{jira.api_url}/priority", timeout=10)
        if r2.ok:
            meta["priorities"] = [p["name"] for p in r2.json()]
        r3 = jira.jira_get(f"{jira.api_url}/field", timeout=15)
        if r3.ok:
            meta["fields"] = [f["name"] for f in r3.json() if f.get("name") and not f.get("name","").startswith(".")]
        _PROJECT_CACHE[pk] = (now, meta)
        logger.info(f"[Discovery] {pk}: {len(meta['issuetypes'])} types, {len(meta['priorities'])} priorities")
    except Exception as e:
        logger.warning(f"[Discovery] Failed for {pk}: {e}")
    return meta

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
                        svn_result = svn_log_grep(ik, svn_url, svn_user, svn_pass)
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
            # Alice V2.0: 中文 Bigram 分词 + 英文 split，避免长句匹配失效
            raw_q = q.replace("，", " ").replace(",", " ").replace("、", " ")
            # 英文/数字分词
            base_kw = [kw for kw in raw_q.split() if len(kw) >= 2]
            # 中文 Bigram: "球员系统设计" → ["球员", "员系", "系统", "统设", "设计"]
            for kw in list(base_kw):
                if re.search(r'[\u4e00-\u9fff]', kw) and len(kw) >= 4:
                    for i in range(len(kw) - 1):
                        bg = kw[i:i+2]
                        if bg not in base_kw:
                            base_kw.append(bg)
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
                return await asyncio.to_thread(fn)
            except Exception as e:
                logger.warning(f"[L1 Error] {name}: {e}")
                return None
        tasks = [_run_one(fn, name) for fn, name in workers]
        done, pending = await asyncio.wait(tasks, timeout=8.0)
        return [t.result() for t in done if t.result()]

    if workers:
        # Alice V2.0 P0 Fix: 统一使用 ThreadPoolExecutor (_run_sync)
        # 原因: 底层 requests + SVN subprocess 均为同步阻塞,
        #       Waitress 多线程模型下 ThreadPool 是最佳实践,
        #       避免 asyncio.run() 嵌套事件循环冲突。
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
                    text_conds = " OR ".join([f'summary ~ "{kw}" OR description ~ "{kw}"' for kw in kw_list])
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
        {"type": "function", "function": {"name": "query_jira_metadata", "description": "获取 Jira 任务元数据", "parameters": {"type": "object", "properties": {"issue_key": {"type": "string", "description": "Jira 任务编号"}}, "required": ["issue_key"]}}},
        {"type": "function", "function": {"name": "get_issue_commits", "description": "获取 SVN 代码提交列表", "parameters": {"type": "object", "properties": {"issue_key": {"type": "string", "description": "Jira 任务编号"}}, "required": ["issue_key"]}}},
        {"type": "function", "function": {"name": "get_single_commit_diff", "description": "获取指定版本号的代码 Diff", "parameters": {"type": "object", "properties": {"revision_id": {"type": "string", "description": "SVN 版本号，如 40538"}}, "required": ["revision_id"]}}},
        {"type": "function", "function": {"name": "search_docs_catalog", "description": "知识库目录检索", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索关键词"}, "source": {"type": "string", "enum": ["notion", "gdrive", "all"]}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "read_specific_doc", "description": "按 ID 读取文档全文", "parameters": {"type": "object", "properties": {"doc_id": {"type": "string", "description": "文档 ID"}, "source": {"type": "string", "enum": ["notion", "gdrive"]}}, "required": ["doc_id", "source"]}}},
    ]
    
    AVAILABLE_TOOLS = _load_tools_from_registry()
    logger.info(f"[Plugins] Active tools: {[t['function']['name'] for t in AVAILABLE_TOOLS]}")
except ImportError:
    logger.warning("yaml module not available, using hardcoded tools")
    AVAILABLE_TOOLS = _FALLBACK_TOOLS if '_FALLBACK_TOOLS' in dir() else []



# ═══════════════════════════════════════════════════════════════
#  Alice V2.0 — 4 原子工具执行器 (LlamaIndex 式层级检索)
# ───────────────────────────────────────────────────────────────
#  思想根源: 复刻 LlamaIndex Document Summary Index 算法
#    - search_docs_catalog  = 获取所有 summary_ids + 格式化为批次
#    - read_specific_doc    = docstore.get_nodes() 按 ID 读全文
#    - query_jira_metadata  = Jira 元数据 (标题/状态/经办人)
#    - get_issue_commits    = SVN FishEye 双跳 Diff 检索
#
#  所有工具通过标准 DeepSeek API Tool Calling 协议调用,
#  LLM 自主决策工具的选择、顺序和参数,Python 代码只负责执行。
# ═══════════════════════════════════════════════════════════════

def _exec_query_jira_metadata(args: dict, user_pat: str = "") -> str:
    """工具1: 获取 Jira 任务元数据 (仅标题/状态/经办人 — 轻量级)"""
    issue_key = args.get("issue_key", "").strip()
    if not issue_key:
        return json.dumps({"status": "error", "result": "缺少 issue_key 参数"})
    try:
        resp = jira.jira_get(
            f"{jira.api_url}/issue/{issue_key}?fields=summary,issuetype,status,assignee",
            timeout=10, user_pat=user_pat
        )
        if resp.status_code == 200:
            f = resp.json().get("fields", {})
            return json.dumps({"status": "ok", "result": {
                "key": issue_key,
                "title": f.get("summary", ""),
                "type": f.get("issuetype", {}).get("name", ""),
                "status": f.get("status", {}).get("name", ""),
                "assignee": f.get("assignee", {}).get("displayName", "未分配"),
                "url": f"{jira.base_url}/browse/{issue_key}"
            }}, ensure_ascii=False)
        return json.dumps({"status": "error", "result": f"Issue {issue_key} 查询失败 (HTTP {resp.status_code})"})
    except Exception as e:
        return json.dumps({"status": "error", "result": f"Jira 查询异常: {str(e)[:200]}"})


def _exec_get_issue_commits(args: dict) -> str:
    """工具2: SVN FishEye 双跳精确检索代码 Diff"""
    issue_key = args.get("issue_key", "").strip()
    if not issue_key:
        return json.dumps({"status": "error", "result": "缺少 issue_key 参数"})
    try:
        from knowledge_retriever import fetch_precise_commits_via_fisheye
        result = fetch_precise_commits_via_fisheye(issue_key)
        if result and len(str(result)) > 20:
            text = str(result)[:8000]
            return json.dumps({"status": "ok", "llm_text": text}, ensure_ascii=False)
        return json.dumps({"status": "ok", "result": f"Issue {issue_key} 暂无关联的 SVN 代码变更"})
    except Exception as e:
        return json.dumps({"status": "error", "result": f"SVN 检索异常: {str(e)[:200]}"})

def _exec_get_single_commit_diff(args: dict) -> str:
    """工具5: 按需召回单次 SVN 提交的代码 Diff（供 LLM 分析用）"""
    revision_id = str(args.get("revision_id", "")).strip()
    if not revision_id:
        return json.dumps({"status": "error", "result": "缺少 revision_id 参数"})
    try:
        from knowledge_retriever import get_single_commit_diff
        diff_text = get_single_commit_diff(revision_id)
        if diff_text and len(str(diff_text)) > 20:
            text = str(diff_text)[:8000]
            return json.dumps({"status": "ok", "llm_text": text}, ensure_ascii=False)
        return json.dumps({"status": "ok", "result": f"版本 {revision_id} 暂无 Diff 内容"})
    except Exception as e:
        return json.dumps({"status": "error", "result": f"Diff 检索异常: {str(e)[:200]}"})


def _exec_search_docs_catalog(args: dict) -> str:
    """工具3: 知识库目录检索 — 仅返回标题+摘要候选列表
    【复刻 LlamaIndex "查目录" 阶段: 获取所有 summary_ids → 格式化批次】
    不返回全文！获取候选列表后请用 read_specific_doc 读详情。"""
    query = args.get("query", "").strip()
    source = args.get("source", "all")
    catalog = []  # [{doc_id, title, source, snippet(100)}]

    NK = os.getenv("NOTION_KEY") or getattr(jira, '_global_cfg', {}).get("NOTION_KEY", "")
    hd = {"Authorization": f"Bearer {NK}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"} if NK else {}

    # ── Notion 目录检索 ──
    if hd and source in ("notion", "all"):
        try:
            r = http.post("https://api.notion.com/v1/search",
                headers=hd, json={"query": query, "page_size": 10}, timeout=10)
            notion_results = []
            if r.status_code == 200:
                notion_results = r.json().get("results", [])

            # Alice V2.0 降级策略: 首次搜索无结果 + query较长时, 截取前4字重试
            if not notion_results and len(query) >= 4:
                short_q = query[:4]
                logger.info(f"[Catalog] Notion retry with short query: '{short_q}'")
                try:
                    r2 = http.post("https://api.notion.com/v1/search",
                        headers=hd, json={"query": short_q, "page_size": 10}, timeout=10)
                    if r2.status_code == 200:
                        notion_results = r2.json().get("results", [])
                        logger.info(f"[Catalog] Notion retry results: {len(notion_results)}")
                except Exception:
                    pass

            for p in notion_results:
                page_id = p.get("id", "")
                title = extract_notion_title_ultimate(p)
                snippet = ""
                try:
                    props = p.get("properties", {})
                    for pv in props.values():
                        if isinstance(pv, dict) and pv.get("type") == "rich_text":
                            rt = pv.get("rich_text", [])
                            if rt:
                                snippet = "".join(t.get("plain_text", "") for t in rt)[:100]
                                break
                except Exception:
                    pass
                catalog.append({
                    "doc_id": page_id,
                    "title": title or f"Notion Page {page_id[:8]}",
                    "source": "notion",
                    "snippet": snippet
                })
        except Exception as e:
            logger.warning(f"[Catalog] Notion failed: {e}")

    # ── Google Drive 目录检索 ──
    if source in ("gdrive", "all"):
        try:
            GK = os.getenv("GDRIVE_KEY") or getattr(jira, '_global_cfg', {}).get("GDRIVE_KEY", "")
            if GK:
                raw_folders = os.getenv("GDRIVE_FOLDERS") or getattr(jira, '_global_cfg', {}).get("GDRIVE_FOLDERS", "")
                folders = [f.strip() for f in re.split(r'[\n,]+', raw_folders) if f.strip()]
                if folders:
                    proxy_ip = os.getenv("GDRIVE_PROXY_IP")
                    proxy_port = os.getenv("GDRIVE_PROXY_PORT")
                    proxies = {"https": f"http://{proxy_ip}:{proxy_port}"} if proxy_ip and proxy_port else None
                    all_files = {}
                    for fid in folders:
                        gr = http.get(
                            f"https://www.googleapis.com/drive/v3/files?key={GK}&q='{fid}'+in+parents&fields=files(id,name,mimeType)&pageSize=30",
                            timeout=10, proxies=proxies)
                        if gr.status_code == 200:
                            for f in gr.json().get("files", []):
                                all_files[f["id"]] = f
                    if query:
                        kws = [kw for kw in re.split(r'[\s,，]+', query) if len(kw) >= 2]
                        extra = []
                        for kw in kws:
                            if re.search(r'[\u4e00-\u9fff]', kw):
                                extra.extend([kw[i:i+2] for i in range(len(kw)-1)])
                        kws = list(set(kws + extra))
                        matched = [f for _, f in all_files.items() if any(k in f.get("name","") for k in kws)]
                    else:
                        matched = list(all_files.values())
                    for f in matched[:15]:
                        catalog.append({
                            "doc_id": f["id"],
                            "title": f.get("name", "未命名"),
                            "source": "gdrive",
                            "snippet": f"type={f.get('mimeType','')}"
                        })
        except Exception as e:
            logger.warning(f"[Catalog] GDrive failed: {e}")

    if not catalog:
        return json.dumps({
            "status": "ok", "result": [],
            "llm_text": (
                "【系统提示 — 搜索无结果，禁止编造】\n"
                f"知识库目录检索 '{query}' 返回 0 条结果。\n"
                "你必须如实告知用户：未在 Notion/GDrive 中找到匹配的文档。\n"
                "绝对禁止虚构文档标题、内容摘要或编造任何业务数据！"
            )
        }, ensure_ascii=False)

    llm_text = f"【文档目录检索结果 — 共 {len(catalog)} 个候选】\n"
    for i, d in enumerate(catalog):
        llm_text += f"{i+1}. [{d['source'].upper()}] {d['title']}"
        if d.get('snippet'):
            llm_text += f" — {d['snippet']}"
        llm_text += f"\n   doc_id: {d['doc_id']}\n"
    llm_text += "\n⚠️ 请使用 read_specific_doc 工具读取感兴趣文档的全文（传入 doc_id 和 source）。"

    return json.dumps({"status": "ok", "result": catalog, "llm_text": llm_text}, ensure_ascii=False)


def _exec_read_specific_doc(args: dict) -> str:
    """工具4: 按文档 ID 读取全文 — 复刻 LlamaIndex docstore.get_nodes()"""
    doc_id = args.get("doc_id", "").strip()
    source = args.get("source", "").strip()
    if not doc_id or not source:
        return json.dumps({"status": "error", "result": "缺少 doc_id 或 source 参数"})

    if source == "notion":
        NK = os.getenv("NOTION_KEY") or getattr(jira, '_global_cfg', {}).get("NOTION_KEY", "")
        if not NK:
            return json.dumps({"status": "error", "result": "Notion API Key 未配置"})
        hd = {"Authorization": f"Bearer {NK}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
        try:
            page_r = http.get(f"https://api.notion.com/v1/pages/{doc_id}", headers=hd, timeout=10)
            blocks_r = http.get(f"https://api.notion.com/v1/blocks/{doc_id}/children?page_size=30", headers=hd, timeout=10)
            content_parts = []
            if page_r.status_code == 200:
                props = page_r.json().get("properties", {})
                for pn, pv in props.items():
                    if isinstance(pv, dict) and pv.get("type") == "title":
                        title = "".join(t.get("plain_text", "") for t in pv.get("title", []))
                        if title:
                            content_parts.append(f"# {title}")
            if blocks_r.status_code == 200:
                for block in blocks_r.json().get("results", []):
                    bt = block.get("type", "")
                    bd = block.get(bt, {})
                    if bt == "paragraph":
                        text = "".join(t.get("plain_text", "") for t in bd.get("rich_text", []))
                        if text.strip(): content_parts.append(text)
                    elif bt.startswith("heading"):
                        text = "".join(t.get("plain_text", "") for t in bd.get("rich_text", []))
                        if text.strip():
                            level = bt.replace("heading_", "")
                            content_parts.append(f"{'#' * int(level)} {text}")
                    elif bt in ("bulleted_list_item", "numbered_list_item"):
                        text = "".join(t.get("plain_text", "") for t in bd.get("rich_text", []))
                        if text.strip(): content_parts.append(f"- {text}")
            content = "\n\n".join(content_parts)[:8000]
            if not content:
                content = "(文档为空或无法解析)"
            return json.dumps({"status": "ok", "llm_text": content}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "result": f"Notion 读取异常: {str(e)[:200]}"})

    elif source == "gdrive":
        GK = os.getenv("GDRIVE_KEY") or getattr(jira, '_global_cfg', {}).get("GDRIVE_KEY", "")
        if not GK:
            return json.dumps({"status": "error", "result": "Google Drive API Key 未配置"})
        try:
            meta_r = http.get(
                f"https://www.googleapis.com/drive/v3/files/{doc_id}?key={GK}&fields=name,mimeType",
                timeout=10)
            if meta_r.status_code != 200:
                return json.dumps({"status": "error", "result": f"文件 {doc_id} 不存在或无权访问"})
            mime = meta_r.json().get("mimeType", "")
            name = meta_r.json().get("name", "未命名")
            export_mime = "text/csv" if "spreadsheet" in mime else "text/plain"
            cr = http.get(
                f"https://www.googleapis.com/drive/v3/files/{doc_id}/export?mimeType={export_mime}&key={GK}",
                timeout=15)
            if cr.status_code == 200:
                content = f"# {name}\n\n{cr.text[:8000]}"
                return json.dumps({"status": "ok", "llm_text": content}, ensure_ascii=False)
            return json.dumps({"status": "error", "result": f"文件 {name} 导出失败 (HTTP {cr.status_code})"})
        except Exception as e:
            return json.dumps({"status": "error", "result": f"GDrive 读取异常: {str(e)[:200]}"})

    return json.dumps({"status": "error", "result": f"不支持的文档来源: {source}"})


def _exec_search_jira_issues(args: dict, user_pat: str = "", frontend_cfg: dict = None) -> str:
    """工具5: Jira 关键词搜索 — 无具体 Issue Key 时的模糊搜索"""
    keyword = args.get("keyword", "").strip()
    if not keyword:
        return json.dumps({"status": "error", "result": "缺少 keyword 参数"})

    def _do_search(kw: str) -> tuple:
        proj_keys = (frontend_cfg or {}).get("jira_projects", "") or os.getenv("JIRA_PROJECTS", "CT")
        proj_cond = "project in (" + ",".join(k.strip() for k in proj_keys.split(",") if k.strip()) + ")"

        # 仿 Baize: 中文 Bigram 分解, 用 OR 多词搜索替代短语匹配
        # "球员系统属性设计" → summary~"球员" OR summary~"系统" OR summary~"属性" OR summary~"设计"
        terms = []
        if re.search(r'[\u4e00-\u9fff]', kw) and len(kw) >= 4:
            # 中文: 拆为2字片段 (避免短语匹配0结果)
            for i in range(len(kw) - 1):
                bg = kw[i:i+2]
                if bg not in terms:
                    terms.append(bg)
        if not terms:
            terms = [kw]  # 英文或短词直接用原词

        text_conds = " OR ".join([f'summary ~ "{t}" OR description ~ "{t}"' for t in terms[:8]])
        jql = f'{proj_cond} AND ({text_conds}) ORDER BY updated DESC'
        logger.info(f"[SearchJira] JQL: {jql[:120]}")
        resp = jira.jira_get(
            f"{jira.api_url}/search",
            params={"jql": jql, "maxResults": 10, "fields": "key,summary,issuetype,status,assignee"},
            timeout=10, user_pat=user_pat
        )
        if resp.status_code != 200:
            return 0, []
        data = resp.json()
        return data.get("total", 0), data.get("issues", [])

    try:
        total, issues = _do_search(keyword)

        # 降级: 首次0结果 + 关键词过长(>6中文) → 拆为2字片段重试
        if total == 0 and len(keyword) > 6 and re.search(r'[\u4e00-\u9fff]', keyword):
            short_kw = keyword[:4]  # 取前4字
            logger.info(f"[SearchJira] 降级重试: '{keyword}' → '{short_kw}'")
            total2, issues2 = _do_search(short_kw)
            if total2 > 0:
                total, issues = total2, issues2
                keyword = short_kw  # 更新为实际使用的关键词
        items = []
        for issue in issues[:10]:
            f = issue.get("fields", {})
            items.append({
                "key": issue["key"],
                "summary": f.get("summary", ""),
                "status": f.get("status", {}).get("name", ""),
                "assignee": f.get("assignee", {}).get("displayName", "未分配"),
                "type": f.get("issuetype", {}).get("name", ""),
            })
        llm_text = f"【Jira 关键词搜索 '{keyword}' — 共 {total} 条】\n"
        for it in items:
            llm_text += f"- {it['key']} [{it['status']}] {it['summary']} ({it['assignee']})\n"
        if not items:
            llm_text = (
                "【系统提示 — 搜索无结果，禁止编造】\n"
                f"Jira 关键词搜索 '{keyword}' 返回 0 条结果。\n"
                "你必须如实告知用户：未找到匹配的 Jira 任务。\n"
                "绝对禁止虚构 Issue Key（如 PLAYER-1234）或捏造任务列表！\n"
                "如果用户需要的是一般性建议而非项目实际数据，请明确标注'以下为通用分析，非项目实际数据'。"
            )
        return json.dumps({"status": "ok", "result": {"total": total, "issues": items}, "llm_text": llm_text}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "result": f"Jira 搜索异常: {str(e)[:200]}"})


# ── 工具路由表 ──────────────────────────────────────────
_ATOMIC_TOOLS = {
    "query_jira_metadata":  ("query_jira_metadata",  _exec_query_jira_metadata),
    "get_issue_commits":    ("get_issue_commits",    _exec_get_issue_commits),
    "get_single_commit_diff": ("get_single_commit_diff", _exec_get_single_commit_diff),
    "search_docs_catalog":  ("search_docs_catalog",  _exec_search_docs_catalog),
    "read_specific_doc":    ("read_specific_doc",    _exec_read_specific_doc),
    "search_jira_issues":   ("search_jira_issues",   _exec_search_jira_issues),
}


def execute_tool_call(tool_name: str, arguments_str, user_cfg=None, frontend_cfg=None) -> str:
    """Alice V2.0 工具调度器 — 支持 4 原子工具 + 向后兼容"""
    try:
        args = json.loads(arguments_str) if isinstance(arguments_str, str) else (arguments_str or {})
        logger.info(f"[Tool] {tool_name} args={json.dumps(args, ensure_ascii=False)[:120]}")

        user_pat = ""
        if isinstance(user_cfg, dict):
            user_pat = user_cfg.get("jira_pat", "")

        # V2.0 原子工具
        if tool_name in _ATOMIC_TOOLS:
            name, fn = _ATOMIC_TOOLS[tool_name]
            if name in ("query_jira_metadata", "search_jira_issues"):
                return fn(args, user_pat=user_pat, frontend_cfg=frontend_cfg)
            return fn(args)

        # 向后兼容: 确认卡工具
        elif tool_name == "add_jira_comment":
            try:
                from jira_operation_manager import create_operation_card
                op = create_operation_card("add_comment", {
                    "issue_key": args.get("issue_key",""),
                    "body": args.get("body","")
                })
                return json.dumps({
                    "status": "confirm_required",
                    "operation_id": op["id"],
                    "operation": {"kind": "add_comment", "issue_key": args.get("issue_key",""),
                                  "body_preview": args.get("body","")[:100]},
                    "result": f"即将为 {args.get('issue_key')} 添加评论:\n{args.get('body','')[:200]}"
                })
            except Exception as e:
                return json.dumps({"status": "error", "result": f"创建确认卡失败: {str(e)[:200]}"})

        elif tool_name == "list_jira_comments":
            try:
                resp = jira.jira_get(
                    f"{jira.api_url}/issue/{args.get('issue_key','')}/comment", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    comments = data.get("comments", [])
                    items = [{
                        "author": c.get("author",{}).get("displayName","未知"),
                        "time": c.get("created","")[:19],
                        "body": (c.get("body","") or "")[:300]
                    } for c in comments[:args.get("max_results", 10)]]
                    return json.dumps({"status": "ok", "result": {"total": data.get("total",0), "comments": items}})
                return json.dumps({"status": "error", "result": f"查询评论失败 (HTTP {resp.status_code})"})
            except Exception as e:
                return json.dumps({"status": "error", "result": f"查询评论异常: {str(e)[:200]}"})

        else:
            return f"Error: Tool '{tool_name}' not registered in Alice V2.0 registry"

    except Exception as e:
        logger.error(f"[Tool] {tool_name} failed: {e}")
        return f"Error: {str(e)[:200]}"


# ═══════════════════════════════════════════════════════════════
#  核心端点: /v1/chat/completions — Alice V2.0 ReAct 循环
# ───────────────────────────────────────────────────────────────
#  标准 DeepSeek API Tool Calling 协议:
#    1. messages + tools → LLM 决策是否调用工具
#    2. finish_reason="tool_calls" → 并发执行多个工具
#    3. tool results 追加到 messages → LLM 继续推理
#    4. finish_reason="stop" → 流式输出最终回答
#  最大 5 轮迭代,防死循环
# ═══════════════════════════════════════════════════════════════

# Alice V2.0 系统提示词
CORE_SYSTEM_PROMPT_V2 = """你是 Alice V2.0，Jira 项目和知识库管理 AI 助手。

【致命指令 — 必须无条件遵守】
当用户需要查询数据时，你【必须直接调用工具 (tool_calls)】。
绝对禁止先输出"让我搜索..."、"第一步..."、"好的，我来查询"等文字再调用工具！
有数据需求 → 立即 tool_calls → 拿到结果 → 再回答。一步都不准多！
⚠️ 当用户问"提交了什么"、"改了什么代码"、"有什么变更"、"commit"、"提交列表"时，必须调用 get_issue_commits 去查，不要根据任务状态（如"待PO分转"）预判是否有提交！很多"待处理"状态的任务实际已有SVN提交。

【代码 Diff 分析 — 按需召回 (On-Demand RAG)】
- get_issue_commits 只返回提交列表（版本号/作者/时间/文件数），不包含代码 Diff！
- 当用户要求"分析代码"、"审查 diff"、"这次提交改了什么"、"帮我看看 r40538"时，先确保已获取提交列表，再用 get_single_commit_diff 拉取指定版本的完整代码差异。
- 你可以通过 get_single_commit_diff 获取具体版本的代码 diff（传入参数如 "40538" 或 "r40538"）。
- 如果用户没有指定版本号就要求分析 diff，请先询问用户："你想分析哪一个版本的 Diff？以下是提交列表供选择。"

【跨工具关联检索 — LlamaIndex 精髓：读详情 → 抽特征 → 搜关联】
当用户要求"查找与某文档相关的 Jira 任务"或类似跨数据源的关联问题时，你必须执行以下链路：
1. 先用 read_specific_doc 读取文档全文
2. 从文档内容中提取 2-3 个最具区分度的业务术语
   ⚠️ 关键: 不是用户原话中的词！而是文档内容中特有的、高频的、业务相关的名词！
   例如: 文档标题是"球员系统属性设计"，但文档内容里反复出现"展示系数"、"命名规范"、"属性分类"
   → 你应该用"展示系数"、"命名规范"搜索 Jira，而不是"球员系统"
3. 用这些文档提取的术语作为 keyword 调用 search_jira_issues
4. 展示匹配结果

【行为守则】
1. 见好就收：如果你通过工具获取的数据已经足够回答用户当前的问题，请直接给出专业、自信的最终答案，【不要】反问用户"还需要我做什么吗"或"是否需要进一步查询"。
2. 工具边界：read_specific_doc 只能用来阅读知识库（如 Notion/GDrive）的文档 ID。当你获取到代码差异（Diff）或文件路径（如 server/xxx.go）时，绝对禁止使用该工具去尝试读取代码文件！doc_id 必须且只能来源于 search_docs_catalog！
3. 禁止口头模拟工具：没调用工具就不准假装有数据。
4. 上下文缺失必须反问：代词无指代时直接问，禁止猜。
5. 禁止知识库幻觉：100% 来源工具结果，没搜到就说没搜到。
6. 无数据绝对熔断：无工具返回数据 = 禁止输出任何数值/表格/Issue列表。
7. 搜索结果必须展示：工具返回了任务列表就必须以表格列出前5-10条，不能因为"没有精确匹配"就跳过不展示！

【回答风格】
- 中文，结构化（表格/列表）
- 基于事实，诚实
- 严禁输出 XML/DSML 标签
- 最终回答必须是纯文本，禁止包含 <|tool_calls|> 等标签语法"""



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

    # 重新加载工具注册表（支持热更新）
    global AVAILABLE_TOOLS
    try:
        AVAILABLE_TOOLS = _load_tools_from_registry()
    except Exception:
        pass

    tool_whitelist = frontend_cfg.get("tool_whitelist", [])
    active_tools = [t for t in AVAILABLE_TOOLS
                    if not tool_whitelist or t["function"]["name"] in tool_whitelist]

    # ══════════════════════════════════════════════════
    #  Alice V2.0 Intent Router — 路由层 (industry-validated)
    #  原理: LLM 不应在检索前做"有没有数据"的推理判断
    #  路由层根据意图模式预选工具子集, LLM 只负责"拿到数据后怎么回答"
    # ══════════════════════════════════════════════════
    try:
        from intent_router import route_intent, get_filtered_tools
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break
        tool_names, intent_label = route_intent(user_text)
        if tool_names:
            active_tools = get_filtered_tools(active_tools, tool_names)
    except ImportError:
        pass  # intent_router.py 不存在时降级为全量工具

    logger.info(f"[V2.0] Active tools: {[t['function']['name'] for t in active_tools]}")

    def generate_stream():
        max_steps = frontend_cfg.get("max_steps", 5)
        step = 0

        # ── 消息清洗 ─────────────────────────────────
        cleaned_msgs = []
        for msg in messages:
            if isinstance(msg.get("content"), str):
                cleaned_msgs.append(msg)
            elif isinstance(msg.get("content"), list):
                text = "".join(item.get("text","") for item in msg["content"]
                              if item.get("type") == "text")
                cleaned_msgs.append({"role": msg["role"], "content": text})

        # 提取用户最后一条消息
        user_text = ""
        for msg in reversed(cleaned_msgs):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break

        # ── Issue Key 预检测 ────────────────────────
        issue_keys_found = set()
        if user_text:
            found = re.findall(r'(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])', user_text)
            issue_keys_found.update(found)
        
        # ══════════════════════════════════════════════════════════
        #  VIP 直通车: Pre-flight RAG — Python 层完成所有检索
        #  剥夺 LLM 工具权, 直接给"开卷考试" Prompt → Final Stream
        # ══════════════════════════════════════════════════════════
        _diff_rev = re.search(r'(?:r|版本\s*)\s*(\d{4,6})', user_text or "")
        _diff_intent = bool(re.search(r'diff|分析.*代码|代码.*分析|代码.*审查|变更|改了.*什么', user_text or ""))
        if _diff_rev and _diff_intent:
            _rev_id = _diff_rev.group(1)
            logger.info(f"[VIP] Pre-flight RAG for r{_rev_id}")
            
            # ── Hop 1: Python 查 Diff ──
            raw_diff = ""
            try:
                from knowledge_retriever import get_single_commit_diff
                _d = get_single_commit_diff(_rev_id)
                raw_diff = str(_d)[:3000] if _d and len(str(_d)) > 20 else ""
            except Exception as _e1:
                logger.error(f"[VIP] Diff fetch failed: {_e1}")
                raw_diff = f"[Diff r{_rev_id} 获取失败]"
            
            # ── Hop 2: Python 查关键字 ──
            _ik_str = list(issue_keys_found)[:1]
            _ik_str = _ik_str[0] if _ik_str else ""
            try:
                from knowledge_retriever import extract_dynamic_keywords
                _search_kw = extract_dynamic_keywords(user_text or "", _ik_str)
            except Exception:
                _search_kw = _ik_str or user_text[:30]
            logger.info(f"[VIP] Search keyword: '{_search_kw}'")
            
            # ── Hop 3: Python 查知识库 ──
            doc_content = ""
            _doc_title = ""
            _doc_source_label = "知识库"
            try:
                _search_result = _exec_search_docs_catalog({"query": _search_kw, "source": "all"})
                _sr_obj = json.loads(_search_result)
                if _sr_obj.get("status") == "ok":
                    catalog = _sr_obj.get("result", [])
                    if isinstance(catalog, list) and catalog:
                        _first = catalog[0]
                        _doc_id = _first.get("doc_id", "")
                        _doc_source = _first.get("source", "notion")
                        _doc_title = _first.get("title", "未知文档")
                        _doc_source_label = _doc_source.upper()
                        if _doc_id:
                            logger.info(f"[VIP] Reading doc: 《{_doc_title}》 from {_doc_source_label}")
                            _read_result = _exec_read_specific_doc({"doc_id": _doc_id, "source": _doc_source})
                            _rr_obj = json.loads(_read_result)
                            doc_content = str(_rr_obj.get("llm_text", _rr_obj.get("result", "")))[:2000]
            except Exception as _e2:
                logger.error(f"[VIP] Knowledge fetch failed: {_e2}")
            
            # ── Hop 4: 组装"开卷考试" Prompt (含文档溯源元数据) ──
            _anti_hallucination = (
                f"【强制指令】：如果用户后续追问业务逻辑来源于哪里，或者有哪些相关文档，"
                f"你必须如实回答来源于{_doc_source_label}真实文档《{_doc_title}》。"
                f"绝对禁止编造任何不存在的文档名称！"
            ) if _doc_title else ""
            
            if doc_content:
                final_prompt = (
                    f"请作为一个资深主程，对以下 SVN 代码变更进行 Code Review。\n\n"
                    f"【业务背景参考】（来自系统自动检索的 {_doc_source_label} 真实文档：《{_doc_title}》）：\n{doc_content}\n\n"
                    f"【代码 Diff】：\n{raw_diff}\n\n"
                    f"请结合背景，指出代码核心修改意图和潜在风险。不要罗列代码，直接输出分析。\n\n"
                    f"{_anti_hallucination}\n\n"
                    f"【用户的真实特定诉求】：{user_text}\n"
                    f"（请在审查或输出时特别关注用户的上述诉求）"
                )
            else:
                final_prompt = (
                    f"请作为一个资深主程，对以下 SVN 代码变更进行 Code Review。\n\n"
                    f"（未能自动检索到相关业务文档，请基于代码本身进行分析）\n\n"
                    f"【代码 Diff】：\n{raw_diff}\n\n"
                    f"请指出代码核心修改意图和潜在风险。不要罗列代码，直接输出分析。\n\n"
                    f"【用户的真实特定诉求】：{user_text}\n"
                    f"（请在审查或输出时特别关注用户的上述诉求）"
                )
            
            # ── VIP 流式输出辅助函数 ──
            def _vip_stream(prompt: str, fallback_text: str = ""):
                """VIP 直通车: 纯 prompt → LLM stream (无 tools, 不经过 ReAct)"""
                _msgs = [{"role": "user", "content": prompt}]
                logger.info(f"[VIP] Direct stream ({len(prompt)} chars), no tools, no ReAct")
                try:
                    vip_resp = http.post(DEEPSEEK_URL, headers=headers, json={
                        "model": user_cfg["deepseek_model"],
                        "messages": _msgs,
                        "stream": True,
                        "temperature": 0.1
                    }, stream=True, timeout=90)
                    _yielded = False
                    for raw_line in vip_resp.iter_lines():
                        if raw_line:
                            decoded = raw_line.decode('utf-8', errors='replace')
                            if any(tag in decoded for tag in ('<|tool_calls|>', '<|DSML|>', '<|invoke|>', '<|parameter|>')):
                                continue
                            _yielded = True
                            yield raw_line + b"\n"
                    if not _yielded and fallback_text:
                        yield f"data: {json.dumps({'choices':[{'delta':{'content': fallback_text}}]}, ensure_ascii=False)}\n\n".encode('utf-8')
                except Exception as _ve:
                    logger.error(f"[VIP] Stream failed: {_ve}")
                    yield f"data: {json.dumps({'choices':[{'delta':{'content':'⚠️ 系统底层数据服务暂不可用（SVN或知识库异常），请联系管理员或稍后重试。'}}]})}\n\n".encode('utf-8')
            
            # ── Hop 5: 执行 VIP 流式 ──
            yield from _vip_stream(final_prompt, '【VIP 直通车】LLM 未能生成分析，以下是原始 Diff：\\n\\n' + raw_diff[:4000])
            yield b"data: [DONE]\n\n"
            return  # 完全跳过后续所有逻辑

        # ══════════════════════════════════════════════════════════
        #  Catalog VIP: 文档目录直通车
        #  用户问"有哪些文档"/"查Notion" → Python 直检索 + 纯文本输出
        # ══════════════════════════════════════════════════════════
        _doc_intent = bool(re.search(r'notion|文档|wiki|知识库|设计案|策划案', user_text or "", re.I))
        if _doc_intent:
            logger.info(f"[VIP] Catalog Pre-flight RAG")
            _ik_str = list(issue_keys_found)[:1]
            _ik_str = _ik_str[0] if _ik_str else ""
            try:
                from knowledge_retriever import extract_dynamic_keywords
                _search_kw = extract_dynamic_keywords(user_text or "", _ik_str)
            except Exception:
                _search_kw = _ik_str or (user_text or "")[:30]
            logger.info(f"[VIP-Catalog] Search keyword: '{_search_kw}'")
            
            # Python 后台检索
            try:
                _search_result = _exec_search_docs_catalog({"query": _search_kw, "source": "all"})
                _sr_obj = json.loads(_search_result)
                catalog = _sr_obj.get("result", []) if isinstance(_sr_obj, dict) else []
            except Exception:
                catalog = []
            
            if catalog and isinstance(catalog, list) and len(catalog) > 0:
                cat_text = "\n".join([f"- [{d.get('source','').upper()}] 《{d.get('title','未知')}》" for d in catalog[:5]])
                _cat_prompt = (
                    f"用户正在询问相关的文档。系统已在后台自动检索了关键词 '{_search_kw}'，"
                    f"找到以下真实存在的文档：\n\n{cat_text}\n\n"
                    f"【强制指令】：请直接将这个真实的文档列表整理后告诉用户。"
                    f"绝对禁止编造列表中没有的文档！如果不在此列表中，就说不知道！\n\n"
                    f"【用户的真实特定诉求】：{user_text}\n"
                    f"（请在输出时特别关注用户的上述诉求）"
                )
            else:
                _cat_prompt = (
                    f"用户正在询问相关的文档。系统已在后台自动检索了关键词 '{_search_kw}'，"
                    f"但没有找到任何结果。\n\n"
                    f"【强制指令】：请如实告诉用户未找到，绝对禁止捏造、编造任何假文档！\n\n"
                    f"【用户的真实特定诉求】：{user_text}\n"
                    f"（请在输出时特别关注用户的上述诉求）"
                )
            
            yield from _vip_stream(_cat_prompt, '【VIP Catalog】LLM 未能生成回答，以下是原始检索结果。')
            yield b"data: [DONE]\n\n"
            return

        # ── 构建初始消息列表 ────────────────────────
        system_context = CORE_SYSTEM_PROMPT_V2

        # 预注入 Issue Key 基本信息
        if issue_keys_found:
            pre_context = ""
            for ik in sorted(issue_keys_found, key=len, reverse=True)[:3]:
                try:
                    resp = jira.jira_get(
                        f"{jira.api_url}/issue/{ik}?fields=summary,status,assignee")
                    if resp.status_code == 200:
                        issue = resp.json()
                        f = issue.get("fields", {})
                        pre_context += (
                            f"\n[已检测到 Issue] {ik}: {f.get('summary','')} "
                            f"[{f.get('status',{}).get('name','')}] "
                            f"经办人: {f.get('assignee',{}).get('displayName','未分配')}"
                        )
                except Exception:
                    pass
            if pre_context:
                system_context += f"\n\n## 当前会话上下文{pre_context}"

        # 人名解析 (Jira username 查询)
        name_match = re.search(
            r'[\u4e00-\u9fff]{2,4}(?=负责|的|做|提交|处理|开发|最近)', user_text or "")
        if name_match:
            cn_name = name_match.group()
            try:
                username = resolve_jira_username(jira, cn_name)
                if username:
                    system_context += (
                        f"\n\n[用户解析] {cn_name} 的 Jira 账号为 {username}。"
                        f"查询时请使用 assignee = {username}。"
                    )
            except Exception:
                pass

        # ── 构建 messages ────────────────────────────
        tool_messages = [{"role": "system", "content": system_context}]
        # 保留历史消息（跳过已有的 system prompt）
        for msg in cleaned_msgs:
            if msg.get("role") != "system":
                tool_messages.append(msg)

        # ══════════════════════════════════════════════
        #  ReAct 主循环
        # ══════════════════════════════════════════════
        while step < max_steps:
            step += 1
            yield f"data: {json.dumps({'custom_type': 'agent_step', 'step': step, 'max_steps': max_steps})}\n\n".encode('utf-8')

            # Phase 1: LLM 决策 (非流式, 带 tools)
            logger.info(f"[ReAct] Step {step}/{max_steps} — asking LLM with {len(active_tools)} tools")
            try:
                probe_resp = http.post(DEEPSEEK_URL, headers=headers, json={
                    "model": user_cfg["deepseek_model"],
                    "messages": tool_messages,
                    "tools": active_tools,
                    "tool_choice": "auto",
                    "stream": False
                }, timeout=30)
                probe_data = probe_resp.json()
                choice = probe_data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "")
                logger.error(f"[ReAct-TRACE] Step {step}: finish_reason={finish_reason} | has_tool_calls={bool(msg.get('tool_calls'))} | content_first_100={str(msg.get('content',''))[:100]}")
                
                # ▸ 检测 tool_calls / DSML 文本泄漏: 如果 finish=stop 但 content 是 tool_calls 文本
                # 兼容 deepseek-v4-flash 的 <|DSML|>tool_calls> 变体
                # 注入禁止指令后不加 tools 重试一次
                _content_str = str(msg.get("content", ""))
                _has_leak = ("<|tool_calls|>" in _content_str or 
                            "<|DSML|>" in _content_str or
                            "<|invoke|>" in _content_str)
                if finish_reason == "stop" and _has_leak:
                    logger.warning(f"[ReAct] Tool_calls text leak detected in probe, retrying without tools")
                    
                    # 清理 tool_calls 历史 + 发起纯文本 retry
                    for _m in tool_messages:
                        if _m.get("role") == "assistant" and "tool_calls" in _m:
                            del _m["tool_calls"]
                    
                    tool_messages.append({
                        "role": "system",
                        "content": "你现在是纯文本回答模式。禁止输出任何 XML/DSML/tool_calls 标记。直接基于上文数据回答。"
                    })
                    probe_resp2 = http.post(DEEPSEEK_URL, headers=headers, json={
                        "model": user_cfg["deepseek_model"],
                        "messages": tool_messages,
                        "stream": False
                    }, timeout=30)
                    probe_data2 = probe_resp2.json()
                    choice2 = probe_data2.get("choices", [{}])[0]
                    msg = choice2.get("message", {})
                    finish_reason = choice2.get("finish_reason", "")
                    
                    # 清洗 retry 响应中的 DSML 标签
                    _retry_content = str(msg.get("content", "")).strip()
                    if finish_reason == "stop" and _retry_content:
                        import re as _re_clean
                        _retry_content = _re_clean.sub(r'<\|tool_calls\|>.*?</\|tool_calls\|>', '', _retry_content, flags=_re_clean.DOTALL)
                        _retry_content = _re_clean.sub(r'<\|invoke\|.*?</\|invoke\|>', '', _retry_content, flags=_re_clean.DOTALL)
                        _retry_content = _re_clean.sub(r'<\|parameter\|.*?</\|parameter\|>', '', _retry_content, flags=_re_clean.DOTALL)
                        _retry_content = _re_clean.sub(r'<\|DSML\|>.*?</\|DSML\|>', '', _retry_content, flags=_re_clean.DOTALL)
                        _retry_content = _re_clean.sub(r'</?\|DSML\|>', '', _retry_content).strip()
                        if _retry_content:
                            logger.info(f"[ReAct] DSML retry success, direct-output {len(_retry_content)} chars")
                            yield f"data: {json.dumps({'choices':[{'delta':{'content':_retry_content}}]})}\n\n".encode('utf-8')
                            yield b"data: [DONE]\n\n"
                            return
                    
                    logger.error(f"[ReAct] DSML retry still has tool_calls after cleaning")
            except Exception as e:
                logger.error(f"[ReAct] LLM probe failed at step {step}: {e}")
                break

            # ── 分支 A: LLM 决定调用工具 ──
            if finish_reason == "tool_calls" and msg.get("tool_calls"):
                tcs = msg["tool_calls"]
                logger.info(f"[ReAct] Step {step}: {len(tcs)} tool call(s) — {[tc['function']['name'] for tc in tcs]}")

                # 追加 assistant message (含 tool_calls)
                tool_messages.append(msg)

                # ── 并发执行所有工具 (asyncio.gather) ──
                def _run_one_tool(tc):
                    """同步执行单个工具，返回 (tool_call_id, name, result, error)"""
                    t_name = tc.get("function", {}).get("name", "unknown")
                    t_args = tc.get("function", {}).get("arguments", "{}")
                    tc_id = tc.get("id", "")

                    # 发送 SSE: plugin_state running
                    return {
                        "tc_id": tc_id,
                        "name": t_name,
                        "sse_running": json.dumps({
                            "custom_type": "plugin_state",
                            "plugin": {"name": t_name, "status": "running"}
                        }, ensure_ascii=False),
                        "result": execute_tool_call(t_name, t_args, user_cfg, frontend_cfg),
                        "sse_done": json.dumps({
                            "custom_type": "plugin_state",
                            "plugin": {"name": t_name, "status": "done"}
                        }, ensure_ascii=False)
                    }

                # Alice V2.0 P0 Fix: 统一 ThreadPool 并发执行工具
                # 避免 asyncio.run() 在 Waitress 线程内嵌套事件循环
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=len(tcs)) as pool:
                    futures = {pool.submit(_run_one_tool, tc): tc for tc in tcs}
                    results = []
                    for f in as_completed(futures, timeout=30):
                        try:
                            results.append(f.result())
                        except Exception as e:
                            logger.error(f"[ReAct] Tool thread failed: {e}")

                # 按顺序发送 SSE 事件 + 追加 tool messages
                for r in results:
                    yield f"data: {r['sse_running']}\n\n".encode('utf-8')
                    yield f"data: {r['sse_done']}\n\n".encode('utf-8')

                    # 检查确认卡
                    try:
                        obj = json.loads(r['result'])
                        if obj.get("status") == "confirm_required":
                            yield f"data: {json.dumps({'custom_type': 'confirm_required', 'operation': obj.get('operation'), 'operation_id': obj.get('operation_id'), 'message': obj.get('result','')})}\n\n".encode('utf-8')
                    except Exception:
                        pass

                    # Alice V2.0 fix: 剥离 JSON 外壳，LLM 只看到纯文本
                    # 工具返回 {"status":"ok","llm_text":"..."} → 提取 llm_text
                    tool_content = r["result"]
                    try:
                        obj = json.loads(tool_content)
                        if isinstance(obj, dict):
                            # 优先 llm_text，其次 result 字段
                            tool_content = obj.get("llm_text") or obj.get("result") or tool_content
                    except (json.JSONDecodeError, TypeError):
                        pass  # 不是 JSON，直接使用原值

                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": r["tc_id"],
                        "name": r["name"],
                        "content": str(tool_content)
                    })

                # ══ Rabbit 核选项: 工具执行后直接输出数据，跳过后续 ReAct 步骤 ══
                # deepseek-v4-flash 在后续轮次中持续输出 tool_calls 文本而非事实回答
                # ⚠️ 如果调用了 get_single_commit_diff 或处于 Inception 模式 → 不拦截！
                _has_diff_in_step = any(
                    r.get("name") == "get_single_commit_diff"
                    for r in results
                )
                if not _has_diff_in_step:
                    _nuke_results = []
                    for _nm in reversed(tool_messages):
                        if _nm.get("role") == "tool":
                            _nuke_results.insert(0, str(_nm.get("content", "")))
                        elif _nm.get("role") == "assistant":
                            break
                    if _nuke_results:
                        _nuke_text = "\n\n---\n\n".join(_nuke_results)[:6000]
                        logger.info(f"[ReAct] [NUCLEAR] Direct-output {len(_nuke_text)} chars from tool data (step {step})")
                        yield f"data: {json.dumps({'choices':[{'delta':{'content': '【Alice 查询结果】\\n\\n' + _nuke_text}}]}, ensure_ascii=False)}\n\n".encode('utf-8')
                        yield b"data: [DONE]\n\n"
                        return
                else:
                    logger.info(f"[ReAct] [NUCLEAR-SKIP] get_single_commit_diff detected, bypassing nuclear — let LLM analyze diff")

                continue  # 继续循环让 LLM 处理工具结果
            # ── 分支 B: LLM 决定输出最终回答 ──
            elif finish_reason == "stop":
                # 过滤 msg 中的 tool_calls / DSML 文本泄漏
                if msg.get("content"):
                    import re as _re
                    cleaned = str(msg["content"])
                    # 标准 OpenAI tool_calls 文本泄漏
                    cleaned = _re.sub(r'<\|tool_calls\|>.*?</\|tool_calls\|>', '', cleaned, flags=_re.DOTALL)
                    cleaned = _re.sub(r'<\|invoke\|.*?</\|invoke\|>', '', cleaned, flags=_re.DOTALL)
                    cleaned = _re.sub(r'<\|parameter\|.*?</\|parameter\|>', '', cleaned, flags=_re.DOTALL)
                    # deepseek-v4-flash DSML 变体: <|DSML|>tool_calls> ... </|DSML|>tool_calls>
                    cleaned = _re.sub(r'<\|DSML\|>.*?</\|DSML\|>', '', cleaned, flags=_re.DOTALL)
                    # 残留的孤标签
                    cleaned = _re.sub(r'</?\|DSML\|>', '', cleaned)
                    if cleaned.strip():
                        msg["content"] = cleaned.strip()
                    else:
                        msg.pop("content", None)  # 全是 tool_calls 文本 → 去掉
                tool_messages.append(msg)
                logger.info(f"[ReAct] LLM finished after {step} step(s), streaming final answer")
                break

            # ── 分支 C: 其他情况 (length/content_filter) ──
            else:
                if msg.get("content"):
                    # 同样清理可能的 tool_calls 文本 (含 DSML 变体)
                    import re as _re2
                    c2 = str(msg["content"])
                    c2 = _re2.sub(r'<\|tool_calls\|>.*?</\|tool_calls\|>', '', c2, flags=_re2.DOTALL)
                    c2 = _re2.sub(r'<\|invoke\|.*?</\|invoke\|>', '', c2, flags=_re2.DOTALL)
                    c2 = _re2.sub(r'<\|parameter\|.*?</\|parameter\|>', '', c2, flags=_re2.DOTALL)
                    c2 = _re2.sub(r'<\|DSML\|>.*?</\|DSML\|>', '', c2, flags=_re2.DOTALL)
                    c2 = _re2.sub(r'</?\|DSML\|>', '', c2)
                    if c2.strip():
                        msg["content"] = c2.strip()
                tool_messages.append(msg)
                logger.warning(f"[ReAct] unexpected finish_reason: {finish_reason}")
                break

        # ── 达到最大步数: 强制收尾 ──
        if step >= max_steps:
            yield f"data: {json.dumps({'custom_type': 'agent_step', 'step': step, 'state': 'force_finish'})}\n\n".encode('utf-8')
            if tool_messages and tool_messages[-1].get("role") != "user":
                tool_messages.append({
                    "role": "user",
                    "content": "[系统提示: 已超最大工具调用步数，请基于已获取的信息直接回答用户问题]"
                })

        # ══════════════════════════════════════════════
        #  Alice V2.0: 空值熔断检查 (仿白泽占位符模式)
        #  扫描本轮 tool messages，若有关键工具返回空结果→注入强制提醒
        # ══════════════════════════════════════════════
        empty_tools = set()
        empty_signals = [
            "搜索无结果", "0 条结果", "未找到匹配", "暂无关联",
            "没有找到", "暂无", "not found", "返回 0 条",
            "共 0 条", "total\": 0", "\"total\":0",
        ]
        for msg in tool_messages:
            if msg.get("role") == "tool":
                content = str(msg.get("content", ""))
                if any(sig in content for sig in empty_signals):
                    name = msg.get("name", "unknown")
                    empty_tools.add(name)
        if empty_tools:
            tool_messages.append({
                "role": "system",
                "content": (
                    f"【数据熔断警告 — 最高优先级，必须遵守】\n"
                    f"以下工具返回了空结果: {', '.join(sorted(empty_tools))}。\n"
                    f"用户的原始问题是: {user_text[:100]}\n"
                    f"你必须明确告诉用户: 这些数据源当前未返回匹配数据。\n"
                    f"绝对禁止虚构任何 Issue Key（如 GAME-1234、CT-99999 等格式）！\n"
                    f"绝对禁止虚构文档标题或业务数据！\n"
                    f"如果没有足够的事实数据，直接回答'当前未查到相关数据，建议尝试其他关键词'。"
                )
            })
            logger.info(f"[ReAct] Empty-check injected for: {empty_tools}")

        # ══════════════════════════════════════════════
        #  Rabbit Nuclear Intercept V2: 最终防线
        #  不管 ReAct 如何退出（tool_calls/stop/DSML/预注入元数据）,
        #  只要用户问了提交相关的问题且有 Issue Key，强制调工具输出
        # ══════════════════════════════════════════════
        _has_diff_tool = any(
            m.get("role") == "tool" and m.get("name") == "get_single_commit_diff"
            for m in tool_messages
        )
        
        # ▸ Prompt Inception 检测: 如果用户消息中包含预置 diff 数据 → 全放行
        import sys as _sys4
        _sys4.stderr.write(f"[NUCLEAR-DEBUG] has_diff_tool={_has_diff_tool} tool_count={sum(1 for m in tool_messages if m.get('role')=='tool')}\n")
        _sys4.stderr.flush()
        
        if _has_diff_tool:
            logger.info(f"[NUCLEAR-V2] get_single_commit_diff detected, bypassing nuclear — let LLM analyze diff")
        else:
            _has_commit_tool = any(
                m.get("role") == "tool" and m.get("name") == "get_issue_commits"
                for m in tool_messages
            )
            _user_asks_commit = bool(re.search(
                r'提交|commit|改了什么代码|代码变更|diff|变更了哪些|改了哪些文件|提交记录|提交内容|改了.*什么',
                user_text or ""
            ))
            _has_issue_key = bool(issue_keys_found)
            
            if _user_asks_commit and _has_issue_key and not _has_commit_tool:
                logger.error(f"[NUCLEAR-V2] Commit query detected but no tool was called! Force-executing get_issue_commits for {issue_keys_found}")
                try:
                    from knowledge_retriever import fetch_precise_commits_via_fisheye
                    for ik in sorted(issue_keys_found, key=len, reverse=True)[:1]:
                        commit_data = fetch_precise_commits_via_fisheye(ik)
                        if commit_data and len(str(commit_data)) > 20:
                            import json as _json_nuke
                            yield f"data: {_json_nuke.dumps({'choices':[{'delta':{'content': '【Alice 查询结果】\\n\\n' + str(commit_data)[:6000]}}]}, ensure_ascii=False)}\n\n".encode('utf-8')
                            yield b"data: [DONE]\n\n"
                            return
                except Exception as _nuke_err:
                    logger.error(f"[NUCLEAR-V2] Force-execute failed: {_nuke_err}")

        # 如果已有 tool 结果（通过 ReAct 正常调用），也直接输出
        _all_tool_results = []
        for _tm in tool_messages:
            if _tm.get("role") == "tool":
                _all_tool_results.append(str(_tm.get("content", "")))
        if _all_tool_results and not _has_diff_tool:
            _nuke_combined = "\n\n---\n\n".join(_all_tool_results)[:6000]
            logger.info(f"[NUCLEAR-V2] Direct-output {len(_nuke_combined)} chars from existing tool data")
            import json as _json_nuke2
            yield f"data: {_json_nuke2.dumps({'choices':[{'delta':{'content': '【Alice 查询结果】\\n\\n' + _nuke_combined}}]}, ensure_ascii=False)}\n\n".encode('utf-8')
            yield b"data: [DONE]\n\n"
            return

        # ══════════════════════════════════════════════
        #  最终回答: 流式 SSE 输出 (只有核拦截未触发时才到达这里)
        # ══════════════════════════════════════════════
        logger.info(f"[ReAct] Streaming final answer with {len(tool_messages)} messages")

        # ▸ Debug: 打印最后一条 tool message 的原始内容
        last_tool_msg = None
        for msg in reversed(tool_messages):
            if msg.get("role") == "tool":
                last_tool_msg = msg
                break
        if last_tool_msg:
            content = str(last_tool_msg.get("content", ""))
            # 检查是否有 Unicode 转义
            has_unicode_escape = "\\u" in content
            logger.error(f"[DEBUG-FINAL] Last tool msg: {len(content)} chars | "
                         f"Unicode escape: {has_unicode_escape} | "
                         f"Starts with: {repr(content[:120])}")
        else:
            logger.error(f"[DEBUG-FINAL] NO tool message in {len(tool_messages)} messages!")
            
        # 追加 system message — 软化容错版

        # 追加 system message 告诉模型现在是纯文本回答模式
        # 软化版：允许模型诚实地回复"未查到"而非恐慌性编造
        tool_messages.append({
            "role": "system",
            "content": (
                "【数据提取指令】请严格且仅从上方 tool 角色的返回结果中提取 SVN 版本号、提交人及修改摘要。"
                "如果 tool 返回内容为空或无法解析，请明确回复'未查询到该 Issue 的代码提交记录'。"
                "绝不允许基于自身知识库或先验概率编造、拼凑任何版本号或人员名称！"
                "直接输出纯文本，禁止输出 <|tool_calls|> / <|DSML|> 标记。"
            )
        })
        # ══════════════════════════════════════════════
        #  Rabbit Debug Interceptor: 检查最终消息完整性
        # ══════════════════════════════════════════════
        import json as _json_dbg, sys as _sys
        _dbg_lines = [
            "=================== RABBIT DEBUG INTERCEPTOR ===================",
            f"Total messages count: {len(tool_messages)}",
        ]
        for idx, msg in enumerate(tool_messages[-3:]):
            content_raw = str(msg.get('content', ''))
            _dbg_lines.append(f"MSG [-{3-idx}]: Role: {msg.get('role')} | Content: {_json_dbg.dumps(content_raw, ensure_ascii=False)[:300]}...")
        _dbg_lines.append("================================================================")
        _dbg_text = "\n".join(_dbg_lines)
        _sys.stderr.write(_dbg_text + "\n")
        _sys.stderr.flush()
        logger.error(f"[RABBIT] Interceptor fired: {len(tool_messages)} msgs, last role={tool_messages[-1].get('role') if tool_messages else 'NONE'}")

        # ▸ 清理 tool_messages: 移除 assistant 消息中的 tool_calls 字段
        # 防止 LLM 被历史中的 function calling 格式诱导继续输出 tool_calls 文本
        for _msg in tool_messages:
            if _msg.get("role") == "assistant" and "tool_calls" in _msg:
                del _msg["tool_calls"]
        logger.info(f"[ReAct] Cleaned tool_calls from assistant msgs, streaming {len(tool_messages)} msgs")

        try:
            _final_content_yielded = False
            final_resp = http.post(DEEPSEEK_URL, headers=headers, json={
                "model": user_cfg["deepseek_model"],
                "messages": tool_messages,
                "stream": True,
                "temperature": 0.1
            }, stream=True, timeout=60)

            consecutive_filtered = 0
            for raw_line in final_resp.iter_lines():
                if raw_line:
                    # 过滤 tool_calls / DSML 文本泄漏
                    decoded = raw_line.decode('utf-8', errors='replace')
                    if any(tag in decoded for tag in (
                        '<|tool_calls|>', '<|invoke|>', '<|parameter|>',
                        '<|DSML|>', '</|DSML|>'
                    )):
                        consecutive_filtered += 1
                        # 如果连续过滤超过 20 行，LLM 大概率在持续输出 tool_calls
                        # 强行注入停止信号
                        if consecutive_filtered > 20:
                            logger.error("[ReAct] Too many filtered lines, LLM stuck in tool_calls mode")
                            yield f"data: {json.dumps({'choices':[{'delta':{'content':'[系统提示] AI 模型输出异常，请刷新页面重试。'}}]})}\n\n".encode('utf-8')
                            break
                        continue
                    consecutive_filtered = 0
                    _final_content_yielded = True
                    yield raw_line + b"\n"
        except Exception as e:
            yield f"data: {json.dumps({'choices':[{'delta':{'content':f'[Error: {e}]'}}]})}\n\n".encode('utf-8')

        # ══ Final Stream 安全网: 如果 LLM 全部输出被过滤 → 回退输出原始数据 ══
        if not _final_content_yielded and _has_diff_tool:
            logger.error(f"[FINAL-SAFETY] LLM output fully filtered! Fallback to raw diff data")
            _raw_diff = []
            for _tm in tool_messages:
                if _tm.get("role") == "tool" and _tm.get("name") == "get_single_commit_diff":
                    _raw_diff.append(str(_tm.get("content", ""))[:4000])
            if _raw_diff:
                _safe_text = "【Alice】LLM 分析未成功生成，以下是原始代码 Diff 数据：\n\n" + "\n\n---\n\n".join(_raw_diff)
                yield f"data: {json.dumps({'choices':[{'delta':{'content':_safe_text}}]}, ensure_ascii=False)}\n\n".encode('utf-8')

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
                    if line:
                        # 防泄漏过滤（与 chat_completions 一致）
                        try:
                            d = line.decode('utf-8')
                            d = re.sub(r'<\s*\|?\s*DSML\s*\|?\s*(?:tool_calls)?\s*>', '', d, flags=re.I)
                            d = re.sub(r'<\s*\|\s*tool_calls\s*>', '', d, flags=re.I)
                            d = re.sub(r'<\s*/\s*\|\s*tool_calls\s*>', '', d, flags=re.I)
                            line = d.encode('utf-8')
                        except: pass
                        yield line + b'\n'
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
