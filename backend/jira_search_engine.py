"""
Jira 结构化查询引擎 — 移植 Baize jira-search-service.js 语义（Python，无 Claude Code 依赖）。
用于提升 Jira 回答准确性：确定性 JQL + 预计算统计 + 用户解析。
"""
from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from jira_runtime_config import JiraRuntimeConfig, load_jira_runtime_config

logger = logging.getLogger("jira-search-engine")

ALLOWED_ORDER_FIELDS = frozenset(["updated", "created", "resolutiondate", "statuscategorychangedate"])
BLOCKED_STATUSES = frozenset(["Blocked", "阻塞", "暂停", "无法进行"])
DONE_STATUS_NAMES = frozenset(["done", "closed", "resolved", "完成", "已关闭", "已解决", "可发布"])
MAX_RECOVERY_ATTEMPTS = 3

ISSUE_KEY_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])")
PROJECT_KEY_RE = re.compile(r"(?:项目|project)\s*[:：]?\s*([A-Z][A-Z0-9]{1,15})\b", re.I)

# 禁止误识别为「人名」的片段（动词/泛指，非 Baize 用户解析）
_ASSIGNEE_STOPWORDS = frozenset({
    "帮我", "帮", "查", "看", "统计", "汇总", "一下", "请", "写", "一份", "项目",
    "哪些", "进行", "有关", "没有", "匹配", "今天", "任务", "列表", "需要", "完成",
    "什么", "怎么", "属性", "设计", "本周", "这周", "工单", "告诉我", "有哪些",
    "未", "的", "一个", "新的", "有关", "属性有", "球员", "系统", "/jira",
    "我查", "查一", "一下", "些进", "行中", "进行", "属性有", "没有匹",
})

_STATUS_KEYWORDS = {
    "进行中": ["进行中", "In Progress"],
    "待办": ["待办", "To Do", "Open"],
    "完成": ["完成", "Done", "Closed"],
}


@dataclass
class JiraSearchQuery:
    project_key: str = ""
    assignees: list = field(default_factory=list)
    assignee_is_current_user: bool = False
    statuses: list = field(default_factory=list)
    issue_types: list = field(default_factory=list)
    labels: list = field(default_factory=list)
    text: str = ""
    jql: str = ""
    updated_after: str = ""
    updated_before: str = ""
    unresolved_only: bool = False
    max_results: int = 50
    order_by: str = "updated DESC"

    def to_dict(self) -> dict:
        return asdict(self)


def _read_str(value) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def quote_jql_value(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def normalize_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(normalize_list(item))
        return out
    s = _read_str(value)
    if not s:
        return []
    parts = re.split(r"[，,、；;]|\s+和\s+|和", s)
    return [p.strip() for p in parts if p and p.strip()]


def quote_jql_identifier(name: str) -> Optional[str]:
    text = _read_str(name)
    if not text:
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9_]*$", text):
        return text
    return quote_jql_value(text)


def build_in_clause(field_name: str, values: list) -> Optional[str]:
    field = quote_jql_identifier(field_name)
    normalized = list(dict.fromkeys(normalize_list(values)))
    if not field or not normalized:
        return None
    if len(normalized) == 1:
        return f"{field} = {quote_jql_value(normalized[0])}"
    return f"{field} in ({', '.join(quote_jql_value(v) for v in normalized)})"


def normalize_order_by(value: str) -> str:
    text = _read_str(value) or "updated DESC"
    normalized = []
    for part in text.split(","):
        part = part.strip()
        m = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*(ASC|DESC)?$", part, re.I)
        if not m:
            continue
        fld = m.group(1).lower()
        if fld not in ALLOWED_ORDER_FIELDS:
            continue
        normalized.append(f"{fld} {(m.group(2) or 'DESC').upper()}")
    return ", ".join(normalized) if normalized else "updated DESC"


def resolve_jira_users(jira_client, term: str, user_pat: str = "") -> list:
    term = _read_str(term)
    if not term:
        return []
    try:
        r = jira_client.jira_get(
            "/user/search",
            params={"username": term, "maxResults": 10},
            timeout=10,
            user_pat=user_pat or None,
        )
        if r.status_code != 200:
            return []
        users = r.json() if hasattr(r, "json") else []
        if not isinstance(users, list):
            return []
        return [u for u in users if u.get("active", True) is not False][:10]
    except Exception as e:
        logger.warning(f"[JiraSearch] user search failed for {term}: {e}")
        return []


def get_jql_user_names(users: list, fallback: list) -> list:
    names = []
    for u in users:
        if u.get("name"):
            names.append(u["name"])
    if names:
        return list(dict.fromkeys(names))
    return list(dict.fromkeys(normalize_list(fallback)))


def _is_assignee_field_name(field_name: str) -> bool:
    """经办人始终单独查；额外人物字段列表里跳过重复项。"""
    n = (field_name or "").strip().lower()
    return n in ("assignee", "经办人")


def build_assignee_or_owner_clause(
    query: JiraSearchQuery,
    config: JiraRuntimeConfig,
    resolved_users: list,
) -> Optional[str]:
    if query.assignee_is_current_user:
        return "assignee = currentUser()"
    people = normalize_list(query.assignees)
    if not people:
        return None
    user_names = get_jql_user_names(resolved_users, people)
    clauses = [build_in_clause("assignee", user_names)]
    proj = config.get_project(query.project_key)
    owner_fields = proj.owner_fields or config.owner_field_candidates
    seen = {"assignee"}
    for field_name in owner_fields:
        if not field_name or _is_assignee_field_name(field_name):
            continue
        key = field_name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        c = build_in_clause(field_name, user_names)
        if c:
            clauses.append(c)
    effective = [c for c in clauses if c]
    if not effective:
        return None
    return f"({' OR '.join(effective)})" if len(effective) > 1 else effective[0]


def build_resolved_jql(
    query: JiraSearchQuery,
    config: JiraRuntimeConfig,
    resolved_users: Optional[list] = None,
) -> dict:
    """
    返回 { jql, requires_user_input?, supplement?, resolved_users }
    """
    resolved_users = resolved_users or []
    explicit = _read_str(query.jql)
    if explicit:
        jql = explicit if re.search(r"\bORDER\s+BY\b", explicit, re.I) else f"{explicit} ORDER BY {normalize_order_by(query.order_by)}"
        return {"jql": jql, "resolved_users": [], "requires_user_input": False}

    clauses = []
    pk = _read_str(query.project_key) or (config.default_project_keys[0] if config.default_project_keys else "")
    if pk and not ISSUE_KEY_RE.fullmatch(pk):
        clauses.append(f"project = {quote_jql_value(pk)}")

    assignee_clause = build_assignee_or_owner_clause(query, config, resolved_users)
    if assignee_clause:
        clauses.append(assignee_clause)

    if query.unresolved_only:
        done_names = config.done_status_keywords or list(DONE_STATUS_NAMES)
        quoted = ", ".join(quote_jql_value(s) for s in done_names[:20])
        if quoted:
            clauses.append(f"status NOT IN ({quoted})")

    status_clause = build_in_clause("status", query.statuses)
    if status_clause:
        clauses.append(status_clause)

    type_clause = build_in_clause("issuetype", query.issue_types)
    if type_clause:
        clauses.append(type_clause)

    for label in normalize_list(query.labels):
        clauses.append(f"labels = {quote_jql_value(label)}")

    if _read_str(query.updated_after):
        clauses.append(f"updated >= {quote_jql_value(query.updated_after)}")
    if _read_str(query.updated_before):
        clauses.append(f"updated <= {quote_jql_value(query.updated_before)}")

    text = _read_str(query.text)
    if text and not assignee_clause:
        terms = []
        if re.search(r"[\u4e00-\u9fff]", text) and len(text) >= 4:
            for i in range(len(text) - 1):
                bg = text[i : i + 2]
                if bg not in terms:
                    terms.append(bg)
        if not terms:
            terms = [text]
        text_conds = " OR ".join(
            f'summary ~ {quote_jql_value(t)} OR description ~ {quote_jql_value(t)}' for t in terms[:8]
        )
        clauses.append(f"({text_conds})")

    if not clauses:
        raise ValueError("请至少提供一个 Jira 查询条件。")

    jql = f"{' AND '.join(clauses)} ORDER BY {normalize_order_by(query.order_by)}"
    return {
        "jql": jql,
        "resolved_users": get_jql_user_names(resolved_users, query.assignees),
        "requires_user_input": False,
    }


def simplify_issue(issue: dict) -> dict:
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}
    assignee = fields.get("assignee") or {}
    itype = fields.get("issuetype") or {}
    project = fields.get("project") or {}
    priority = fields.get("priority") or {}
    return {
        "key": issue.get("key", ""),
        "id": issue.get("id", ""),
        "summary": fields.get("summary", ""),
        "status": status.get("name", ""),
        "assignee": assignee.get("displayName") or assignee.get("name"),
        "issueType": itype.get("name", ""),
        "project": project.get("key", ""),
        "priority": priority.get("name", ""),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "duedate": fields.get("duedate"),
    }


def analyze_issues(issues: list) -> dict:
    by_status = {}
    by_assignee = {}
    for issue in issues:
        st = issue.get("status") or "未设置状态"
        asn = issue.get("assignee") or "未分配"
        by_status[st] = by_status.get(st, 0) + 1
        by_assignee[asn] = by_assignee.get(asn, 0) + 1

    blocked = [i for i in issues if i.get("status") in BLOCKED_STATUSES]
    done_count = sum(
        1 for i in issues
        if (i.get("status") or "").lower() in {s.lower() for s in DONE_STATUS_NAMES}
    )
    total = len(issues)
    completion_rate = round((done_count / total) * 100) if total else 0
    summary = (
        "没有找到符合条件的 Jira 任务。"
        if total == 0
        else f"共找到 {total} 个任务，完成率约 {completion_rate}%。"
        + (f"其中 {len(blocked)} 个处于阻塞状态。" if blocked else "当前没有识别到阻塞状态任务。")
    )
    return {
        "total": total,
        "byStatus": by_status,
        "byAssignee": by_assignee,
        "completionRate": completion_rate,
        "blockedKeys": [i.get("key") for i in blocked if i.get("key")],
        "summary": summary,
    }


def build_empty_analysis(message: str = "") -> dict:
    base = analyze_issues([])
    base["summary"] = message or "没有找到符合条件的 Jira 任务。"
    return base


def _week_date_range_label(user_text: str) -> tuple:
    """返回 (updated_after ISO date or '', label)"""
    import datetime as dt
    now = dt.datetime.now()
    if re.search(r"本周|这周|当周", user_text):
        start = now - dt.timedelta(days=now.weekday())
        return start.strftime("%Y-%m-%d"), "本周"
    if re.search(r"今天|当日", user_text):
        return now.strftime("%Y-%m-%d"), "今天"
    return "", ""


def _normalize_person_name(raw: str) -> Optional[str]:
    """校验并规范化中文人名候选"""
    name = (raw or "").strip()
    if not name or len(name) < 2 or len(name) > 4:
        return None
    if name in _ASSIGNEE_STOPWORDS:
        return None
    if any(sw in name for sw in _ASSIGNEE_STOPWORDS if len(sw) >= 2):
        return None
    if name.endswith("的"):
        name = name[:-1]
    if name in _ASSIGNEE_STOPWORDS or len(name) < 2:
        return None
    return name


def _extract_assignee_names(text: str) -> list:
    """从问句提取经办人/负责人（避免把「查一下」当人名）"""
    if re.search(r"当前用户|我(?:的)?(?:任务|工单)|本人|assignee\s*=\s*currentUser", text, re.I):
        return ["__current_user__"]

    patterns = [
        r"([\u4e00-\u9fa5]{2,3})的(?:任务|工单|issue|工作|列表)",
        r"(?:负责人|经办人|分配(?:给)?)[是为：:\s]*([\u4e00-\u9fa5]{2,3})",
        r"(?:统计|查询|查|看|找)(?:一下)?\s*([\u4e00-\u9fa5]{2,3})(?:\s*(?:本周|今天|的|负责|未完成))",
        r"(?:^|[，,。\s])([\u4e00-\u9fa5]{2,3})(?:\s*(?:本周|今天).{0,6}(?:任务|未完成|工单))",
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            n = _normalize_person_name(m.group(1))
            if n and n not in found:
                found.append(n)
    return found


def _extract_keyword_text(text: str) -> str:
    m_rel = re.search(
        r"(?:和|与)\s*([^\s，,。]+?)\s*有关(?:的)?\s*(?:Jira\s*)?(?:任务|issue|单|需求)",
        text,
        re.I,
    )
    if m_rel:
        kw = m_rel.group(1).strip()
        if 2 <= len(kw) <= 60:
            return kw
    kw_m = re.search(
        r"(?:关于|包含|涉及)\s*[「\"']?([^」\"'\n]+?)[」\"']?\s*(?:有关|相关)?(?:的)?(?:\s*Jira\s*)?(?:任务|issue|单|需求)",
        text,
        re.I,
    )
    if kw_m:
        kw = kw_m.group(1).strip()
        if 2 <= len(kw) <= 60 and not _normalize_person_name(kw):
            return kw
    m2 = re.search(
        r"(?:找|搜索|查找)(?:与|和)?\s*(.+?)(?:相关|有关)?(?:的)?(?:\s*Jira\s*)?(?:任务|issue|单)\b",
        text,
        re.I,
    )
    if m2:
        kw = m2.group(1).strip()
        kw = re.sub(r"^(一下|下|jira)\s*", "", kw, flags=re.I)
        if 2 <= len(kw) <= 40:
            return kw
    return ""


def parse_query_from_natural_language(user_text: str, config: JiraRuntimeConfig) -> JiraSearchQuery:
    """规则槽位：从自然语言提取结构化查询（不依赖 LLM 生成 JQL）"""
    text = (user_text or "").strip()

    # 消歧卡回填：JIRA_USER:zhangsan 张三
    m_user_hint = re.search(r"JIRA_USER:([^\s]+)(?:\s+([\u4e00-\u9fa5]{2,4}))?", text, re.I)
    if m_user_hint:
        text = f"统计 {m_user_hint.group(2) or m_user_hint.group(1)} 本周未完成任务"

    q = JiraSearchQuery(max_results=config.max_search_results)

    m_proj = PROJECT_KEY_RE.search(text)
    if m_proj:
        q.project_key = m_proj.group(1).upper()
    else:
        for pk in config.default_project_keys:
            if pk and re.search(rf"\b{re.escape(pk)}\b", text, re.I):
                q.project_key = pk.upper()
                break
        if not q.project_key and config.default_project_keys:
            q.project_key = config.default_project_keys[0]

    if re.search(r"未完成|待办|未关闭|open|not\s+done", text, re.I):
        q.unresolved_only = True
    _status_scan = re.sub(r"需要完成|待完成|要完成", " ", text)
    for label, names in _STATUS_KEYWORDS.items():
        if label in _status_scan:
            q.statuses.extend(names)
            if label == "进行中":
                q.unresolved_only = False

    if re.search(r"\bbug\b|缺陷", text, re.I):
        q.issue_types = ["Bug"]

    after, _ = _week_date_range_label(text)
    if after:
        q.updated_after = after

    names = _extract_assignee_names(text)
    if names == ["__current_user__"]:
        q.assignee_is_current_user = True
        q.assignees = []
    elif names:
        q.assignees = names

    kw = _extract_keyword_text(text)
    if kw:
        q.text = kw
        q.assignees = []  # 关键词搜索不与经办人 OR 混用，避免误 JQL

    if re.search(r"需要完成|待办|本周.*任务|本周.*哪些", text) and not q.assignees:
        if re.search(r"我|本人|当前用户", text) or re.search(
            r"本周.*(?:需要|要).*(?:完成|办)|有哪些.*任务", text
        ):
            q.assignee_is_current_user = True
        q.unresolved_only = True

    return normalize_search_query(q, text)


def normalize_search_query(query: JiraSearchQuery, user_text: str = "") -> JiraSearchQuery:
    """对齐 Baize normalizeSearchInput：bug 标签 → BUG 项目等。"""
    text = user_text or ""
    labels = normalize_list(query.labels)
    if any(re.fullmatch(r"bug", lb, re.I) for lb in labels) or (
        re.search(r"\bBUG\s*项目\b", text, re.I) and not query.project_key
    ):
        q = JiraSearchQuery(**query.to_dict())
        q.project_key = "BUG"
        q.labels = [lb for lb in labels if not re.fullmatch(r"bug", lb, re.I)]
        if re.search(r"\bbug\b|缺陷", text, re.I) and not q.issue_types:
            q.issue_types = ["Bug"]
        return q
    return query


def should_force_jira_structured_read(
    user_text: str,
    intent_route: str = "",
    intent_label: str = "",
) -> bool:
    """是否必须走结构化读直通车（含 intent_router / classify 命中）"""
    keys = ISSUE_KEY_RE.findall(user_text or "")
    if len(keys) == 1 and re.search(
        r"详情|内容|描述|评论|什么情况|怎么样|是谁|备注|改成|改为|流转|完成|关闭",
        user_text or "",
    ):
        return False
    if is_jira_structured_read_query(user_text, intent_route):
        return True
    if intent_route == "jira_query":
        return True
    if intent_label in ("JIRA_STRUCTURED_SEARCH", "JIRA_KEYWORD_SEARCH"):
        return True
    if re.search(r"本周.*(?:任务|待办|需要完成)|需要完成.*任务|有哪些.*任务", user_text or "", re.I):
        return True
    return False


def is_jira_structured_read_query(user_text: str, intent_route: str = "") -> bool:
    """是否应走 Jira 读直通车（非代码/非写/非纯闲聊）"""
    if not user_text or not user_text.strip():
        return False
    if intent_route == "jira_write":
        return False
    if re.search(
        r"提交|commit|diff|代码|svn|fisheye|变更了哪些文件|改了什么代码",
        user_text,
        re.I,
    ):
        return False
    if re.search(
        r"创建|新建|添加.*任务|批量导入|改成完成|删除.*issue|更新.*jira",
        user_text,
        re.I,
    ):
        return False
    if ISSUE_KEY_RE.search(user_text) and re.search(
        r"详情|内容|描述|评论|状态|什么情况|怎么样|是谁",
        user_text,
    ):
        return False
    if re.search(
        r"jira|任务|issue|bug|需求|story|工单|周报|日报|月报|迭代|sprint|经办|负责人|未完成|待办",
        user_text,
        re.I,
    ):
        return True
    if ISSUE_KEY_RE.search(user_text) and not re.search(r"提交|commit|diff|代码", user_text, re.I):
        return True
    return intent_route == "jira_query"


def parse_jira_transition_target(user_text: str) -> str:
    """从自然语言提取目标状态关键词（用于匹配 transition）"""
    text = user_text or ""
    for label, hint in (
        ("完成", r"完成|done|resolved|解决|关闭"),
        ("关闭", r"关闭|closed"),
        ("进行中", r"进行中|in\s*progress"),
        ("待办", r"待办|to\s*do|open"),
    ):
        if re.search(hint, text, re.I):
            return label
    return "完成"


def is_jira_transition_write_request(user_text: str, intent_route: str = "") -> bool:
    if intent_route != "jira_write":
        return False
    if not ISSUE_KEY_RE.search(user_text or ""):
        return False
    return bool(
        re.search(
            r"改成|改为|更新.*状态|流转|transition|完成|关闭|resolved|进行中|待办",
            user_text or "",
            re.I,
        )
    )


def validate_recovery_jql(jql: str, original: str = "") -> dict:
    text = _read_str(jql)
    if not text:
        return {"valid": False, "reason": "JQL 为空"}
    if len(text) > 2000:
        return {"valid": False, "reason": "JQL 过长"}
    if re.search(r"\b(DELETE|UPDATE|INSERT|DROP|TRUNCATE|ALTER|CREATE)\b", text, re.I):
        return {"valid": False, "reason": "含破坏性关键词"}
    patterns = [
        r"project\s*[=!~]",
        r"assignee\s*[=!~]",
        r"任务负责人",
        r"status\s*[=!~]|status\s+in\b",
        r"issuetype\s*[=!~]|issuetype\s+in\b",
        r"summary\s*~",
        r"updated\s*[<>=]",
        r"key\s*[=!~]",
    ]
    if not any(re.search(p, text, re.I) for p in patterns):
        return {"valid": False, "reason": "JQL 缺少有效约束"}
    normalized = text if re.search(r"\bORDER\s+BY\b", text, re.I) else f"{text} ORDER BY updated DESC"
    if original and normalized.strip() == original.strip():
        return {"valid": False, "reason": "JQL 未改写"}
    return {"valid": True, "jql": normalized}


def classify_jira_search_error(error_msg: str, http_status: int = 0) -> str:
    from jira_search_recovery import classify_jira_search_error as _c
    return _c(error_msg, http_status)


def recover_jql_on_error(jql: str, error_msg: str, query: JiraSearchQuery, config: JiraRuntimeConfig) -> Optional[str]:
    """规则化 JQL 恢复（Phase 1b 基础版）"""
    err = (error_msg or "").lower()
    if "labels" in err and query.labels:
        q2 = JiraSearchQuery(**query.to_dict())
        q2.labels = []
        try:
            return build_resolved_jql(q2, config).get("jql")
        except ValueError:
            pass
    if "cannot be set" in err or "field" in err:
        m = re.search(r"field\s+'([^']+)'", error_msg, re.I)
        if m:
            bad = m.group(1)
            if bad in (query.to_dict().get("text") or ""):
                q2 = JiraSearchQuery(**query.to_dict())
                q2.text = ""
                try:
                    return build_resolved_jql(q2, config).get("jql")
                except ValueError:
                    pass
    if "permission" in err or "403" in err:
        return None
    return None


def search_and_analyze(
    jira_client,
    query: JiraSearchQuery,
    config: Optional[JiraRuntimeConfig] = None,
    user_pat: str = "",
    frontend_cfg: Optional[dict] = None,
    resolve_users: bool = True,
    user_question: str = "",
    api_key: str = "",
    http_post=None,
) -> dict:
    config = config or load_jira_runtime_config(frontend_cfg)
    user_resolution = []
    query = normalize_search_query(query, user_question)
    if not api_key:
        api_key = os.getenv("DEEPSEEK_KEY", "")
    use_llm_recovery = os.environ.get("JIRA_LLM_RECOVERY", "1").strip() not in ("0", "false", "no")

    if resolve_users and query.assignees:
        resolved_all = []
        for term in normalize_list(query.assignees):
            candidates = resolve_jira_users(jira_client, term, user_pat=user_pat)
            user_resolution.append({"term": term, "candidates": len(candidates)})
            if len(candidates) > 1:
                return {
                    "requires_user_input": True,
                    "jql": None,
                    "issues": [],
                    "total": 0,
                    "analysis": build_empty_analysis(f"需要确认「{term}」对应哪个 Jira 用户。"),
                    "supplement": {
                        "prompt": f"请选择 Jira 用户：{term}",
                        "choices": [
                            {"value": u.get("name") or u.get("key", ""), "label": u.get("displayName") or u.get("name", "")}
                            for u in candidates[:8]
                            if u.get("name") or u.get("key")
                        ],
                    },
                    "user_resolution": user_resolution,
                }
            resolved_all.extend(candidates)
        built = build_resolved_jql(query, config, resolved_users=resolved_all)
    else:
        built = build_resolved_jql(query, config)

    if built.get("requires_user_input"):
        return built

    jql = built["jql"]
    original_jql = jql
    recovery_history = []
    max_results = min(query.max_results or 50, config.max_search_results)

    for attempt in range(1, MAX_RECOVERY_ATTEMPTS + 2):
        try:
            r = jira_client.jira_get(
                "/search",
                params={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": "summary,status,assignee,issuetype,project,priority,created,updated,duedate,labels",
                },
                timeout=30,
                user_pat=user_pat or None,
            )
            if r.status_code != 200:
                raise RuntimeError(f"Jira HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            raw_issues = data.get("issues") or []
            issues = [simplify_issue(i) for i in raw_issues]
            result = {
                "jql": jql,
                "originalJql": original_jql if jql != original_jql else None,
                "resolved_users": built.get("resolved_users", []),
                "user_resolution": user_resolution,
                "total": data.get("total", len(issues)),
                "issues": issues,
                "analysis": analyze_issues(issues),
                "requires_user_input": False,
                "jira_lane": "structured_search",
            }
            if recovery_history:
                result["jira_search_recovery"] = {"status": "retry_succeeded", "history": recovery_history}
            logger.info(f"[JiraSearch] lane=structured_search jql={jql[:100]} count={result['total']}")
            return result
        except Exception as e:
            err_msg = str(e)
            http_status = 0
            m_st = re.search(r"HTTP\s+(\d+)", err_msg)
            if m_st:
                http_status = int(m_st.group(1))
            err_code = classify_jira_search_error(err_msg, http_status)
            recovery_history.append({
                "attempt": attempt, "jql": jql, "error": err_msg[:200], "error_code": err_code,
            })
            if attempt > MAX_RECOVERY_ATTEMPTS:
                break
            new_jql = recover_jql_on_error(jql, err_msg, query, config)
            if (not new_jql or new_jql == jql) and use_llm_recovery and err_code in (
                "JIRA_API_ERROR", "JIRA_REQUEST_TIMEOUT", "JIRA_INVALID_VALUE",
            ):
                try:
                    from jira_search_recovery import llm_analyze_jira_search_recovery
                    llm_rec = llm_analyze_jira_search_recovery(
                        user_question or "",
                        jql,
                        err_code,
                        err_msg,
                        config.default_project_keys,
                        api_key=api_key,
                        http_post=http_post,
                    )
                    if llm_rec:
                        recovery_history.append({"llm_recovery": llm_rec.get("status")})
                        if llm_rec.get("status") == "retry_available":
                            new_jql = (llm_rec.get("retry") or {}).get("jql")
                        elif llm_rec.get("status") == "needs_user_input":
                            sup = llm_rec.get("supplement") or {}
                            choices = sup.get("choices") or []
                            if not choices and sup.get("inputs"):
                                for inp in sup["inputs"]:
                                    if inp.get("type") == "select":
                                        choices = [
                                            {"value": o, "label": o}
                                            for o in (inp.get("options") or [])
                                        ]
                            return {
                                "requires_user_input": True,
                                "jql": jql,
                                "issues": [],
                                "total": 0,
                                "analysis": build_empty_analysis(llm_rec.get("summary", "")),
                                "supplement": {
                                    "prompt": sup.get("prompt", "请补充查询条件"),
                                    "choices": choices[:8],
                                },
                                "jira_search_recovery": llm_rec,
                                "user_resolution": user_resolution,
                                "jira_lane": "structured_search",
                            }
                        elif llm_rec.get("status") == "not_recoverable":
                            return {
                                "jql": jql,
                                "issues": [],
                                "total": 0,
                                "analysis": build_empty_analysis(llm_rec.get("summary", "")),
                                "requires_user_input": False,
                                "not_recoverable": True,
                                "jira_search_recovery": llm_rec,
                                "error": err_msg[:200],
                                "jira_lane": "structured_search",
                            }
                except Exception as llm_e:
                    logger.warning(f"[JiraSearch] LLM recovery skipped: {llm_e}")
            if not new_jql or new_jql == jql:
                break
            v = validate_recovery_jql(new_jql, jql)
            if not v.get("valid"):
                break
            jql = v["jql"]
            logger.info(f"[JiraSearch] recovery attempt {attempt}: {jql[:80]}")

    return {
        "jql": jql,
        "issues": [],
        "total": 0,
        "analysis": build_empty_analysis("多次尝试后仍无法完成 Jira 搜索。"),
        "requires_user_input": False,
        "not_recoverable": True,
        "jira_search_recovery": {"status": "not_recoverable", "history": recovery_history},
        "error": recovery_history[-1]["error"] if recovery_history else "unknown",
        "jira_lane": "structured_search",
    }


def format_issues_table(issues: list, max_rows: int = 15) -> str:
    lines = ["| 编号 | 状态 | 经办人 | 类型 | 标题 |", "|------|------|--------|------|------|"]
    for it in issues[:max_rows]:
        lines.append(
            f"| {it.get('key','')} | {it.get('status','')} | {it.get('assignee') or '未分配'} | "
            f"{it.get('issueType','')} | {(it.get('summary') or '')[:60]} |"
        )
    if len(issues) > max_rows:
        lines.append(f"\n（仅展示前 {max_rows} 条，共 {len(issues)} 条）")
    return "\n".join(lines)


def format_search_result_for_llm(result: dict, user_question: str = "") -> str:
    analysis = result.get("analysis") or {}
    jql = result.get("jql") or "（未生成）"
    parts = [
        "【Jira 结构化查询结果 — 必须基于以下事实回答】",
        f"- 用户问题: {user_question[:200]}",
        f"- 执行 JQL: {jql}",
        f"- 统计摘要: {analysis.get('summary', '')}",
    ]
    if analysis.get("byStatus"):
        parts.append(f"- 按状态: {analysis['byStatus']}")
    if analysis.get("byAssignee"):
        parts.append(f"- 按经办人: {analysis['byAssignee']}")
    if analysis.get("blockedKeys"):
        parts.append(f"- 阻塞任务: {', '.join(analysis['blockedKeys'][:10])}")
    issues = result.get("issues") or []
    if issues:
        parts.append("\n【任务列表】")
        parts.append(format_issues_table(issues))
    else:
        parts.append(
            "\n【系统提示 — 搜索无结果，禁止编造】\n"
            "必须如实告知用户未找到匹配任务，禁止虚构 Issue Key 或任务列表。"
        )
    return "\n".join(parts)


def build_jira_read_answer_prompt(user_question: str, result: dict) -> str:
    facts = format_search_result_for_llm(result, user_question)
    return (
        "你是 Alice，项目协调 PM 助理。请仅根据下方【真实 Jira 数据】回答，禁止编造 Issue Key。\n"
        "回答须包含：1) 数据依据（JQL）；2) 统计结论；3) 任务表格或明确说明无结果。\n\n"
        f"{facts}\n\n【用户问题】\n{user_question}"
    )
