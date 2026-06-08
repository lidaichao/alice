"""
Workspace Manager — P1-4 受控代码分析工作区授权模块
对标 Baize workspace authorization：所有文件操作必须经过工作区白名单检查。

职责：
  1. 工作区授权管理（authorize / revoke）
  2. 路径安全校验（白名单 + 敏感文件拦截 + 路径穿越拦截）
  3. 持久化到 backend/data/workspaces.json
"""
import json
import os
import threading
from pathlib import Path
from typing import Optional

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_WORKSPACES_FILE = os.path.join(_DATA_DIR, "workspaces.json")
_lock = threading.RLock()

# 敏感文件名黑名单
_SENSITIVE_NAMES = frozenset([
    ".env", "credentials", "secret", "token", "key", "password",
    ".env.local", ".env.production", ".env.development",
    "credentials.json", "secrets.json", ".secrets",
    "serviceAccountKey.json", "private.key", "id_rsa",
    "known_hosts", ".aws", ".gcloud", ".ssh",
])


def _load_workspaces() -> list:
    """加载工作区列表"""
    try:
        if not os.path.exists(_WORKSPACES_FILE):
            return []
        with open(_WORKSPACES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_workspaces(workspaces: list) -> None:
    """保存工作区列表"""
    os.makedirs(os.path.dirname(_WORKSPACES_FILE), exist_ok=True)
    with open(_WORKSPACES_FILE, "w", encoding="utf-8") as f:
        json.dump(workspaces, f, ensure_ascii=False, indent=2)


def list_workspaces() -> list:
    """返回所有已授权工作区"""
    with _lock:
        return _load_workspaces()


def authorize_workspace(root_path: str, name: str = "") -> dict:
    """授权一个工作区目录"""
    with _lock:
        p = Path(root_path).resolve()
        if not p.exists() or not p.is_dir():
            return {"ok": False, "error": f"路径不存在或不是目录: {p}"}

        normalized = str(p)
        workspaces = _load_workspaces()

        # 去重
        for ws in workspaces:
            if ws.get("root_path") == normalized:
                return {"ok": True, "workspace": ws, "warning": "已存在，未重复添加"}

        workspace_id = f"ws-{len(workspaces) + 1:03d}"
        entry = {
            "id": workspace_id,
            "name": name or p.name,
            "root_path": normalized,
            "created_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        }
        workspaces.append(entry)
        _save_workspaces(workspaces)
        return {"ok": True, "workspace": entry}


def revoke_workspace(workspace_id: str) -> dict:
    """撤销工作区授权"""
    with _lock:
        workspaces = _load_workspaces()
        removed = [ws for ws in workspaces if ws.get("id") == workspace_id]
        if not removed:
            return {"ok": False, "error": f"未找到工作区: {workspace_id}"}
        workspaces = [ws for ws in workspaces if ws.get("id") != workspace_id]
        _save_workspaces(workspaces)
        return {"ok": True, "removed": removed[0]}


def _check_sensitive_filename(filepath: str) -> bool:
    """检查文件名是否包含敏感关键词"""
    name = os.path.basename(filepath).lower()
    for sensitive in _SENSITIVE_NAMES:
        if name == sensitive or name.startswith(sensitive):
            return True
        # 检查路径中任意一段
        parts = filepath.replace("\\", "/").split("/")
        for part in parts:
            if part.lower() in _SENSITIVE_NAMES:
                return True
    return False


def is_path_allowed(requested_path: str) -> bool:
    """检查路径是否在已授权工作区白名单内且安全"""
    if not requested_path:
        return False

    # 规范化为绝对路径
    try:
        p = Path(requested_path).resolve()
    except Exception:
        return False

    resolved = str(p)

    # 敏感文件名检查
    if _check_sensitive_filename(resolved):
        return False

    # 路径穿越检查：确保 resolve 后的路径不含 ..
    if ".." in resolved.split(os.sep):
        return False

    workspaces = _load_workspaces()
    for ws in workspaces:
        root = ws.get("root_path", "")
        root_resolved = str(Path(root).resolve())
        # 检查是否为根目录本身或在其子树内
        if resolved == root_resolved or resolved.startswith(root_resolved + os.sep):
            return True

    return False


def get_allowed_root(requested_path: str) -> Optional[str]:
    """返回匹配的工作区根路径，或 None"""
    if not requested_path:
        return None

    try:
        p = Path(requested_path).resolve()
    except Exception:
        return None

    resolved = str(p)
    workspaces = _load_workspaces()
    for ws in workspaces:
        root = ws.get("root_path", "")
        root_resolved = str(Path(root).resolve())
        if resolved == root_resolved or resolved.startswith(root_resolved + os.sep):
            return root_resolved

    return None
