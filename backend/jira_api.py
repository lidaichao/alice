"""
Jira API 查询模块
封装 Jira REST API 调用，提供本周未完成任务查询
"""

import base64
import os
import requests
from datetime import datetime, timedelta
from typing import Optional


class JiraClient:
    """Jira REST API 客户端"""

    def __init__(self, base_url: str, email: str, password: str,
                 session_cookie: str = None, pat_token: str = None):
        """
        初始化 Jira 客户端

        Args:
            base_url: Jira 服务地址
            email: 登录用户名
            password: 登录密码
            session_cookie: 可选，JIRASESSIONID cookie（会过期）
            pat_token: 可选，Personal Access Token（永久有效，推荐）
        """
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/rest/api/2"
        self.email = email
        self.password = password

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        # 内网Jira，不走代理
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}
        # 连接池配置：防 Jira 服务端主动关闭连接导致 -32000
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5,
            pool_maxsize=5,
            max_retries=1,
            pool_block=False,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        # Keep-Alive 相关：确保 HTTP/1.1 连接复用
        self.session.headers["Connection"] = "keep-alive"

        # 保存认证参数以便重建 session
        self._email = email
        self._password = password
        self._session_cookie = session_cookie
        self._pat_token = pat_token

        # 认证方式优先级: PAT > Session Cookie > Basic Auth
        if pat_token:
            self.session.headers["Authorization"] = f"Bearer {pat_token}"
            self._auth_method = "pat"
        elif session_cookie:
            self.session.cookies.set("JIRASESSIONID", session_cookie, domain="ctjira1.lmdgame.com")
            self._auth_method = "cookie"
        else:
            # 尝试 Basic Auth (可能被CAPTCHA拦截)
            auth_str = base64.b64encode(f"{email}:{password}".encode()).decode()
            self.session.headers["Authorization"] = f"Basic {auth_str}"
            self._auth_method = "basic"

        # 请求计数器，用于触发周期性 session 重建
        self._request_count = 0
        self._session_rebuild_interval = 100  # 每 100 次请求重建一次 session

    def _rebuild_session(self):
        """重建 HTTP session，解决 Jira 服务端关闭长连接导致的 ConnectionError"""
        old_session = self.session
        try:
            old_session.close()
        except Exception:
            pass

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}
        self.session.headers["Connection"] = "keep-alive"
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5, pool_maxsize=5, max_retries=1, pool_block=False
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # 恢复认证
        if self._pat_token:
            self.session.headers["Authorization"] = f"Bearer {self._pat_token}"
        elif self._session_cookie:
            self.session.cookies.set("JIRASESSIONID", self._session_cookie,
                                      domain="ctjira1.lmdgame.com")
        else:
            auth_str = base64.b64encode(
                f"{self._email}:{self._password}".encode()
            ).decode()
            self.session.headers["Authorization"] = f"Basic {auth_str}"

        self._request_count = 0

    RETRYABLE_ERRORS = (
        "Connection aborted",
        "RemoteDisconnected",
        "Connection reset by peer",
        "Connection refused",
        "Read timed out",
        "ReadTimeout",
        "('Connection aborted.'",
    )

    def _request(self, method: str, endpoint: str, params: dict = None,
                 json_data: dict = None, timeout: int = 30, user_pat: str = None,
                 retry_on_connect: bool = True) -> requests.Response:
        """
        统一请求方法 — 支持动态 PAT 注入 + 连接断开自动重试
        
        优先级: 参数 user_pat > 初始化时的全局 PAT
        用于 2.3 Jira 鉴权隔离：每个用户用自己的 PAT
        """
        headers = {}
        if user_pat:
            headers["Authorization"] = f"Bearer {user_pat}"
        # 否则使用 session 中已有的认证

        max_retries = 2 if retry_on_connect else 1
        last_error = None

        for attempt in range(max_retries):
            try:
                # 定期重建 session 防止长连接过期
                self._request_count += 1
                if self._request_count >= self._session_rebuild_interval:
                    self._rebuild_session()

                return self.session.request(
                    method=method,
                    url=f"{self.api_url}{endpoint}",
                    params=params,
                    json=json_data,
                    headers=headers,
                    timeout=timeout,
                )
            except (requests.ConnectionError, requests.exceptions.ConnectionError) as e:
                last_error = e
                err_str = str(e)
                is_retryable = any(tag in err_str for tag in self.RETRYABLE_ERRORS)
                if is_retryable and attempt < max_retries - 1:
                    import time as _time
                    _time.sleep(0.5)
                    self._rebuild_session()
                    continue
                raise
            except requests.Timeout as e:
                last_error = e
                if attempt < max_retries - 1:
                    import time as _time
                    _time.sleep(0.5)
                    continue
                raise

        raise last_error

    def jira_get(self, endpoint: str, params: dict = None, timeout: int = 30, user_pat: str = None):
        """便捷 GET 请求 — 支持动态 PAT，自动处理 URL 前缀"""
        if endpoint.startswith("http"):
            url = endpoint.replace(self.api_url + "/", "/").replace(self.api_url, "/")
            if not url.startswith("/"): url = "/" + url
        else:
            url = endpoint
        return self._request("GET", url, params=params, timeout=timeout, user_pat=user_pat)
    
    def jira_post(self, endpoint: str, json_data: dict = None, timeout: int = 30, user_pat: str = None):
        """便捷 POST 请求 — 支持动态 PAT，自动处理 URL 前缀"""
        if endpoint.startswith("http"):
            url = endpoint.replace(self.api_url + "/", "/").replace(self.api_url, "/")
            if not url.startswith("/"): url = "/" + url
        else:
            url = endpoint
        return self._request("POST", url, json_data=json_data, timeout=timeout, user_pat=user_pat)

    def jira_put(self, endpoint: str, json_data: dict = None, timeout: int = 30, user_pat: str = None):
        """便捷 PUT 请求 — 支持动态 PAT"""
        if endpoint.startswith("http"):
            url = endpoint.replace(self.api_url + "/", "/").replace(self.api_url, "/")
            if not url.startswith("/"):
                url = "/" + url
        else:
            url = endpoint
        return self._request("PUT", url, json_data=json_data, timeout=timeout, user_pat=user_pat)

    @staticmethod
    def draft_to_fields(draft: dict, default_issue_type: str = "Task", skip_labels: bool = False) -> dict:
        """将确认卡草稿转为 Jira REST fields（对齐 Baize draftToJiraFields）"""
        project_key = (draft.get("projectKey") or "").strip()
        if not project_key:
            raise ValueError("Jira 项目 Key 不能为空。")
        summary = (draft.get("summary") or "").strip()
        if not summary:
            raise ValueError("Issue 标题不能为空。")
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "description": draft.get("description") or "",
            "issuetype": (
                {"id": draft["issueTypeId"]}
                if draft.get("issueTypeId")
                else {"name": draft.get("issueType") or default_issue_type}
            ),
        }
        assignee = draft.get("assigneeName") or draft.get("assigneeAccountId") or draft.get("assignee")
        if assignee:
            if draft.get("assigneeAccountId"):
                fields["assignee"] = {"accountId": draft["assigneeAccountId"]}
            else:
                fields["assignee"] = {"name": assignee}
        if draft.get("priority"):
            fields["priority"] = {"name": draft["priority"]}
        if not skip_labels and draft.get("labels"):
            labels = draft["labels"]
            if isinstance(labels, list) and labels:
                fields["labels"] = labels
        return fields

    def create_issue(self, fields: dict, user_pat: str = None) -> dict:
        """POST /rest/api/2/issue"""
        r = self._request("POST", "/issue", json_data={"fields": fields}, timeout=30, user_pat=user_pat)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"创建 Issue 失败 (HTTP {r.status_code}): {r.text[:300]}")
        data = r.json()
        return {"id": data.get("id"), "key": data.get("key"), "self": data.get("self")}

    def create_issue_from_draft(self, draft: dict, user_pat: str = None,
                                default_issue_type: str = "Task", skip_labels: bool = False) -> dict:
        fields = self.draft_to_fields(draft, default_issue_type=default_issue_type, skip_labels=skip_labels)
        created = self.create_issue(fields, user_pat=user_pat)
        created["summary"] = draft.get("summary", "")
        return created

    def add_comment(self, issue_key: str, body: str, user_pat: str = None) -> dict:
        """POST /rest/api/2/issue/{key}/comment"""
        key = (issue_key or "").strip()
        if not key:
            raise ValueError("issue_key 不能为空")
        r = self._request(
            "POST", f"/issue/{key}/comment",
            json_data={"body": body or ""},
            timeout=30,
            user_pat=user_pat,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"添加评论失败 (HTTP {r.status_code}): {r.text[:300]}")
        data = r.json()
        return {"id": data.get("id"), "issue_key": key}

    def list_transitions(self, issue_key: str, user_pat: str = None) -> list:
        r = self._request("GET", f"/issue/{issue_key}/transitions", timeout=15, user_pat=user_pat)
        if r.status_code != 200:
            raise RuntimeError(f"查询流转失败 (HTTP {r.status_code}): {r.text[:200]}")
        return r.json().get("transitions", [])

    def transition_issue(self, issue_key: str, user_pat: str = None,
                         transition_id: str = None, transition_name: str = None) -> dict:
        body = {}
        if transition_id:
            body["transition"] = {"id": str(transition_id)}
        elif transition_name:
            body["transition"] = {"name": transition_name}
        else:
            raise ValueError("需要 transition_id 或 transition_name")
        r = self._request(
            "POST", f"/issue/{issue_key}/transitions",
            json_data=body, timeout=30, user_pat=user_pat,
        )
        if r.status_code not in (200, 204):
            raise RuntimeError(f"状态流转失败 (HTTP {r.status_code}): {r.text[:300]}")
        return {"issue_key": issue_key, "transition": body["transition"]}

    def update_issue_fields(self, issue_key: str, fields: dict, user_pat: str = None) -> dict:
        r = self.jira_put(f"/issue/{issue_key}", json_data={"fields": fields or {}}, user_pat=user_pat)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"更新 Issue 失败 (HTTP {r.status_code}): {r.text[:300]}")
        return {"issue_key": issue_key}

    def test_connection(self, user_pat: str = None) -> dict:
        """测试连接，返回当前用户信息"""
        try:
            r = self._request("GET", "/myself", timeout=15, user_pat=user_pat)
            if r.status_code == 200:
                user = r.json()
                return {
                    "success": True,
                    "display_name": user.get("displayName", "Unknown"),
                    "email": user.get("emailAddress", "Unknown"),
                }
            return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    # 完成状态 — 动态发现（从 Jira 项目配置中获取，缓存 1 小时）
    # 环境变量 DONE_STATUS_KEYWORDS 可用于覆盖关键词（逗号分隔）
    # 默认关键词匹配中英文常见完成态
    _done_statuses_cache = None   # (project_key, timestamp, statuses)
    _done_statuses_ttl = 3600     # 1 小时缓存

    def _discover_done_statuses(self, project_key: str = "CT") -> list:
        """
        AI Decision First: 动态从 Jira API 获取项目的完成状态列表。
        避免硬编码，换项目自动适配。
        缓存 1 小时。
        """
        import time as _time
        now = _time.time()
        cache = self._done_statuses_cache
        if cache and cache[0] == project_key and now - cache[1] < self._done_statuses_ttl:
            return cache[2]

        # 关键词匹配：中英文常见完成/关闭/搁置/拒绝状态
        custom_keywords = os.getenv("DONE_STATUS_KEYWORDS", "")
        if custom_keywords:
            keywords = [k.strip() for k in custom_keywords.split(",") if k.strip()]
        else:
            keywords = ["完成", "关闭", "搁置", "解决", "发布", "拒绝", "取消",
                        "done", "closed", "resolved", "released", "rejected", "cancelled"]

        try:
            r = self._request("GET", f"/project/{project_key}/statuses", timeout=15)
            if r.status_code == 200:
                discovered = []
                for item in r.json():
                    for s in item.get("statuses", []):
                        name = s["name"]
                        if any(kw.lower() in name.lower() for kw in keywords):
                            if name not in discovered:
                                discovered.append(name)
                self._done_statuses_cache = (project_key, now, discovered)
                return discovered
        except Exception:
            pass

        # 回退：用最简单的兜底（不含任何项目特定状态名）
        fallback = ["完成", "已解决", "可发布"]
        self._done_statuses_cache = (project_key, now, fallback)
        return fallback

    @property
    def DONE_STATUSES(self):
        """动态获取完成状态（带缓存）"""
        statuses = self._discover_done_statuses()
        return [f'"{s}"' for s in statuses]

    def get_this_week_unfinished_issues(self, assignee: str = "currentUser()",
                                         max_results: int = 50, user_pat: str = None) -> dict:
        """
        获取本周未完成的任务

        Args:
            assignee: 经办人，默认当前用户
            max_results: 最大返回数量
        """
        done = ", ".join(self.DONE_STATUSES)
        jql = (
            f"assignee = {assignee} "
            f"AND status NOT IN ({done}) "
            f"ORDER BY priority DESC, updated DESC"
        )

        return self._search_issues(jql, max_results, user_pat=user_pat)

    def get_my_open_issues(self, max_results: int = 50, user_pat: str = None) -> dict:
        """获取当前用户所有未完成任务"""
        done = ", ".join(self.DONE_STATUSES)
        jql = (
            f"assignee = currentUser() "
            f"AND status NOT IN ({done}) "
            f"ORDER BY priority DESC, updated DESC"
        )
        return self._search_issues(jql, max_results, user_pat=user_pat)

    def search_issues(self, jql: str, max_results: int = 50, user_pat: str = None) -> dict:
        """使用自定义 JQL 查询"""
        return self._search_issues(jql, max_results, user_pat=user_pat)

    def _search_issues(self, jql: str, max_results: int = 50, user_pat: str = None) -> dict:
        """执行 JQL 查询"""
        try:
            r = self._request("GET", "/search",
                params={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": "summary,status,priority,assignee,reporter,created,updated,"
                              "duedate,issuetype,project,timeoriginalestimate,timeestimate,timespent",
                },
                timeout=30,
                user_pat=user_pat,
            )

            if r.status_code != 200:
                return {
                    "success": False,
                    "error": f"Jira API error: HTTP {r.status_code} - {r.text[:300]}",
                    "jql": jql,
                }

            data = r.json()
            issues = []
            for item in data.get("issues", []):
                fields = item.get("fields", {})
                status = fields.get("status", {})
                priority = fields.get("priority", {})
                issue_type = fields.get("issuetype", {})
                project = fields.get("project", {})
                assignee = fields.get("assignee", {})

                issues.append({
                    "key": item.get("key"),
                    "summary": fields.get("summary", ""),
                    "status": status.get("name", "Unknown"),
                    "priority": priority.get("name", "None") if priority else "None",
                    "type": issue_type.get("name", ""),
                    "project": project.get("name", ""),
                    "assignee": assignee.get("displayName", "Unassigned") if assignee else "Unassigned",
                    "created": fields.get("created", ""),
                    "updated": fields.get("updated", ""),
                    "due_date": fields.get("duedate", ""),
                    "url": f"{self.base_url}/browse/{item.get('key')}",
                    # 时间估算 (秒)
                    "original_estimate": fields.get("timeoriginalestimate"),
                    "remaining_estimate": fields.get("timeestimate"),
                    "time_spent": fields.get("timespent"),
                })

            return {
                "success": True,
                "issues": issues,
                "total": data.get("total", 0),
                "jql": jql,
            }

        except requests.RequestException as e:
            return {"success": False, "error": f"Request failed: {e}", "jql": jql}

    def format_issues_for_wecom(self, issues: list, title: str = "本周未完成任务") -> str:
        """
        将 Jira 任务列表格式化为企业微信消息文本

        Args:
            issues: 任务列表
            title: 消息标题

        Returns:
            格式化的文本消息 (Markdown 格式)
        """
        if not issues:
            return f"## {title}\n\n暂无未完成任务"

        lines = [f"## {title}", f"共 {len(issues)} 个未完成任务：", ""]

        # 按优先级分组
        priority_order = {"Highest": 0, "High": 1, "Medium": 2, "Low": 3, "Lowest": 4}
        sorted_issues = sorted(
            issues,
            key=lambda x: priority_order.get(x.get("priority", ""), 99)
        )

        for i, issue in enumerate(sorted_issues, 1):
            priority_icon = {
                "Highest": "🔴", "High": "🟠", "Medium": "🟡",
                "Low": "🟢", "Lowest": "⚪"
            }.get(issue.get("priority", ""), "⚪")

            status = issue.get("status", "")
            summary = issue.get("summary", "")

            # 格式化时间估算
            time_str = ""
            remaining = issue.get("remaining_estimate")
            if remaining and remaining > 0:
                hours = remaining / 3600
                time_str = f" [预估{hours:.1f}h]"

            due_str = ""
            if issue.get("due_date"):
                due_str = f" 截止:{issue['due_date']}"

            lines.append(
                f"{i}. {priority_icon} **{issue['key']}** [{status}] {summary}{time_str}{due_str}"
            )
            lines.append(f"   📁 {issue.get('project', '')} | {issue.get('type', '')}")

        # 如果有截止日期临近的任务，特别标注
        today = datetime.now().date()
        urgent = []
        for issue in issues:
            if issue.get("due_date"):
                try:
                    due = datetime.strptime(issue["due_date"], "%Y-%m-%d").date()
                    days_left = (due - today).days
                    if days_left <= 2:
                        urgent.append((issue, days_left))
                except (ValueError, TypeError):
                    pass

        if urgent:
            lines.append("")
            lines.append("### ⚠️ 即将到期")
            for issue, days in urgent:
                label = "今天截止!" if days == 0 else f"{days}天后截止" if days > 0 else f"已超期{-days}天"
                lines.append(f"- **{issue['key']}**: {issue.get('summary', '')} ({label})")

        return "\n".join(lines)
