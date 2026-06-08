"""
MailboxStore — M2 async task queue (SQLite, C8).

Boundary (M2.6 / C2):
  - Mailbox stores async work payloads and execution results only.
  - It does NOT store HITL approval state (awaiting_confirmation, etc.).
  - `operation_id` is an optional foreign reference to jira_operation_manager,
    not a substitute for mailbox_task_id.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("mailbox-store")

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DEFAULT_DB = _DATA_DIR / "mailbox.db"
_SCHEMA_FILE = Path(__file__).resolve().parent / "mailbox_schema.sql"

VALID_STATUSES = frozenset({"pending", "claimed", "done", "failed"})
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"claimed", "failed"}),
    "claimed": frozenset({"done", "failed"}),
    "done": frozenset(),
    "failed": frozenset(),
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
    result = None
    if row["result_json"]:
        try:
            result = json.loads(row["result_json"])
        except json.JSONDecodeError:
            result = row["result_json"]
    return {
        "id": row["id"],
        "mailbox_task_id": row["id"],
        "status": row["status"],
        "assignee": row["assignee"],
        "payload": payload,
        "payload_json": row["payload_json"],
        "result": result,
        "result_json": row["result_json"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "operation_id": row["operation_id"],
    }


class MailboxStore:
    """Thread-safe SQLite store for mailbox_tasks."""

    def __init__(self, database: str | Path | None = None) -> None:
        self._db_path = str(database if database is not None else _DEFAULT_DB)
        self._lock = threading.RLock()
        self._local = threading.local()
        self._ensure_data_dir()
        self.init_schema()

    def _ensure_data_dir(self) -> None:
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            self._local.conn = conn
        return conn

    def init_schema(self) -> None:
        sql = _SCHEMA_FILE.read_text(encoding="utf-8")
        with self._lock:
            conn = self._connect()
            conn.executescript(sql)
            conn.commit()
        logger.info("[Mailbox] schema ready db=%s", self._db_path)

    def create_task(
        self,
        *,
        assignee: str,
        payload: dict[str, Any],
        operation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if not (assignee or "").strip():
            raise ValueError("assignee 不能为空")
        if not isinstance(payload, dict):
            raise ValueError("payload 必须为 JSON 对象")
        task_id = f"mbox-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        payload_json = json.dumps(payload, ensure_ascii=False)
        op_ref = (operation_id or "").strip() or None
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO mailbox_tasks
                    (id, status, assignee, payload_json, result_json, created_at, updated_at, operation_id)
                VALUES (?, 'pending', ?, ?, NULL, ?, ?, ?)
                """,
                (task_id, assignee.strip(), payload_json, now, now, op_ref),
            )
            conn.commit()
        logger.info("[Mailbox] dispatch %s assignee=%s", task_id, assignee.strip())
        return self.get_task(task_id) or {"id": task_id}

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        if not (task_id or "").strip():
            return None
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM mailbox_tasks WHERE id = ?",
                (task_id.strip(),),
            ).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 200))
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            st = status.strip().lower()
            if st not in VALID_STATUSES:
                raise ValueError(f"非法 status: {status}")
            clauses.append("status = ?")
            params.append(st)
        if assignee:
            clauses.append("assignee = ?")
            params.append(assignee.strip())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT * FROM mailbox_tasks
            {where}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)
        with self._lock:
            conn = self._connect()
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_task(r) for r in rows]

    def update_task(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        result: Any = None,
        assignee: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        task = self.get_task(task_id)
        if not task:
            return None
        new_status = status.strip().lower() if status else task["status"]
        if new_status not in VALID_STATUSES:
            raise ValueError(f"非法 status: {status}")
        if new_status != task["status"]:
            allowed = STATUS_TRANSITIONS.get(task["status"], frozenset())
            if new_status not in allowed:
                raise ValueError(
                    f"非法状态转移: {task['status']} → {new_status}",
                )
        result_json = task.get("result_json")
        if result is not None:
            result_json = json.dumps(result, ensure_ascii=False)
        new_assignee = assignee.strip() if assignee else task["assignee"]
        now = _now_iso()
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                UPDATE mailbox_tasks
                SET status = ?, result_json = ?, assignee = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_status, result_json, new_assignee, now, task_id),
            )
            conn.commit()
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        """Test helper — remove a task row."""
        with self._lock:
            conn = self._connect()
            cur = conn.execute("DELETE FROM mailbox_tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cur.rowcount > 0


_default_store: Optional[MailboxStore] = None
_singleton_lock = threading.Lock()


def get_mailbox_store() -> MailboxStore:
    """Process-wide singleton (default backend/data/mailbox.db)."""
    global _default_store
    if _default_store is None:
        with _singleton_lock:
            if _default_store is None:
                _default_store = MailboxStore()
    return _default_store
