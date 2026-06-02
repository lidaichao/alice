"""
AuditGateway — 操作安全审计网关
移植自白泽 Baize plugin-gateway-service.js + audit-rules/

职责：
  1. 审计插件操作（敏感操作拦截、写操作确认）
  2. 操作日志记录
  3. 审计规则配置化管理
"""

import time
import logging
import threading
from typing import Optional

logger = logging.getLogger("audit-gateway")

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
}


# ══════════════════════════════════════════════════════════════
#  速率限制
# ══════════════════════════════════════════════════════════════

class RateLimiter:
    """简单内存速率限制器"""

    def __init__(self):
        self._windows: dict = {}          # tool_id → [(timestamp, count)]
        self._lock = threading.Lock()

    def check(self, tool_id: str, limits: dict) -> dict:
        """检查速率。返回 {allowed: bool, retry_after: int}"""
        now = time.time()
        with self._lock:
            if tool_id not in self._windows:
                self._windows[tool_id] = []

            per_min = limits.get("per_minute", 0)
            per_hour = limits.get("per_hour", 0)

            # 清理过期记录
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

            # 记录
            self._windows[tool_id].append((now, 1))
            return {"allowed": True, "retry_after": 0}


_rate_limiter = RateLimiter()


# ══════════════════════════════════════════════════════════════
#  审计引擎
# ══════════════════════════════════════════════════════════════

# 敏感字段检测
SENSITIVE_PATTERNS = [
    "password", "passwd", "secret", "api_key", "apikey",
    "token", "credential", "密钥", "密码", "令牌",
]


def _has_sensitive_data(data: dict) -> list:
    """检查数据中是否包含敏感字段"""
    found = []
    for key in (data or {}).keys():
        for pattern in SENSITIVE_PATTERNS:
            if pattern in key.lower():
                found.append(key)
                break
    return found


def _check_forbidden_keywords(data: dict, keywords: list) -> list:
    """检查内容中是否包含禁止关键词"""
    found = []
    data_str = str(data).lower()
    for kw in keywords:
        if kw.lower() in data_str:
            found.append(kw)
    return found


def audit(
    tool_id: str,
    action: str,
    data: dict = None,
    user_id: str = "",
) -> dict:
    """
    审计操作。

    返回:
    {
        "decision": "allow" | "deny" | "confirm_required",
        "reason": str,
        "warnings": [],
        "tool_id": str,
        "action": str,
    }
    """
    rules = DEFAULT_RULES.get(tool_id, {})

    # 1. 工具未注册
    if not rules:
        return {
            "decision": "deny",
            "reason": f"工具 '{tool_id}' 未注册审计规则，默认拒绝。",
            "warnings": [],
            "tool_id": tool_id,
            "action": action,
        }

    # 2. 速率限制
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

    # 3. 敏感字段检测
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

    # 4. 禁止关键词
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

    # 5. 批量上限
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

    # 6. 确认要求
    if rules.get("require_confirmation", False):
        return {
            "decision": "confirm_required",
            "reason": f"工具 '{tool_id}' 的 {action} 操作需要用户确认",
            "warnings": [],
            "tool_id": tool_id,
            "action": action,
        }

    # 7. 放行
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
#  审计日志
# ══════════════════════════════════════════════════════════════

_audit_log: list = []
_audit_lock = threading.Lock()
MAX_LOG_SIZE = 500


def log_audit(result: dict, user_id: str = "", context: dict = None):
    """记录审计日志"""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool_id": result["tool_id"],
        "action": result["action"],
        "decision": result["decision"],
        "reason": result["reason"],
        "user_id": user_id,
        "context": context or {},
    }
    with _audit_lock:
        _audit_log.append(entry)
        if len(_audit_log) > MAX_LOG_SIZE:
            _audit_log.pop(0)
    logger.info(f"[Audit] {result['decision']:>16} | {result['tool_id']}.{result['action']} | {result['reason']}")


def get_recent_logs(limit: int = 50) -> list:
    """获取最近审计日志"""
    with _audit_lock:
        return list(reversed(_audit_log[-limit:]))


# ══════════════════════════════════════════════════════════════
#  便捷函数：完整审计流
# ══════════════════════════════════════════════════════════════

def audit_and_log(tool_id: str, action: str, data: dict = None, user_id: str = "", origin: str = "ai") -> dict:
    """审计 + 自动记录日志 — origin: 'ai' | 'human'"""
    result = audit(tool_id, action, data, user_id)
    result["origin"] = origin
    log_audit(result, user_id, {"data_keys": list((data or {}).keys()), "origin": origin})
    return result


# ══════════════════════════════════════════════════════════════
#  自测
# ══════════════════════════════════════════════════════════════

_TEST_CASES = [
    # (tool_id, action, data, expected_decision)
    ("jira_query", "search", {"jql": "project=CT"}, "allow"),
    ("jira_write", "create", {"summary": "fix bug", "projectKey": "CT"}, "confirm_required"),
    ("wecom_notify", "send", {"content": "hello"}, "confirm_required"),
    ("wecom_notify", "send", {"content": "这是密码:xxx"}, "deny"),        # 禁止关键词
    ("unknown_tool", "test", {}, "deny"),                                 # 未注册
    ("jira_write", "create", {"password": "123"}, "deny"),                # 敏感字段
    ("svn_code", "diff", {"path": "/trunk"}, "allow"),
    ("jira_write", "create", {"drafts": list(range(25))}, "deny"),        # 超批量
]


def run_self_test():
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

    # 速率限制测试
    print()
    total += 1
    rl = RateLimiter()
    limits = {"per_minute": 3}
    results = [rl.check("test_tool", limits) for _ in range(5)]
    if results[0]["allowed"] and results[1]["allowed"] and results[2]["allowed"] and not results[3]["allowed"]:
        print(f"  ✓ 速率限制: 前3次允许，第4次拦截")
        passed += 1
    else:
        print(f"  ✗ 速率限制测试失败")

    print(f"\n{'='*40}")
    print(f"  AuditGateway 自测: {passed}/{total} 通过 ({passed*100//total}%)")
    print(f"{'='*40}\n")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    run_self_test()
