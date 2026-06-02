"""
knowledge_retriever.py — 知识检索服务模块
职责：多数据源 L1 获取 + 缓存管理 + 辅助工具
"""
import os
import re
import time
import json
import logging
import asyncio
import collections
import concurrent.futures

logger = logging.getLogger("knowledge-retriever")

# ── BoundedCache: LRU 淘汰 + TTL 过期 ─────────────────────
class BoundedCache:
    """容量上限安全缓存"""
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
            self._cache.popitem(last=False)

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

# ── 缓存实例 ───────────────────────────────────────────────
_CONTEXT_CACHE = BoundedCache(max_size=200)
CACHE_TTL = 120
_SEMANTIC_CACHE = BoundedCache(max_size=100)
_SVN_COMMIT_CACHE = BoundedCache(max_size=150)

# ── 摘要 & 分类工具 ────────────────────────────────────────
L1_CHARS = {"jira": 500, "svn": 600, "notion": 400, "gdrive": 400}

def make_source_summary(source: str, raw_text: str, max_chars: int) -> str:
    """制造结构化摘要: 取首段 + 关键行"""
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    result = lines[:2]
    for line in lines[2:]:
        if line.startswith('|') or line.startswith('##') or line.startswith('###'):
            result.append(line)
        if sum(len(l) for l in result) > max_chars:
            break
    return "\n".join(result)[:max_chars]

def classify_file_changes(diff_text: str) -> str:
    """按扩展名分类文件变更类型"""
    if not diff_text:
        return ""
    patterns = {
        "代码": r"\.cs\b|\.java\b|\.py\b|\.cpp\b|\.h\b",
        "配置": r"\.json\b|\.csv\b|\.xml\b|\.yaml\b|\.yml\b|\.bytes\b|\.xlsx\b",
        "资源": r"\.prefab\b|\.unity\b|\.asset\b|\.mat\b|\.fbx\b|\.png\b|\.jpg\b",
        "项目": r"\.csproj\b|\.sln\b|\.meta\b|\.shader\b",
        "文档": r"\.md\b|\.txt\b|\.pdf\b",
    }
    counts = {}
    for name, p in patterns.items():
        matches = re.findall(p, diff_text, re.I)
        if matches:
            counts[name] = len(matches)
    if not counts:
        return ""
    parts = [f"{k}({v}个)" for k, v in counts.items()]
    return "📁 变更类型: " + " / ".join(parts)

# ── SVN 工具 ───────────────────────────────────────────────
def svn_log_grep(issue_key: str, svn_url: str, svn_user: str, svn_pass: str) -> str:
    """DevStatus 兜底：SVN 命令行直查提交记录"""
    import subprocess
    try:
        cmd = [
            "svn", "log", "--limit", "10", "--non-interactive",
            "--trust-server-cert", "--no-auth-cache",
            "--username", svn_user, "--password", svn_pass, svn_url
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25,
                              env={"LC_ALL": "en_US.UTF-8"})
        if proc.returncode != 0:
            return ""
        blocks = proc.stdout.split("------------------------------------------------------------------------")
        matched = []
        for block in blocks:
            if issue_key in block and "r" in block[:20]:
                lines_block = block.strip().split("\n")
                rev_line = lines_block[0] if lines_block else ""
                parts = rev_line.split(" | ")
                rev = parts[0].strip() if len(parts) > 0 else "?"
                author = parts[1].strip() if len(parts) > 1 else "?"
                date = parts[2].strip().split(" ")[0] if len(parts) > 2 else "?"
                msg = lines_block[-1].strip()[:100] if len(lines_block) > 1 else ""
                matched.append(f"### {rev} by {author} @ {date}\n> {msg}\n")
        if matched:
            return f"## {issue_key}: SVN提交 ({len(matched)}条)\n" + "\n".join(matched[:15])
    except FileNotFoundError:
        logger.warning(f"[SVN] svn_log_grep: SVN CLI 未安装，无法查询提交记录")
        return "* ⚠️ 当前服务器/本地环境未安装 SVN 命令行客户端，无法拉取代码变更明细。请联系管理员安装 SVN 并配置环境变量。*"
    except Exception as e:
        logger.warning(f"[SVN] svn_log_grep failed: {e}")
        return f"* ⚠️ SVN 查询异常: {str(e)[:200]}*"
    return ""

def safe_get_commits(issue_key, timeout=2.5):
    """带 TTL 缓存 + 超时熔断的 SVN 提交获取"""
    now = time.time()
    if issue_key in _SVN_COMMIT_CACHE:
        cached_time, cached_data = _SVN_COMMIT_CACHE[issue_key]
        if now - cached_time < CACHE_TTL:
            return cached_data
    try:
        from jira_mcp_server import jira_get_commits
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(jira_get_commits, issue_key)
            result = future.result(timeout=timeout)
            if result and "没有关联" not in result and "查询失败" not in result:
                _SVN_COMMIT_CACHE[issue_key] = (now, result)
                return result
    except concurrent.futures.TimeoutError:
        logger.warning(f"[Timeout] SVN fetch for {issue_key} exceeded {timeout}s!")
    except Exception as e:
        logger.warning(f"[Error] SVN fetch for {issue_key} failed: {e}")
    return None

# ── 结构化双跳检索：Jira → FishEye DevStatus → SVN CLI ──
def fetch_precise_commits_via_fisheye(issue_key: str) -> str:
    """Jira → FishEye DevStatus → SVN CLI 精确提交检索。
    
    算法流程:
    1. 调用 Jira API 获取 Issue 的 Jira Issue ID
    2. 调用 FishEye DevStatus API 提取关联的 SVN 版本号 (Revision IDs)
    3. 如果没有找到 Revision IDs → 返回明确提示
    4. 如果找到 → 使用 SVN CLI svn log/diff 精准拉取提交信息和代码变更
    5. 聚合结构化字符串返回（禁止模糊文本匹配，杜绝幻觉）
    """
    try:
        from jira_mcp_server import ensure_jira_connected
        client, err = ensure_jira_connected()
        if err:
            return f"[PreciseCommits] Jira 连接失败: {err}"

        # ── Hop 1: Jira API → Issue ID ──
        r = client.session.get(
            f"{client.api_url}/issue/{issue_key}?fields=id,summary",
            timeout=15
        )
        if r.status_code != 200:
            return f"[PreciseCommits] Issue {issue_key} 不存在 (HTTP {r.status_code})"

        issue_data = r.json()
        issue_id = issue_data["id"]
        summary = issue_data["fields"]["summary"]

        # ── Hop 2: FishEye DevStatus → Revision IDs ──
        r = client.session.get(
            f"{client.base_url}/rest/dev-status/1.0/issue/detail"
            f"?issueId={issue_id}&applicationType=fecru&dataType=repository",
            timeout=15
        )

        if r.status_code != 200:
            # 降级：回退到 jira_mcp_server.jira_get_commits (FishEye 直接查询)
            from jira_mcp_server import jira_get_commits
            logger.info(f"[PreciseCommits] DevStatus 不可用(HTTP {r.status_code}), 回退至 FishEye 直接查询")
            return jira_get_commits(issue_key)

        detail = r.json()
        repos = detail.get("detail", [{}])[0].get("repositories", [])

        if not repos or not any(rp.get("commits") for rp in repos):
            return (
                f"## {issue_key}: {summary}\n\n"
                f"> \u2757 未在 Jira 的 FishEye 面板中找到关联的 SVN 提交记录。\n"
                f"> 该 Issue 可能尚未关联代码提交，或 FishEye 索引尚未完成。\n"
                f"> 请检查 Jira Issue 页面的 \"Development\" 面板确认。"
            )

        # ── Hop 3: 组装元数据（不拉取 Raw Diff）──
        lines = [f"## {issue_key}: {summary}\n"]

        # 只取最近 5 条提交，防止噪音过载
        recent_commits = []
        for repo in repos:
            for commit in repo.get("commits", []):
                recent_commits.append(commit)
        recent_commits.sort(key=lambda c: c.get("authorTimestamp", 0), reverse=True)
        recent_commits = recent_commits[:5]

        lines.append("| 版本 | 作者 | 时间 | 文件数 | +/- | 说明 |")
        lines.append("|------|------|------|:--:|:--:|------|")
        for commit in recent_commits:
            author = commit["author"]["name"]
            ts = commit.get("authorTimestamp", "")
            display_id = commit.get("displayId", "")
            file_count = commit.get("fileCount", 0)
            message = commit.get("message", "").split("\n")[0][:80]
            total_added = sum(f.get("linesAdded", 0) for f in commit.get("files", []))
            total_removed = sum(f.get("linesRemoved", 0) for f in commit.get("files", []))
            lines.append(
                f"| r{display_id} | {author} | {ts} | {file_count} | +{total_added}/-{total_removed} | {message} |"
            )

        # 只列前 5 个文件（不再拉取 SVN Diff）
        lines.append(f"\n共 {len(recent_commits)} 条提交记录")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"[PreciseCommits] {issue_key} failed: {e}")
        # 最终降级
        try:
            from jira_mcp_server import jira_get_commits
            return jira_get_commits(issue_key)
        except:
            return f"[PreciseCommits] {issue_key} 检索失败: {str(e)[:200]}"

def extract_dynamic_keywords(user_text: str = "", issue_key: str = "") -> str:
    """DynamicContextResolver: 从 Jira 摘要或用户文本中动态提取搜索关键词。
    
    优先级:
    1. issue_key → Jira API 获取 summary → 提取核心词 (去除【系统】等前缀)
    2. Jira 失败/超时 → 从 user_text 提取 2-3 个关键词
    3. 兜底 → 直接使用 issue_key 本身
    
    ⚠️ 绝对禁止硬编码默认业务词汇!
    """
    # ── 尝试 Jira API ──
    if issue_key:
        try:
            from ai_bridge import jira as _jira_mod
            api_url = getattr(_jira_mod, 'api_url', '')
            if api_url:
                resp = _jira_mod.jira_get(f"{api_url}/issue/{issue_key}?fields=summary", timeout=5)
                if resp.status_code == 200:
                    summary = resp.json().get("fields", {}).get("summary", "")
                    if summary:
                        # 清洗: 去除【系统】【功能】等前缀和括号内容
                        import re as _re
                        cleaned = _re.sub(r'【[^】]*】', '', summary)
                        cleaned = _re.sub(r'[（(][^）)]*[）)]', '', cleaned)
                        cleaned = cleaned.strip()
                        if cleaned and len(cleaned) > 1:
                            logger.info(f"[DynamicContext] From Jira: '{summary}' → '{cleaned}'")
                            return cleaned[:50]
        except Exception as e:
            logger.warning(f"[DynamicContext] Jira API failed: {e}")
    
    # ── 从 user_text 提取 ──
    if user_text:
        import re as _re2
        # 移除常见问句前缀、版本号、标点
        cleaned = _re2.sub(r'(?:帮我|请|分析一下|查看|看看|的.*diff|r\d+|代码|需要)', '', user_text)
        cleaned = _re2.sub(r'[^\u4e00-\u9fff\w\s]', ' ', cleaned)
        words = [w.strip() for w in cleaned.split() if len(w.strip()) >= 2]
        # 取前 2-3 个有意义的中文词
        meaningful = [w for w in words if _re2.search(r'[\u4e00-\u9fff]', w)][:3]
        if meaningful:
            kw = ' '.join(meaningful)[:50]
            logger.info(f"[DynamicContext] From user_text: '{kw}'")
            return kw
    
    # ── 兜底 ──
    result = issue_key or user_text[:50] or ""
    logger.info(f"[DynamicContext] Fallback: '{result}'")
    return result

def get_single_commit_diff(revision_id: str) -> str:
    """按需召回: 拉取指定版本号(r40538)的单次提交代码 Diff。
    
    算法:
    1. 从环境变量获取 SVN 仓库凭据
    2. 调用 svn diff -c {revision_id} 获取纯文本 Diff
    3. 截断至 3000 tokens (~8000 字符)
    4. 仅返回 Diff 文本, 不作分析
    
    Args:
        revision_id: SVN 版本号, 如 "40538" 或 "r40538"
    """
    import subprocess, os
    
    # 清洗版本号: 去除 "r" 前缀
    rev = str(revision_id).lstrip("rR")
    
    svn_url = os.getenv("SVN_URL", "")
    svn_user = os.getenv("SVN_USERNAME", "")
    svn_pass = os.getenv("SVN_PASSWORD", "")
    
    if not svn_url:
        try:
            from ai_bridge import jira as _jira_mod
            gcfg = getattr(_jira_mod, '_global_cfg', {})
            svn_url = gcfg.get("SVN_URL", "")
            svn_user = gcfg.get("SVN_USERNAME", "")
            svn_pass = gcfg.get("SVN_PASSWORD", "")
        except Exception:
            pass
    
    if not svn_url:
        return "[get_single_commit_diff] SVN 仓库地址未配置"
    
    try:
        result = subprocess.run(
            ["svn", "--non-interactive",
             "--trust-server-cert-failures=unknown-ca,cn-mismatch,expired,not-yet-valid,other",
             "--username", svn_user, "--password", svn_pass,
             "diff", "-c", rev, svn_url],
            capture_output=True, text=False, timeout=45,
            env={**os.environ, "NO_PROXY": "*"}
        )
        
        if result.returncode != 0:
            err = result.stderr.decode('utf-8', errors='ignore')[:300]
            return f"[get_single_commit_diff] SVN diff 失败 (r{rev}): {err}"
        
        diff_text = result.stdout.decode('utf-8', errors='ignore')
        
        if not diff_text.strip():
            return f"[get_single_commit_diff] r{rev} 无 Diff 内容（可能是空提交或二进制文件）"
        
        # 安全护栏: 截断至 ~3000 tokens (约 8000 字符)
        MAX_CHARS = 8000
        if len(diff_text) > MAX_CHARS:
            diff_text = diff_text[:MAX_CHARS]
            diff_text += f"\n\n[Diff过长已截断] 原始 Diff 共 {len(result.stdout)} 字符, 仅展示前 {MAX_CHARS} 字符。如需完整 Diff 请缩小范围。"
        
        return f"## SVN Diff: r{rev}\n\n```diff\n{diff_text}\n```"
        
    except FileNotFoundError:
        return "[get_single_commit_diff] 当前环境未安装 SVN 命令行客户端"
    except subprocess.TimeoutExpired:
        return f"[get_single_commit_diff] SVN diff r{rev} 超时 (45s)"
    except Exception as e:
        return f"[get_single_commit_diff] r{rev} 异常: {str(e)[:300]}"

# ── Notion 工具 ────────────────────────────────────────────
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
                if result:
                    return result
        elif isinstance(node, list):
            for i in node:
                result = deep_search_text(i)
                if result:
                    return result
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

# ── 用户名解析（依赖 jira_client 实例，由调用方注入）─────
def resolve_jira_username(jira_client, chinese_name: str) -> str:
    """调用 Jira /user/search API，将中文显示名转为英文 username"""
    try:
        resp = jira_client.jira_get(f"{jira_client.api_url}/user/search?username={chinese_name}&maxResults=3")
        users = resp.json() if hasattr(resp, 'json') else resp
        if isinstance(users, list) and len(users) > 0:
            username = users[0].get("name", "")
            display = users[0].get("displayName", "")
            logger.info(f"[UserResolve] {chinese_name} → {username} ({display})")
            return username
    except Exception as e:
        logger.warning(f"[UserResolve] {chinese_name} failed: {e}")
    return ""

# ── L1 检索函数（同步，由旧 collect_context 闭包调用）───
import requests as http  # 保留同步 requests 用于 JiraClient 兼容

def l1_jira_fetch(issue_key, jira_client, user_pat, state):
    """Jira L1: 摘要 + 评论 + 版本信息（同步版）"""
    try:
        r = jira_client.jira_get(
            f"{jira_client.api_url}/issue/{issue_key}?fields=summary,issuetype,status,assignee,description,comment,fixVersions,versions,priority",
            timeout=15, user_pat=user_pat
        )
        if r.status_code != 200:
            return None

        f = r.json()["fields"]
        fix_vs = [v.get("name", "") for v in (f.get("fixVersions") or []) if v.get("name")]
        aff_vs = [v.get("name", "") for v in (f.get("versions") or []) if v.get("name")]
        vinfo = ""
        if fix_vs:
            vinfo += f"修复:{','.join(fix_vs)} "
        if aff_vs:
            vinfo += f"影响:{','.join(aff_vs)} "

        short_raw = (
            f"{f.get('summary', '?')}\n"
            f"{vinfo}类型:{f.get('issuetype', {}).get('name', '?')} "
            f"状态:{f.get('status', {}).get('name', '?')} "
            f"描述:{(f.get('description') or '无')[:100]}"
        )

        comments_data = f.get("comment", {}).get("comments", [])
        comments_text = ""
        if comments_data:
            comments_text = "\n【最新历史评论】\n"
            for c in comments_data[-10:]:
                author = c.get("author", {}).get("displayName", "Unknown")
                body = c.get("body", "")[:500]
                comments_text += f"- {author}: {body}\n"

        desc_full = (f.get('description') or '无')[:4000]
        priority_name = (f.get('priority') or {}).get('name', '') if f.get('priority') else ''
        assignee_val = f.get('assignee') or {}
        assignee_name = assignee_val.get('displayName', '未分配') if isinstance(assignee_val, dict) else '未分配'

        state["current_issue_detail"] = (
            f"### 当前 Issue ({issue_key}) 完整详情\n"
            f"标题: {f.get('summary', '?')}\n"
            f"{vinfo}类型:{f.get('issuetype', {}).get('name', '?')} | "
            f"状态:{f.get('status', {}).get('name', '?')} | "
            f"优先级:{priority_name} | "
            f"经办人:{assignee_name}\n"
            f"【描述正文】\n{desc_full}\n"
            f"{comments_text}"
        )

        return make_source_summary("jira", short_raw, L1_CHARS["jira"])
    except Exception as e:
        return f"(Jira: {e})"


# ── L1 检索函数（异步，供 S1 并行调度器调用）───────────

async def l1_jira_fetch_async(issue_key, jira_client, user_pat, state):
    """Jira L1: 异步包装 → asyncio.to_thread 做非阻塞 IO"""
    return await asyncio.to_thread(l1_jira_fetch, issue_key, jira_client, user_pat, state)


async def l1_svn_fetch_async(issue_key, q, state):
    """SVN L1: 异步包装（subprocess 阻塞调用）"""
    return await asyncio.to_thread(l1_svn_fetch, issue_key, q, state)


async def _notion_post_async(url, headers, json_body, timeout=10):
    """Notion API 异步 POST 调用"""
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=headers, json=json_body) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.debug(f"Notion async POST {url}: {e}")
    return None


async def _gdrive_get_async(url, timeout=10):
    """GDrive API 异步 GET 调用"""
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.debug(f"GDrive async GET {url[:80]}: {e}")
    return None


async def l1_notion_fetch_async(issue_key, q, is_global, state):
    """Notion L1: aiohttp 异步多策略并发搜索"""
    NOTION_KEY = os.getenv("NOTION_KEY", "")
    if not NOTION_KEY:
        return None

    NOTION_DB_ID = os.getenv("NOTION_DB_ID", "")
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    # 策略0~3 并发执行
    tasks = []
    if NOTION_DB_ID:
        tasks.append(_notion_post_async(
            f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
            headers, {"page_size": 20}, 10))
    if issue_key != "__global__":
        tasks.append(_notion_post_async(
            "https://api.notion.com/v1/search",
            headers, {"query": issue_key, "page_size": 5}, 10))
    base_kw = [kw for kw in q.replace("，", " ").replace(",", " ").split() if len(kw) >= 2]
    if base_kw:
        tasks.append(_notion_post_async(
            "https://api.notion.com/v1/search",
            headers, {"query": " ".join(base_kw[:5]), "page_size": 10}, 10))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    pids = set()
    for r in results:
        if isinstance(r, Exception) or r is None:
            continue
        for item in r.get("results", [])[:20]:
            pid = item.get("id") or item.get("id", "")
            if pid:
                pids.add(pid)

    if pids:
        state["notion_pids"] = pids
        return f"\n## Notion (L1)\n找到 {len(pids)} 篇相关文档"
    return None


async def l1_gdrive_fetch_async(q, frontend_cfg, state):
    """Google Drive L1: aiohttp 异步并行拉取多文件夹"""
    GK = os.getenv("GDRIVE_KEY", "")
    if not GK:
        return None
    raw_folders = os.getenv("GDRIVE_FOLDERS", "")
    folders = [f.strip() for f in re.split(r'[\n,]+', raw_folders) if f.strip()]
    if not folders:
        return None

    # 并行拉取所有文件夹
    tasks = []
    for fid in folders:
        url = f"https://www.googleapis.com/drive/v3/files?key={GK}&q='{fid}'+in+parents&fields=files(id,name,mimeType)&pageSize=30"
        tasks.append(_gdrive_get_async(url, 10))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_files = {}
    for r in results:
        if isinstance(r, Exception) or r is None:
            continue
        for f in r.get("files", []):
            all_files[f["id"]] = f

    base_kw = [kw for kw in q.replace("，", " ").replace(",", " ").split() if len(kw) >= 2]
    matched = [f for _, f in all_files.items() if any(k in f.get("name", "") for k in set(base_kw))]
    if matched:
        state["gdrive_matched"] = matched
        return "\n## Google Drive (L1)\n" + "\n".join([f"- {f['name']}" for f in matched[:5]])
    return None


# ── 同步版 L1 函数（供旧 pipeline 兼容）───────────────

def l1_svn_fetch(issue_key, q, state):
    """SVN L1: 提交记录 + 缓存（同步版）"""
    SVN_CACHE_TTL = 300
    all_commits = []

    target_keys = [issue_key] if issue_key != "__global__" else []
    for ik in re.findall(r'([A-Z]{2,}-\d+)', q):
        if ik not in target_keys:
            target_keys.append(ik)
    if not target_keys:
        return None

    for ik in target_keys:
        if ik in _SVN_COMMIT_CACHE:
            ts, cached = _SVN_COMMIT_CACHE[ik]
            if time.time() - ts < SVN_CACHE_TTL:
                all_commits.append((ik, cached))
                continue

        from jira_mcp_server import jira_get_commits
        commits = jira_get_commits(ik)
        if commits and "没有关联" not in commits and "查询失败" not in commits:
            all_commits.append((ik, commits))
            _SVN_COMMIT_CACHE[ik] = (time.time(), commits)
        else:
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
    return None


def l1_notion_fetch(issue_key, q, is_global, state):
    """Notion L1: 策略0~4 多级搜索（同步版）"""
    NOTION_KEY = os.getenv("NOTION_KEY", "")
    if not NOTION_KEY:
        return None

    NOTION_DB_ID = os.getenv("NOTION_DB_ID", "")
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    pids = set()

    if NOTION_DB_ID:
        try:
            r = http.post(f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
                          headers=headers, json={"page_size": 20}, timeout=10)
            if r.status_code == 200:
                for p in r.json().get("results", []):
                    pids.add(p["id"])
        except Exception as e:
            logger.debug(f"Notion strategy0: {e}")

    if issue_key != "__global__":
        try:
            r = http.post("https://api.notion.com/v1/search",
                          headers=headers, json={"query": issue_key, "page_size": 5}, timeout=10)
            if r.status_code == 200:
                for item in r.json().get("results", []):
                    pids.add(item["id"])
        except Exception as e:
            logger.debug(f"Notion strategy1: {e}")

    base_kw = [kw for kw in q.replace("，", " ").replace(",", " ").split() if len(kw) >= 2]
    if base_kw:
        try:
            r = http.post("https://api.notion.com/v1/search",
                          headers=headers, json={"query": " ".join(base_kw[:5]), "page_size": 10}, timeout=10)
            if r.status_code == 200:
                for item in r.json().get("results", []):
                    pids.add(item["id"])
        except Exception as e:
            logger.debug(f"Notion strategy2: {e}")

    if pids:
        state["notion_pids"] = pids
        return f"\n## Notion (L1)\n找到 {len(pids)} 篇相关文档"
    return None


def l1_gdrive_fetch(q, frontend_cfg, state):
    """Google Drive L1: 关键词匹配文件列表（同步版）"""
    try:
        GK = os.getenv("GDRIVE_KEY", "")
        if not GK:
            return None
        raw_folders = os.getenv("GDRIVE_FOLDERS", "")
        folders = [f.strip() for f in re.split(r'[\n,]+', raw_folders) if f.strip()]
        if not folders:
            return None

        proxy_url = frontend_cfg.get("proxy", "") if frontend_cfg else ""
        proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None

        all_files = {}
        for fid in folders:
            r = http.get(
                f"https://www.googleapis.com/drive/v3/files?key={GK}&q='{fid}'+in+parents&fields=files(id,name,mimeType)&pageSize=30",
                timeout=10, proxies=proxies)
            if r.status_code == 200:
                for f in r.json().get("files", []):
                    all_files[f["id"]] = f

        base_kw = [kw for kw in q.replace("，", " ").replace(",", " ").split() if len(kw) >= 2]
        matched = [f for _, f in all_files.items() if any(k in f.get("name", "") for k in set(base_kw))]
        if matched:
            state["gdrive_matched"] = matched
            return "\n## Google Drive (L1)\n" + "\n".join([f"- {f['name']}" for f in matched[:5]])
    except Exception as e:
        logger.debug(f"GDrive L1: {e}")
    return None
