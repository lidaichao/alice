"""
RBAC — Alice 角色权限管理（v1.10-rbac）
存储后端：backend/data/rbac_config.json

与 Carroll PRD v1.0 对齐：
  - 4 个预设角色（管理员/项目主管/开发者/访客）
  - 管理员 * 通配
  - 权限分组：jira / kb / workspace / audit / system
"""
import json
import os
import hashlib
import logging
from typing import Optional

logger = logging.getLogger("rbac")

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_RBAC_FILE = os.path.join(_DATA_DIR, "rbac_config.json")
_lock = __import__("threading").RLock()

# ══════════════════════════════════════════════════════════════
#  预设角色（与 Carroll PRD 第 377-422 行完全一致）
# ══════════════════════════════════════════════════════════════
_PRESET_ROLES = [
    {
        "id": "admin",
        "name": "管理员",
        "icon": "🛡️",
        "description": "全局最高权限，管理 Alice 所有配置",
        "members": [],
        "permissions": {"*": True},
    },
    {
        "id": "manager",
        "name": "项目主管",
        "icon": "👔",
        "description": "可直接读写 Jira、审批知识库变更",
        "members": [],
        "permissions": {
            "jira.read": True, "jira.write_create": True,
            "jira.write_update": True, "jira.write_comment": True,
            "kb.read": True, "kb.manage": True,
            "workspace.read_code": True, "workspace.run_workflow": True,
            "audit.read": True,
        },
    },
    {
        "id": "developer",
        "name": "开发者",
        "icon": "💻",
        "description": "可查 Jira / 知识库 / 工作区代码",
        "members": [],
        "permissions": {
            "jira.read": True, "kb.read": True,
            "workspace.read_code": True, "workspace.run_workflow": True,
        },
    },
    {
        "id": "guest",
        "name": "访客",
        "icon": "👁️",
        "description": "只读权限，可查 Jira 和知识库",
        "members": [],
        "permissions": {
            "jira.read": True, "kb.read": True,
        },
    },
]

# ── 权限项定义（用于 Admin 矩阵渲染） ──
_PERMISSION_DEFS = [
    # 分组：Jira 操作
    {"key": "jira.read", "group": "jira", "label": "查阅 Jira"},
    {"key": "jira.write_create", "group": "jira", "label": "创建 Issue"},
    {"key": "jira.write_update", "group": "jira", "label": "修改 Issue"},
    {"key": "jira.write_comment", "group": "jira", "label": "添加评论"},
    # 分组：知识库
    {"key": "kb.read", "group": "kb", "label": "查阅知识库"},
    {"key": "kb.manage", "group": "kb", "label": "管理知识库"},
    {"key": "kb.rebuild_index", "group": "kb", "label": "索引重建"},
    {"key": "kb.doc_crud", "group": "kb", "label": "文档增删"},
    # 分组：工作区
    {"key": "workspace.read_code", "group": "workspace", "label": "阅读代码"},
    {"key": "workspace.run_workflow", "group": "workspace", "label": "运行工作流"},
    # 分组：审计
    {"key": "audit.read", "group": "audit", "label": "查阅审计日志"},
    {"key": "audit.manage", "group": "audit", "label": "管理审计"},
    # 分组：系统
    {"key": "system.manage", "group": "system", "label": "系统配置"},
]


# ══════════════════════════════════════════════════════════════
#  存储读写
# ══════════════════════════════════════════════════════════════

def load_roles() -> list[dict]:
    """加载所有角色。文件不存在时返回预设默认值（不写盘）。"""
    with _lock:
        if not os.path.exists(_RBAC_FILE):
            return [dict(r) for r in _PRESET_ROLES]
        try:
            with open(_RBAC_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            roles = data.get("roles", [])
            if not roles:
                return [dict(r) for r in _PRESET_ROLES]
            return roles
        except Exception as e:
            logger.warning(f"rbac: failed to load roles: {e}")
            return [dict(r) for r in _PRESET_ROLES]


def save_roles(roles: list[dict]) -> None:
    """写盘 rbac_config.json。"""
    with _lock:
        os.makedirs(_DATA_DIR, exist_ok=True)
        try:
            with open(_RBAC_FILE, "w", encoding="utf-8") as f:
                json.dump({"roles": roles}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"rbac: failed to save roles: {e}")
            raise RuntimeError(f"保存角色失败: {e}")


# ══════════════════════════════════════════════════════════════
#  权限查询
# ══════════════════════════════════════════════════════════════

def get_user_role(user_id: str) -> Optional[dict]:
    """查找 user_id 所属的角色。优先查 accounts 的 role_ids，降级查成员列表。"""
    if not user_id:
        return None
    # v2.0 wave1: 优先通过 accounts.json 的角色分配查找
    try:
        from accounts import get_account_by_username, load_accounts as load_accs
        _acc = get_account_by_username(user_id)
        if _acc and _acc.get("role_ids"):
            roles = load_roles()
            role_id_set = set(_acc["role_ids"])
            for r in roles:
                if r.get("id") in role_id_set:
                    return r
    except Exception:
        pass
    # 降级：旧版成员列表
    roles = load_roles()
    for role in roles:
        members = role.get("members", [])
        if user_id in members:
            return role
    return None


def check_permission(user_id: str, permission_key: str) -> bool:
    """查用户是否有指定权限。管理员 * 通配直接 True。"""
    if not user_id or not permission_key:
        return False
    role = get_user_role(user_id)
    if not role:
        return False
    perms = role.get("permissions", {})
    if perms.get("*") is True:
        return True
    return perms.get(permission_key, False) is True


def get_user_permissions(user_id: str) -> list[str]:
    """返回该用户所有为 True 的权限键列表。"""
    if not user_id:
        return []
    role = get_user_role(user_id)
    if not role:
        return []
    perms = role.get("permissions", {})
    if perms.get("*") is True:
        return [d["key"] for d in _PERMISSION_DEFS]
    return [k for k, v in perms.items() if v is True and k != "*"]


def get_permission_defs() -> list[dict]:
    """返回所有权限项定义（供 Admin 矩阵渲染）。"""
    return list(_PERMISSION_DEFS)


# ══════════════════════════════════════════════════════════════
#  快捷方法（供 API 使用）
# ══════════════════════════════════════════════════════════════

def get_roles_with_member_count() -> list[dict]:
    """返回角色列表，每个附加 member_count 字段。"""
    roles = load_roles()
    result = []
    for r in roles:
        d = dict(r)
        d["member_count"] = len(r.get("members", []))
        result.append(d)
    return result


def set_role_permission(role_id: str, permission_key: str, value: bool) -> dict:
    """更新某角色某权限项的值。返回更新后的角色。"""
    with _lock:
        roles = load_roles()
        for r in roles:
            if r.get("id") == role_id:
                perms = r.get("permissions", {})
                if value:
                    perms[permission_key] = True
                else:
                    perms.pop(permission_key, None)
                r["permissions"] = perms
                save_roles(roles)
                return r
        raise ValueError(f"角色 {role_id} 不存在")


# ══════════════════════════════════════════════════════════════
#  P1: 权限变更被动检测（Carroll PRD B5）
#  存储 last_perm_hash 在 rbac_config.json 顶层
# ══════════════════════════════════════════════════════════════

def _load_hash_map() -> dict:
    """加载 per-user permission hash 快照。"""
    try:
        if os.path.exists(_RBAC_FILE):
            with open(_RBAC_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("last_perm_hash", {})
    except Exception:
        pass
    return {}


def _save_hash_map(hm: dict) -> None:
    """写回 hash 快照（合并到 rbac_config.json 顶层）。"""
    with _lock:
        os.makedirs(_DATA_DIR, exist_ok=True)
        try:
            existing = {}
            if os.path.exists(_RBAC_FILE):
                with open(_RBAC_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing["last_perm_hash"] = hm
            with open(_RBAC_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"rbac: failed to save hash map: {e}")


def get_permission_hash(user_id: str) -> str:
    """当前用户角色权限的 MD5（用于变更检测）。"""
    perms = sorted(get_user_permissions(user_id))
    role = get_user_role(user_id)
    role_id = role.get("id", "") if role else ""
    payload = json.dumps({"role": role_id, "perms": perms}, sort_keys=True)
    return hashlib.md5(payload.encode()).hexdigest()


def check_permission_change(user_id: str):
    """比对上次 hash，返回 (changed: bool, detail: dict|None)。

    若 changed=True，detail 包含：
      - role_name: str
      - added: list[str]
      - removed: list[str]
    同时更新 last_perm_hash。
    """
    if not user_id:
        return False, None
    new_hash = get_permission_hash(user_id)
    hm = _load_hash_map()
    old_hash = hm.get(user_id, "")
    hm[user_id] = new_hash
    # 首次记录不算变更
    if not old_hash:
        _save_hash_map(hm)
        return False, None
    if new_hash == old_hash:
        return False, None
    # 计算 diff
    old_perms = set(get_user_permissions_stale(user_id, hm.get(f"_{user_id}_perms", [])))
    new_perms = sorted(get_user_permissions(user_id))
    role = get_user_role(user_id)
    import hashlib as _hashlib
    hm[f"_{user_id}_perms"] = list(new_perms)
    _save_hash_map(hm)
    added = [p for p in new_perms if p not in old_perms]
    removed = [p for p in old_perms if p not in new_perms]
    _perm_label_map = {d["key"]: d["label"] for d in _PERMISSION_DEFS}
    return True, {
        "role_name": role.get("name", "") if role else "",
        "added": [_perm_label_map.get(p, p) for p in added],
        "removed": [_perm_label_map.get(p, p) for p in removed],
    }


def get_user_permissions_stale(user_id: str, perms_list: list) -> list[str]:
    """从缓存的权限列表返回（用于 diff 计算）。"""
    return list(perms_list)
