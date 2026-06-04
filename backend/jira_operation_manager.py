"""
JiraOperationManager — Jira 操作确认卡 + 失败恢复机制
移植自白泽 Baize jira-operation-service.js

职责：
  1. 生成确认卡 (OperationCard)
  2. 状态机管理 (awaiting_confirmation → running → created/failed → recovery_required)
  3. 失败分类 (classify_error)
  4. 恢复方案生成 (build_recovery)
"""

import json
import os
import time
import uuid
import logging
import threading
from typing import Optional

logger = logging.getLogger("jira-op-manager")

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_OPS_FILE = os.path.join(_DATA_DIR, "operations.json")
_DRAFTS_FILE = os.path.join(_DATA_DIR, "jira_draft_box.json")
_LEGACY_OPS_INDEX = os.path.join(
    os.path.dirname(__file__), "runtime", "jira-operations", "index.json",
)
_store: dict = {}
_draft_box: dict = {}
_lock = threading.RLock()

# ══════════════════════════════════════════════════════════════
#  状态机定义
# ══════════════════════════════════════════════════════════════

STATUS_TRANSITIONS = {
    "awaiting_confirmation": ["running", "rejected"],
    "running": ["created", "failed"],
    "failed": ["recovery_required", "rejected"],
    "recovery_required": ["awaiting_confirmation", "rejected"],
    "created": [],         # 终态
    "rejected": [],        # 终态
}

# ══════════════════════════════════════════════════════════════
#  错误分类（移植自 Baize classifyJiraApiError / buildFailureContext）
# ══════════════════════════════════════════════════════════════

ERROR_CLASSIFICATIONS = {
    "missing_project_key": {
        "type": "missing_required_field",
        "field": "projectKey",
        "safe_default_recovery": "submit_supplement",
        "retryable": False,
        "requires_user_input": True,
        "patterns": [
            "未配置项目 Key", "projectKey", "项目 Key",
        ]
    },
    "labels_unsupported": {
        "type": "field_not_on_screen",
        "field": "labels",
        "safe_default_recovery": "retry_without_labels",
        "retryable": True,
        "requires_user_input": False,
        "patterns": [
            "labels cannot be set", "标签字段不能创建", "not on the appropriate screen",
        ]
    },
    "assignee_invalid": {
        "type": "invalid_user",
        "field": "assignee",
        "safe_default_recovery": "retry_without_assignee",
        "retryable": True,
        "requires_user_input": False,
        "patterns": [
            "user", "assignee", "does not exist", "不存在",
        ]
    },
    "permission_denied": {
        "type": "permission_error",
        "field": None,
        "safe_default_recovery": None,
        "retryable": False,
        "requires_user_input": True,
        "patterns": [
            "permission", "403", "not allowed", "无权限",
        ]
    },
    "network_error": {
        "type": "network_error",
        "field": None,
        "safe_default_recovery": "retry",
        "retryable": True,
        "requires_user_input": False,
        "patterns": [
            "timeout", "connection", "network", "ECONNREFUSED",
        ]
    },
}


def classify_error(error_msg: str) -> dict:
    """根据错误消息自动分类错误类型"""
    if not error_msg:
        return {
            "type": "unknown",
            "safe_default_recovery": None,
            "retryable": False,
        }
    msg_lower = error_msg.lower()
    for key, info in ERROR_CLASSIFICATIONS.items():
        for pattern in info["patterns"]:
            if pattern.lower() in msg_lower:
                return {
                    "type": info["type"],
                    "classification_key": key,
                    "field": info["field"],
                    "safe_default_recovery": info["safe_default_recovery"],
                    "retryable": info["retryable"],
                    "requires_user_input": info["requires_user_input"],
                }
    return {
        "type": "unknown",
        "safe_default_recovery": None,
        "retryable": False,
    }


# ══════════════════════════════════════════════════════════════
#  恢复方案生成（移植自 Baize buildDefaultRecoveryFromFailure）
# ══════════════════════════════════════════════════════════════

def build_recovery(operation: dict) -> dict:
    """
    根据失败原因自动生成恢复方案。
    返回结构: {status, summary, reason, actions[]}
    """
    failure = operation.get("failure", {}) or {}
    classification = failure.get("classification", {}) or {}
    recovery_key = classification.get("safe_default_recovery")

    if recovery_key == "submit_supplement":
        return {
            "status": "needs_user_input",
            "summary": "创建 Jira 前需要补充项目 Key。",
            "reason": "Jira 创建必须知道每个 Issue 要写入哪个项目；当前有 Issue 缺少 projectKey。",
            "actions": [
                {
                    "id": "submit_supplement",
                    "kind": "submit",
                    "label": "补充项目 Key",
                    "style": "primary",
                    "requires_confirmation": False,
                    "risk_level": "low",
                    "description": "填写项目 Key 后继续创建。",
                    "inputs": [
                        {"id": "projectKey", "type": "text", "label": "项目 Key", "required": True}
                    ]
                },
                {
                    "id": "cancel",
                    "kind": "cancel",
                    "label": "取消创建",
                    "style": "secondary",
                    "requires_confirmation": False,
                    "risk_level": "low",
                    "description": "取消本次 Jira 创建。"
                }
            ]
        }
    elif recovery_key == "retry_without_labels":
        return {
            "status": "available",
            "summary": "Jira 不支持标签字段，可以移除标签后重试。",
            "reason": "labels 是附加字段；移除后会保留标题、描述、项目、类型、负责人和优先级等核心字段。",
            "actions": [
                {
                    "id": "retry_without_labels",
                    "kind": "safe_retry",
                    "label": "移除标签后重试",
                    "style": "primary",
                    "requires_confirmation": True,
                    "risk_level": "low",
                    "description": "保留其他字段，只移除 labels 后重新创建。"
                },
                {
                    "id": "cancel",
                    "kind": "cancel",
                    "label": "取消创建",
                    "style": "secondary",
                    "requires_confirmation": False,
                    "risk_level": "low",
                }
            ]
        }
    elif recovery_key == "retry":
        return {
            "status": "available",
            "summary": "网络错误，可以重试。",
            "reason": f"操作因网络问题失败: {operation.get('error', '')}",
            "actions": [
                {
                    "id": "retry",
                    "kind": "retry",
                    "label": "重试创建",
                    "style": "primary",
                    "requires_confirmation": False,
                    "risk_level": "low",
                    "description": "重新执行失败的 Jira 创建操作。"
                },
                {
                    "id": "cancel",
                    "kind": "cancel",
                    "label": "取消创建",
                    "style": "secondary",
                    "requires_confirmation": False,
                    "risk_level": "low",
                }
            ]
        }
    else:
        return {
            "status": "not_recoverable",
            "summary": "当前错误还没有可自动执行的安全恢复方案。",
            "reason": operation.get("error", "未知错误"),
            "actions": [
                {
                    "id": "cancel",
                    "kind": "cancel",
                    "label": "取消创建",
                    "style": "secondary",
                    "requires_confirmation": False,
                    "risk_level": "low",
                }
            ]
        }


# ══════════════════════════════════════════════════════════════
#  AI 创建 Issue 溯源（审计分级）
# ══════════════════════════════════════════════════════════════

_AI_CREATED_ISSUES = set()  # AI 创建的任务 key 集合

def register_ai_created_issue(issue_key: str):
    """注册一个 AI 创建的任务"""
    _AI_CREATED_ISSUES.add(issue_key.upper())
    logger.info(f"[Audit] Registered AI-created: {issue_key}")

def is_ai_created_issue(issue_key: str) -> bool:
    """检查任务是否由 AI 创建"""
    return issue_key.upper() in _AI_CREATED_ISSUES

def get_ai_created_count() -> int:
    """返回 AI 创建的任务数量"""
    return len(_AI_CREATED_ISSUES)


# ══════════════════════════════════════════════════════════════
#  OperationCard 生成
# ══════════════════════════════════════════════════════════════

def operation_to_confirm_ui(operation: dict) -> dict:
    """将操作卡转为前端 ConfirmCard.operation 结构"""
    kind = operation.get("kind", "")
    ui_type = kind.replace("jira_", "") if kind.startswith("jira_") else kind
    drafts = operation.get("drafts") or []
    first = drafts[0] if drafts else {}
    ui = {
        "type": ui_type or "unknown",
        "issue_key": first.get("issue_key", ""),
        "summary": first.get("summary", ""),
        "description": (first.get("body") or first.get("description") or "")[:500],
        "project": first.get("projectKey", ""),
        "drafts_count": len(drafts),
        "warnings": operation.get("warnings") or [],
    }
    if kind == "jira_bulk_create" and drafts:
        ui["drafts"] = draft_items_for_ui(drafts)
    return ui


def build_confirm_tool_response(operation: dict, message: str = "") -> dict:
    """工具层返回 + SSE 共用的确认卡 JSON"""
    return {
        "status": "confirm_required",
        "operation_id": operation["id"],
        "operation": operation_to_confirm_ui(operation),
        "result": message or f"请在确认卡上授权后执行（{operation.get('kind', '')}）。",
    }


def resolve_transition_for_target(transitions: list, target_status: str) -> dict:
    """在 Jira transitions 列表中匹配目标状态，返回 {transition_id, transition_name, to_status}。"""
    target = (target_status or "").strip().lower()
    if not target:
        return {}
    aliases = {
        "完成": ("完成", "done", "resolved", "解决", "可发布", "关闭"),
        "关闭": ("关闭", "closed", "done"),
        "处理中": ("处理中", "in progress", "处理", "进行中"),
        "进行中": ("进行中", "in progress", "处理"),
        "待办": ("待办", "to do", "open", "新建"),
    }
    needles = list(aliases.get(target_status, (target,)))
    best = None
    for tr in transitions or []:
        to_name = ((tr.get("to") or {}).get("name") or "").lower()
        tr_name = (tr.get("name") or "").lower()
        for needle in needles:
            n = needle.lower()
            if n in to_name or n in tr_name:
                best = tr
                break
        if best:
            break
    if not best and transitions:
        best = transitions[0]
    if not best:
        return {}
    return {
        "transition_id": str(best.get("id", "")),
        "transition_name": best.get("name", ""),
        "to_status": (best.get("to") or {}).get("name", ""),
    }


def create_transition_operation_card(
    issue_key: str,
    target_status: str,
    transition_id: str = "",
    transition_name: str = "",
    to_status: str = "",
    conversation_id: str = "",
    client_id: str = "",
    user_id: str = "",
) -> dict:
    """生成 Jira 状态流转确认卡"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    operation = {
        "id": f"jira-op-{uuid.uuid4().hex[:12]}",
        "kind": "jira_transition_issue",
        "status": "awaiting_confirmation",
        "conversation_id": conversation_id,
        "client_id": client_id,
        "user_id": user_id,
        "drafts": [{
            "issue_key": issue_key,
            "target_status": target_status,
            "transition_id": transition_id,
            "transition_name": transition_name,
            "to_status": to_status,
        }],
        "warnings": [],
        "created_issues": [],
        "error": None,
        "failure": None,
        "recovery": None,
        "created_at": now,
        "updated_at": now,
    }
    if not issue_key:
        operation["warnings"].append("缺少 issue_key。")
    if not transition_id and not transition_name:
        operation["warnings"].append(
            f"未能解析「{target_status}」对应的 Jira 流转，确认前请检查权限或状态名。"
        )
    logger.info(f"[OpCard] Transition card: {operation['id']} | {issue_key} → {target_status}")
    return operation


def create_comment_operation_card(
    issue_key: str,
    body: str,
    conversation_id: str = "",
    client_id: str = "",
    user_id: str = "",
) -> dict:
    """生成 Jira 评论确认卡"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    operation = {
        "id": f"jira-op-{uuid.uuid4().hex[:12]}",
        "kind": "jira_add_comment",
        "status": "awaiting_confirmation",
        "conversation_id": conversation_id,
        "client_id": client_id,
        "user_id": user_id,
        "drafts": [{"issue_key": issue_key, "body": body}],
        "warnings": [],
        "created_issues": [],
        "error": None,
        "failure": None,
        "recovery": None,
        "created_at": now,
        "updated_at": now,
    }
    if not issue_key:
        operation["warnings"].append("缺少 issue_key。")
    if not (body or "").strip():
        operation["warnings"].append("评论内容为空。")
    logger.info(f"[OpCard] Comment card: {operation['id']} | {issue_key}")
    return operation


def create_operation_card(
    drafts: list,
    conversation_id: str = "",
    client_id: str = "",
    user_id: str = "",
    kind: str = "jira_bulk_create",
) -> dict:
    """
    生成 Jira 操作确认卡。
    
    drafts: [{summary, projectKey, issueType, assignee, priority, labels, description}, ...]
    
    返回操作卡对象：
    {
        id, kind, status, conversation_id, client_id,
        drafts[], warnings[], created_issues[],
        created_at, updated_at
    }
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    operation = {
        "id": f"jira-op-{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "status": "awaiting_confirmation",
        "conversation_id": conversation_id,
        "client_id": client_id,
        "user_id": user_id,
        "drafts": drafts,
        "warnings": _build_warnings(drafts),
        "created_issues": [],
        "error": None,
        "failure": None,
        "recovery": None,
        "created_at": now,
        "updated_at": now,
    }
    logger.info(f"[OpCard] Created: {operation['id']} | {len(drafts)} drafts | warnings: {len(operation['warnings'])}")
    return operation


def _build_warnings(drafts: list) -> list:
    """生成前置校验警告"""
    warnings = []
    for i, d in enumerate(drafts):
        if not d.get("projectKey") or not d["projectKey"].strip():
            warnings.append(f"草稿 #{i+1} 缺少项目 Key，创建前需要补充。")
        if not d.get("summary") or not d["summary"].strip():
            warnings.append(f"草稿 #{i+1} 缺少标题。")
        if not d.get("issueType"):
            warnings.append(f"草稿 #{i+1} 未指定问题类型，将使用默认值 Task。")
    return warnings


# ══════════════════════════════════════════════════════════════
#  草稿箱（draft_card）— 批量创建前先落本地 JSON，禁止直写 Jira
# ══════════════════════════════════════════════════════════════

def _normalize_issue_draft(item: dict, index: int = 0) -> dict:
    d = item if isinstance(item, dict) else {}
    return {
        "summary": (d.get("summary") or d.get("title") or f"草稿任务 #{index + 1}").strip(),
        "projectKey": (d.get("projectKey") or d.get("project_key") or "CT").strip(),
        "issueType": (d.get("issueType") or d.get("issue_type") or "Task").strip(),
        "description": (d.get("description") or "").strip(),
        "assignee": (d.get("assignee") or "").strip(),
        "priority": d.get("priority"),
        "labels": d.get("labels") if isinstance(d.get("labels"), list) else [],
    }


def draft_items_for_ui(items: list) -> list:
    out = []
    for i, raw in enumerate(items or []):
        d = _normalize_issue_draft(raw, i)
        out.append({
            "index": i,
            "summary": d["summary"],
            "projectKey": d["projectKey"],
            "issueType": d["issueType"],
            "description": d["description"][:500],
            "assignee": d.get("assignee") or "",
        })
    return out


def _load_draft_box():
    global _draft_box
    try:
        if os.path.isfile(_DRAFTS_FILE):
            with open(_DRAFTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data.get("drafts") or []:
                if d.get("id"):
                    _draft_box[d["id"]] = d
            if _draft_box:
                logger.info(f"[DraftBox] loaded {len(_draft_box)} drafts")
    except Exception as e:
        logger.warning(f"[DraftBox] load failed: {e}")


def _persist_draft_box():
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with _lock:
            payload = {
                "drafts": list(_draft_box.values()),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        with open(_DRAFTS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[DraftBox] persist failed: {e}")


def create_issues_draft(
    issues_list: list,
    conversation_id: str = "",
    client_id: str = "",
    user_id: str = "",
    source_text: str = "",
) -> dict:
    """批量草稿入箱（虚拟态），返回 draft 记录供 draft_card SSE 使用。"""
    raw = issues_list if isinstance(issues_list, list) else []
    if not raw:
        raise ValueError("issues_list 不能为空")
    items = [_normalize_issue_draft(x, i) for i, x in enumerate(raw)]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    draft = {
        "id": f"draft-{uuid.uuid4().hex[:12]}",
        "status": "awaiting_review",
        "items": items,
        "warnings": _build_warnings(items),
        "conversation_id": conversation_id,
        "client_id": client_id,
        "user_id": user_id,
        "source_text": (source_text or "")[:500],
        "operation_id": None,
        "created_at": now,
        "updated_at": now,
    }
    with _lock:
        _draft_box[draft["id"]] = draft
        _persist_draft_box()
    logger.info(
        f"[DraftBox] draft_card created: {draft['id']} | items={len(items)} | "
        f"summaries={[x['summary'][:40] for x in items[:3]]}"
    )
    return draft


def get_draft(draft_id: str) -> Optional[dict]:
    with _lock:
        return _draft_box.get(draft_id)


def build_draft_tool_response(draft: dict, message: str = "") -> dict:
    items = draft_items_for_ui(draft.get("items") or [])
    preview = message or (
        f"已生成 {len(items)} 条 Jira 草稿，请在草稿卡中核对后批量提交。"
        "Alice 不会未经确认直接创建 Issue。"
    )
    return {
        "status": "draft_required",
        "draft_id": draft["id"],
        "items": items,
        "warnings": draft.get("warnings") or [],
        "result": preview,
    }


def submit_draft_to_operation(draft_id: str, items: Optional[list] = None) -> dict:
    """草稿箱确认 → 升级为正式 operation（awaiting_confirmation），再走 confirm API 写 Jira。"""
    with _lock:
        draft = _draft_box.get(draft_id)
        if not draft:
            raise ValueError("草稿不存在")
        if draft.get("status") not in ("awaiting_review",):
            raise ValueError(f"草稿状态 {draft.get('status')} 不可提交")
        if items:
            draft["items"] = [_normalize_issue_draft(x, i) for i, x in enumerate(items)]
            draft["warnings"] = _build_warnings(draft["items"])
        op = create_operation_card(
            drafts=draft["items"],
            conversation_id=draft.get("conversation_id", ""),
            client_id=draft.get("client_id", ""),
            user_id=draft.get("user_id", ""),
            kind="jira_bulk_create",
        )
        save_operation(op)
        draft["status"] = "promoted"
        draft["operation_id"] = op["id"]
        draft["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _persist_draft_box()
        logger.info(f"[DraftBox] promoted {draft_id} → operation {op['id']}")
        return op


def reject_draft(draft_id: str) -> dict:
    """作废草稿（awaiting_review → rejected）。"""
    with _lock:
        draft = _draft_box.get(draft_id)
        if not draft:
            raise ValueError("草稿不存在")
        if draft.get("status") == "promoted":
            raise ValueError("草稿已提交，请操作确认卡")
        if draft.get("status") == "rejected":
            return draft
        draft["status"] = "rejected"
        draft["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _persist_draft_box()
        logger.info(f"[DraftBox] rejected {draft_id}")
        return draft


# ══════════════════════════════════════════════════════════════
#  状态转换
# ══════════════════════════════════════════════════════════════

def transition(operation: dict, new_status: str, extra: dict = None) -> dict:
    """安全状态转换"""
    current = operation.get("status", "")
    allowed = STATUS_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        raise ValueError(f"无效状态转换: {current} → {new_status}（允许: {allowed}）")

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    operation["status"] = new_status
    operation["updated_at"] = now
    if extra:
        operation.update(extra)
    logger.info(f"[OpCard] {operation['id']}: {current} → {new_status}")
    return operation


def mark_running(operation: dict) -> dict:
    return transition(operation, "running")


def mark_created(operation: dict, created_issues: list) -> dict:
    return transition(operation, "created", {
        "created_issues": created_issues,
        "error": None,
        "failure": None,
    })


def mark_failed(operation: dict, error_msg: str, context: dict = None) -> dict:
    """标记失败并自动分析错误类型"""
    error_type = classify_error(error_msg)
    failure = {
        "plugin": "jira",
        "operation_kind": operation.get("kind", ""),
        "code": error_type.get("type", "UNKNOWN_ERROR"),
        "message": error_msg,
        "failed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "retryable": error_type.get("retryable", False),
        "classification": error_type,
        "context": context or {},
    }
    operation = transition(operation, "failed", {
        "error": error_msg,
        "failure": failure,
    })
    # 自动附加恢复方案
    recovery = build_recovery(operation)
    if recovery["status"] in ("available", "needs_user_input"):
        operation = transition(operation, "recovery_required", {
            "recovery": recovery
        })
    return operation


def mark_rejected(operation: dict) -> dict:
    return transition(operation, "rejected")


# ══════════════════════════════════════════════════════════════
#  内存存储（单进程，与 ai_bridge.py 共享）
# ══════════════════════════════════════════════════════════════

def _persist_operations_index():
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with _lock:
            payload = {"operations": list(_store.values()), "updated_at": time.time()}
        with open(_OPS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[OpCard] persist failed: {e}")


def _load_operations_index():
    paths = [_OPS_FILE, _LEGACY_OPS_INDEX]
    for path in paths:
        try:
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for op in data.get("operations") or []:
                if op.get("id"):
                    _store[op["id"]] = op
            if _store:
                logger.info(f"[OpCard] loaded {len(_store)} operations from {path}")
                if path == _LEGACY_OPS_INDEX and not os.path.isfile(_OPS_FILE):
                    _persist_operations_index()
                return
        except Exception as e:
            logger.warning(f"[OpCard] load from {path} failed: {e}")


_load_operations_index()
_load_draft_box()


def save_operation(op: dict) -> dict:
    with _lock:
        _store[op["id"]] = op
        _persist_operations_index()
    return op


def get_operation(op_id: str) -> Optional[dict]:
    with _lock:
        return _store.get(op_id)


def get_pending_operations(conversation_id: str = "") -> list:
    """获取待确认的操作"""
    with _lock:
        ops = []
        for op in _store.values():
            if op["status"] in ("awaiting_confirmation", "recovery_required"):
                if conversation_id and op.get("conversation_id") != conversation_id:
                    continue
                ops.append(op)
        return sorted(ops, key=lambda o: o["created_at"], reverse=True)


def execute_confirmed_operation(jira_client, operation: dict, user_pat: str = "",
                                skip_labels: bool = False) -> dict:
    """
    用户确认后执行 Jira 写操作（对齐 Baize confirm → runJiraCreateOperation）。
    返回: {created_issues: [...], comment: {...}, message: str}
    """
    kind = operation.get("kind", "")
    if kind == "jira_add_comment":
        draft = (operation.get("drafts") or [{}])[0]
        issue_key = draft.get("issue_key", "")
        body = draft.get("body", "")
        comment = jira_client.add_comment(issue_key, body, user_pat=user_pat)
        return {
            "created_issues": [],
            "comment": comment,
            "message": f"已为 {issue_key} 添加评论。",
        }

    if kind == "jira_bulk_create":
        drafts = operation.get("drafts") or []
        already = operation.get("created_issues") or []
        start_index = len(already)
        created_issues = list(already)
        for index in range(start_index, len(drafts)):
            draft = drafts[index]
            try:
                item = jira_client.create_issue_from_draft(
                    draft, user_pat=user_pat, skip_labels=skip_labels,
                )
                created_issues.append(item)
                register_ai_created_issue(item.get("key", ""))
            except Exception as e:
                err_msg = str(e)
                if not skip_labels and "labels" in err_msg.lower():
                    try:
                        item = jira_client.create_issue_from_draft(
                            draft, user_pat=user_pat, skip_labels=True,
                        )
                        created_issues.append(item)
                        register_ai_created_issue(item.get("key", ""))
                        continue
                    except Exception:
                        pass
                operation["created_issues"] = created_issues
                raise RuntimeError(
                    f"草稿 #{index + 1} 创建失败: {err_msg}"
                ) from e
        keys = ", ".join(i.get("key", "") for i in created_issues if i.get("key"))
        return {
            "created_issues": created_issues,
            "message": f"已创建 {len(created_issues)} 个 Issue: {keys}",
        }

    if kind == "jira_transition_issue":
        draft = (operation.get("drafts") or [{}])[0]
        issue_key = draft.get("issue_key", "")
        jira_client.transition_issue(
            issue_key,
            user_pat=user_pat,
            transition_id=draft.get("transition_id"),
            transition_name=draft.get("transition_name"),
        )
        return {
            "created_issues": [],
            "message": f"已更新 {issue_key} 状态。",
        }

    raise ValueError(f"不支持的操作类型: {kind}")


def supersede_older(conversation_id: str, new_op_id: str):
    """将同一会话中旧的待确认操作标记为被取代"""
    with _lock:
        for op_id, op in list(_store.items()):
            if op_id == new_op_id:
                continue
            if op.get("conversation_id") == conversation_id and op["status"] == "awaiting_confirmation":
                op["status"] = "superseded"
                op["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                logger.info(f"[OpCard] Superseded: {op_id}")
        _persist_operations_index()


# ══════════════════════════════════════════════════════════════
#  自测
# ══════════════════════════════════════════════════════════════

_TEST_CASES = [
    ("labels_unsupported", "Field 'labels' cannot be set. It is not on the appropriate screen, or unknown.", "retry_without_labels"),
    ("missing_project_key", "存在未配置项目 Key 的草稿", "submit_supplement"),
    ("permission", "403 Forbidden: you don't have permission", None),
    ("network", "Connection timeout after 30s", "retry"),
    ("unknown", "Something went wrong unexpectedly", None),
]


def run_self_test():
    """运行自测"""
    import sys
    passed, total = 0, 0

    # 测试 1: 错误分类
    print("\n── 测试 1: 错误分类 ──")
    for name, msg, expected_recovery in _TEST_CASES:
        result = classify_error(msg)
        ok = True
        if expected_recovery == "retry_without_labels" and result.get("type") != "field_not_on_screen":
            ok = False
        elif expected_recovery == "submit_supplement" and result.get("type") != "missing_required_field":
            ok = False
        status = "✓" if ok else "✗"
        print(f"  {status} {name}: {result.get('type')} → recover={result.get('safe_default_recovery')}")
        if ok: passed += 1
        total += 1

    # 测试 2: 确认卡生成
    print("\n── 测试 2: 确认卡生成 ──")
    total += 1
    op = create_operation_card(
        drafts=[
            {"summary": "修复登录页bug", "projectKey": "CT", "issueType": "Bug", "priority": "High"},
            {"summary": "更新用户手册", "projectKey": "", "issueType": "Task"},
        ],
        conversation_id="conv-001",
    )
    if op["status"] == "awaiting_confirmation" and len(op["warnings"]) >= 1:
        print(f"  ✓ 确认卡生成: {op['id']} | status={op['status']} | warnings={len(op['warnings'])}")
        passed += 1
    else:
        print(f"  ✗ 确认卡生成失败")

    # 测试 3: 状态转换
    print("\n── 测试 3: 状态转换 ──")
    save_operation(op)
    total += 4
    op = mark_running(op)
    if op["status"] == "running": passed += 1; print("  ✓ awaiting_confirmation → running")
    else: print("  ✗ running failed")

    op = mark_created(op, [{"key": "CT-9999", "id": "10001"}])
    if op["status"] == "created": passed += 1; print("  ✓ running → created")
    else: print("  ✗ created failed")

    # 模拟失败
    op2 = create_operation_card(
        drafts=[{"summary": "测试labels", "projectKey": "CT", "issueType": "Bug", "labels": ["test"]}],
        conversation_id="conv-002",
    )
    save_operation(op2)
    op2 = mark_running(op2)
    op2 = mark_failed(op2, "Field 'labels' cannot be set. It is not on the appropriate screen, or unknown.")
    if op2["status"] == "recovery_required": 
        passed += 1; print(f"  ✓ failed → recovery_required (auto)")
    else: print(f"  ✗ recovery: {op2['status']}")

    # 恢复方案结构
    recovery = op2.get("recovery", {})
    if recovery.get("status") in ("available", "needs_user_input") and len(recovery.get("actions", [])) >= 1:
        passed += 1; print(f"  ✓ 恢复方案: {recovery['status']} | actions={len(recovery['actions'])}")
    else: print(f"  ✗ 恢复方案缺失")

    # 状态转换验证
    print("\n── 测试 4: 非法状态转换拦截 ──")
    total += 1
    try:
        transition(op, "running")  # created → running 不允许
        print("  ✗ 应该抛出异常但没有")
    except ValueError:
        passed += 1
        print("  ✓ 非法转换被正确拦截")

    print(f"\n{'='*40}")
    print(f"  自测结果: {passed}/{total} 通过 ({passed*100//total}%)")
    if passed == total:
        print(f"  ✅ 全部通过!")
    print(f"{'='*40}\n")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_self_test()
