"""M4.1 — 统一解析客户端用户身份（header + body），禁止各 Route 复制粘贴。"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from flask import request as flask_request

logger = logging.getLogger("user-identity")

ALICE_USER_ID_HEADER = "X-Alice-User-Id"
_USER_ID_RE = re.compile(r"[^\w.@+-]")


def _sanitize_user_id(raw: Any) -> str:
    uid = str(raw or "").strip()
    if not uid:
        return ""
    return _USER_ID_RE.sub("_", uid)[:64]


def parse_user_id_from_request(req=None, body: Optional[dict] = None) -> str:
    """
    优先级：X-Alice-User-Id > body.user_id > user_config.user_id > config.user_id
    空 user_id 允许降级（内网 Hub 过渡期），但打 info 日志。
    """
    req = req or flask_request
    if body is None:
        body = req.get_json(silent=True) or {}
    candidates = [
        req.headers.get(ALICE_USER_ID_HEADER),
        body.get("user_id"),
        (body.get("user_config") or {}).get("user_id"),
        (body.get("config") or {}).get("user_id"),
    ]
    uid = _sanitize_user_id(next((c for c in candidates if c), ""))
    if not uid:
        logger.info("[UserId] empty user_id on %s %s", req.method, getattr(req, "path", "?"))
    return uid
