"""
AI Bridge v6 — Alice V2.0 — asyncio 真并发 + 流式优先 + 语义缓存
启动: python ai_bridge.py
"""
import os, sys, re, json, time, logging, asyncio, hashlib, threading, collections, concurrent.futures
import selectors

# ═══════════════════════════════════════════════════════════════
#  cursor-sdk WinError 10038 补丁（Python 3.12+Windows 下 select.select 不支持 pipe）
#  与 cursor_agent_lane.py L18-62 完全一致，确保 ai_bridge.py 内所有
#  cursor-sdk 调用（test/models 端点）不受 WinError 10038 影响。
# ═══════════════════════════════════════════════════════════════

class _PollingSelector(selectors._BaseSelectorImpl):
    """轮询选择器：用轮询替代 select.select()，绕过 WinError 10038。"""
    _POLL_S = 0.02

    def register(self, fileobj, events, data=None):
        key = super().register(fileobj, events, data)
        return key

    def unregister(self, fileobj):
        return super().unregister(fileobj)

    def select(self, timeout=None):
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        while True:
            ready = []
            for fd in list(self._fd_to_key):
                key = self._fd_to_key[fd]
                if key.events & selectors.EVENT_READ:
                    try:
                        os.read(fd, 0)
                    except (BlockingIOError, OSError):
                        continue
                    ready.append((key, selectors.EVENT_READ))
            if ready or (deadline is not None and time.monotonic() >= deadline):
                return ready
            time.sleep(min(timeout or self._POLL_S, self._POLL_S))


selectors.DefaultSelector = _PollingSelector  # type: ignore[assignment]

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

# ═══════════════════════════════════════════════════════════════
# v3.0 Phase 0-1 新增：loguru 日志基建（约束#16-17）
# ═══════════════════════════════════════════════════════════════
from loguru import logger as loguru_logger
import uuid

loguru_logger.remove()  # 移除默认 handler
loguru_logger.add(
    "logs/alice_{time:YYYY-MM-DD}.log",
    rotation="50 MB",
    retention="5 days",
    compression="zip",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[trace_id]: <8} | {message}",
)
loguru_logger.configure(extra={"trace_id": "--------"})

# H6: loguru → logging 桥接（v3.0 loguru 日志同步到 logging，保证监控/审计统一）
class _LoguruToLoggingHandler:
    """将 loguru 消息转发到 Python logging。"""
    def write(self, msg: str):
        msg = msg.strip()
        if msg:
            logging.getLogger("v3").info(msg)
    def flush(self):
        pass

loguru_logger.add(_LoguruToLoggingHandler(), level="INFO", format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[trace_id]: <8} | {message}")

# ═══════════════════════════════════════════════════════════════
# v3.0 Phase 0.11：Pydantic API 契约校验（约束#20）
# ═══════════════════════════════════════════════════════════════
from pydantic import BaseModel, Field


class ConfirmCardPayload(BaseModel):
    """HITL ConfirmCard 确认载荷：幂等 Key + 操作类型 + 数据"""
    idempotency_key: str = Field(..., pattern=r'^alice-tx-[a-f0-9\-]+$')
    action: str = Field(..., pattern=r'^(create_issue|update_issue|add_comment)$')
    issue_data: dict


# ═══════════════════════════════════════════════════════════════
# v3.0 Phase 1.3：Dify RAG 调用器（约束#2：仅 RAG API）
# ═══════════════════════════════════════════════════════════════
import httpx as _httpx_module

# ── Dify 配置（.env.dify，Phase 0.3 / Phase 5.1） — 必须在 DIFY_* 读取前加载 ──
_DIFY_DOTENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.dify")
if os.path.exists(_DIFY_DOTENV_PATH):
    with open(_DIFY_DOTENV_PATH, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                _key, _val = _key.strip(), _val.strip()
                if _key and (not os.environ.get(_key)):
                    os.environ[_key] = _val

# 直接从 JSON 文件读取 Dify 配置（避免循环依赖 load_global_config）
_DIFY_CONFIG = {}
_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "global_config.json")
if os.path.exists(_config_path):
    try:
        with open(_config_path, "r", encoding="utf-8") as _f:
            _DIFY_CONFIG = json.load(_f)
    except Exception:
        pass

DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", _DIFY_CONFIG.get("DIFY_BASE_URL", "http://localhost:5001"))
DIFY_API_KEY = os.getenv("DIFY_API_KEY", _DIFY_CONFIG.get("DIFY_API_KEY", ""))
DIFY_DATASET_ID = os.getenv("DIFY_DATASET_ID", _DIFY_CONFIG.get("DIFY_DATASET_ID", ""))
DIFY_DATASET_API_KEY = os.getenv("DIFY_DATASET_API_KEY", _DIFY_CONFIG.get("DIFY_DATASET_API_KEY", ""))


def _dify_dataset_api_key() -> str:
    """获取 Dify 数据集 API 可用的 Key（v3.1 双模）。
    优先 Dataset Key（dataset-*），为空则回退 App Key（app-*）。
    """
    return DIFY_DATASET_API_KEY or DIFY_API_KEY


def _dify_check_configured() -> bool:
    """Dify 是否已配置（至少有一个 Key 和一个 Dataset ID）。"""
    return bool((DIFY_DATASET_API_KEY or DIFY_API_KEY) and DIFY_DATASET_ID)

# ── n8n 配置（.env.n8n，Phase 0.4-0.6 产出） ───────────────
_N8N_DOTENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.n8n")
_NEARBY_DOTENV_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(_N8N_DOTENV_PATH):
    with open(_N8N_DOTENV_PATH, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                _key, _val = _key.strip(), _val.strip()
                if _key and (not os.environ.get(_key)):
                    os.environ[_key] = _val

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")


def dify_retrieve(query: str, trace_id: str = "", top_k: int = 5) -> dict:
    """Dify 知识库 RAG 检索（仅检索，不使用对话/工作流端点·约束#2）"""
    api_key = _dify_dataset_api_key()
    if not api_key or not DIFY_DATASET_ID:
        loguru_logger.warning(f"[{trace_id}] Dify RAG 未配置，返回空结果")
        return {"error": "知识库未配置，请联系管理员。"}

    url = f"{DIFY_BASE_URL}/v1/datasets/{DIFY_DATASET_ID}/retrieve"
    try:
        resp = _httpx_module.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "query": query,
                "retrieval_model": {
                    "search_method": "keyword_search",
                    "reranking_enable": False,
                    "top_k": top_k,
                    "score_threshold_enabled": False,
                    "score_threshold": 0.0,
                },
            },
            timeout=10.0,  # 约束#8c
        )
        if resp.status_code == 401:
            _hint = "（RAG API 需 dataset-* 开头的 Key，当前仅配置了 app-* Key）" if not DIFY_DATASET_API_KEY else ""
            loguru_logger.error(f"[{trace_id}] Dify RAG 401: Key 权限不足{_hint}")
            return {"error": f"Dify Key 权限不足（RAG API 需 dataset-* 开头的 Key）"}
        if resp.status_code != 200:
            loguru_logger.error(f"[{trace_id}] Dify RAG 检索失败: HTTP {resp.status_code}")
            return {"error": "知识库服务暂时不可用，请稍后重试"}  # 约束#8c 中文翻译
        loguru_logger.info(f"[{trace_id}] Dify RAG 检索耗时 {resp.elapsed.total_seconds():.1f}s")
        return resp.json()
    except Exception as e:
        loguru_logger.error(f"[{trace_id}] Dify RAG 检索异常: {e}")
        return {"error": "知识库服务暂时不可用，请稍后重试"}

# ── 意图分类（移植自白泽 Baize）─────────────────────────────
from intent_classifier import (
    classify_intent,
    should_intercept,
    needs_confirmation,
    is_jira_operation,
    is_smalltalk_greeting,
    should_use_chat_only_lane,
)

# ── 模块拆分导入 ──────────────────────────────────────────
from prompt_manager import (
    PROJECT_SCHEMA_MAP, CN_STATUS_MAP, enhance_jql,
    classify_query_type, L1_CHARS, L2_CHARS,
    CONTEXT_TOTAL_LIMIT, JIRA_ISSUE_DETAIL_LIMIT,
    DECISION_PROMPT, build_decision_prompt,
    AVAILABLE_KNOWLEDGE_SOURCES, CORE_AGENT_SYSTEM_PROMPT,
    resolve_deadline_field, parse_date_range_from_text,
    build_weekly_report_jql, extract_deadline_display,
)
from jira_field_glossary import (
    normalize_glossary,
    format_glossary_for_prompt,
    resolve_glossary_entry_by_text,
    glossary_suggests_deadline,
)
from chat_pipeline.dsml_cleaner import (
    clean_dsml_leak,
    filter_content_lines,
    sse_line_has_dsml_leak,
)
from saas_http import saas_request, get_http_proxies
from chat_orchestrator import (
    prepare_orchestrator_context,
    iter_preflight_sse,
    clean_chat_messages,
    last_user_message_text as _orch_last_user_text,
    build_chat_only_messages,
    iter_llm_sse_messages,
    CHAT_ONLY_SYSTEM,
)

# ═══════════════════════════════════════════════════════════════
#  v3.0 Phase 4.3 — 废弃模块本地桩（约束#21 死代码零残留）
#  react_runner / plugin_gateway / knowledge_retriever 物理删除后
#  此处提供最小兼容桩，保证 ai_bridge.py 可编译运行。
# ═══════════════════════════════════════════════════════════════

# ── 简单 LRU 缓存（H5: threading.Lock 保护读写） ──
class BoundedCache:
    """简单 LRU 缓存桩。"""
    def __init__(self, maxsize=128, ttl=300):
        self._store = {}
        self.maxsize = maxsize
        self.ttl = ttl
        self._lock = threading.Lock()
    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if entry:
                ts, val = entry
                if time.time() - ts < self.ttl:
                    return val
                del self._store[key]
            return None
    def set(self, key, value):
        with self._lock:
            if len(self._store) >= self.maxsize:
                oldest = min(self._store.keys(), key=lambda k: self._store[k][0], default=None)
                if oldest:
                    del self._store[oldest]
            self._store[key] = (time.time(), value)
    def __len__(self):
        with self._lock:
            return len(self._store)
    def keys(self):
        with self._lock:
            return list(self._store.keys())
    def items(self):
        with self._lock:
            return {k: v[1] for k, v in self._store.items()}.items()
    def clear(self):
        with self._lock:
            self._store.clear()

CACHE_TTL = 300
_CONTEXT_CACHE = BoundedCache(maxsize=128, ttl=CACHE_TTL)
_SEMANTIC_CACHE = BoundedCache(maxsize=64, ttl=CACHE_TTL)
_SVN_COMMIT_CACHE = BoundedCache(maxsize=256, ttl=CACHE_TTL)


def make_source_summary(*args, **kwargs):
    return ""


def classify_file_changes(*args, **kwargs):
    return {}


def svn_log_grep(*args, **kwargs):
    return []


def safe_get_commits(*args, **kwargs):
    return []


def extract_notion_title_ultimate(*args, **kwargs):
    return ""


def resolve_jira_username(*args, **kwargs):
    return ""


def l1_jira_fetch(*args, **kwargs):
    return []


def l1_svn_fetch(*args, **kwargs):
    return []


def l1_notion_fetch(*args, **kwargs):
    return []


def l1_gdrive_fetch(*args, **kwargs):
    return []


async def l1_jira_fetch_async(*args, **kwargs):
    return []


async def l1_svn_fetch_async(*args, **kwargs):
    return []


async def l1_notion_fetch_async(*args, **kwargs):
    return []


async def l1_gdrive_fetch_async(*args, **kwargs):
    return []


# ── react_runner 桩 ──
class ReactFallback(Exception):
    pass


ReactRunContext = type("ReactRunContext", (), {
    "__init__": lambda self, **kw: setattr(self, "__dict__", kw),
    "__repr__": lambda self: f"<ReactRunContext stub>",
})


def iter_v2_graph_stream(*args, **kwargs):
    yield "data: {\"type\":\"error\",\"error\":\"Agent v2 已移除（v3.0 迁移），请使用 /v1/agent/stream\"}\n\n"
    yield "data: [DONE]\n\n"


def iter_react_pipeline(*args, **kwargs):
    return iter_v2_graph_stream(*args, **kwargs)


# ── plugin_gateway 桩 ──
def _collect_draft_sse_chunks(*args, **kwargs):
    return []


def _collect_jira_write_sse_chunks(*args, **kwargs):
    return []


def _heuristic_issues_drafts(*args, **kwargs):
    return []


# ── 知识库 L1 懒加载桩（用于 chat_pipeline/vip_fastpath.py） ──
def fetch_precise_commits_via_fisheye(*args, **kwargs):
    return []


def get_single_commit_diff(*args, **kwargs):
    return {}


def extract_dynamic_keywords(*args, **kwargs):
    return []


# ── 持久化日志配置 ──────────────────────────────────────
os.makedirs("logs", exist_ok=True)
_log_format = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
_fh = RotatingFileHandler("logs/alice_bridge.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
_fh.setFormatter(logging.Formatter(_log_format))
_sh = logging.StreamHandler(sys.stderr)
_sh.setFormatter(logging.Formatter(_log_format))
logging.basicConfig(level=logging.INFO, handlers=[_fh, _sh])
logger = logging.getLogger("ai-bridge")

# ═══════════════════════════════════════════════════════════════
# v3.0 Phase 0.10：生产环境 Fail-fast Mock 检查（约束#18）
# ═══════════════════════════════════════════════════════════════
if os.getenv("FLASK_ENV") == "production" and os.getenv("ALICE_MOCK_N8N", "").lower() in ("true", "1", "yes"):
    sys.exit("\u274c 致命错误：生产环境禁止启用 ALICE_MOCK_N8N。请检查环境变量配置。")

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


def _load_field_glossary() -> list:
    return normalize_glossary(load_global_config().get("JIRA_FIELD_GLOSSARY", []))


def _resolved_deepseek_model(config: dict) -> str:
    """文件 global_config 优先，其次环境变量，最后默认 deepseek-chat。"""
    raw = config.get("DEEPSEEK_MODEL")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()


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

def _hub_only_jira_enabled() -> bool:
    return os.environ.get("ALICE_HUB_ONLY_JIRA", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


# ── 前端配置解析（支持用户级 Key 注入）───────────────────────
def parse_user_config(data: dict) -> dict:
    """
    从请求中提取用户配置，优先级：请求体 user_config > config > 环境变量
    返回: {deepseek_key, deepseek_model, jira_pat, jira_email}
    """
    uc = data.get("user_config", {}) or {}
    frontend_cfg = data.get("config", {}) or {}
    global_cfg = load_global_config()
    hub_only = _hub_only_jira_enabled()
    hub_pat = config["jira_pat"] or global_cfg.get("JIRA_PAT", "") or os.getenv("JIRA_PAT", "")
    client_pat = (
        uc.get("user_jira_pat")
        or frontend_cfg.get("jira_pat")
        or data.get("jira_pat")
        or ""
    )
    jira_pat = hub_pat if hub_only else (client_pat or hub_pat)
    return {
        "deepseek_key": uc.get("ai_api_key") or frontend_cfg.get("deepseek_key") or config["deepseek_key"] or global_cfg.get("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_KEY", ""),
        "deepseek_model": (
            uc.get("ai_model")
            or frontend_cfg.get("deepseek_model")
            or global_cfg.get("DEEPSEEK_MODEL")
            or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        ),
        "jira_pat": jira_pat,
        "jira_email": uc.get("user_email") or os.getenv("JIRA_EMAIL", ""),
        "hub_only_jira": hub_only,
    }


_JIRA_FIELDS_CACHE = {"ts": 0, "fields": []}
_JIRA_FIELDS_CACHE_TTL = 3600
_DEADLINE_FIELD_CACHE = {}


def _load_deadline_config_map() -> dict:
    """global_config JIRA_DEADLINE_FIELD_BY_PROJECT → dict"""
    raw = load_global_config().get("JIRA_DEADLINE_FIELD_BY_PROJECT", {})
    if isinstance(raw, dict):
        return {str(k).upper(): str(v) for k, v in raw.items()}
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return {str(k).upper(): str(v) for k, v in obj.items()}
        except json.JSONDecodeError:
            pass
    return {}


def get_all_jira_fields_cached() -> list:
    """GET /rest/api/2/field，进程内缓存 1h"""
    now = time.time()
    if _JIRA_FIELDS_CACHE["fields"] and now - _JIRA_FIELDS_CACHE["ts"] < _JIRA_FIELDS_CACHE_TTL:
        return _JIRA_FIELDS_CACHE["fields"]
    try:
        r = jira.jira_get(f"{jira.api_url}/field", timeout=15)
        if r.status_code == 200:
            fields = r.json()
            _JIRA_FIELDS_CACHE["fields"] = fields
            _JIRA_FIELDS_CACHE["ts"] = now
            return fields
    except Exception as e:
        logger.warning(f"[Fields] /field fetch failed: {e}")
    return _JIRA_FIELDS_CACHE["fields"] or []


def resolve_deadline_field_for_project(project_key: str) -> dict:
    pk = (project_key or "CT").strip().upper()
    cached = _DEADLINE_FIELD_CACHE.get(pk)
    if cached and time.time() - cached[0] < _JIRA_FIELDS_CACHE_TTL:
        return cached[1]
    meta = resolve_deadline_field(pk, _load_deadline_config_map(), get_all_jira_fields_cached())
    _DEADLINE_FIELD_CACHE[pk] = (time.time(), meta)
    logger.info(f"[DeadlineField] {pk} → {meta.get('display_name')} (source={meta.get('source')})")
    return meta


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
    decision_prompt = build_decision_prompt(project_meta, field_glossary=_load_field_glossary())

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
    glossary = _load_field_glossary()
    glossary_hint = format_glossary_for_prompt(glossary, max_items=15)
    glossary_section = ""
    if glossary_hint:
        glossary_section = f"\n团队字段词典（用户口语可能对应下列 Jira 字段）:\n{glossary_hint}\n"
    matched_glossary = resolve_glossary_entry_by_text(question, glossary)

    prompt = f"""分析用户的 Jira 查询需求，提取关键过滤条件并严格输出 JSON 格式。
用户问题: {question}
{glossary_section}
输出格式必须为：
{{
    "time_filter": "this_week" | "this_month" | "today" | "none",
    "target_field": "deadline" | "created" | "updated",
    "status_filter": "unfinished" | "done" | "all"
}}
注意：若询问"本周需要完成/结束的任务"，target_field 取 "deadline"，time_filter 取 "this_week"。
若用户口语命中词典别名且与截止/周报相关，target_field 取 "deadline"。只输出合法的 JSON，不要包裹 Markdown 标记。"""

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

            target_proj = proj_keys[0] if proj_keys else "CT"
            target_field_logical = intent_data.get("target_field", "created")
            if matched_glossary and glossary_suggests_deadline(question, glossary):
                target_field_logical = "deadline"
            if target_field_logical == "deadline":
                if matched_glossary and matched_glossary.get("fieldName"):
                    cfg_map = dict(_load_deadline_config_map())
                    cfg_map[target_proj] = matched_glossary["fieldName"]
                    field_physical = resolve_deadline_field(
                        target_proj, cfg_map, get_all_jira_fields_cached()
                    )["jql_name"]
                else:
                    field_physical = resolve_deadline_field_for_project(target_proj)["jql_name"]
            else:
                schema = PROJECT_SCHEMA_MAP.get(target_proj, PROJECT_SCHEMA_MAP["DEFAULT"])
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


def _extract_project_key_from_text(user_text: str, default: str = "CT") -> str:
    m2 = re.search(r"([A-Z][A-Z0-9]*)\s*项目", user_text or "")
    if m2:
        return m2.group(1).upper()
    skip = {"PM", "SVN", "API", "JIRA", "HTTP", "SSE"}
    for key in re.findall(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*)", user_text or ""):
        if key not in skip and len(key) <= 10:
            return key
    proj_keys = (os.getenv("JIRA_PROJECTS", default) or default).split(",")[0].strip()
    return proj_keys.upper() if proj_keys else default


def _build_weekly_jira_snapshot(user_text: str, frontend_cfg: dict, user_pat: str = "") -> tuple:
    """周报直通车：动态截止时间字段 + 日期区间 → (表格文本, JQL, 元信息)"""
    proj_cfg = (frontend_cfg or {}).get("jira_projects", "") or os.getenv("JIRA_PROJECTS", "CT")
    proj_list = [k.strip().upper() for k in re.split(r'[\s,，]+', proj_cfg) if k.strip()]
    project_key = _extract_project_key_from_text(user_text, proj_list[0] if proj_list else "CT")
    if project_key not in proj_list and proj_list:
        project_key = proj_list[0]

    deadline_meta = resolve_deadline_field_for_project(project_key)
    date_range = parse_date_range_from_text(user_text)
    jql = build_weekly_report_jql(project_key, deadline_meta, date_range)

    rest_fields = "key,summary,status,assignee,issuetype,updated,priority"
    rid = deadline_meta.get("rest_id")
    if rid and rid != "duedate":
        rest_fields += f",{rid}"

    resp = jira.jira_get(
        f"{jira.api_url}/search",
        params={"jql": jql, "maxResults": 50, "fields": rest_fields},
        timeout=15,
        user_pat=user_pat or None,
    )
    if resp.status_code != 200:
        return f"Jira 查询失败 (HTTP {resp.status_code})", jql, deadline_meta, date_range

    data = resp.json()
    total = data.get("total", 0)
    issues = data.get("issues", [])
    disp = deadline_meta.get("display_name", "截止时间")
    start, end, range_label, _ = date_range

    lines = [
        f"【Jira 周报数据】",
        f"- 项目: {project_key}",
        f"- 筛选字段: {disp}（来源: {deadline_meta.get('source', '?')}）",
        f"- 时间范围: {range_label}",
        f"- JQL: {jql}",
        f"- 命中: {total} 条",
        "",
    ]
    lines.append(f"| 编号 | 状态 | 优先级 | 经办人 | {disp} | 标题 |")
    lines.append("|------|------|--------|--------|----------|------|")
    for issue in issues[:30]:
        f = issue.get("fields", {})
        key = issue.get("key", "")
        status = (f.get("status") or {}).get("name", "")
        priority = (f.get("priority") or {}).get("name", "")
        assignee = (f.get("assignee") or {}).get("displayName", "未分配")
        summary = (f.get("summary") or "")[:60]
        dl_val = extract_deadline_display(f, deadline_meta)
        lines.append(f"| {key} | {status} | {priority} | {assignee} | {dl_val} | {summary} |")
    if not issues:
        lines.append(f"| — | — | — | — | — | 该时间范围内无匹配任务 |")
    return "\n".join(lines), jql, deadline_meta, date_range


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
        """Jira 搜索: 结构化引擎优先，LLM JQL 兜底"""
        try:
            from jira_search_engine import (
                parse_query_from_natural_language,
                search_and_analyze,
                format_search_result_for_llm,
            )
            from jira_runtime_config import load_jira_runtime_config

            rt_cfg = load_jira_runtime_config(frontend_cfg)
            query = parse_query_from_natural_language(q, rt_cfg)
            result = search_and_analyze(
                jira, query, config=rt_cfg, user_pat=user_pat, frontend_cfg=frontend_cfg,
                user_question=q, api_key=api_key or "", http_post=http.post,
            )
            if result.get("total", 0) > 0:
                return "## Jira 结构化搜索\n" + format_search_result_for_llm(result, q)[:L1_CHARS["jira"]]

            proj_keys = frontend_cfg.get("jira_projects", "") or os.getenv("JIRA_PROJECTS", "")
            if not proj_keys:
                m = re.search(r'([A-Z]{2,})(?:\u9879\u76ee|\u9879\u76EE|\u4e13\u6848|\s)', q)
                if m: proj_keys = m.group(1)
            if not proj_keys:
                proj_keys = "CT"
            keys = [k.strip() for k in proj_keys.split(",") if k.strip()]
            if not keys:
                return None

            jql = llm_decide_jql(q, keys)
            if not jql:
                explicit_keys = re.findall(r'([A-Z]{2,}-\d+)', q)
                if explicit_keys:
                    jql = f"project in ({','.join(keys)}) AND issue in ({','.join(explicit_keys[:10])})"
            if not jql:
                return None

            r = jira.jira_get(
                "/search",
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
        {"type": "function", "function": {"name": "search_doc_chunks", "description": "知识库语义检索（FAISS 向量相似度）", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "语义查询文本"}, "doc_id": {"type": "string", "description": "限定文档 ID"}, "top_k": {"type": "integer", "description": "返回片段数量", "default": 5}}, "required": ["query"]}}},
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
def _strip_html(text: str) -> str:
    """移除 HTML 标签和实体，返回纯文本"""
    if not text:
        return ""
    import re
    # 移除 HTML 标签
    text = re.sub(r"<[^>]+>", " ", text)
    # 常见 HTML 实体
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&rsquo;", "'")
        .replace("&ldquo;", '"')
        .replace("&rdquo;", '"')
        .replace("&#x27;", "'")
    )
    # 压缩多余空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _exec_query_jira_metadata(args: dict, user_pat: str = "", **kwargs) -> str:
    """工具: 获取 Jira 任务详情（优先用 simplify_issue + 描述摘要 + 最新评论）"""
    issue_key = args.get("issue_key", "").strip()
    if not issue_key:
        return json.dumps({"status": "error", "result": "缺少 issue_key 参数"})
    try:
        resp = jira.jira_get(
            f"{jira.api_url}/issue/{issue_key}"
            "?fields=summary,issuetype,status,assignee,priority,created,updated,duedate,description,project,comment"
            "&expand=renderedFields",
            timeout=10, user_pat=user_pat,
        )
        if resp.status_code == 200:
            data = resp.json()
            from jira_search_engine import simplify_issue
            simplified = simplify_issue(data)

            fields = data.get("fields", {})

            # 描述摘要（尝试 renderedFields，降级到纯文本）
            desc = ""
            rendered = data.get("renderedFields", {})
            if rendered.get("description"):
                desc = _strip_html(rendered["description"])[:500]
            elif fields.get("description"):
                desc_raw = fields["description"]
                if isinstance(desc_raw, dict):
                    desc = _strip_html(str(desc_raw.get("content", desc_raw)))[:500]
                elif isinstance(desc_raw, str):
                    desc = _strip_html(desc_raw)[:500]

            # 最新评论摘要（最近 3 条，每条 ≤200 字）
            comments = []
            comment_data = fields.get("comment") or {}
            raw_comments = comment_data.get("comments", [])
            if isinstance(raw_comments, list) and raw_comments:
                for c in raw_comments[-3:]:
                    body = _strip_html(c.get("body", ""))[:200]
                    author = (c.get("author") or {}).get("displayName", "未知")
                    comments.append({
                        "author": author,
                        "body": body,
                        "created": c.get("created"),
                    })

            result = {
                "key": simplified.get("key", issue_key),
                "title": simplified.get("summary", ""),
                "type": simplified.get("issueType", ""),
                "status": simplified.get("status", ""),
                "assignee": simplified.get("assignee"),
                "priority": simplified.get("priority", ""),
                "created": simplified.get("created"),
                "updated": simplified.get("updated"),
                "duedate": simplified.get("duedate"),
                "description": desc,
                "comments": comments,
                "url": f"{jira.base_url}/browse/{issue_key}",
            }
            return json.dumps({"status": "ok", "result": result}, ensure_ascii=False)
        return json.dumps({"status": "error",
                           "result": f"Issue {issue_key} 查询失败 (HTTP {resp.status_code})"})
    except Exception as e:
        return json.dumps({"status": "error",
                           "result": f"Jira 查询异常: {str(e)[:200]}"})


def _exec_get_issue_commits(args: dict, **kwargs) -> str:
    """工具2: SVN FishEye 双跳精确检索代码 Diff"""
    issue_key = args.get("issue_key", "").strip()
    if not issue_key:
        return json.dumps({"status": "error", "result": "缺少 issue_key 参数"})
    try:
        try:
            from knowledge_retriever import fetch_precise_commits_via_fisheye
            result = fetch_precise_commits_via_fisheye(issue_key)
        except (ImportError, ModuleNotFoundError):
            loguru_logger.warning(f"knowledge_retriever 不可用（v3.0 已迁移），issue_key={issue_key}")
            return json.dumps({"status": "error", "result": "SVN 变更检索不可用（v3.0 已迁移至 FishEye 代理）"})
        if result and len(str(result)) > 20:
            text = str(result)[:8000]
            return json.dumps({"status": "ok", "llm_text": text}, ensure_ascii=False)
        return json.dumps({"status": "ok", "result": f"Issue {issue_key} 暂无关联的 SVN 代码变更"})
    except Exception as e:
        return json.dumps({"status": "error", "result": f"SVN 检索异常: {str(e)[:200]}"})

def _exec_get_single_commit_diff(args: dict, **kwargs) -> str:
    """工具5: 按需召回单次 SVN 提交的代码 Diff（供 LLM 分析用）"""
    revision_id = str(args.get("revision_id", "")).strip()
    if not revision_id:
        return json.dumps({"status": "error", "result": "缺少 revision_id 参数"})
    try:
        try:
            from knowledge_retriever import get_single_commit_diff
            diff_text = get_single_commit_diff(revision_id)
        except (ImportError, ModuleNotFoundError):
            loguru_logger.warning(f"knowledge_retriever 不可用（v3.0 已迁移），revision_id={revision_id}")
            return json.dumps({"status": "error", "result": "Diff 检索不可用（v3.0 已迁移至 SVN Proxy）"})
        if diff_text and len(str(diff_text)) > 20:
            text = str(diff_text)[:8000]
            return json.dumps({"status": "ok", "llm_text": text}, ensure_ascii=False)
        return json.dumps({"status": "ok", "result": f"版本 {revision_id} 暂无 Diff 内容"})
    except Exception as e:
        return json.dumps({"status": "error", "result": f"Diff 检索异常: {str(e)[:200]}"})


from workspace_tools import _exec_read_file, _exec_search_code, _exec_svn_log, _exec_list_directory


def _exec_search_docs_catalog(args: dict, user_text: str = "", **kwargs) -> str:
    """工具3: 知识库目录检索 — 仅返回标题+摘要候选列表
    【复刻 LlamaIndex "查目录" 阶段: 获取所有 summary_ids → 格式化批次】
    不返回全文！获取候选列表后请用 read_specific_doc 读详情。"""
    query = args.get("query", "").strip()
    catalog_query = (user_text or "").strip() or query
    source = args.get("source", "all")
    # E6.2：Issue Key 穿透 — 检索词前置 Key 提高目录命中
    _ik = re.search(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])", query)
    if _ik and _ik.group(1) not in query[:20]:
        query = f"{_ik.group(1)} {query}"
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
            from gdrive_knowledge import (
                enrich_spreadsheet_snippets,
                extract_catalog_keywords,
                is_spreadsheet_mime,
                looks_like_gdrive_file_id,
                match_files_by_name,
                parse_gdrive_file_id,
            )

            GK = os.getenv("GDRIVE_KEY") or getattr(jira, '_global_cfg', {}).get("GDRIVE_KEY", "")
            if GK:
                proxies = get_http_proxies()
                direct_id = parse_gdrive_file_id(query) or (
                    query.strip() if looks_like_gdrive_file_id(query) else ""
                )
                if direct_id:
                    meta_r = saas_request(
                        "GET",
                        f"https://www.googleapis.com/drive/v3/files/{direct_id}?key={GK}&fields=id,name,mimeType",
                        proxies=proxies,
                    )
                    if meta_r.status_code == 200:
                        mf = meta_r.json()
                        snippet = f"type={mf.get('mimeType', '')}"
                        if is_spreadsheet_mime(mf.get("mimeType", "")):
                            row_snip = enrich_spreadsheet_snippets(
                                [mf], extract_catalog_keywords(catalog_query), GK, saas_request, proxies, max_scan=1
                            ).get(direct_id, "")
                            if row_snip:
                                snippet = row_snip
                        catalog.append({
                            "doc_id": mf.get("id", direct_id),
                            "title": mf.get("name", "GDrive"),
                            "source": "gdrive",
                            "snippet": snippet,
                        })
                raw_folders = os.getenv("GDRIVE_FOLDERS") or getattr(jira, '_global_cfg', {}).get("GDRIVE_FOLDERS", "")
                folders = [f.strip() for f in re.split(r'[\n,]+', raw_folders) if f.strip()]
                if folders:
                    all_files = {}
                    for fid in folders:
                        gr = saas_request(
                            "GET",
                            f"https://www.googleapis.com/drive/v3/files?key={GK}&q='{fid}'+in+parents&fields=files(id,name,mimeType)&pageSize=100",
                            proxies=proxies,
                        )
                        if gr.status_code == 200:
                            for f in gr.json().get("files", []):
                                all_files[f["id"]] = f
                    kws = extract_catalog_keywords(catalog_query)
                    row_map: dict = {}
                    matched = match_files_by_name(all_files, kws, query)
                    if not matched and kws:
                        sheets = [f for f in all_files.values() if is_spreadsheet_mime(f.get("mimeType", ""))]
                        row_map = enrich_spreadsheet_snippets(
                            sheets, kws, GK, saas_request, proxies, max_scan=8
                        )
                        matched = [all_files[i] for i in row_map if i in all_files]
                    elif matched and kws:
                        sheets = [f for f in matched if is_spreadsheet_mime(f.get("mimeType", ""))]
                        row_map = enrich_spreadsheet_snippets(
                            sheets, kws, GK, saas_request, proxies, max_scan=5
                        )
                    if not matched and not direct_id:
                        matched = list(all_files.values())[:10]
                    seen_ids = {c["doc_id"] for c in catalog}
                    for f in matched[:15]:
                        fid = f.get("id", "")
                        if fid in seen_ids:
                            continue
                        snippet = row_map.get(fid, "") or f"type={f.get('mimeType','')}"
                        catalog.append({
                            "doc_id": fid,
                            "title": f.get("name", "未命名"),
                            "source": "gdrive",
                            "snippet": snippet,
                        })
        except Exception as e:
            logger.warning(f"[Catalog] GDrive failed: {e}")
            if source == "gdrive":
                return json.dumps({
                    "status": "error",
                    "result": [],
                    "llm_text": (
                        f"【GDrive 目录检索失败】{str(e)[:120]}\n"
                        "请检查 .env 中 HTTP_PROXY/HTTPS_PROXY 或 GDRIVE_PROXY_IP/PORT，稍后重试。"
                    ),
                }, ensure_ascii=False)

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

    from catalog_hybrid import boost_catalog_entries, extract_catalog_needles

    for needle in extract_catalog_needles(query):
        if needle.upper() not in query.upper():
            query = f"{needle} {query}"
    catalog = boost_catalog_entries(catalog, query)

    # M5.x KB 优化令 — FAISS 语义检索主路径，catalog 关键词退为附录
    hybrid_appendix = ""
    faiss_primary = ""
    try:
        import rag_engine as _rag_mod  # noqa: F811
    except (ImportError, ModuleNotFoundError):
        _rag_mod = None

    if _rag_mod is not None:
        try:
            if _rag_mod.is_index_ready():
                chunk_text = _rag_mod.search_doc_chunks(query, top_k=5)
                if chunk_text and not chunk_text.startswith("[RAG]"):
                    faiss_primary = f"【FAISS 语义检索 · 主路径】\n{chunk_text}"
        except Exception as he:
            loguru_logger.debug("[Catalog] FAISS primary failed: %s", he)

    if not faiss_primary:
        # FAISS 不可用 — 降级回 catalog 关键词路径
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
        if os.environ.get("ALICE_HYBRID_RAG", "1").strip().lower() not in ("0", "false", "no"):
            try:
                if _rag_mod._vector_store is None:
                    _rag_mod.init_engine(deepseek_key=os.getenv("DEEPSEEK_KEY", ""))
                if _rag_mod._vector_store:
                    chunk_text = _rag_mod.search_doc_chunks(query, top_k=2)
                    if chunk_text and not chunk_text.startswith("[RAG]"):
                        hybrid_appendix = f"\n\n【Hybrid 向量补充 · E6.5】\n{chunk_text}"
            except Exception as he:
                logger.debug("[Catalog] hybrid rag skipped: %s", he)

    if faiss_primary:
        llm_text = faiss_primary
        if catalog:
            llm_text += f"\n\n【目录关键词附录 — 共 {len(catalog)} 个候选】\n"
            for i, d in enumerate(catalog[:5]):
                llm_text += f"{i+1}. [{d['source'].upper()}] {d['title']} — doc_id: {d['doc_id']}\n"
        llm_text += "\n⚠️ 请使用 read_specific_doc 工具读取感兴趣文档的全文（传入 doc_id 和 source）。"
    else:
        llm_text = f"【文档目录检索结果 — 共 {len(catalog)} 个候选】\n"
        for i, d in enumerate(catalog):
            llm_text += f"{i+1}. [{d['source'].upper()}] {d['title']}"
            if d.get('snippet'):
                llm_text += f" — {d['snippet']}"
            llm_text += f"\n   doc_id: {d['doc_id']}\n"
        llm_text += "\n⚠️ 请使用 read_specific_doc 工具读取感兴趣文档的全文（传入 doc_id 和 source）。"
        llm_text += hybrid_appendix

    return json.dumps({"status": "ok", "result": catalog, "llm_text": llm_text}, ensure_ascii=False)


def _exec_read_specific_doc(args: dict, user_text: str = "", **kwargs) -> str:
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
            content = "\n\n".join(content_parts)
            if not content:
                content = "(文档为空或无法解析)"
            else:
                from doc_content_extractor import build_skeleton_from_markdown, should_use_skeleton

                title = content_parts[0].lstrip("# ").strip() if content_parts else ""
                if should_use_skeleton(content):
                    content = build_skeleton_from_markdown(content, title=title)
                else:
                    content = content[:8000]
            return json.dumps({"status": "ok", "llm_text": content}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "result": f"Notion 读取异常: {str(e)[:200]}"})

    elif source == "gdrive":
        GK = os.getenv("GDRIVE_KEY") or getattr(jira, '_global_cfg', {}).get("GDRIVE_KEY", "")
        if not GK:
            return json.dumps({"status": "error", "result": "Google Drive API Key 未配置"})
        try:
            from gdrive_knowledge import read_gdrive_file_content

            proxies = get_http_proxies()
            uq = (user_text or kwargs.get("user_text") or args.get("user_query") or "").strip()
            ok, content, err = read_gdrive_file_content(
                doc_id, GK, saas_request, proxies, user_query=uq
            )
            if ok:
                return json.dumps({"status": "ok", "llm_text": content}, ensure_ascii=False)
            return json.dumps({
                "status": "error",
                "result": err,
                "llm_text": f"【GDrive】{err}",
            }, ensure_ascii=False)
        except Exception as e:
            hint = (
                "请确认 .env 已配置 HTTP_PROXY/HTTPS_PROXY 或 GDRIVE_PROXY_IP/PORT，"
                "网络恢复后让我重新读取该文档。"
            )
            return json.dumps({
                "status": "error",
                "result": f"GDrive 读取异常: {str(e)[:200]}",
                "llm_text": f"【GDrive 网络异常】无法读取文档内容。{hint}",
            }, ensure_ascii=False)

    return json.dumps({"status": "error", "result": f"不支持的文档来源: {source}"})


def _exec_search_jira_issues(args: dict, user_pat: str = "", frontend_cfg: dict = None, **kwargs) -> str:
    """工具: Jira 结构化搜索（主路径 jira_search_engine，兼容 keyword 参数）"""
    keyword = (args.get("keyword") or args.get("query") or "").strip()
    if not keyword:
        return json.dumps({"status": "error", "result": "缺少 keyword 参数"})
    try:
        from jira_search_engine import (
            parse_query_from_natural_language,
            search_and_analyze,
            format_search_result_for_llm,
            JiraSearchQuery,
        )
        from jira_runtime_config import load_jira_runtime_config

        rt_cfg = load_jira_runtime_config(frontend_cfg or {})

        # ── P1-1: LLM 结构化查询优先（失败降级 regex 规则槽位）──
        query = None
        try:
            from jira_query_builder import parse_query_llm
            structured = parse_query_llm(keyword)
            if structured:
                query = JiraSearchQuery(max_results=rt_cfg.max_search_results)
                if structured.get("assignee"):
                    query.assignees = [structured["assignee"]]
                if structured.get("status"):
                    query.statuses = [structured["status"]]
                if structured.get("projectKey"):
                    query.project_key = structured["projectKey"]
                if structured.get("issueType"):
                    query.issue_types = [structured["issueType"]]
                if structured.get("text"):
                    query.text = structured["text"]
                if structured.get("updatedAfter"):
                    query.updated_after = structured["updatedAfter"]
                if structured.get("updatedBefore"):
                    query.updated_before = structured["updatedBefore"]
                if structured.get("maxResults"):
                    query.max_results = int(structured["maxResults"])
                if structured.get("orderBy"):
                    query.order_by = structured["orderBy"]
                logger.info(
                    "[search_jira_issues] LLM parsed: %s",
                    json.dumps(structured, ensure_ascii=False),
                )
        except Exception as _ql_e:
            logger.warning("[search_jira_issues] LLM query builder failed: %s", _ql_e)

        if query is None:
            query = parse_query_from_natural_language(keyword, rt_cfg)
        if not query.text and not query.assignees:
            query.text = keyword
        if args.get("project_key"):
            query.project_key = args["project_key"]
        if args.get("assignee"):
            query.assignees = [args["assignee"]]
        if args.get("unresolved_only"):
            query.unresolved_only = True
        uc = kwargs.get("user_cfg") if isinstance(kwargs.get("user_cfg"), dict) else {}
        result = search_and_analyze(
            jira, query, config=rt_cfg, user_pat=user_pat, frontend_cfg=frontend_cfg,
            user_question=keyword, api_key=uc.get("deepseek_key", ""), http_post=http.post,
        )
        llm_text = format_search_result_for_llm(result, keyword)
        items = result.get("issues") or []
        return json.dumps({
            "status": "ok",
            "result": {
                "total": result.get("total", 0),
                "issues": items,
                "jql": result.get("jql"),
                "analysis": result.get("analysis"),
            },
            "llm_text": llm_text,
        }, ensure_ascii=False)
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
    "read_file":            ("read_file",            _exec_read_file),
    "search_code":          ("search_code",          _exec_search_code),
    "svn_log":              ("svn_log",              _exec_svn_log),
    "list_directory":       ("list_directory",       _exec_list_directory),
}

def _rag_search(args: dict) -> str:
    """RAG 工具包装器: search_doc_chunks — Phase 4.3 降级为空"""
    query = args.get("query", "")
    top_k = int(args.get("top_k", 3))
    try:
        from backend.rag_engine import search_doc_chunks
        doc_id = args.get("doc_id")
        return search_doc_chunks(query, doc_id, top_k)
    except (ImportError, ModuleNotFoundError):
        return f"[FAISS 索引已废弃（v3.0 迁移至 Dify RAG），查询: {query[:80]}]"
    except Exception as e:
        return f"[RAG 检索异常: {str(e)[:100]}]"

# ── V2.0 Agent 工具执行器映射 (必须在所有 _exec_* 定义之后) ──
_TOOL_EXECUTORS = {
    "query_jira_metadata": _exec_query_jira_metadata,
    "get_issue_commits": _exec_get_issue_commits,
    "get_single_commit_diff": _exec_get_single_commit_diff,
    "search_docs_catalog": _exec_search_docs_catalog,
    "read_specific_doc": _exec_read_specific_doc,
    "search_jira_issues": _exec_search_jira_issues,
    "search_doc_chunks": lambda args: _rag_search(args),  # RAG 工具
    "read_file": _exec_read_file,
    "search_code": _exec_search_code,
    "svn_log": _exec_svn_log,
    "list_directory": _exec_list_directory,
}


def _iter_jira_structured_read_lane(user_text, frontend_cfg, user_cfg, vip_stream_fn):
    """Jira 结构化读直通车 SSE 片段（成功或失败均 yield，失败不抛到 ReAct）。"""
    from jira_search_engine import (
        parse_query_from_natural_language,
        search_and_analyze,
        build_jira_read_answer_prompt,
        format_search_result_for_llm,
    )
    from jira_runtime_config import load_jira_runtime_config

    yield f"data: {json.dumps({'custom_type': 'plugin_state', 'plugin': {'name': 'jira_structured_search', 'status': 'running'}}, ensure_ascii=False)}\n\n".encode("utf-8")
    _rt_cfg = load_jira_runtime_config(frontend_cfg)
    _pat = user_cfg.get("jira_pat", "")
    _query = parse_query_from_natural_language(user_text, _rt_cfg)
    _search_result = search_and_analyze(
        jira, _query, config=_rt_cfg, user_pat=_pat, frontend_cfg=frontend_cfg,
        user_question=user_text,
        api_key=user_cfg.get("deepseek_key", ""),
        http_post=http.post,
    )
    if _search_result.get("requires_user_input") and _search_result.get("supplement"):
        _sup = _search_result["supplement"]
        yield f"data: {json.dumps({'_event': 'jira_search_supplement', 'supplement': _sup, 'partial_jql': _search_result.get('jql')}, ensure_ascii=False)}\n\n".encode("utf-8")
        _fallback = format_search_result_for_llm(_search_result, user_text)
        yield from vip_stream_fn(
            "用户需要在界面选择 Jira 用户后才能继续查询。请先说明需要用户确认的原因，并列出候选。\n\n" + _fallback,
            _fallback,
        )
        return
    yield f"data: {json.dumps({'custom_type': 'plugin_state', 'plugin': {'name': 'jira_structured_search', 'status': 'done', 'jql': _search_result.get('jql'), 'issue_count': _search_result.get('total', 0)}}, ensure_ascii=False)}\n\n".encode("utf-8")
    _read_prompt = build_jira_read_answer_prompt(user_text, _search_result)
    _fallback2 = format_search_result_for_llm(_search_result, user_text)
    yield from vip_stream_fn(_read_prompt, _fallback2)


def _iter_jira_write_express_lane(user_text, user_cfg, intent_info):
    for chunk in _collect_jira_write_sse_chunks(user_text, user_cfg, intent_info):
        yield chunk


def execute_tool_call(
    tool_name: str,
    arguments_str,
    user_cfg=None,
    frontend_cfg=None,
    user_text: str = "",
    request_user_id: str = "",
) -> str:
    """Alice V2.0 工具调度器 — 支持 4 原子工具 + 向后兼容"""
    try:
        args = json.loads(arguments_str) if isinstance(arguments_str, str) else (arguments_str or {})
        logger.info(f"[Tool] {tool_name} args={json.dumps(args, ensure_ascii=False)[:120]}")

        user_pat = ""
        creator_id = (request_user_id or "").strip()
        if isinstance(user_cfg, dict):
            user_pat = user_cfg.get("jira_pat", "")
            if not creator_id:
                creator_id = (user_cfg.get("user_id") or "").strip()
        if not creator_id and isinstance(frontend_cfg, dict):
            creator_id = (frontend_cfg.get("user_id") or "").strip()

        # V2.0 原子工具
        if tool_name in _ATOMIC_TOOLS:
            name, fn = _ATOMIC_TOOLS[tool_name]
            if name in ("query_jira_metadata", "search_jira_issues"):
                return fn(args, user_pat=user_pat, frontend_cfg=frontend_cfg, user_cfg=user_cfg)
            if name in ("search_docs_catalog", "read_specific_doc"):
                return fn(args, user_text=user_text or "")
            return fn(args)

        elif tool_name == "create_issues_draft":
            try:
                from jira_operation_manager import (
                    create_issues_draft,
                    build_draft_tool_response,
                )
                raw = (
                    args.get("issues_list")
                    or args.get("issues")
                    or args.get("drafts")
                    or []
                )
                if not isinstance(raw, list) or len(raw) == 0:
                    return json.dumps({
                        "status": "error",
                        "result": "issues_list 不能为空",
                    })
                draft = create_issues_draft(
                    raw,
                    conversation_id=args.get("conversation_id", ""),
                    source_text=(args.get("source_text") or "")[:500],
                    user_id=creator_id,
                )
                return json.dumps(build_draft_tool_response(draft), ensure_ascii=False)
            except Exception as e:
                return json.dumps({"status": "error", "result": f"草稿箱失败: {str(e)[:200]}"})

        # ── P1-4 受控代码分析工具（只读）─────────────────────
        elif tool_name in ("read_file", "search_code", "svn_log", "list_directory"):
            fn = _TOOL_EXECUTORS.get(tool_name)
            if fn:
                return fn(args)

        # 向后兼容: Jira 写操作确认卡 / 批量 → 草稿箱
        elif tool_name in ("add_jira_comment", "create_jira_issues", "create_issue"):
            try:
                from audit_gateway import audit
                from jira_operation_manager import (
                    create_comment_operation_card,
                    create_operation_card,
                    create_issues_draft,
                    build_draft_tool_response,
                    save_operation,
                    build_confirm_tool_response,
                )
                user_pat = user_cfg.get("jira_pat", "") if isinstance(user_cfg, dict) else ""
                if tool_name == "add_jira_comment":
                    audit_action = "add_comment"
                    audit_data = {
                        "issue_key": args.get("issue_key", ""),
                        "body": args.get("body", ""),
                    }
                    op = create_comment_operation_card(
                        issue_key=args.get("issue_key", ""),
                        body=args.get("body", ""),
                        conversation_id=args.get("conversation_id", ""),
                        user_id=creator_id,
                    )
                    preview = f"即将为 {args.get('issue_key')} 添加评论:\n{(args.get('body') or '')[:200]}"
                else:
                    audit_action = "create"
                    drafts = args.get("drafts") or [{
                        "summary": args.get("summary", ""),
                        "projectKey": args.get("projectKey") or args.get("project_key", ""),
                        "issueType": args.get("issueType") or args.get("issue_type", "Task"),
                        "description": args.get("description", ""),
                        "priority": args.get("priority"),
                        "labels": args.get("labels"),
                        "assignee": args.get("assignee"),
                    }]
                    audit_data = {"drafts": drafts}
                    if len(drafts) > 1:
                        draft = create_issues_draft(
                            drafts,
                            conversation_id=args.get("conversation_id", ""),
                            source_text="tool:create_jira_issues",
                            user_id=creator_id,
                        )
                        return json.dumps(
                            build_draft_tool_response(draft),
                            ensure_ascii=False,
                        )
                    op = create_operation_card(
                        drafts=drafts,
                        conversation_id=args.get("conversation_id", ""),
                        kind="jira_bulk_create",
                        user_id=creator_id,
                    )
                    preview = f"即将创建 {len(drafts)} 个 Jira Issue，请在确认卡上授权。"

                audit_result = audit("jira_write", audit_action, audit_data)
                if audit_result.get("decision") == "deny":
                    return json.dumps({
                        "status": "error",
                        "result": audit_result.get("reason", "审计拒绝"),
                    })
                save_operation(op)
                payload = build_confirm_tool_response(op, preview)
                return json.dumps(payload, ensure_ascii=False)
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

【批量创建 Jira — 草稿箱协议】
当用户要求「草拟 / 拆分多个子任务 / 批量创建多个 Issue」时：
- 【禁止】直接调用 create_issue 写 Jira！
- 【必须】调用 create_issues_draft，传入 issues_list（每条含 summary、projectKey、issueType）。
- 系统会弹出 draft_card，用户核对后才真正创建。

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
   例如: 文档标题是"某模块属性设计"，但文档内容里反复出现"展示系数"、"命名规范"、"属性分类"
   → 你应该用"展示系数"、"命名规范"搜索 Jira，而不是照搬文档标题
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
8. 名单/表格完整输出（最高优先级）：当工具返回了具体的名单、表格行或明确条目数据（如人名、角色名、配置项、Issue Key）时，最终回答必须逐项完整列出具体名称与对应数值，绝对禁止用「等」「若干」「部分」「主要包括」概括或省略工具结果中的任何一条！

【知识库多轮追问 — C9.5】
当用户在后续消息中更换筛选条件（如不同位置、类别、范围）但仍查文档/表格时，必须重新调用 search_docs_catalog 与 read_specific_doc，禁止仅凭上一轮回答推断或否认数据存在。

【Jira 写操作 — 操作确认卡协议】
- 你拥有修改 Jira 状态、创建任务的能力；系统会在执行前自动生成「操作确认卡」供用户审核。
- 用户要求「改成处理中/完成/关闭」等时：走写操作直通车，禁止回答「无权限」「无法修改」。
- 正确话术示例：「已为您生成确认卡，请在卡片上确认后将 CT-10859 流转到处理中。」
- 禁止在未确认的情况下声称已修改成功。

【回答风格】
- 中文，结构化（表格/列表）
- 基于事实，诚实
- 严禁输出 XML/DSML 标签
- 最终回答必须是纯文本，禁止包含 <|tool_calls|> 等标签语法"""


def _message_content_to_text(content) -> str:
    """OpenAI 兼容：string 或 multimodal parts → 纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def _last_user_message_text(messages: list) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            return _message_content_to_text(msg.get("content")).strip()
    return ""


def _build_chat_only_messages(user_text: str) -> list:
    return build_chat_only_messages(user_text)


def _iter_llm_sse_messages(messages, user_cfg, headers, *, temperature=0.65):
    return iter_llm_sse_messages(
        messages,
        user_cfg,
        headers,
        deepseek_url=DEEPSEEK_URL,
        http_post=http.post,
        temperature=temperature,
    )


@app.route("/v1/chat/completions", methods=["POST", "OPTIONS"])
def chat_completions():
    if request.method == 'OPTIONS':
        return Response(status=204)

    data = request.json or {}
    messages = data.get("messages", [])
    user_cfg = parse_user_config(data)
    from user_identity import parse_user_id_from_request

    user_cfg["user_id"] = parse_user_id_from_request(body=data)
    frontend_cfg = data.get("config", {}) or {}
    if user_cfg["user_id"]:
        frontend_cfg = {**frontend_cfg, "user_id": user_cfg["user_id"]}

    # P2-2: 前端发送 engine/mode 参数 → 注入 user_cfg，供 chat_orchestrator 预检链消费
    engine = (data.get("engine") or "").strip()
    if engine and not user_cfg.get("engine"):
        user_cfg["engine"] = engine
    mode = (data.get("mode") or "").strip()
    if mode and not user_cfg.get("mode"):
        user_cfg["mode"] = mode
    # 若 frontend_cfg 中有 cursor_api_key / cursor_sdk_model，也注入 user_cfg
    for _k in ("cursor_api_key", "cursor_sdk_model"):
        _v = (frontend_cfg.get(_k) or "").strip()
        if _v and not user_cfg.get(_k):
            user_cfg[_k] = _v

    conversation_id = (
        data.get("conversation_id")
        or frontend_cfg.get("conversation_id")
        or ""
    )

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
    intent_label = "FULL_SET"
    tool_names: list = []
    route_meta: dict = {}
    user_text = _last_user_message_text(messages)
    intent_info_pre = (
        classify_intent(user_text)
        if user_text
        else {"route": "ordinary_chat", "reason": "empty_text"}
    )
    chat_only_precheck = should_use_chat_only_lane(
        user_text, intent_info_pre, intent_label
    )
    try:
        from intent_router import route_intent, get_filtered_tools

        if not chat_only_precheck and not is_smalltalk_greeting(user_text):
            tool_names, intent_label, route_meta = route_intent(
                user_text, api_key=user_cfg.get("deepseek_key")
            )
            if tool_names:
                active_tools = get_filtered_tools(active_tools, tool_names)
    except ImportError:
        pass  # intent_router.py 不存在时降级为全量工具
    if chat_only_precheck:
        intent_label = "CHAT_ONLY"

    logger.info(f"[V2.0] Active tools: {[t['function']['name'] for t in active_tools]}")

    def generate_stream():
        max_steps = frontend_cfg.get("max_steps", 5)
        step = 0

        dis = route_meta.get("disambiguation") if route_meta else None
        if dis:
            from hitl_sse import intent_disambiguation

            yield intent_disambiguation(dis)

        orch_ctx = prepare_orchestrator_context(
            messages,
            user_cfg,
            frontend_cfg,
            headers,
            conversation_id,
            intent_label,
            active_tools,
            deepseek_url=DEEPSEEK_URL,
            http_post=http.post,
            jira_client=jira,
            exec_search_docs_catalog=_exec_search_docs_catalog,
            exec_read_specific_doc=_exec_read_specific_doc,
            build_weekly_jira_snapshot=_build_weekly_jira_snapshot,
            iter_jira_structured_read_lane=_iter_jira_structured_read_lane,
        )
        cleaned_msgs = orch_ctx.cleaned_msgs
        user_text = orch_ctx.user_text
        intent_info = dict(orch_ctx.intent_info or {})
        intent_info["intent_label"] = intent_label
        issue_keys_found = orch_ctx.issue_keys_found

        for _chunk in iter_preflight_sse(orch_ctx):
            yield _chunk
        if orch_ctx.terminated:
            return

        react_ctx = ReactRunContext(
            cleaned_msgs=cleaned_msgs,
            user_text=user_text,
            issue_keys_found=issue_keys_found,
            intent_info=intent_info,
            user_cfg=user_cfg,
            frontend_cfg=frontend_cfg,
            headers=headers,
            active_tools=active_tools,
            tool_names=tool_names,
            jira_client=jira,
            deepseek_url=DEEPSEEK_URL,
            http_post=http.post,
            execute_tool_call=execute_tool_call,
            core_system_prompt=CORE_SYSTEM_PROMPT_V2,
            resolve_jira_username=resolve_jira_username,
            tool_executors=_TOOL_EXECUTORS,
        )

        if user_cfg.get("engine") == "v2-graph" or os.environ.get("ALICE_ENGINE") == "v2":
            try:
                yield from iter_v2_graph_stream(react_ctx)
                return
            except ReactFallback:
                pass
            except Exception as _v2e:
                logger.error(f"[V2 Graph] Failed: {_v2e}, falling back to ReAct")

        yield from iter_react_pipeline(react_ctx)
        return


    return Response(generate_stream(), mimetype='text/event-stream')
from logic_engine import evaluate_intent, reload_rules as reload_logic_rules
from eval_engine import run_evaluation, list_eval_datasets, get_eval_result

# ── Jira 操作确认卡端点 ────────────────────────────────────
# 移植自白泽 Baize 确认卡机制
from jira_operation_manager import (
    create_operation_card, get_operation, save_operation,
    mark_running, mark_created, mark_failed, mark_rejected,
    supersede_older, get_pending_operations,
    execute_confirmed_operation,
)

def _mailbox_task_json(task: dict) -> dict:
    """API 响应用的 Mailbox 任务摘要（不含内部 payload_json 冗余）。"""
    return {
        "id": task["id"],
        "mailbox_task_id": task["id"],
        "status": task["status"],
        "assignee": task["assignee"],
        "payload": task.get("payload"),
        "result": task.get("result"),
        "operation_id": task.get("operation_id"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


@app.route("/v1/mailbox/dispatch", methods=["POST"])
def mailbox_dispatch():
    """M2.3 — 派工：创建 Mailbox 异步任务，返回 mailbox_task_id。"""
    from mailbox_store import get_mailbox_store

    data = request.get_json(silent=True) or {}
    assignee = (data.get("assignee") or "").strip()
    payload = data.get("payload")
    if payload is None and data.get("payload_json") is not None:
        raw = data.get("payload_json")
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return jsonify({"ok": False, "error": "payload_json 不是合法 JSON"}), 400
        else:
            payload = raw
    if not assignee:
        return jsonify({"ok": False, "error": "assignee 不能为空"}), 400
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "payload 必须为 JSON 对象"}), 400
    operation_id = (data.get("operation_id") or "").strip() or None
    try:
        task = get_mailbox_store().create_task(
            assignee=assignee,
            payload=payload,
            operation_id=operation_id,
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("[Mailbox] dispatch failed")
        return jsonify({"ok": False, "error": str(e)[:500]}), 500
    return jsonify({
        "ok": True,
        "mailbox_task_id": task["id"],
        "task": _mailbox_task_json(task),
    })


@app.route("/v1/mailbox/tasks", methods=["GET"])
def mailbox_list_tasks():
    """M2.4 — 拉取 Mailbox 任务列表。"""
    from mailbox_store import get_mailbox_store

    status = (request.args.get("status") or "").strip() or None
    assignee = (request.args.get("assignee") or "").strip() or None
    try:
        limit = int(request.args.get("limit", "50") or 50)
    except ValueError:
        return jsonify({"ok": False, "error": "limit 必须为整数"}), 400
    limit = max(1, min(limit, 200))
    store = get_mailbox_store()
    try:
        tasks = store.list_tasks(status=status, assignee=assignee, limit=limit)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({
        "ok": True,
        "tasks": [_mailbox_task_json(t) for t in tasks],
    })


@app.route("/v1/mailbox/tasks/<mailbox_task_id>/claim", methods=["POST"])
def mailbox_claim_task(mailbox_task_id: str):
    """Worker 领取：pending → claimed（拉取与回报之间的标准步骤）。"""
    from mailbox_store import get_mailbox_store

    store = get_mailbox_store()
    task = store.get_task(mailbox_task_id)
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    try:
        updated = store.update_task(mailbox_task_id, status="claimed")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    return jsonify({"ok": True, "task": _mailbox_task_json(updated or task)})


@app.route("/v1/mailbox/tasks/<mailbox_task_id>/report", methods=["POST"])
def mailbox_report_task(mailbox_task_id: str):
    """M2.5 — 回报：claimed → done / failed，写入 result。"""
    from mailbox_store import get_mailbox_store

    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip().lower()
    if new_status not in ("done", "failed"):
        return jsonify({"ok": False, "error": "status 必须为 done 或 failed"}), 400
    result = data.get("result")
    if new_status == "done" and result is None:
        return jsonify({"ok": False, "error": "status=done 时建议提供 result 对象"}), 400
    store = get_mailbox_store()
    if not store.get_task(mailbox_task_id):
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    try:
        updated = store.update_task(mailbox_task_id, status=new_status, result=result)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    return jsonify({"ok": True, "task": _mailbox_task_json(updated or {})})


@app.route("/v1/jira/search", methods=["POST"])
def v1_jira_search():
    """结构化 Jira 搜索 API（调试 / MCP 复用）"""
    data = request.get_json(silent=True) or {}
    user_pat = ""
    if isinstance(data.get("user_config"), dict):
        user_pat = data["user_config"].get("jira_pat", "")
    user_pat = data.get("jira_pat") or user_pat
    frontend_cfg = data.get("config") or {}
    try:
        from jira_search_engine import (
            JiraSearchQuery,
            parse_query_from_natural_language,
            search_and_analyze,
            format_search_result_for_llm,
        )
        from jira_runtime_config import load_jira_runtime_config

        rt_cfg = load_jira_runtime_config(frontend_cfg)
        if data.get("query"):
            q = parse_query_from_natural_language(str(data["query"]), rt_cfg)
        else:
            q = JiraSearchQuery(
                project_key=data.get("project_key", ""),
                assignees=normalize_list(data.get("assignees") or data.get("assignee") or []),
                statuses=normalize_list(data.get("statuses") or data.get("status") or []),
                issue_types=normalize_list(data.get("issue_types") or data.get("issue_type") or []),
                text=data.get("text", "") or data.get("keyword", ""),
                jql=data.get("jql", ""),
                unresolved_only=bool(data.get("unresolved_only")),
                max_results=int(data.get("max_results") or 50),
            )
        uq = str(data.get("query") or data.get("keyword") or "")
        gcfg = load_global_config()
        result = search_and_analyze(
            jira, q, config=rt_cfg, user_pat=user_pat, frontend_cfg=frontend_cfg,
            user_question=uq,
            api_key=gcfg.get("DEEPSEEK_KEY", "") or os.getenv("DEEPSEEK_KEY", ""),
            http_post=http.post,
        )
        return jsonify({
            "ok": not result.get("not_recoverable"),
            "result": result,
            "llm_text": format_search_result_for_llm(result, uq),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 500


def normalize_list(value):
    from jira_search_engine import normalize_list as _nl
    return _nl(value)


@app.route("/operations/<op_id>", methods=["GET"])
def get_op(op_id):
    """获取操作详情"""
    from jira_operation_manager import operation_audit_fields

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
        **operation_audit_fields(op),
    }})

def _gate_operation_approval(actor_id: str, action: str, op_id: str):
    """M4.5 — 审批白名单；deny 时落盘 audit 并返回中文 error。"""
    from audit_gateway import check_operation_approver, record_operation_audit

    verdict = check_operation_approver(actor_id, action, op_id)
    if verdict.get("decision") == "deny":
        record_operation_audit(
            actor=actor_id or "",
            action=f"operation_{action}",
            operation_id=op_id,
            decision="deny",
            reason=verdict.get("reason", ""),
            origin="http",
        )
        return verdict.get("reason", "无权执行审批操作")
    return None


# ═══════════════════════════════════════════════════════════════
#  v3.0 Phase 4 — HITL 桥接器 + Agent SSE 流式端点
# ═══════════════════════════════════════════════════════════════

import re as _re_module

_MOCK_N8N = os.getenv("ALICE_MOCK_N8N", "False").lower() in ("true", "1", "yes")

# 真实 Jira API 创建 Issue 成功响应体（约束#14 Mock 保真）
_MOCK_JIRA_CREATE_RESPONSE = {
    "id": "10000",
    "key": "CT-9999",
    "self": "http://ctjira1.lmdgame.com:8080/rest/api/2/issue/10000",
}


def _send_to_n8n_mock(action: str, issue_data: dict) -> dict:
    """Mock n8n 桥接：模拟 Jira 创建操作（约束#14：真实响应体硬编码）"""
    import time as _time
    _time.sleep(1)
    return {"success": True, **_MOCK_JIRA_CREATE_RESPONSE}


def _generate_idempotency_key() -> str:
    """生成幂等 Key：alice-tx-{UUID}，正则清洗（约束#10）"""
    raw = str(_uuid_module.uuid4())
    cleaned = _re_module.sub(r"[^a-zA-Z0-9\-]", "", raw)
    return f"alice-tx-{cleaned}"


@app.route("/v1/agent/stream", methods=["POST", "OPTIONS"])
def agent_stream():
    """
    LangGraph Agent SSE 流式端点（Phase 4.2）。
    入参: {"messages": [...], "thread_id": "conv-xxx", "trace_id": "xxx"}
    出参: SSE 事件流（message / confirm_card / done / error）
    约束#15: @stream_with_context + GeneratorExit 归还线程
    """
    from flask import stream_with_context
    from agent_graph import graph
    from langchain_core.messages import HumanMessage
    import uuid as _uuid

    if request.method == "OPTIONS":
        return Response(status=204)

    body = request.get_json(silent=True) or {}
    messages_raw = body.get("messages", [])
    thread_id = (body.get("thread_id") or "").strip() or _uuid.uuid4().hex[:12]
    trace_id = body.get("trace_id", _uuid.uuid4().hex[:8])

    # 转换消息格式
    msgs = []
    for m in messages_raw:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "user":
            msgs.append(HumanMessage(content=content))

    if not msgs:
        return jsonify({"ok": False, "error": "messages 不能为空"}), 400

    config = {"configurable": {"thread_id": thread_id}}

    def _sse_generator():
        try:
            # Step 1: 初始推理
            events = graph.stream({"messages": msgs, "trace_id": trace_id}, config, stream_mode="values")
            for event in events:
                if "messages" in event:
                    last_msg = event["messages"][-1] if event["messages"] else None
                    if last_msg:
                        content = getattr(last_msg, "content", "")
                        msg_type = type(last_msg).__name__
                        yield f"data: {json.dumps({'type': 'message', 'msg_type': msg_type, 'content': content}, ensure_ascii=False)}\n\n"

            # Step 2: 检查是否被 interrupt_before=["action"] 暂停
            state = graph.get_state(config)
            if state.next and "action" in state.next:
                # HITL: 需要确认工具执行
                pending_tool = None
                if state.values and "messages" in state.values:
                    messages = state.values["messages"]
                    if messages:
                        last = messages[-1]
                        if hasattr(last, "tool_calls") and last.tool_calls:
                            pending_tool = last.tool_calls[0]

                idempotency_key = _generate_idempotency_key()
                payload = {
                    "type": "confirm_card",
                    "idempotency_key": idempotency_key,
                    "action": pending_tool.get("name", "unknown") if pending_tool else "unknown",
                    "args": pending_tool.get("args", {}) if pending_tool else {},
                    "thread_id": thread_id,
                    "trace_id": trace_id,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'done', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"

        except GeneratorExit:
            logger.info(f"[{trace_id}] Agent SSE 客户端断开连接")
        except TimeoutError as e:
            logger.error(f"[{trace_id}] Agent SSE LLM 超时: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': 'LLM 响应超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"[{trace_id}] Agent SSE 异常: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': f'Agent 推理异常: {str(e)[:200]}'}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(_sse_generator()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/v1/agent/confirm", methods=["POST", "OPTIONS"])
def agent_confirm():
    """
    HITL 确认/拒绝桥接（Phase 4.1）。
    入参: ConfirmCardPayload (idempotency_key, action, issue_data)
    Mock 模式: _send_to_n8n_mock → 1s sleep + 硬编码 Jira 响应
    非 Mock: n8n_webhook_call("alice-jira-create", ...) → 幂等去重
    """
    from agent_graph import graph, n8n_webhook_call

    if request.method == "OPTIONS":
        return Response(status=204)

    try:
        payload = ConfirmCardPayload(**request.get_json(silent=True) or {})
    except Exception as e:
        return jsonify({"ok": False, "error": f"参数校验失败: {e}"}), 400

    thread_id = (request.get_json(silent=True) or {}).get("thread_id", "")
    trace_id = payload.issue_data.get("trace_id", "unknown")

    try:
        if _MOCK_N8N:
            logger.info(f"[{trace_id}] Mock n8n: action={payload.action}")
            result = _send_to_n8n_mock(payload.action, payload.issue_data)
        else:
            # H1: 复用 payload 中的 idempotency_key 保证幂等去重（非生成新 Key）
            result_raw = n8n_webhook_call(
                "alice-jira-create",
                {
                    "idempotency_key": payload.idempotency_key,
                    "project_key": payload.issue_data.get("project_key", ""),
                    "summary": payload.issue_data.get("summary", ""),
                    "issue_type": payload.issue_data.get("issue_type", "Task"),
                    "description": payload.issue_data.get("description", ""),
                    "trace_id": trace_id,
                },
                timeout=3,
            )
            if not result_raw.get("ok"):
                return jsonify({"ok": False, "error": result_raw.get("error", "外部服务异常")}), 502
            result_data = result_raw.get("data", {})
            result = result_data.get("data") if isinstance(result_data, dict) else result_data

        # 恢复 LangGraph 执行（C3: 必须 as_node="action" 才能从 interrupt 恢复）
        if thread_id:
            config = {"configurable": {"thread_id": thread_id}}
            try:
                graph.update_state(config, values=None, as_node="action")
            except Exception as e:
                logger.warning(f"[{trace_id}] graph.update_state 失败: {e}")

        issue_key = result.get("key", result.get("issue_key", "?"))
        logger.info(f"[{trace_id}] Agent confirm 完成: issue_key={issue_key}")
        return jsonify({"ok": True, "issue_key": issue_key})
    except Exception as e:
        logger.error(f"[{trace_id}] Agent confirm 异常: {e}")
        return jsonify({"ok": False, "error": f"操作执行失败: {str(e)[:200]}"}), 500


@app.route("/v1/agent/reject", methods=["POST", "OPTIONS"])
def agent_reject():
    """
    HITL 拒绝端点（Phase 4.1）。
    入参: {"thread_id": str, "idempotency_key": str, "reason": str}
    结束当前 LangGraph 执行。
    """
    from agent_graph import graph

    if request.method == "OPTIONS":
        return Response(status=204)

    body = request.get_json(silent=True) or {}
    thread_id = (body.get("thread_id") or "").strip()
    reason = (body.get("reason") or "用户拒绝").strip()

    if not thread_id:
        return jsonify({"ok": False, "error": "缺少 thread_id"}), 400

    try:
        config = {"configurable": {"thread_id": thread_id}}
        # C3: as_node="action" 必填——否则 agent 不会从 interrupt 恢复
        graph.update_state(config, values={"confirm_result": "rejected", "draft": None}, as_node="action")
        logger.info(f"[Agent] 已拒绝操作 thread={thread_id} reason={reason[:80]}")
        return jsonify({"ok": True, "message": "已拒绝操作"})
    except Exception as e:
        logger.error(f"[Agent] reject 异常: {e}")
        return jsonify({"ok": False, "error": f"拒绝操作失败: {str(e)[:200]}"}), 500


@app.route("/operations/<op_id>/confirm", methods=["POST"])
def confirm_op(op_id):
    """用户确认操作 — 执行 Jira REST 写入（?stream=1 返回 operation_progress SSE）"""
    from operation_confirm import execute_operation_confirm, iter_operation_confirm_sse
    from user_identity import parse_user_id_from_request

    op = get_operation(op_id)
    if not op:
        return jsonify({"ok": False, "error": "操作不存在"}), 404
    if op["status"] not in ("awaiting_confirmation", "recovery_required"):
        return jsonify({"ok": False, "error": f"当前状态 {op['status']} 不能确认"}), 409

    body = request.get_json(silent=True) or {}
    approver_id = parse_user_id_from_request(body=body)
    deny_reason = _gate_operation_approval(approver_id, "confirm", op_id)
    if deny_reason:
        return jsonify({"ok": False, "error": deny_reason}), 403
    want_stream = (
        request.args.get("stream") == "1"
        or body.get("stream") is True
        or "text/event-stream" in (request.headers.get("Accept") or "")
    )
    logger.info("[Confirm] gate passed op_id=%s approver=%s stream=%s", op_id, approver_id, want_stream)
    _deps = dict(
        save_operation=save_operation,
        mark_running=mark_running,
        mark_created=mark_created,
        mark_failed=mark_failed,
        execute_confirmed_operation=execute_confirmed_operation,
    )
    if want_stream:
        return Response(
            iter_operation_confirm_sse(jira, op, body, **_deps),
            mimetype="text/event-stream",
        )
    status, payload = execute_operation_confirm(jira, op, body, **_deps)
    logger.info("[Confirm] response status=%s op_id=%s", status, op_id)
    return jsonify(payload), status

@app.route("/operations/<op_id>/reject", methods=["POST"])
def reject_op(op_id):
    """用户拒绝操作"""
    from audit_gateway import record_operation_audit
    from jira_operation_manager import operation_audit_fields
    from user_identity import parse_user_id_from_request

    op = get_operation(op_id)
    if not op:
        return jsonify({"ok": False, "error": "操作不存在"}), 404
    if op["status"] not in ("awaiting_confirmation", "recovery_required"):
        return jsonify({"ok": False, "error": f"当前状态 {op['status']} 不能拒绝"}), 409
    body = request.get_json(silent=True) or {}
    rejector_id = parse_user_id_from_request(body=body)
    deny_reason = _gate_operation_approval(rejector_id, "reject", op_id)
    if deny_reason:
        return jsonify({"ok": False, "error": deny_reason}), 403
    op = mark_rejected(op, rejected_by=rejector_id)
    save_operation(op)
    record_operation_audit(
        actor=rejector_id,
        action="operation_reject",
        operation_id=op_id,
        decision="allow",
        origin="http",
    )
    logger.info(f"[OpCard] Rejected: {op_id} | rejected_by={rejector_id or '-'}")
    return jsonify({
        "ok": True,
        "operation": {
            "id": op["id"],
            "status": op["status"],
            **operation_audit_fields(op),
        },
    })

@app.route("/drafts", methods=["GET"])
def list_draft_boxes():
    """列出草稿箱（F5 恢复 draft_card）。"""
    from jira_operation_manager import draft_items_for_ui, list_pending_drafts

    conv_id = request.args.get("conversation_id", "")
    status = request.args.get("status", "awaiting_review")
    drafts = list_pending_drafts(conv_id, status=status)
    return jsonify({
        "ok": True,
        "drafts": [
            {
                "id": d["id"],
                "status": d.get("status"),
                "items": draft_items_for_ui(d.get("items") or []),
                "warnings": d.get("warnings") or [],
                "preview": (
                    f"已生成 {len(d.get('items') or [])} 条 Jira 草稿，请在草稿卡中核对后批量提交。"
                ),
                "conversation_id": d.get("conversation_id"),
                "user_id": d.get("user_id") or "",
                "created_at": d.get("created_at"),
            }
            for d in drafts
        ],
    })


@app.route("/drafts", methods=["POST"])
def create_draft_box():
    """创建草稿箱（供前端/集成测试；聊天流仍由 tool 写入）。"""
    from jira_operation_manager import create_issues_draft, draft_items_for_ui
    from user_identity import parse_user_id_from_request

    body = request.get_json(silent=True) or {}
    items_in = body.get("items") or body.get("issues_list") or []
    creator_id = parse_user_id_from_request(body=body)
    try:
        draft = create_issues_draft(
            items_in,
            conversation_id=body.get("conversation_id", ""),
            client_id=body.get("client_id", ""),
            user_id=creator_id,
            source_text=body.get("source_text", ""),
        )
        return jsonify({
            "ok": True,
            "draft_id": draft["id"],
            "user_id": draft.get("user_id") or "",
            "items": draft_items_for_ui(draft.get("items") or []),
            "warnings": draft.get("warnings") or [],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 400


@app.route("/drafts/<draft_id>", methods=["GET"])
def get_draft_box(draft_id):
    """获取草稿箱内容"""
    from jira_operation_manager import get_draft, draft_items_for_ui
    draft = get_draft(draft_id)
    if not draft:
        return jsonify({"ok": False, "error": "草稿不存在"}), 404
    return jsonify({
        "ok": True,
        "draft": {
            "id": draft["id"],
            "status": draft["status"],
            "items": draft_items_for_ui(draft.get("items") or []),
            "warnings": draft.get("warnings") or [],
            "operation_id": draft.get("operation_id"),
            "created_at": draft.get("created_at"),
        },
    })


@app.route("/drafts/<draft_id>/confirm", methods=["POST"])
def confirm_draft_box(draft_id):
    """
    草稿箱批量确认 → 升级为 operation（awaiting_confirmation）。
    前端再调 /operations/<id>/confirm 执行 Jira 写入。
    """
    from jira_operation_manager import (
        get_draft,
        submit_draft_to_operation,
        build_confirm_tool_response,
    )
    draft = get_draft(draft_id)
    if not draft:
        return jsonify({"ok": False, "error": "草稿不存在"}), 404
    body = request.get_json(silent=True) or {}
    items = body.get("items")
    try:
        op = submit_draft_to_operation(draft_id, items=items)
        from jira_operation_manager import draft_items_for_ui, operation_to_confirm_ui

        payload = build_confirm_tool_response(
            op,
            f"草稿已锁定，共 {len(op.get('drafts') or [])} 条，请在确认卡上授权创建。",
        )
        ui_drafts = draft_items_for_ui(op.get("drafts") or [])
        return jsonify({
            "ok": True,
            "draft_id": draft_id,
            "operation_id": op["id"],
            "operation": operation_to_confirm_ui(op),
            "drafts": ui_drafts,
            "warnings": op.get("warnings") or draft.get("warnings") or [],
            "message": payload.get("result"),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 400


@app.route("/drafts/<draft_id>/reject", methods=["POST"])
def reject_draft_box(draft_id):
    """作废草稿"""
    from jira_operation_manager import reject_draft

    try:
        draft = reject_draft(draft_id)
        return jsonify({"ok": True, "draft_id": draft_id, "status": draft.get("status")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 400


@app.route("/api/memory/entries", methods=["GET"])
def list_memory_entries():
    from memory_manager import get_all_memory, get_memory_meta

    return jsonify({
        "ok": True,
        "entries": get_all_memory(),
        "meta": get_memory_meta(),
    })


@app.route("/api/memory/entries", methods=["POST"])
def create_memory_entry():
    from memory_manager import add_memory_entry

    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    try:
        entry = add_memory_entry(text, source=body.get("source") or "ui")
        return jsonify({"ok": True, "entry": entry})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 400


@app.route("/api/memory/entries/<entry_id>", methods=["PUT"])
def update_memory_entry_route(entry_id):
    from memory_manager import update_memory_entry, get_memory_meta

    body = request.get_json(silent=True) or {}
    try:
        entry = update_memory_entry(entry_id, body.get("text") or "")
        return jsonify({"ok": True, "entry": entry, "meta": get_memory_meta()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 400


@app.route("/api/memory/entries/<entry_id>", methods=["DELETE"])
def delete_memory_entry_route(entry_id):
    from memory_manager import delete_memory_entry, get_memory_meta

    try:
        delete_memory_entry(entry_id)
        return jsonify({"ok": True, "meta": get_memory_meta()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 400


@app.route("/operations/pending", methods=["GET"])
def list_pending_ops():
    """列出待确认的操作"""
    from jira_operation_manager import operation_to_confirm_ui

    conv_id = request.args.get("conversation_id", "")
    ops = get_pending_operations(conv_id)
    return jsonify({"ok": True, "operations": [{
        "id": o["id"],
        "status": o["status"],
        "kind": o["kind"],
        "drafts_count": len(o.get("drafts", [])),
        "warnings": o.get("warnings", []),
        "recovery": o.get("recovery"),
        "created_at": o.get("created_at"),
        "operation": operation_to_confirm_ui(o),
    } for o in ops]})


@app.route("/operations", methods=["GET"])
def list_ops_console():
    """M3 管控台：按状态列出操作（默认待确认+恢复+进行中+失败）。"""
    from jira_operation_manager import (
        list_operations,
        operation_audit_fields,
        operation_to_confirm_ui,
        _store,
    )

    conv_id = request.args.get("conversation_id", "")
    user_id = request.args.get("user_id", "")
    raw_status = request.args.get("status", "")
    limit = int(request.args.get("limit", "50") or 50)
    if raw_status:
        statuses = [s.strip() for s in raw_status.split(",") if s.strip()]
    else:
        statuses = [
            "awaiting_confirmation",
            "recovery_required",
            "running",
            "failed",
            "created",
        ]
    ops = list_operations(statuses=statuses, conversation_id=conv_id, user_id=user_id, limit=limit)
    logger.info("[API] /operations returned %d ops, store_size=%d", len(ops), len(_store))
    return jsonify({
        "ok": True,
        "operations": [{
            "id": o["id"],
            "status": o["status"],
            "kind": o.get("kind"),
            "conversation_id": o.get("conversation_id"),
            "drafts_count": len(o.get("drafts", [])),
            "warnings": o.get("warnings", []),
            "error": o.get("error"),
            "failure": o.get("failure"),
            "recovery": o.get("recovery"),
            "created_at": o.get("created_at"),
            "updated_at": o.get("updated_at"),
            **operation_audit_fields(o),
            "operation": operation_to_confirm_ui(o),
        } for o in ops],
    })


@app.route("/mcp/v1/tools", methods=["GET"])
def mcp_list_tools():
    from mcp_registry import list_mcp_tools_payload

    return jsonify({"ok": True, "api_version": "1.0", "tools": list_mcp_tools_payload()})


@app.route("/mcp/v1/tools/<tool_name>", methods=["POST"])
def mcp_invoke_tool(tool_name: str):
    from mcp_registry import invoke_mcp_tool

    body = request.get_json(silent=True) or {}
    user_cfg = parse_user_config(body)
    out = invoke_mcp_tool(
        tool_name,
        body.get("arguments") or body.get("args") or {},
        user_cfg,
        origin="mcp_http",
    )
    code = out.pop("http_status", None)
    if code is None:
        code = 200 if out.get("ok") else 400
    return jsonify(out), code


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
        r = jira.jira_post(f"/issue/{issue_key}/comment",
            json_data={"body": comment_body}, timeout=15)
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


# ═══════════════════════════════════════════════════════════════
#  Phase 3.1 — Dify RAG 代理端点（Admin → Hub → Dify）
# ═══════════════════════════════════════════════════════════════

from pydantic import BaseModel, Field as _PydanticField

class DifyRagProxyRequest(BaseModel):
    query: str
    top_k: int = 5

class N8nJiraProxyRequest(BaseModel):
    jql: str
    max_results: int = 15


class DifyUploadRequest(BaseModel):
    """Phase 5.1: Dify 知识库文档上传请求"""
    name: str
    text: str
    indexing_technique: str = "high_quality"


@app.route("/v1/admin/proxy/dify/rag", methods=["POST", "OPTIONS"])
def admin_proxy_dify_rag():
    """
    Admin 前端 → Hub 代理 → Dify 知识库 RAG 检索。
    入参: {"query": "...", "top_k": 5}
    出参: {"ok": true/false, "records": [...] / "error": "中文错误"}
    """
    if request.method == "OPTIONS":
        return Response(status=204)
    try:
        req = DifyRagProxyRequest(**request.get_json(silent=True) or {})
    except Exception as e:
        return jsonify({"ok": False, "error": f"参数校验失败: {e}"}), 400
    if not _dify_check_configured():
        return jsonify({"ok": False, "error": "知识库服务未配置，请联系管理员（需 DIFY_API_KEY 或 DIFY_DATASET_API_KEY + DIFY_DATASET_ID）"}), 503
    api_key = _dify_dataset_api_key()
    url = f"{DIFY_BASE_URL}/v1/datasets/{DIFY_DATASET_ID}/retrieve"
    try:
        resp = http.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"query": req.query, "retrieval_model": {
                "search_method": "keyword_search",
                "reranking_enable": False,
                "top_k": req.top_k,
                "score_threshold_enabled": False,
                "score_threshold": 0.0,
            }},
            timeout=10.0,
        )
        if resp.status_code == 401:
            _hint = "（RAG API 需 dataset-* 开头的 Key，当前仅配置了 app-* Key）" if not DIFY_DATASET_API_KEY else ""
            logger.error(f"[Admin] Dify RAG proxy HTTP 401: Key 权限不足{_hint}")
            return jsonify({"ok": False, "error": "Dify Key 权限不足（RAG API 需 dataset-* 开头的 Key）"}), 502
        if resp.status_code == 200:
            data = resp.json()
            records = data.get("records", [])
            return jsonify({"ok": True, "records": records, "total": len(records)})
        logger.error(f"[Admin] Dify RAG proxy HTTP {resp.status_code}: {resp.text[:200]}")
        return jsonify({"ok": False, "error": "知识库服务异常，请联系管理员"}), 502
    except http.exceptions.Timeout:
        return jsonify({"ok": False, "error": "知识库检索超时，请稍后重试"}), 504
    except http.exceptions.ConnectionError:
        return jsonify({"ok": False, "error": "无法连接到知识库服务"}), 503
    except Exception as e:
        logger.error(f"[Admin] Dify RAG proxy exception: {e}")
        return jsonify({"ok": False, "error": "知识库服务异常，请联系管理员"}), 500


@app.route("/v1/admin/proxy/dify/upload", methods=["POST", "OPTIONS"])
def admin_proxy_dify_upload():
    """
    Phase 5.1: Admin → Hub → Dify 知识库文档上传。
    入参: {"name": str, "text": str, "indexing_technique": "high_quality"}
    出参: {"ok": true/false, "document_id": "xxx" / "error": "..."}
    """
    if request.method == "OPTIONS":
        return Response(status=204)

    if not _dify_check_configured():
        return jsonify({"ok": False, "error": "Dify 知识库未配置，请联系管理员"}), 503

    try:
        req = DifyUploadRequest(**request.get_json(silent=True) or {})
    except Exception as e:
        return jsonify({"ok": False, "error": f"参数校验失败: {e}"}), 400

    trace_id = str(uuid.uuid4())[:8]
    api_key = _dify_dataset_api_key()
    upload_url = f"{DIFY_BASE_URL}/v1/datasets/{DIFY_DATASET_ID}/documents/create-by-text"

    # Step 1: 上传文档
    try:
        resp = http.post(
            upload_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "name": req.name,
                "text": req.text,
                "indexing_technique": req.indexing_technique,
                "process_rule": {"mode": "automatic"},
            },
            timeout=30.0,
        )
        if resp.status_code == 401:
            _hint = "（需 dataset-* 开头的 Key）" if not DIFY_DATASET_API_KEY else ""
            logger.error(f"[{trace_id}] Dify upload HTTP 401: Key 权限不足{_hint}")
            return jsonify({"ok": False, "error": "Dify Key 权限不足（RAG API 需 dataset-* 开头的 Key）"}), 502
        if resp.status_code not in (200, 201):
            logger.error(f"[{trace_id}] Dify upload HTTP {resp.status_code}: {resp.text[:200]}")
            return jsonify({"ok": False, "error": f"文档上传失败（{resp.status_code}），请稍后重试"}), 502
        upload_data = resp.json()
    except http.exceptions.Timeout:
        return jsonify({"ok": False, "error": "文档上传超时，请稍后重试"}), 504
    except http.exceptions.ConnectionError:
        return jsonify({"ok": False, "error": "无法连接到知识库服务"}), 503
    except Exception as e:
        logger.error(f"[{trace_id}] Dify upload exception: {e}")
        return jsonify({"ok": False, "error": "知识库服务异常，请联系管理员"}), 500

    doc_id = (upload_data.get("document") or {}).get("id") or upload_data.get("id", "")
    if not doc_id:
        return jsonify({"ok": False, "error": "文档上传成功但未返回 document_id", "raw": upload_data}), 502

    # Step 2: SSE 索引进度推送（H3: 替代 sleep 同步轮询）
    status_url = f"{DIFY_BASE_URL}/v1/datasets/{DIFY_DATASET_ID}/documents/{doc_id}/indexing-status"
    logger.info(f"[{trace_id}] Dify upload doc_id={doc_id}, SSE polling indexing status...")

    def _indexing_stream():
        for attempt in range(1, 31):
            time.sleep(2)
            try:
                status_resp = _httpx_module.get(
                    status_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    status_val = status_data.get("status") or status_data.get("indexing_status", "")
                    logger.info(f"[{trace_id}] Dify indexing attempt={attempt} status={status_val}")
                    yield f"data: {json.dumps({'type': 'progress', 'attempt': attempt, 'status': status_val}, ensure_ascii=False)}\n\n"
                    if status_val in ("completed", "enabled", "warning", "partial"):
                        yield f"data: {json.dumps({'type': 'done', 'ok': True, 'document_id': doc_id, 'indexing_status': status_val}, ensure_ascii=False)}\n\n"
                        return
            except Exception as e:
                logger.warning(f"[{trace_id}] Dify indexing poll attempt={attempt} error: {e}")
                yield f"data: {json.dumps({'type': 'progress', 'attempt': attempt, 'status': 'error', 'error': str(e)[:100]}, ensure_ascii=False)}\n\n"

        logger.warning(f"[{trace_id}] Dify indexing timeout for doc_id={doc_id}")
        yield f"data: {json.dumps({'type': 'done', 'ok': True, 'document_id': doc_id, 'indexing_status': 'pending', 'warning': '索引轮询超时（60s），请在 Dify 控制台确认'}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(_indexing_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════
#  Phase 3.2 — n8n Jira 代理端点（Admin → Hub → n8n Webhook）
# ═══════════════════════════════════════════════════════════════

@app.route("/v1/admin/proxy/n8n/jira", methods=["POST", "OPTIONS"])
def admin_proxy_n8n_jira():
    """
    Admin 前端 → Hub 代理 → n8n Jira Search Webhook。
    入参: {"jql": "project=CT", "max_results": 15}
    出参: {"ok": true/false, "issues": [...] / "error": "中文错误"}
    """
    if request.method == "OPTIONS":
        return Response(status=204)
    try:
        req = N8nJiraProxyRequest(**request.get_json(silent=True) or {})
    except Exception as e:
        return jsonify({"ok": False, "error": f"参数校验失败: {e}"}), 400
    if not N8N_BASE_URL:
        return jsonify({"ok": False, "error": "n8n 服务未配置，请联系管理员"}), 503
    url = f"{N8N_BASE_URL}/webhook/alice-jira-search"
    try:
        resp = http.post(
            url,
            json={"jql": req.jql, "limit": req.max_results},
            headers={"X-N8N-API-KEY": N8N_API_KEY} if N8N_API_KEY else {},
            timeout=3.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            issues = data.get("issues", [])
            return jsonify({"ok": True, "issues": issues, "total": len(issues)})
        logger.error(f"[Admin] n8n Jira proxy HTTP {resp.status_code}: {resp.text[:200]}")
        return jsonify({"ok": False, "error": "外部服务异常，请联系管理员"}), 502
    except http.exceptions.Timeout:
        return jsonify({"ok": False, "error": "n8n 服务响应超时，请稍后重试"}), 504
    except http.exceptions.ConnectionError:
        return jsonify({"ok": False, "error": "无法连接到 n8n 服务，请确认 n8n 已启动"}), 503
    except Exception as e:
        logger.error(f"[Admin] n8n Jira proxy exception: {e}")
        return jsonify({"ok": False, "error": "外部服务异常，请联系管理员"}), 500


@app.route("/test")
def test_suite():
    from flask import send_file
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jira", "jira-workbuddy-plugin", "test_suite.html")
    return send_file(path)

def _probe_jira_health(timeout: float = 3.0) -> dict:
    """Lightweight Jira reachability for Admin /health (E7.2)."""
    cfg = load_global_config()
    base = (cfg.get("JIRA_BASE_URL") or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
    pat = cfg.get("JIRA_PAT") or os.getenv("JIRA_PAT", "")
    if not base or not pat:
        return {"status": "unconfigured", "detail": "缺少 JIRA_BASE_URL 或 PAT"}
    t0 = time.time()
    try:
        res = http.get(
            f"{base}/rest/api/2/myself",
            headers={"Authorization": f"Bearer {pat}"},
            timeout=timeout,
        )
        latency_ms = int((time.time() - t0) * 1000)
        if res.status_code == 200:
            return {"status": "ok", "latency_ms": latency_ms}
        if res.status_code == 502:
            return {
                "status": "gateway_error",
                "http_status": 502,
                "detail": "Jira 网关错误 (502)：上游或反向代理不可达",
                "latency_ms": latency_ms,
            }
        if res.status_code in (401, 403):
            return {
                "status": "auth_error",
                "http_status": res.status_code,
                "detail": f"Jira 凭据被拒绝 (HTTP {res.status_code})",
                "latency_ms": latency_ms,
            }
        return {
            "status": "http_error",
            "http_status": res.status_code,
            "detail": f"Jira 返回 HTTP {res.status_code}",
            "latency_ms": latency_ms,
        }
    except http.exceptions.Timeout:
        return {"status": "timeout", "detail": "Jira 连接超时，请检查网络或增大超时"}
    except http.exceptions.RequestException as e:
        return {"status": "unreachable", "detail": f"Jira 无法连接: {e}"}


def _probe_model_health() -> dict:
    cfg = load_global_config()
    key = (cfg.get("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_KEY") or "").strip()
    url = (cfg.get("DEEPSEEK_URL") or os.getenv("DEEPSEEK_BASE_URL") or "").strip()
    if not key:
        return {"status": "unconfigured", "detail": "未配置 DeepSeek API Key"}
    return {"status": "configured", "detail": "API Key 已配置", "url_set": bool(url)}


def _probe_kb_health() -> dict:
    cfg = load_global_config()
    notion = bool((cfg.get("NOTION_TOKEN") or os.getenv("NOTION_TOKEN") or "").strip())
    gdrive = bool((cfg.get("GDRIVE_CREDENTIALS_JSON") or cfg.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip())
    if notion and gdrive:
        return {"status": "ok", "detail": "Notion + Google 云盘已配置"}
    if notion:
        return {"status": "partial", "detail": "仅 Notion 已配置"}
    if gdrive:
        return {"status": "partial", "detail": "仅 Google 云盘已配置"}
    return {"status": "unconfigured", "detail": "未配置知识库源（Notion / GDrive）"}


def _get_faiss_doc_count() -> int:
    try:
        import rag_engine as _rag_mod  # noqa: F811
    except (ImportError, ModuleNotFoundError):
        return 0
    try:
        return _rag_mod.get_indexed_doc_count() if _rag_mod.is_index_ready() else 0
    except Exception:
        return 0


def _build_faiss_index_on_startup():
    """
    M5.x KB 优化令 — Hub 启动时从 GDrive 目录构建 FAISS 语义索引。
    无 GDrive 配置 → 跳过不崩；API 错误 → 跳过不崩。
    """
    try:
        import rag_engine as _rag_mod  # noqa: F811
    except (ImportError, ModuleNotFoundError):
        loguru_logger.info("[FAISS] rag_engine 不可用（v3.0 已迁移至 Dify RAG），跳过索引构建")
        return
    try:
        GK = os.getenv("GDRIVE_KEY") or getattr(jira, '_global_cfg', {}).get("GDRIVE_KEY", "")
        if not GK:
            loguru_logger.info("[FAISS] GDrive KEY not configured, skipping startup index build")
            return
        raw_folders = os.getenv("GDRIVE_FOLDERS") or getattr(jira, '_global_cfg', {}).get("GDRIVE_FOLDERS", "")
        folders = [f.strip() for f in re.split(r'[\n,]+', raw_folders) if f.strip()]
        if not folders:
            loguru_logger.info("[FAISS] GDRIVE_FOLDERS empty, skipping startup index build")
            return
        proxies = get_http_proxies()
        all_files = {}
        for fid in folders:
            try:
                gr = saas_request(
                    "GET",
                    f"https://www.googleapis.com/drive/v3/files?key={GK}&q='{fid}'+in+parents&fields=files(id,name,mimeType)&pageSize=100",
                    proxies=proxies,
                )
                if gr.status_code == 200:
                    for f in gr.json().get("files", []):
                        all_files[f["id"]] = f
            except Exception as fe:
                loguru_logger.warning("[FAISS] folder %s fetch failed: %s", fid, fe)
        if not all_files:
            loguru_logger.info("[FAISS] no GDrive files found, skipping startup index build")
            return
        catalog_items = []
        for fid, f in all_files.items():
            catalog_items.append({
                "doc_id": fid,
                "title": f.get("name", "未命名"),
                "snippet": f"type={f.get('mimeType', '')}",
            })
        dsk = os.getenv("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
        ok = _rag_mod.build_index_from_catalog_items(catalog_items, deepseek_key=dsk)
        if ok:
            logger.info(
                "[FAISS] startup index built: %d docs / %d chunks",
                _rag_mod.get_indexed_doc_count(),
                len(_rag_mod._vector_store.get("chunks", [])),
            )
        else:
            loguru_logger.info("[FAISS] startup index build returned empty — no crash")
    except Exception as e:
        loguru_logger.warning("[FAISS] startup index build failed (non-fatal): %s", e)


@app.route("/v1/audit/logs", methods=["GET"])
def list_audit_logs():
    """M4.6 — 只读持久审计日志（Hub 内网）。"""
    from audit_gateway import query_persistent_audit_logs

    limit = int(request.args.get("limit", "50") or 50)
    operation_id = (request.args.get("operation_id") or "").strip()
    logs = query_persistent_audit_logs(limit=limit, operation_id=operation_id)
    return jsonify({
        "ok": True,
        "count": len(logs),
        "logs": logs,
    })


@app.route("/health")
@app.route("/api/system/status")
def health():
    integrations = {
        "jira": _probe_jira_health(),
        "model": _probe_model_health(),
        "kb": _probe_kb_health(),
    }
    _bad = {"gateway_error", "auth_error", "timeout", "unreachable", "http_error", "error"}
    degraded = any(integrations.get(k, {}).get("status") in _bad for k in ("jira", "model", "kb"))
    faiss_docs = _get_faiss_doc_count()
    with _active_lock:
        return jsonify({
            "status": "degraded" if degraded else "ok",
            "service": "ai-bridge-v5",
            "api_version": "1.0",
            "hub_only_jira": _hub_only_jira_enabled(),
            "engine": _resolved_deepseek_model(load_global_config()),
            "active_requests": _active_requests,
            "max_threads": 10,
            "integrations": integrations,
            "faiss_indexed_docs": faiss_docs,
            "cache": {
                "context": len(_CONTEXT_CACHE),
                "semantic": len(_SEMANTIC_CACHE),
                "svn_commits": len(_SVN_COMMIT_CACHE),
            },
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
    # 旧格式：纯密码或 user-pass 组合
    if token_or_user == ADMIN_PASS or token_or_user == (ADMIN_USER + "-" + ADMIN_PASS):
        return True
    # v2.0 wave1: 账号 token 验证
    try:
        from accounts import verify_token
        return verify_token(token_or_user) is not None
    except Exception:
        return False
    return False
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
            admin_batch_task_id, action, params = task
            with _task_lock:
                if admin_batch_task_id in _task_store:
                    _task_store[admin_batch_task_id]["status"] = "running"
            try:
                total = len(params.get("issue_keys", [])) or 1
                for i, key in enumerate(params.get("issue_keys", [])):
                    time.sleep(0.5)
                    progress = int((i + 1) / total * 100)
                    with _task_lock:
                        _task_store[admin_batch_task_id]["progress"] = progress
                        _task_store[admin_batch_task_id]["current"] = key
                        _task_store[admin_batch_task_id]["log"].append(f"[{i+1}/{total}] 分析 {key}: 完成")
                with _task_lock:
                    _task_store[admin_batch_task_id]["status"] = "done"
                    _task_store[admin_batch_task_id]["result"] = f"分析完成，共处理 {total} 个 Issue"
            except Exception as e:
                with _task_lock:
                    _task_store[admin_batch_task_id]["status"] = "failed"
                    _task_store[admin_batch_task_id]["error"] = str(e)
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
    # M2.8：Admin 批量分析 ID 已统一为 admin_batch_task_id（与 mailbox_task_id 区分）
    admin_batch_task_id = f"admin-batch-{uuid.uuid4().hex[:8]}"
    with _task_lock:
        _task_store[admin_batch_task_id] = {
            "id": admin_batch_task_id,
            "action": "batch_analysis",
            "status": "pending",
            "progress": 0, "current": None, "result": None, "error": None,
            "log": [], "created_at": time.time(),
        }
    _task_queue.put((admin_batch_task_id, "batch_analysis", {"issue_keys": issue_keys}))
    return jsonify({"ok": True, "admin_batch_task_id": admin_batch_task_id, "issue_count": len(issue_keys)})

@app.route('/v1/admin/tasks/<admin_batch_task_id>/status')
@require_admin
def get_task_status(admin_batch_task_id):
    def stream_status():
        last_log_len = 0
        while True:
            with _task_lock:
                task = _task_store.get(admin_batch_task_id)
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
    resolved_model = _resolved_deepseek_model(config)

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
        "DEEPSEEK_MODEL": resolved_model,
        "saved_model": resolved_model,
        "JIRA_DEADLINE_FIELD_BY_PROJECT": config.get("JIRA_DEADLINE_FIELD_BY_PROJECT", {}),
        "JIRA_FIELD_MAPPINGS": config.get("JIRA_FIELD_MAPPINGS") or config.get("fieldMappings") or {},
        "JIRA_PROJECT_CONFIG": config.get("JIRA_PROJECT_CONFIG", {}),
        "JIRA_FIELD_GLOSSARY": config.get("JIRA_FIELD_GLOSSARY", []),
        "JIRA_PROJECTS": config.get("JIRA_PROJECTS", os.getenv("JIRA_PROJECTS", "")),
    })

@app.route("/v1/config/engines", methods=["GET"])
def config_engines():
    """返回可用引擎列表（DeepSeek + Cursor SDK）供客户端 EngineSelector 下拉菜单"""
    config = load_global_config()
    deepseek_model = _resolved_deepseek_model(config)
    # 注意：plan/agent/ask 是 Cursor IDE 的交互模式概念，不是 cursor-sdk 的 API 参数。
    # SDK 侧无 mode 参数，仅通过 model + 提示词控制行为。此处保留作为用户意图标签，
    # 后续 cursor lane 实现时会将意图映射到具体 SDK 配置。
    cursor_modes = [
        {"id": "plan", "label": "plan（先规划后执行）"},
        {"id": "agent", "label": "agent（直接执行）"},
        {"id": "ask", "label": "ask（仅问答）"},
    ]
    return jsonify({
        "deepseek": {
            "model": deepseek_model,
            "label": "DeepSeek 回答",
        },
        "cursor": {
            "modes": cursor_modes,
            "label": "Cursor 深度分析",
        },
    })

@app.route("/v1/admin/cursor-sdk/test", methods=["POST"])
def cursor_sdk_test():
    """代理测试 Cursor SDK 连通性（Key 由客户端传入，不存储）"""
    data = request.json or {}
    api_key = (data.get("api_key") or "").strip()
    model = (data.get("model") or "composer-2.5").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "缺少 api_key"}), 400
    try:
        import cursor_sdk
        _ = cursor_sdk
    except ImportError:
        return jsonify({"ok": False, "error": "服务器未安装 cursor-sdk（pip install cursor-sdk）"}), 500
    try:
        from cursor_sdk import Agent, LocalAgentOptions

        # 使用临时目录作为 workspace，避免污染实际项目
        test_cwd = os.path.join(os.environ.get("TEMP", os.getcwd()), "alice_cursor_sdk_test")
        os.makedirs(test_cwd, exist_ok=True)

        with Agent.create(
            model=model,
            api_key=api_key,
            local=LocalAgentOptions(cwd=test_cwd),
        ) as agent:
            run = agent.send("Hello, respond with 'OK' only.")
            run.wait()
            text = (run.text() or "").strip()
        
        if "OK" in text or "ok" in text:
            return jsonify({"ok": True, "model": model})
        return jsonify({"ok": True, "model": model, "warning": f"返回非预期内容: {text[:200]}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]})

@app.route("/v1/admin/cursor-sdk/models", methods=["GET"])
def cursor_sdk_models():
    """返回 Cursor API Key 可用的模型列表（前端下拉菜单数据源）"""
    api_key = (request.args.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "缺少 api_key", "models": []}), 400
    try:
        import cursor_sdk
        _ = cursor_sdk
    except ImportError:
        return jsonify({"ok": False, "error": "服务器未安装 cursor-sdk", "models": []}), 500
    try:
        from cursor_sdk import Cursor
        sdk_models = Cursor.models.list(api_key=api_key)
        models = [{"id": m.id, "display_name": m.display_name} for m in sdk_models]
        return jsonify({"ok": True, "models": models})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300], "models": []})

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

        _DEADLINE_FIELD_CACHE.clear()
        _JIRA_FIELDS_CACHE["ts"] = 0
            
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
                        # 行级 DSML 防泄漏过滤
                        try:
                            d = line.decode('utf-8')
                            stripped = d.strip()
                            if re.match(r'\s*<\s*\|?\s*(?:tool_calls|DSML|invoke|parameter)\s*\|?\s*>', stripped, re.I):
                                continue
                            if re.match(r'\s*<\s*\|?\s*/\s*(?:tool_calls|DSML)\s*\|?\s*>', stripped, re.I):
                                continue
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
@app.route('/admin/', methods=['GET'])
@app.route('/admin.html', methods=['GET'])
def render_admin_page():
    """Element Plus 管理后台（Vite 构建产物）— /admin 或 /admin.html"""
    from flask import send_file
    import os as _os
    _backend = _os.path.dirname(_os.path.abspath(__file__))
    spa_index = _os.path.join(_backend, 'static', 'admin', 'index.html')
    if _os.path.exists(spa_index):
        return send_file(spa_index)
    return "admin UI not found — run `cd backend/admin-ui && npm run build`", 404


@app.route('/admin-static/<path:filename>')
def serve_admin_vite_assets(filename):
    """Admin SPA 静态资源（Vite base=/admin-static/ → static/admin/assets/…）"""
    from flask import send_from_directory
    import os as _os
    asset_root = _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)),
        'static', 'admin',
    )
    return send_from_directory(asset_root, filename)


# ═══════════════════════════════════════════════════════════════
# v3.1-rc5：Chat 前端静态文件服务（Vite build → frontend/dist/）
# ═══════════════════════════════════════════════════════════════

@app.route('/chat/<path:filename>')
def serve_chat_static(filename):
    """Chat SPA 静态资源（前端 Vite build → frontend/dist/）"""
    from flask import send_from_directory
    import os as _os
    chat_root = _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)),
        '..', 'frontend', 'dist',
    )
    return send_from_directory(chat_root, filename)


@app.route('/chat')
@app.route('/chat/')
def serve_chat_index():
    """Chat SPA 入口页"""
    from flask import send_from_directory
    import os as _os
    chat_root = _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)),
        '..', 'frontend', 'dist',
    )
    return send_from_directory(chat_root, 'index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    """离线静态资源: Vue 3 + Tailwind CDN 本地化"""
    from flask import send_from_directory
    import os as _os
    static_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'static')
    return send_from_directory(static_dir, filename)

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
        res = http.get(f"{jira_url}/rest/api/2/myself", headers=headers, timeout=8)
        latency = int((time.time() - start_time) * 1000)
        if res.status_code == 200:
            return jsonify({"success": True, "status": res.status_code, "latency_ms": latency})
        if res.status_code == 502:
            return jsonify({
                "success": False,
                "error_category": "gateway",
                "error": "Jira 网关错误 (HTTP 502)：上游 Jira 或反向代理不可达，请联系运维检查服务器/网关。",
                "http_status": 502,
                "latency_ms": latency,
            }), 502
        if res.status_code in (401, 403):
            return jsonify({
                "success": False,
                "error_category": "auth",
                "error": f"Jira 凭据无效或被拒绝 (HTTP {res.status_code})：请检查 PAT 是否过期、是否有 REST API 权限。",
                "http_status": res.status_code,
                "latency_ms": latency,
            }), 401
        return jsonify({
            "success": False,
            "error_category": "http",
            "error": f"Jira 返回异常状态 HTTP {res.status_code}，请查看 Jira 日志或联系管理员。",
            "http_status": res.status_code,
            "latency_ms": latency,
        }), 400
    except http.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error_category": "timeout",
            "error": "Jira 连接超时：请检查网络、防火墙或 Jira 地址是否可达。",
        }), 504
    except http.exceptions.RequestException as e:
        return jsonify({
            "success": False,
            "error_category": "network",
            "error": f"Jira 无法连接或 DNS 解析失败：{e}",
        }), 500


def _admin_resolve_jira_pat(pat: str = "") -> str:
    p = (pat or "").strip()
    if p == "********" or not p:
        p = load_global_config().get("JIRA_PAT", os.getenv("JIRA_PAT", ""))
    return p or ""


def _admin_fetch_jira_fields_raw(jira_url: str = "", pat: str = "") -> list:
    """Admin：用指定 URL/PAT 拉取 Jira /field（不写全局缓存）。"""
    base = (jira_url or load_global_config().get("JIRA_BASE_URL", os.getenv("JIRA_BASE_URL", ""))).rstrip("/")
    token = _admin_resolve_jira_pat(pat)
    if not base or not token:
        return []
    try:
        r = http.get(
            f"{base}/rest/api/2/field",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"[Admin] Jira /field failed: {e}")
    return []


def _admin_simplify_jira_fields(raw_fields: list) -> list:
    out = []
    for f in raw_fields or []:
        if not isinstance(f, dict):
            continue
        name = (f.get("name") or "").strip()
        fid = (f.get("id") or "").strip()
        if not name:
            continue
        schema = f.get("schema") if isinstance(f.get("schema"), dict) else {}
        st = (schema.get("type") or "").lower()
        custom = bool(f.get("custom")) or fid.startswith("customfield_")
        out.append({
            "id": fid,
            "name": name,
            "custom": custom,
            "schemaType": st,
        })

    def _rank(item):
        n = item["name"].lower()
        score = 0
        if item["schemaType"] == "date":
            score += 100
        if any(k in n for k in ("截止", "end", "due", "完成日期", "结束")):
            score += 80
        if any(k in n for k in ("负责", "owner", "assignee", "经办")):
            score += 40
        return -score

    out.sort(key=lambda x: (_rank(x), x["name"]))
    return out


def _admin_fetch_jira_projects_raw(jira_url: str = "", pat: str = "") -> list:
    """Admin：GET /rest/api/2/project 可访问项目列表。"""
    base = (jira_url or load_global_config().get("JIRA_BASE_URL", os.getenv("JIRA_BASE_URL", ""))).rstrip("/")
    token = _admin_resolve_jira_pat(pat)
    if not base or not token:
        return []
    try:
        r = http.get(
            f"{base}/rest/api/2/project",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20,
        )
        if r.status_code != 200:
            logger.warning(f"[Admin] Jira /project HTTP {r.status_code}")
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        out = []
        for p in data:
            if not isinstance(p, dict):
                continue
            key = (p.get("key") or "").strip().upper()
            if not key:
                continue
            out.append({
                "key": key,
                "name": (p.get("name") or key).strip(),
                "id": str(p.get("id") or ""),
            })
        out.sort(key=lambda x: x["key"])
        return out
    except Exception as e:
        logger.warning(f"[Admin] Jira /project failed: {e}")
        return []


@app.route('/v1/admin/jira/projects', methods=['GET', 'OPTIONS'])
@require_admin
def admin_jira_projects():
    if request.method == 'OPTIONS':
        return Response(status=204)
    jira_url = request.args.get("url", "").strip()
    pat = request.args.get("pat", "").strip()
    projects = _admin_fetch_jira_projects_raw(jira_url, pat)
    if not projects:
        return jsonify({
            "success": False,
            "error": "无法获取 Jira 项目列表，请先在「Jira 连接」测试连通并保存 PAT",
        }), 400
    return jsonify({"success": True, "projects": projects})


@app.route('/v1/admin/jira/fields', methods=['GET', 'OPTIONS'])
@require_admin
def admin_jira_fields():
    if request.method == 'OPTIONS':
        return Response(status=204)
    jira_url = request.args.get("url", "").strip()
    pat = request.args.get("pat", "").strip()
    raw = _admin_fetch_jira_fields_raw(jira_url, pat)
    if not raw:
        return jsonify({"success": False, "error": "无法获取 Jira 字段列表，请先测试连通并填写地址与 PAT"}), 400
    return jsonify({"success": True, "fields": _admin_simplify_jira_fields(raw)})


@app.route('/v1/admin/jira/deadline-suggest', methods=['GET', 'OPTIONS'])
@require_admin
def admin_jira_deadline_suggest():
    if request.method == 'OPTIONS':
        return Response(status=204)
    project = (request.args.get("project") or "CT").strip().upper()
    jira_url = request.args.get("url", "").strip()
    pat = request.args.get("pat", "").strip()
    cfg_map = _load_deadline_config_map()
    raw = _admin_fetch_jira_fields_raw(jira_url, pat)
    meta = resolve_deadline_field(project, cfg_map, raw)
    return jsonify({
        "success": True,
        "project": project,
        "display_name": meta.get("display_name", ""),
        "jql_name": meta.get("jql_name", ""),
        "field_id": meta.get("field_id", ""),
        "source": meta.get("source", ""),
        "hint": "Alice 将用此字段筛选「本周周报 / 待办任务」",
    })


@app.route('/v1/admin/jira/issuetypes', methods=['GET', 'OPTIONS'])
@require_admin
def admin_jira_issuetypes():
    """返回指定项目的可用 Issue 类型列表（供 Admin 后台 E 段调用）。"""
    if request.method == 'OPTIONS':
        return Response(status=204)
    project_key = (request.args.get("project_key") or request.args.get("project") or "").strip()
    if not project_key:
        return jsonify({"success": False, "error": "缺少 project_key 参数"}), 400
    jira_url = request.args.get("url", "").strip()
    pat = request.args.get("pat", "").strip()
    base = (jira_url or GLOBAL_CONFIG.get("JIRA_BASE_URL", os.getenv("JIRA_BASE_URL", ""))).rstrip("/")
    if not base:
        return jsonify({"success": False, "error": "Jira 地址未配置"}), 400
    pat = pat or load_global_config().get("JIRA_PAT", os.getenv("JIRA_PAT", ""))
    email = load_global_config().get("JIRA_EMAIL", os.getenv("JIRA_EMAIL", "")) or "alice-bot"
    try:
        from jira_api import JiraClient
        client = JiraClient(base, email, pat)
        issuetypes = client.get_project_issuetypes(project_key, user_pat=pat)
        return jsonify({"success": True, "issuetypes": issuetypes, "project": project_key})
    except Exception as e:
        logger.error(f"admin_jira_issuetypes failed for {project_key}: {e}")
        return jsonify({"success": False, "error": str(e)[:200]}), 500


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
            saved_model = _resolved_deepseek_model(config)
            if saved_model and saved_model not in models:
                models.insert(0, saved_model)
            return jsonify({"success": True, "models": models, "saved_model": saved_model})
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

# ═══════════════════════════════════════════════════════════
#  /api/test_connection — 自助排障探测器
#  用当前 PAT 尝试获取 Jira 用户信息，验证连通性
# ═══════════════════════════════════════════════════════════
@app.route('/api/test_connection', methods=['POST'])
def test_connection():
    """轻量级连通性测试：用 PAT 请求 Jira /rest/api/2/myself"""
    data = request.json or {}
    jira_url = data.get("jira_url", "").strip()
    jira_pat = data.get("jira_pat", "").strip()
    
    # 空 body → 从 global_config 读取
    if not jira_url or not jira_pat:
        _cfg = load_global_config()
        jira_url = jira_url or _cfg.get("jira_url", "") or os.getenv("JIRA_URL", "")
        jira_pat = jira_pat or _cfg.get("jira_pat", "") or os.getenv("JIRA_PAT", "")
    
    if not jira_url or not jira_pat:
        return jsonify({"ok": False, "error": "Jira 未配置 — 请前往 /admin 填写凭据"}), 400
    
    try:
        import urllib.request as _ur, json as _j, base64 as _b64
        url = f"{jira_url.rstrip('/')}/rest/api/2/myself"
        auth = _b64.b64encode(f"{jira_pat}:".encode()).decode()
        req = _ur.Request(url, headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json"
        })
        resp = _ur.urlopen(req, timeout=10)
        user_data = _j.loads(resp.read().decode())
        return jsonify({
            "ok": True,
            "user": user_data.get("displayName", "Unknown"),
            "email": user_data.get("emailAddress", ""),
            "active": user_data.get("active", False)
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Jira 连接失败: {str(e)[:200]}"}), 500

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
        from dotenv import set_key

        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if not os.path.exists(env_path):
            open(env_path, "a", encoding="utf-8").close()
        set_key(env_path, "ADMIN_PASS", new_pwd)
    except Exception as e:
        logger.warning(f"Failed to persist ADMIN_PASS: {e}")
    return jsonify({"ok": True, "message": "密码已更新，下次登录请使用新密码"})


# ═══════════════════════════════════════════════════════════
#  /v1/admin/roles — RBAC 角色管理 API（v1.10-rbac）
#  /v1/admin/permissions — 权限矩阵 API
#  /v1/user/permissions — 前端权限查询
# ═══════════════════════════════════════════════════════════

@app.route('/v1/admin/roles', methods=['GET', 'POST', 'OPTIONS'])
@require_admin
def admin_roles():
    if request.method == 'OPTIONS':
        return Response(status=204)
    if request.method == 'GET':
        from rbac import get_roles_with_member_count, get_permission_defs
        roles = get_roles_with_member_count()
        perms = get_permission_defs()
        return jsonify({"ok": True, "roles": roles, "permission_defs": perms})
    # POST: 创建/更新角色（整表保存）
    data = request.json or {}
    roles = data.get("roles")
    if not isinstance(roles, list):
        return jsonify({"ok": False, "error": "roles 必须为数组"}), 400
    from rbac import save_roles
    save_roles(roles)
    return jsonify({"ok": True, "message": f"已保存 {len(roles)} 个角色"})


@app.route('/v1/admin/roles/<role_id>', methods=['DELETE', 'OPTIONS'])
@require_admin
def admin_role_delete(role_id):
    if request.method == 'OPTIONS':
        return Response(status=204)
    from rbac import load_roles, save_roles
    roles = load_roles()
    target = next((r for r in roles if r.get("id") == role_id), None)
    if not target:
        return jsonify({"ok": False, "error": f"角色 {role_id} 不存在"}), 404
    members = target.get("members", [])
    if members:
        return jsonify({"ok": False, "error": f"角色仍有 {len(members)} 名成员，请先清空成员", "members": members}), 409
    roles = [r for r in roles if r.get("id") != role_id]
    save_roles(roles)
    return jsonify({"ok": True, "message": f"角色 {role_id} 已删除"})


@app.route('/v1/admin/roles/<role_id>/members', methods=['PUT', 'OPTIONS'])
@require_admin
def admin_role_members(role_id):
    if request.method == 'OPTIONS':
        return Response(status=204)
    data = request.json or {}
    members = data.get("members")
    if not isinstance(members, list):
        return jsonify({"ok": False, "error": "members 必须为数组"}), 400
    from rbac import load_roles, save_roles
    roles = load_roles()
    target = next((r for r in roles if r.get("id") == role_id), None)
    if not target:
        return jsonify({"ok": False, "error": f"角色 {role_id} 不存在"}), 404
    target["members"] = [str(m).strip() for m in members if str(m).strip()]
    save_roles(roles)
    return jsonify({"ok": True, "members": target["members"], "message": f"已更新 {len(target['members'])} 名成员"})


@app.route('/v1/admin/permissions', methods=['GET', 'POST', 'OPTIONS'])
@require_admin
def admin_permissions():
    if request.method == 'OPTIONS':
        return Response(status=204)
    if request.method == 'GET':
        from rbac import get_roles_with_member_count, get_permission_defs
        roles = get_roles_with_member_count()
        perms = get_permission_defs()
        return jsonify({"ok": True, "roles": roles, "permissions": perms})
    # POST: 更新某个角色的某个权限项
    data = request.json or {}
    role_id = (data.get("role_id") or "").strip()
    perm_key = (data.get("permission_key") or "").strip()
    value = data.get("value", False)
    if not role_id or not perm_key:
        return jsonify({"ok": False, "error": "缺少 role_id 或 permission_key"}), 400
    from rbac import set_role_permission
    try:
        updated = set_role_permission(role_id, perm_key, bool(value))
        return jsonify({"ok": True, "role": updated, "message": f"{role_id}.{perm_key} = {bool(value)}"})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@app.route('/v1/user/permissions', methods=['GET', 'OPTIONS'])
def user_permissions():
    """前端调用：当前用户的权限清单。"""
    if request.method == 'OPTIONS':
        return Response(status=204)
    from user_identity import parse_user_id_from_request
    body = request.get_json(silent=True) or {}
    # GET 请求时 query string 也支持 user_id
    qs_user = (request.args.get("user_id") or "").strip()
    if qs_user:
        body = {**body, "user_id": qs_user}
    user_id = parse_user_id_from_request(request, body=body)
    from rbac import get_user_permissions, get_user_role
    role = get_user_role(user_id) if user_id else None
    perms = get_user_permissions(user_id) if user_id else []
    return jsonify({
        "ok": True,
        "user_id": user_id or "",
        "role": role,
        "permissions": perms,
    })


# ═══════════════════════════════════════════════════════════
#  /v1/auth/login — 账号登录（v2.0-wave1）
# ═══════════════════════════════════════════════════════════
@app.route('/v1/auth/login', methods=['POST', 'OPTIONS'])
def auth_login():
    if request.method == 'OPTIONS':
        return Response(status=204)
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "")
    if not username or not password:
        return jsonify({"ok": False, "error": "用户名和密码不能为空"}), 400
    from accounts import login as account_login
    result = account_login(username, password)
    if not result:
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401
    return jsonify({"ok": True, **result})


# ═══════════════════════════════════════════════════════════
#  /v1/admin/accounts — 账号管理 CRUD（v2.0-wave1）
# ═══════════════════════════════════════════════════════════
@app.route('/v1/admin/accounts', methods=['GET', 'POST', 'OPTIONS'])
@require_admin
def admin_accounts():
    if request.method == 'OPTIONS':
        return Response(status=204)
    from accounts import load_accounts, create_account
    if request.method == 'GET':
        accounts = load_accounts()
        # 脱敏：移除 password_hash 和 salt
        safe = []
        for a in accounts:
            d = dict(a)
            d.pop("password_hash", None)
            d.pop("salt", None)
            safe.append(d)
        return jsonify({"ok": True, "accounts": safe})
    # POST: 创建账号
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    display_name = (body.get("display_name") or "").strip()
    password = (body.get("password") or "")
    role_ids = body.get("role_ids", [])
    if not username or not password:
        return jsonify({"ok": False, "error": "用户名和密码不能为空"}), 400
    try:
        account = create_account(username, display_name, password, role_ids)
        safe = dict(account)
        safe.pop("password_hash", None)
        safe.pop("salt", None)
        return jsonify({"ok": True, "account": safe})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 409


@app.route('/v1/admin/accounts/<account_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@require_admin
def admin_account_by_id(account_id):
    if request.method == 'OPTIONS':
        return Response(status=204)
    from accounts import get_account_by_id, update_account, delete_account
    if request.method == 'DELETE':
        try:
            account = delete_account(account_id)
            return jsonify({"ok": True, "account": account})
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
    # PUT: 编辑账号
    body = request.get_json(silent=True) or {}
    try:
        fields = {}
        if "display_name" in body:
            fields["display_name"] = body["display_name"]
        if "role_ids" in body:
            fields["role_ids"] = body["role_ids"]
        if "disabled" in body:
            fields["disabled"] = body["disabled"]
        if "password" in body and body["password"]:
            fields["password"] = body["password"]
        account = update_account(account_id, **fields)
        safe = dict(account)
        safe.pop("password_hash", None)
        safe.pop("salt", None)
        return jsonify({"ok": True, "account": safe})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404


# ═══════════════════════════════════════════════════════════
#  /api/diagnostics/logs — 飞行记录仪：返回最近 N 行日志
#  供前端 BugReport 异步拉取，嵌入反馈报告
# ═══════════════════════════════════════════════════════════
@app.route('/api/diagnostics/logs', methods=['GET'])
def diagnostics_logs():
    """返回 app.log 最近 200 行（灰度测试诊断用）"""
    import os as _os
    log_paths = [
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'logs', 'alice_bridge.log'),
        _os.path.join('logs', 'alice_bridge.log'),
    ]
    log_file = None
    for p in log_paths:
        if _os.path.exists(p):
            log_file = p
            break

    if not log_file:
        return jsonify({"ok": False, "error": "日志文件未找到", "lines": [], "hint": "RotatingFileHandler 可能尚未写入"}), 404

    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
        tail = all_lines[-200:] if len(all_lines) > 200 else all_lines
        return jsonify({
            "ok": True,
            "path": log_file,
            "total_lines": len(all_lines),
            "returned_lines": len(tail),
            "lines": [l.rstrip('\n\r') for l in tail]
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200], "lines": []}), 500

if __name__ == "__main__":
    from waitress import serve
    _build_faiss_index_on_startup()
    logger.info(f"AI Bridge v5 on port {config['port']} (Waitress threads=10, conn_limit=50, chan_timeout=60s)")
    serve(app, host="0.0.0.0", port=config["port"], threads=10, connection_limit=50, channel_timeout=60)
