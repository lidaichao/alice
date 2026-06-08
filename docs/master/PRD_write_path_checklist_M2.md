# M2 — 写路径自动化覆盖（PRD #14–17）

> 不要求人工点验签字。Hub 集成由 `scripts/e2e_short_draft_memory.py` 覆盖；recovery 由 `test_recovery_supplement.py` 覆盖。

| # | 场景 | 自动化 |
|---|------|--------|
| W1 | 批量创建草稿 | e2e `POST /drafts` + `draft_card` SSE（需 Hub） |
| W2 | 草稿 → confirm_card | e2e `POST /drafts/:id/confirm` |
| W3 | 授权写入 + progress | `operation_confirm` SSE + 单测 hitl_sse |
| W4 | 拒绝 | e2e `POST /operations/:id/reject` |
| W5 | 标签 recovery | ConfirmCard `retry_without_labels` |
| W5b | 缺 projectKey recovery | `test_recovery_supplement.py` |
| W6 | 状态流转 | `scripts/e2e_w6_transition.py`（`ALICE_RUN_W6=1` + `W6_ISSUE_KEY`） |
