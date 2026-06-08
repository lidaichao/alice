-- M2 Mailbox async task queue (SQLite, C8 — no Redis)
-- Persisted at backend/data/mailbox.db by default.

CREATE TABLE IF NOT EXISTS mailbox_tasks (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'claimed', 'done', 'failed')),
    assignee        TEXT NOT NULL DEFAULT '',
    payload_json    TEXT NOT NULL,
    result_json     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    operation_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_mailbox_tasks_status
    ON mailbox_tasks (status);

CREATE INDEX IF NOT EXISTS idx_mailbox_tasks_assignee
    ON mailbox_tasks (assignee);

CREATE INDEX IF NOT EXISTS idx_mailbox_tasks_status_assignee
    ON mailbox_tasks (status, assignee);
