"""
Jira MCP Server
基于 FastMCP 实现，连接自托管 Jira Server，提供 6 个查询工具。

认证方式:
  - Session Cookie (JIRA_SESSION_COOKIE 环境变量) — 绕过 CAPTCHA
  - 或 Basic Auth (JIRA_USERNAME + JIRA_PASSWORD)

使用方式:
  python jira_mcp_server.py
  (以 stdio 模式运行，供 WorkBuddy MCP Client 调用)
"""

import os
import sys

# 强制不走系统代理（内网 Jira）
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

# 初始化 FastMCP（仅在 MCP server 模式下需要）
mcp = FastMCP("jira") if FastMCP else None

# 如果 FastMCP 不可用，提供一个空装饰器，让函数可被 ai_bridge 导入
if mcp is None:
    class _DummyTool:
        def __call__(self, *a, **kw):
            def decorator(fn): return fn
            return decorator
    _dt = _DummyTool()
    def tool(): return _dt
else:
    tool = mcp.tool

# ── JiraClient 初始化 ──────────────────────────────────────────
from jira_api import JiraClient

# 懒加载，在第一个工具调用时才初始化
_jira_client = None

def get_jira_client():
    """懒加载 JiraClient，确保环境变量已设置"""
    global _jira_client
    if _jira_client is None:
        _jira_client = JiraClient(
            base_url=os.getenv("JIRA_BASE_URL", "http://ctjira1.lmdgame.com:8080"),
            email=os.getenv("JIRA_USERNAME", "admin"),
            password=os.getenv("JIRA_PASSWORD", ""),
            session_cookie=os.getenv("JIRA_SESSION_COOKIE") or None,
            pat_token=os.getenv("JIRA_PAT") or None,
        )
    return _jira_client

def ensure_jira_connected():
    """
    确保 Jira 连接可用 — 连接断开时自动重建 session
    MCP -32000 错误通常由 Jira 服务端关闭长连接导致，
    此函数在工具调用前验证连接，必要时重建。
    返回: (JiraClient, error_message_or_None)
    """
    global _jira_client
    try:
        client = get_jira_client()
        # 快速健康检查：发一次轻量请求
        result = client.test_connection()
        if result.get("success"):
            return client, None
        # 连接失败，尝试重建 session
        client._rebuild_session()
        result = client.test_connection()
        if result.get("success"):
            return client, None
        return client, result.get("error", "Jira 连接失败")
    except Exception as e:
        # 重建 session 再试
        try:
            if _jira_client:
                _jira_client._rebuild_session()
                result = _jira_client.test_connection()
                if result.get("success"):
                    return _jira_client, None
                return _jira_client, result.get("error", "Jira 连接重建后仍失败")
        except Exception as e2:
            return _jira_client, f"Jira 连接异常: {e2}"
        return _jira_client, f"Jira 连接异常: {e}"

jira = get_jira_client()


# ── Tools ──────────────────────────────────────────────────────

@tool()
def jira_test_connection() -> str:
    """测试 Jira 服务器连接，返回当前登录用户信息。用于验证配置是否正确。"""
    result = jira.test_connection()
    if result.get("success"):
        return f"""Jira 连接成功!
用户名: {result['display_name']}
邮箱: {result['email']}
服务器: {jira.base_url}"""
    else:
        return f"Jira 连接失败: {result.get('error', '未知错误')}\n\n提示: 如果看到 CAPTCHA 错误，请设置 JIRA_SESSION_COOKIE 环境变量。"


@tool()
def jira_list_projects() -> str:
    """列出 Jira 中所有可访问的项目。"""
    client, err = ensure_jira_connected()
    if err:
        return f"Jira 连接失败: {err}\n提示: 请检查 Jira 服务器是否在线，或配置 JIRA_PAT 环境变量。"
    try:
        r = client.session.get(
            f"{client.api_url}/project",
            timeout=30,
        )
        if r.status_code != 200:
            return f"查询失败: HTTP {r.status_code}"

        projects = r.json()
        if not projects:
            return "没有找到任何项目。"

        lines = [f"共 {len(projects)} 个项目:", ""]
        for p in projects:
            lines.append(
                f"  [{p.get('key', '?')}] {p.get('name', '?')}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"查询失败: {e}"


@tool()
def jira_search(jql: str) -> str:
    """使用 JQL (Jira Query Language) 搜索问题。

    Args:
        jql: JQL 查询语句，例如:
             "project = DEMO AND status != Closed"
             "assignee = currentUser() AND priority = High"
    """
    client, err = ensure_jira_connected()
    if err:
        return f"Jira 连接失败: {err}"
    result = client.search_issues(jql)
    if not result or not result.get("success"):
        error_detail = result.get('error', '返回为空') if result else '返回为 None'
        # 打印详细错误到 stderr（方便调试）
        import sys
        print(f"[DEBUG] jira_search failed: {error_detail}", file=sys.stderr)
        return f"查询失败: {error_detail}"

    formatted = jira.format_issues_for_wecom(
        result["issues"],
        f"JQL 查询结果 ({result['total']} 个问题)"
    )
    formatted += f"\n\n执行 JQL: `{jql}`"
    return formatted


@tool()
def jira_my_open_issues() -> str:
    """获取当前用户所有未完成的任务。"""
    result = jira.get_my_open_issues()
    if not result.get("success"):
        return f"查询失败: {result.get('error', '未知错误')}"

    return jira.format_issues_for_wecom(
        result["issues"],
        f"我的未完成任务 ({result['total']} 个)"
    )


@tool()
def jira_this_week_issues() -> str:
    """获取当前用户本周未完成的任务。"""
    result = jira.get_this_week_unfinished_issues()
    if not result.get("success"):
        return f"查询失败: {result.get('error', '未知错误')}"

    return jira.format_issues_for_wecom(
        result["issues"],
        f"本周未完成任务 ({result['total']} 个)"
    )


@tool()
def jira_get_issue(issue_key: str) -> str:
    """获取单个 Jira 问题的详细信息。

    Args:
        issue_key: 问题编号，例如 "DEMO-123" 或 "PROJ-456"
    """
    client, err = ensure_jira_connected()
    if err:
        return f"Jira 连接失败: {err}"
    try:
        r = client.session.get(
            f"{client.api_url}/issue/{issue_key}",
            timeout=30,
        )
        if r.status_code != 200:
            return f"查询失败: HTTP {r.status_code} - 问题 {issue_key} 可能不存在"

        data = r.json()
        fields = data.get("fields", {})

        status = fields.get("status", {}).get("name", "?")
        priority = fields.get("priority", {}).get("name", "?")
        issue_type = fields.get("issuetype", {}).get("name", "?")
        project = fields.get("project", {}).get("name", "?")
        assignee = fields.get("assignee", {})
        reporter = fields.get("reporter", {})
        summary = fields.get("summary", "?")
        description = fields.get("description", "无描述")
        created = fields.get("created", "?")
        updated = fields.get("updated", "?")
        due_date = fields.get("duedate", "无")

        # 截断过长的描述
        if description and len(description) > 500:
            description = description[:500] + "..."

        return f"""## {issue_key}: {summary}

| 字段 | 值 |
|------|-----|
| 状态 | {status} |
| 优先级 | {priority} |
| 类型 | {issue_type} |
| 项目 | {project} |
| 经办人 | {assignee.get('displayName', '未分配')} |
| 报告人 | {reporter.get('displayName', '?')} |
| 创建时间 | {created} |
| 更新时间 | {updated} |
| 截止日期 | {due_date} |

### 描述
{description}

链接: {client.base_url}/browse/{issue_key}"""
    except Exception as e:
        return f"查询失败: {e}"


@tool()
def jira_get_commits(issue_key: str) -> str:
    """获取某个 Jira 问题关联的代码提交信息（提交者、时间、文件清单、增删行数）。

    Args:
        issue_key: 问题编号，例如 "CT-11086"
    """
    client, err = ensure_jira_connected()
    if err:
        return f"Jira 连接失败: {err}"
    try:
        # 先获取 issue 数字 ID
        r = client.session.get(
            f"{client.api_url}/issue/{issue_key}?fields=id,summary",
            timeout=15,
        )
        if r.status_code != 200:
            return f"查询失败: 问题 {issue_key} 不存在"

        issue_data = r.json()
        issue_id = issue_data["id"]
        summary = issue_data["fields"]["summary"]

        # 查 FishEye 关联提交
        r = client.session.get(
            f"{client.base_url}/rest/dev-status/1.0/issue/detail"
            f"?issueId={issue_id}&applicationType=fecru&dataType=repository",
            timeout=15,
        )

        if r.status_code != 200:
            return f"查询开发信息失败: HTTP {r.status_code}"

        detail = r.json()
        repos = detail.get("detail", [{}])[0].get("repositories", [])

        if not repos:
            return f"## {issue_key}: {summary}\n\n该问题没有关联的代码提交。"

        lines = [f"## {issue_key}: {summary}", ""]

        for repo in repos:
            for commit in repo.get("commits", []):
                author = commit["author"]["name"]
                timestamp = commit["authorTimestamp"]
                rev = commit["displayId"]
                file_count = commit["fileCount"]
                message = commit["message"].split("\n")[0][:150]
                url = commit["url"]

                total_added = sum(f.get("linesAdded", 0) for f in commit.get("files", []))
                total_removed = sum(f.get("linesRemoved", 0) for f in commit.get("files", []))

                lines.append(f"### r{rev} by {author} @ {timestamp}")
                lines.append(f"> {message}")
                lines.append(f"文件数: {file_count} | +{total_added} -{total_removed}")
                lines.append(f"FishEye: {url}")
                lines.append("")

                lines.append("| 变更 | 文件 |")
                lines.append("|------|------|")
                for f in commit.get("files", []):
                    ct = f.get("changeType", "?")
                    icon = {"ADDED": "➕", "MODIFIED": "✏️", "DELETED": "➖"}.get(ct, "")
                    lines.append(
                        f"| {icon} +{f.get('linesAdded',0)} -{f.get('linesRemoved',0)} "
                        f"| `{f['path']}` |"
                    )

        return "\n".join(lines)

    except Exception as e:
        return f"查询失败: {e}"


@tool()
def jira_get_svn_diff(issue_key: str, max_files: int = 10, svn_cfg: dict = None) -> str:
    """获取某个 Jira 问题关联提交的代码 Diff 内容（通过 SVN 直连）。

    注意：该功能需要 SVN 命令行工具和仓库访问权限。
    支持通过 svn_cfg 动态传入凭证（优先），否则回退到环境变量。

    Args:
        issue_key: 问题编号
        max_files: 最多展示文件数（默认10）
        svn_cfg: 可选，包含 svn_url, svn_user, svn_pass 的字典
    """
    import subprocess
    import os

    svn_cfg = svn_cfg or {}
    svn_url = svn_cfg.get("svn_url") or os.getenv("SVN_URL", "")
    svn_user = svn_cfg.get("svn_user") or os.getenv("SVN_USERNAME", "")
    svn_pass = svn_cfg.get("svn_pass") or os.getenv("SVN_PASSWORD", "")

    client, err = ensure_jira_connected()
    if err:
        return f"Jira 连接失败: {err}"
    try:
        # 先获取提交信息
        r = client.session.get(f"{client.api_url}/issue/{issue_key}?fields=id,summary", timeout=15)
        if r.status_code != 200:
            return f"问题 {issue_key} 不存在"
        issue_id = r.json()["id"]

        r = client.session.get(
            f"{client.base_url}/rest/dev-status/1.0/issue/detail"
            f"?issueId={issue_id}&applicationType=fecru&dataType=repository",
            timeout=15,
        )

        if r.status_code != 200:
            return f"查询开发信息失败: HTTP {r.status_code}"

        detail = r.json()
        repos = detail.get("detail", [{}])[0].get("repositories", [])

        if not repos:
            return f"## {issue_key}\n该问题没有关联的代码提交。"

        lines = [f"## {issue_key} 代码 Diff", ""]

        for repo in repos:
            for commit in repo.get("commits", []):
                rev = commit["displayId"]
                author = commit["author"]["name"]
                message = (commit.get("message") or "").split("\n")[0][:100]

                lines.append(f"### r{rev} by {author}")
                lines.append(f"> {message}")
                lines.append("")

                # 调用 SVN 获取 diff
                try:
                    result = subprocess.run(
                        ["svn", "--non-interactive",
                         "--trust-server-cert-failures=unknown-ca,cn-mismatch,expired,not-yet-valid,other",
                         "--username", svn_user, "--password", svn_pass,
                         "diff", "-c", rev, svn_url],
                        capture_output=True, text=False, timeout=60,
                        env={**os.environ, "NO_PROXY": "*"}
                    )

                    if result.returncode != 0:
                        lines.append(f"*SVN diff 失败: {result.stderr.decode('utf-8', errors='ignore')[:200]}*")
                        continue

                    diff_text = result.stdout.decode('utf-8', errors='ignore')
                    # 按文件分割
                    file_diffs = diff_text.split("Index: ")
                    shown = 0

                    for fd in file_diffs:
                        if not fd.strip():
                            continue
                        if shown >= max_files:
                            remaining = len(file_diffs) - 1 - max_files
                            if remaining > 0:
                                lines.append(f"\n*... 还有 {remaining} 个文件*")
                            break

                        # 提取文件路径
                        path_line = fd.split("\n")[0].strip()
                        # 截断 diff，每个文件最多显示 80 行
                        diff_lines = fd.split("\n")
                        header = diff_lines[:3]
                        content = diff_lines[3:83]

                        lines.append(f"#### `{path_line}`")
                        lines.append("```diff")
                        lines.extend(content)
                        lines.append("```")
                        lines.append("")
                        shown += 1

                except subprocess.TimeoutExpired:
                    lines.append("*SVN diff 超时*")
                except FileNotFoundError:
                    lines.append("*SVN 命令不可用 (需安装 SVN 客户端)*")
                    break

        return "\n".join(lines)

    except Exception as e:
        return f"查询失败: {e}"


# ── 启动 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
