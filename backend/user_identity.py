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

    当 body 已提供时（SSE 生成器等不在 request context 的路径），
    只从 body 取值，不访问 flask_request，避免 RuntimeError。
    """
    candidates = []
    # 只在未传 body 时才从 req.headers 读（非 SSE 路径用）
    if body is None:
        req = req or flask_request
        if req:
            candidates.append(req.headers.get(ALICE_USER_ID_HEADER))
        body = req.get_json(silent=True) or {} if req else {}
    candidates.extend([
        body.get("user_id"),
        (body.get("user_config") or {}).get("user_id"),
        (body.get("config") or {}).get("user_id"),
    ])
    uid = _sanitize_user_id(next((c for c in candidates if c), ""))
    if not uid:
        logger.info("[UserId] empty user_id on %s %s",
                   getattr(req, "method", "?") if req else "body",
                   getattr(req, "path", "?") if req else "?")
    return uid
