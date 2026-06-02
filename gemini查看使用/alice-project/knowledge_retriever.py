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
                lines = block.strip().split("\n")
                rev_line = lines[0] if lines else ""
                parts = rev_line.split(" | ")
                rev = parts[0].strip() if len(parts) > 0 else "?"
                author = parts[1].strip() if len(parts) > 1 else "?"
                date = parts[2].strip().split(" ")[0] if len(parts) > 2 else "?"
                msg = lines[-1].strip()[:100] if len(lines) > 1 else ""
                matched.append(f"### {rev} by {author} @ {date}\n> {msg}\n")
        if matched:
            return f"## {issue_key}: SVN提交 ({len(matched)}条)\n" + "\n".join(matched[:15])
    except Exception as e:
        logger.debug(f"SVN log fallback: {e}")
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

        # ── Hop 3: SVN CLI 精准拉取 ──
        import subprocess
        svn_url = os.getenv("SVN_URL", "")
        svn_user = os.getenv("SVN_USERNAME", "")
        svn_pass = os.getenv("SVN_PASSWORD", "")

        lines = [f"## {issue_key}: {summary}\n"]
        total_revisions = 0

        for repo in repos:
            repo_name = repo.get("name", "Unknown")
            for commit in repo.get("commits", []):
                author = commit["author"]["name"]
                timestamp = commit["authorTimestamp"]
                display_id = commit.get("displayId", "")
                file_count = commit.get("fileCount", 0)
                message = commit.get("message", "").split("\n")[0][:150]
                url = commit.get("url", "")
                total_revisions += 1

                total_added = sum(f.get("linesAdded", 0) for f in commit.get("files", []))
                total_removed = sum(f.get("linesRemoved", 0) for f in commit.get("files", []))

                lines.append(f"### r{display_id} by {author} @ {timestamp}")
                lines.append(f"> {message}")
                lines.append(f"仓库: {repo_name} | 文件数: {file_count} | +{total_added} -{total_removed}")
                lines.append(f"FishEye: {url}")

                # SVN CLI 精确 Diff（仅当凭证可用时）
                if svn_url and svn_user and display_id:
                    try:
                        # svn log -r <rev> 获取精确提交详情
                        log_cmd = [
                            "svn", "log", "-r", display_id, "--non-interactive",
                            "--trust-server-cert", "--no-auth-cache",
                            "--username", svn_user, "--password", svn_pass, svn_url
                        ]
                        log_proc = subprocess.run(log_cmd, capture_output=True, text=True,
                                                   timeout=15, env={"LC_ALL": "en_US.UTF-8"})
                        if log_proc.returncode == 0 and log_proc.stdout.strip():
                            log_text = log_proc.stdout.strip()
                            # 提取提交信息（跳过分隔线和头部行）
                            log_parts = log_text.split("\n")
                            commit_msg_line = ""
                            for lp in log_parts:
                                lp = lp.strip()
                                if lp and not lp.startswith("-") and not lp.startswith("r"):
                                    if not any(lp.startswith(p) for p in ["Changed", "Index:", "==="]):
                                        commit_msg_line = lp[:200]
                                        break
                            if commit_msg_line:
                                lines.append(f"  SVN log: {commit_msg_line}")

                        # svn diff -c <rev> 获取代码变更（截取前 80 行）
                        diff_cmd = [
                            "svn", "diff", "-c", display_id, "--non-interactive",
                            "--trust-server-cert", "--no-auth-cache",
                            "--username", svn_user, "--password", svn_pass, svn_url
                        ]
                        diff_proc = subprocess.run(diff_cmd, capture_output=True, text=True,
                                                    timeout=20, env={"LC_ALL": "en_US.UTF-8"})
                        if diff_proc.returncode == 0 and diff_proc.stdout.strip():
                            diff_lines = diff_proc.stdout.strip().split("\n")[:80]
                            lines.append("\n```diff")
                            lines.extend(diff_lines)
                            lines.append("```")
                    except Exception as e:
                        logger.debug(f"[PreciseCommits] SVN CLI failed for r{display_id}: {e}")

                # 文件变更清单
                lines.append("\n| 变更 | 文件 | + | - |")
                lines.append("|------|------|---|---|")
                for f in commit.get("files", []):
                    ct = f.get("changeType", "?")
                    icon = {"ADDED": "➕", "MODIFIED": "✏️", "DELETED": "➖"}.get(ct, "")
                    lines.append(
                        f"| {icon} | `{f['path']}` "
                        f"| +{f.get('linesAdded',0)} | -{f.get('linesRemoved',0)} |"
                    )
                lines.append("")

        if total_revisions == 0:
            return (
                f"## {issue_key}: {summary}\n\n"
                f"> 该问题在 FishEye 中有记录但解析失败。请检查 FishEye 索引或联系管理员。"
            )

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"[PreciseCommits] {issue_key} failed: {e}")
        # 最终降级
        try:
            from jira_mcp_server import jira_get_commits
            return jira_get_commits(issue_key)
        except:
            return f"[PreciseCommits] {issue_key} 检索失败: {str(e)[:200]}"

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
