"""
AuditGateway — 操作安全审计网关
移植自白泽 Baize plugin-gateway-service.js + audit-rules/

职责：
  1. 审计插件操作（敏感操作拦截、写操作确认）
  2. 操作日志记录（内存 + 持久 JSONL audit.log）
  3. 审计规则配置化管理（skills/registry.yaml）
  4. 操作审批权限（M4.5 operation_approval 白名单）
"""

import json
import os
import time
import logging
import threading
from typing import Optional

logger = logging.getLogger("audit-gateway")

_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "skills", "registry.yaml")
_AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "data", "audit.log")

# ══════════════════════════════════════════════════════════════
#  审计规则（可配置化，从 registry.yaml 加载）
# ══════════════════════════════════════════════════════════════

DEFAULT_RULES = {
    "jira_write": {
        "require_confirmation": True,
        "max_batch_size": 20,
        "forbidden_fields": ["password", "api_key", "secret"],
        "rate_limit": {"per_minute": 10, "per_hour": 100},
    },
    "wecom_notify": {
        "require_confirmation": True,
        "max_recipients": 50,
        "forbidden_keywords": ["密码", "密钥", "secret", "token", "api_key"],
        "rate_limit": {"per_minute": 5},
    },
    "ai_reasoning": {
        "require_confirmation": False,
    },
    "jira_query": {
        "require_confirmation": False,
    },
    "svn_code": {
        "require_confirmation": False,
    },
    "notion_docs": {
        "require_confirmation": False,
    },
    "gdrive_files": {
        "require_confirmation": False,
    },
    "mailbox_worker": {
        "require_confirmation": False,
        "rate_limit": {"per_minute": 120, "per_hour": 2000},
    },
}

_loaded_rules: Optional[dict] = None
_operation_approval: Optional[dict] = None
_load_lock = threading.Lock()


def _load_registry_config() -> tuple[dict, dict]:
    """M4.7 — 从 skills/registry.yaml 加载 audit_rules + operation_approval。"""
    rules = {k: dict(v) for k, v in DEFAULT_RULES.items()}
    approval = {
        "enabled": False,
        "approver_user_ids": [],
        "approver_roles": [],
    }
    try:
        import yaml

        with open(_REGISTRY_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for tool_id, cfg in (data.get("audit_rules") or {}).items():
            if isinstance(cfg, dict):
                merged = dict(rules.get(tool_id, {}))
                merged.update(cfg)
                rules[tool_id] = merged
        oa = data.get("operation_approval") or {}
        if isinstance(oa, dict):
            approval["enabled"] = bool(oa.get("enabled", False))
            approval["approver_user_ids"] = list(oa.get("approver_user_ids") or [])
            approval["approver_roles"] = list(oa.get("approver_roles") or [])
        logger.info(
            "[Audit] loaded registry: %d rules, approval enabled=%s ids=%d",
            len(rules),
            approval["enabled"],
            len(approval["approver_user_ids"]),
        )
    except Exception as e:
        logger.warning("[Audit] load registry failed, using defaults: %s", e)
    return rules, approval


def _ensure_registry_loaded():
    global _loaded_rules, _operation_approval
    if _loaded_rules is not None:
        return
    with _load_lock:
        if _loaded_rules is None:
            _loaded_rules, _operation_approval = _load_registry_config()


def get_audit_rules(tool_id: str) -> dict:
    _ensure_registry_loaded()
    return (_loaded_rules or DEFAULT_RULES).get(tool_id, {})


def reload_audit_config():
    """热重载 registry 审计配置（管理/测试用）。"""
    global _loaded_rules, _operation_approval
    with _load_lock:
        _loaded_rules, _operation_approval = _load_registry_config()


# ══════════════════════════════════════════════════════════════
#  速率限制
# ══════════════════════════════════════════════════════════════

class RateLimiter:
    """简单内存速率限制器"""

    def __init__(self):
        self._windows: dict = {}
        self._lock = threading.Lock()

    def check(self, tool_id: str, limits: dict) -> dict:
        now = time.time()
        with self._lock:
            if tool_id not in self._windows:
                self._windows[tool_id] = []

            per_min = limits.get("per_minute", 0)
            per_hour = limits.get("per_hour", 0)

            minute_ago = now - 60
            hour_ago = now - 3600
            self._windows[tool_id] = [
                (ts, c) for ts, c in self._windows[tool_id] if ts > hour_ago
            ]

            min_count = sum(c for ts, c in self._windows[tool_id] if ts > minute_ago)
            hour_count = sum(c for ts, c in self._windows[tool_id])

            if per_min > 0 and min_count >= per_min:
                return {"allowed": False, "retry_after": 60, "reason": f"超过每分钟 {per_min} 次限制"}
            if per_hour > 0 and hour_count >= per_hour:
                return {"allowed": False, "retry_after": 3600, "reason": f"超过每小时 {per_hour} 次限制"}

            self._windows[tool_id].append((now, 1))
            return {"allowed": True, "retry_after": 0}


_rate_limiter = RateLimiter()

# ══════════════════════════════════════════════════════════════
#  敏感字段 / 关键词检测
# ══════════════════════════════════════════════════════════════

SENSITIVE_PATTERNS = [
    "password", "passwd", "secret", "api_key", "apikey",
    "token", "credential", "密钥", "密码", "令牌",
]


def _has_sensitive_data(data: dict) -> list:
    found = []
    for key in (data or {}).keys():
        for pattern in SENSITIVE_PATTERNS:
            if pattern in key.lower():
                found.append(key)
                break
    return found


def _check_forbidden_keywords(data: dict, keywords: list) -> list:
    found = []
    data_str = str(data).lower()
    for kw in keywords:
        if kw.lower() in data_str:
            found.append(kw)
    return found


# ══════════════════════════════════════════════════════════════
#  审计引擎
# ══════════════════════════════════════════════════════════════

def audit(
    tool_id: str,
    action: str,
    data: dict = None,
    user_id: str = "",
) -> dict:
    """审计操作。返回 decision: allow | deny | confirm_required"""
    rules = get_audit_rules(tool_id)

    if not rules:
        return {
            "decision": "deny",
            "reason": f"工具 '{tool_id}' 未注册审计规则，默认拒绝。",
            "warnings": [],
            "tool_id": tool_id,
            "action": action,
        }

    rate_limits = rules.get("rate_limit", {})
    if rate_limits:
        rl = _rate_limiter.check(tool_id, rate_limits)
        if not rl["allowed"]:
            return {
                "decision": "deny",
                "reason": f"速率限制: {rl['reason']}",
                "warnings": [],
                "tool_id": tool_id,
                "action": action,
            }

    data = data or {}
    sensitive = _has_sensitive_data(data)
    if sensitive:
        logger.warning(f"[Audit] DENIED: {tool_id}.{action} contains sensitive fields: {sensitive}")
        return {
            "decision": "deny",
            "reason": f"请求包含敏感字段: {sensitive}",
            "warnings": [f"检测到敏感字段: {', '.join(sensitive)}"],
            "tool_id": tool_id,
            "action": action,
        }

    forbidden = rules.get("forbidden_keywords", [])
    if forbidden:
        found = _check_forbidden_keywords(data, forbidden)
        if found:
            logger.warning(f"[Audit] DENIED: {tool_id}.{action} contains forbidden keywords: {found}")
            return {
                "decision": "deny",
                "reason": f"内容包含禁止关键词: {found}",
                "warnings": [f"检测到禁止关键词: {', '.join(found)}"],
                "tool_id": tool_id,
                "action": action,
            }

    max_batch = rules.get("max_batch_size", 0)
    if max_batch > 0:
        batch_count = len(data.get("drafts", data.get("items", data.get("issues", []))))
        if batch_count > max_batch:
            return {
                "decision": "deny",
                "reason": f"批量操作 {batch_count} 超过上限 {max_batch}",
                "warnings": [f"单次最多 {max_batch} 条"],
                "tool_id": tool_id,
                "action": action,
            }

    if rules.get("require_confirmation", False):
        return {
            "decision": "confirm_required",
            "reason": f"工具 '{tool_id}' 的 {action} 操作需要用户确认",
            "warnings": [],
            "tool_id": tool_id,
            "action": action,
        }

    return {
        "decision": "allow",
        "reason": "",
        "warnings": [],
        "tool_id": tool_id,
        "action": action,
    }


def is_allowed(result: dict) -> bool:
    return result["decision"] == "allow"


def needs_confirmation(result: dict) -> bool:
    return result["decision"] == "confirm_required"


def is_denied(result: dict) -> bool:
    return result["decision"] == "deny"


# ══════════════════════════════════════════════════════════════
#  M4.5 — 操作审批权限（confirm / reject）
# ══════════════════════════════════════════════════════════════

def _user_matches_role(user_id: str, role: str) -> bool:
    r = (role or "").strip().lower()
    u = (user_id or "").strip().lower()
    if not r or not u:
        return False
    return u == r or u.endswith(f"-{r}") or u.startswith(f"{r}-")


def check_operation_approver(
    user_id: str,
    action: str,
    operation_id: str = "",
) -> dict:
    """
    检查 user_id 是否可执行 operation confirm/reject。
    action: confirm | reject
    """
    _ensure_registry_loaded()
    cfg = _operation_approval or {}
    if not cfg.get("enabled"):
        return {"decision": "allow", "reason": "", "action": action, "operation_id": operation_id}

    uid = (user_id or "").strip()
    if not uid:
        return {
            "decision": "deny",
            "reason": "缺少用户身份（X-Alice-User-Id），无法执行审批操作",
            "action": action,
            "operation_id": operation_id,
        }

    allowed_ids = {str(x).strip() for x in (cfg.get("approver_user_ids") or []) if x}
    if uid in allowed_ids:
        return {"decision": "allow", "reason": "", "action": action, "operation_id": operation_id}

    for role in cfg.get("approver_roles") or []:
        if _user_matches_role(uid, str(role)):
            return {"decision": "allow", "reason": "", "action": action, "operation_id": operation_id}

    return {
        "decision": "deny",
        "reason": f"用户「{uid}」无权执行操作审批（{action}），请联系管理员加入审批白名单",
        "action": action,
        "operation_id": operation_id,
    }


# ══════════════════════════════════════════════════════════════
#  M4.6 — 审计日志（内存 + 持久 JSONL）
# ══════════════════════════════════════════════════════════════

_audit_log: list = []
_audit_lock = threading.Lock()
MAX_LOG_SIZE = 500


def append_persistent_audit(entry: dict):
    """append-only 写入 backend/data/audit.log（JSONL，重启不丢）。"""
    os.makedirs(os.path.dirname(_AUDIT_LOG_PATH), exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    with _audit_lock:
        with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def log_audit(result: dict, user_id: str = "", context: dict = None):
    """记录审计日志（内存 + 持久）。"""
    ctx = context or {}
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "actor": user_id or "",
        "action": result.get("action", ""),
        "decision": result.get("decision", ""),
        "reason": result.get("reason", ""),
        "tool_id": result.get("tool_id", ""),
        "origin": ctx.get("origin", "ai"),
        "operation_id": ctx.get("operation_id", ""),
        "context": {k: v for k, v in ctx.items() if k not in ("origin", "operation_id")},
    }
    with _audit_lock:
        _audit_log.append(entry)
        if len(_audit_log) > MAX_LOG_SIZE:
            _audit_log.pop(0)
    append_persistent_audit(entry)
    logger.info(
        "[Audit] %s | %s.%s | %s",
        result.get("decision", ""),
        result.get("tool_id", ""),
        result.get("action", ""),
        result.get("reason", ""),
    )


def record_operation_audit(
    *,
    actor: str,
    action: str,
    operation_id: str,
    decision: str,
    reason: str = "",
    origin: str = "http",
    context: dict = None,
):
    """M4.6 — confirm/reject/deny 操作审计落盘。"""
    log_audit(
        {
            "tool_id": "operation_approval",
            "action": action,
            "decision": decision,
            "reason": reason,
        },
        actor,
        {"operation_id": operation_id, "origin": origin, **(context or {})},
    )


def get_recent_logs(limit: int = 50) -> list:
    with _audit_lock:
        return list(reversed(_audit_log[-limit:]))


def query_persistent_audit_logs(
    limit: int = 50,
    operation_id: str = "",
) -> list:
    """读取持久 audit.log，最新在前。"""
    if not os.path.isfile(_AUDIT_LOG_PATH):
        return []
    limit = max(1, min(int(limit or 50), 500))
    entries: list = []
    try:
        with open(_AUDIT_LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if operation_id and entry.get("operation_id") != operation_id:
                continue
            entries.append(entry)
            if len(entries) >= limit:
                break
    except Exception as e:
        logger.warning("[Audit] read audit.log failed: %s", e)
    return entries


def audit_and_log(
    tool_id: str,
    action: str,
    data: dict = None,
    user_id: str = "",
    origin: str = "ai",
) -> dict:
    """审计 + 自动记录日志 — origin: 'ai' | 'human' | 'mcp' | 'http'"""
    result = audit(tool_id, action, data, user_id)
    result["origin"] = origin
    log_audit(
        result,
        user_id,
        {"data_keys": list((data or {}).keys()), "origin": origin},
    )
    return result


# ══════════════════════════════════════════════════════════════
#  自测
# ══════════════════════════════════════════════════════════════

_TEST_CASES = [
    ("jira_query", "search", {"jql": "project=CT"}, "allow"),
    ("jira_write", "create", {"summary": "fix bug", "projectKey": "CT"}, "confirm_required"),
    ("wecom_notify", "send", {"content": "hello"}, "confirm_required"),
    ("wecom_notify", "send", {"content": "这是密码:xxx"}, "deny"),
    ("unknown_tool", "test", {}, "deny"),
    ("jira_write", "create", {"password": "123"}, "deny"),
    ("svn_code", "diff", {"path": "/trunk"}, "allow"),
    ("jira_write", "create", {"drafts": list(range(25))}, "deny"),
]


def run_self_test():
    reload_audit_config()
    passed, total = 0, 0
    for tool_id, action, data, expected in _TEST_CASES:
        result = audit(tool_id, action, data, "test_user")
        ok = result["decision"] == expected
        status = "✓" if ok else "✗"
        print(f"  {status} {tool_id}.{action} → {result['decision']} (expected: {expected})")
        if ok:
            passed += 1
        else:
            print(f"      reason: {result.get('reason', '')}")
        total += 1

    print()
    total += 1
    v = check_operation_approver("e2e-audit-pm", "reject", "op-1")
    if v["decision"] == "allow":
        print("  ✓ operation_approval: e2e-audit-pm allowed")
        passed += 1
    else:
        print(f"  ✗ operation_approval allow failed: {v}")

    total += 1
    v2 = check_operation_approver("stranger", "confirm", "op-1")
    if v2["decision"] == "deny":
        print("  ✓ operation_approval: stranger denied")
        passed += 1
    else:
        print(f"  ✗ operation_approval deny failed: {v2}")

    print()
    total += 1
    rl = RateLimiter()
    limits = {"per_minute": 3}
    results = [rl.check("test_tool", limits) for _ in range(5)]
    if results[0]["allowed"] and results[1]["allowed"] and results[2]["allowed"] and not results[3]["allowed"]:
        print("  ✓ 速率限制: 前3次允许，第4次拦截")
        passed += 1
    else:
        print("  ✗ 速率限制测试失败")

    print(f"\n{'='*40}")
    print(f"  AuditGateway 自测: {passed}/{total} 通过 ({passed*100//total}%)")
    print(f"{'='*40}\n")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    run_self_test()
