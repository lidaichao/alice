# 里程碑 M3 — 自动化交付记录（E4 + E6）

| 字段 | 值 |
|------|-----|
| 里程碑 | M3（近一期第 16 周） |
| 版本 | v1.0.6 |
| 完成条件 | CI_GATE_OK + WBS `[x]`（无人工签字） |

## 交付摘要

- **E4** `ALICE_HUB_ONLY_JIRA`、客户端可无 PAT → [E4_hub_credentials_migration.md](../../docs/master/E4_hub_credentials_migration.md)
- **E6** 文档骨架、memory 按 intent 过滤、作业通道摘要、catalog hybrid、`ALICE_HYBRID_RAG`

## 自动化门禁

同 M2；Hub 在线时 smoke + `e2e_short_draft_memory.py` 覆盖草稿/记忆 HTTP 路径。
