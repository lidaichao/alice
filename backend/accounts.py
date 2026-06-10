"""
Accounts — Alice 账号系统（v2.0-wave1）
存储后端：backend/data/accounts.json
密码方案：sha256(password + salt)
Token 方案：base64(username + ":" + timestamp + ":" + hmac)
"""
import json
import os
import hashlib
import hmac
import base64
import time
import secrets
import logging
from threading import RLock
from typing import Optional

logger = logging.getLogger("accounts")

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_ACCOUNTS_FILE = os.path.join(_DATA_DIR, "accounts.json")
_lock = RLock()

_TOKEN_SECRET = b"alice-accounts-v2.0-secret-key-change-in-prod"
_TOKEN_TTL = 86400  # 24 hours


# ══════════════════════════════════════════════════════════════
#  File I/O
# ══════════════════════════════════════════════════════════════

def load_accounts() -> list[dict]:
    """加载全部账号列表。首次自动创建 admin 账号。"""
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(_ACCOUNTS_FILE):
        with _lock:
            if not os.path.exists(_ACCOUNTS_FILE):  # double-check
                salt = secrets.token_hex(16)
                admin = {
                    "id": "account-admin",
                    "username": "admin",
                    "display_name": "管理员",
                    "password_hash": _hash_password("admin", salt),
                    "salt": salt,
                    "role_ids": ["admin"],
                    "disabled": False,
                    "created_at": _now_iso(),
                    "last_login_at": None,
                }
                _write([admin])
                logger.info("accounts: auto-created default admin account")
    try:
        with open(_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("accounts: failed to load")
        return []


def _write(accounts: list[dict]) -> None:
    with _lock:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════
#  Crypto helpers
# ══════════════════════════════════════════════════════════════

def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _make_token(username: str) -> str:
    """生成 24h 有效期的 token。"""
    ts = str(int(time.time()))
    # 简化实现：base64(username:ts:hmac_sha256_hex(username:ts))
    raw = f"{username}:{ts}"
    mac = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    payload = f"{username}:{ts}:{mac}"
    return base64.b64encode(payload.encode("utf-8")).decode("utf-8")


def verify_token(token: str) -> Optional[str]:
    """验证 token，成功返回 username，失败返回 None。"""
    try:
        payload = base64.b64decode(token).decode("utf-8")
        parts = payload.split(":")
        if len(parts) != 3:
            return None
        username, ts, mac = parts
        expected_ts = int(ts)
        now = int(time.time())
        if now - expected_ts > _TOKEN_TTL:
            return None
        expected_mac = hashlib.sha256(f"{username}:{ts}".encode("utf-8")).hexdigest()[:16]
        if not hmac.compare_digest(mac, expected_mac):
            return None
        return username
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
#  CRUD
# ══════════════════════════════════════════════════════════════

def get_account_by_username(username: str) -> Optional[dict]:
    accounts = load_accounts()
    for a in accounts:
        if a.get("username", "").lower() == username.strip().lower():
            return a
    return None


def get_account_by_id(account_id: str) -> Optional[dict]:
    accounts = load_accounts()
    for a in accounts:
        if a.get("id") == account_id:
            return a
    return None


def verify_password(username: str, password: str) -> Optional[dict]:
    """验证用户名密码，成功返回 account dict，失败返回 None。"""
    account = get_account_by_username(username)
    if not account:
        return None
    if account.get("disabled"):
        return None
    stored_hash = account.get("password_hash", "")
    salt = account.get("salt", "")
    if _hash_password(password, salt) != stored_hash:
        return None
    # 更新最后登录时间
    with _lock:
        accounts = load_accounts()
        for a in accounts:
            if a.get("id") == account["id"]:
                a["last_login_at"] = _now_iso()
                _write(accounts)
                break
    return account


def create_account(
    username: str,
    display_name: str,
    password: str,
    role_ids: list[str] = None,
) -> dict:
    """创建账号。用户名重复抛 ValueError。"""
    username = username.strip()
    if not username:
        raise ValueError("用户名不能为空")
    if get_account_by_username(username):
        raise ValueError(f"用户名 '{username}' 已存在")
    salt = secrets.token_hex(16)
    account = {
        "id": f"account-{secrets.token_hex(6)}",
        "username": username,
        "display_name": display_name.strip() or username,
        "password_hash": _hash_password(password, salt),
        "salt": salt,
        "role_ids": role_ids or [],
        "disabled": False,
        "created_at": _now_iso(),
        "last_login_at": None,
    }
    with _lock:
        accounts = load_accounts()
        accounts.append(account)
        _write(accounts)
    return account


def update_account(account_id: str, **fields) -> dict:
    """更新账号字段。支持：display_name, role_ids, disabled, password。
    返回更新后的 account dict。"""
    accounts = load_accounts()
    for a in accounts:
        if a.get("id") == account_id:
            if "display_name" in fields:
                a["display_name"] = fields["display_name"].strip()
            if "role_ids" in fields:
                a["role_ids"] = fields["role_ids"]
            if "disabled" in fields:
                a["disabled"] = bool(fields["disabled"])
            if "password" in fields:
                salt = secrets.token_hex(16)
                a["salt"] = salt
                a["password_hash"] = _hash_password(fields["password"], salt)
            _write(accounts)
            return a
    raise ValueError(f"账号 {account_id} 不存在")


def delete_account(account_id: str) -> dict:
    """软删除：设置 disabled=True。"""
    return update_account(account_id, disabled=True)


def login(username: str, password: str) -> Optional[dict]:
    """登录：验证密码 → 返回 { token, user, roles, permissions }。"""
    account = verify_password(username, password)
    if not account:
        return None
    token = _make_token(account["username"])
    from rbac import check_permission
    role_ids = account.get("role_ids", [])
    # 通过 rbac 查询用户权限
    all_perms = []
    try:
        from rbac import get_user_permissions as _rbac_get_perms
        all_perms = _rbac_get_perms(account["username"])
    except Exception:
        pass
    return {
        "token": token,
        "user": {
            "username": account["username"],
            "display_name": account.get("display_name", ""),
            "id": account["id"],
        },
        "roles": role_ids,
        "permissions": all_perms,
    }


