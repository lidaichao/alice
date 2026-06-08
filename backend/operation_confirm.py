"""Operation confirm execution — shared by JSON and SSE confirm (E2.2)."""
from __future__ import annotations

import logging
from typing import Any, Iterator, Tuple

from hitl_sse import operation_progress, sse_event

logger = logging.getLogger(__name__)
SSE_DONE = b"data: [DONE]\n\n"


def _resolve_user_pat(body: dict) -> str:
    user_pat = ""
    if isinstance(body.get("user_config"), dict):
        user_pat = body["user_config"].get("jira_pat", "")
    return body.get("jira_pat") or user_pat


def _skip_labels_from_body(op: dict, body: dict) -> bool:
    skip = body.get("recovery_action") == "retry_without_labels"
    if op.get("recovery") and op["recovery"].get("pending_action"):
        skip = skip or op["recovery"]["pending_action"] == "retry_without_labels"
    return skip


def execute_operation_confirm(
    jira_client: Any,
    op: dict,
    body: dict,
    *,
    save_operation,
    mark_running,
    mark_created,
    mark_failed,
    execute_confirmed_operation,
) -> Tuple[int, dict]:
    """Run confirm; returns (http_status, json_payload)."""
    from jira_operation_manager import operation_audit_fields, resolve_transition_for_target
    from user_identity import parse_user_id_from_request

    op_id = op["id"]
    user_pat = _resolve_user_pat(body)
    approver_id = parse_user_id_from_request(body=body)
    skip_labels = _skip_labels_from_body(op, body)

    try:
        if body.get("recovery_action") == "submit_supplement":
            from jira_operation_manager import apply_supplement_to_operation

            supplement = body.get("supplement") if isinstance(body.get("supplement"), dict) else body
            op = apply_supplement_to_operation(op, supplement)
            save_operation(op)

        if op.get("kind") == "jira_transition_issue":
            draft = (op.get("drafts") or [{}])[0]
            if not draft.get("transition_id"):
                try:
                    target = draft.get("target_status") or "处理中"
                    transitions = jira_client.list_transitions(
                        draft.get("issue_key", ""),
                        user_pat=user_pat or None,
                    )
                    tr_meta = resolve_transition_for_target(transitions, target)
                    if tr_meta.get("transition_id"):
                        draft.update({
                            "transition_id": tr_meta["transition_id"],
                            "transition_name": tr_meta.get("transition_name", ""),
                            "to_status": tr_meta.get("to_status", ""),
                        })
                        save_operation(op)
                except Exception as te:
                    logger.warning("[OpCard] resolve transition on confirm failed: %s", te)

        op = mark_running(op)
        save_operation(op)
        result = execute_confirmed_operation(
            jira_client, op, user_pat=user_pat, skip_labels=skip_labels
        )
        created = result.get("created_issues") or []
        op = (
            mark_created(op, created, confirmed_by=approver_id)
            if created
            else mark_created(op, [], confirmed_by=approver_id)
        )
        op["last_result_message"] = result.get("message", "")
        save_operation(op)
        from audit_gateway import record_operation_audit

        record_operation_audit(
            actor=approver_id,
            action="operation_confirm",
            operation_id=op_id,
            decision="allow",
            origin="http",
            context={"created_count": len(created)},
        )
        logger.info(
            "[OpCard] Executed: %s | kind=%s | created=%s | confirmed_by=%s",
            op_id,
            op.get("kind"),
            len(created),
            approver_id or "-",
        )
        return 200, {
            "ok": True,
            "message": result.get("message", "操作已完成"),
            "operation": {
                "id": op["id"],
                "status": op["status"],
                "kind": op.get("kind"),
                "created_issues": op.get("created_issues", []),
                **operation_audit_fields(op),
            },
        }
    except Exception as e:
        err_msg = str(e)[:500]
        op = mark_failed(op, err_msg)
        save_operation(op)
        logger.error("[OpCard] Execute failed: %s | %s", op_id, err_msg)
        return 500, {
            "ok": False,
            "error": err_msg,
            "operation": {
                "id": op["id"],
                "status": op["status"],
                "recovery": op.get("recovery"),
            },
        }


def iter_operation_confirm_sse(
    jira_client: Any,
    op: dict,
    body: dict,
    *,
    save_operation,
    mark_running,
    mark_created,
    mark_failed,
    execute_confirmed_operation,
) -> Iterator[bytes]:
    op_id = op["id"]
    yield operation_progress("start", "开始执行 Jira 写入…", percent=10, op_id=op_id)
    yield operation_progress("running", "正在调用 Jira API…", percent=45, op_id=op_id)
    status, payload = execute_operation_confirm(
        jira_client,
        op,
        body,
        save_operation=save_operation,
        mark_running=mark_running,
        mark_created=mark_created,
        mark_failed=mark_failed,
        execute_confirmed_operation=execute_confirmed_operation,
    )
    if payload.get("ok"):
        yield operation_progress("done", payload.get("message", "操作已完成"), percent=100, op_id=op_id)
        yield sse_event("operation_complete", payload)
    else:
        yield operation_progress("failed", payload.get("error", "操作失败"), percent=100, op_id=op_id)
        yield sse_event("operation_error", payload)
    yield SSE_DONE
