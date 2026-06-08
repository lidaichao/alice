# 里程碑 M3 — 内部「日常可用」签字纪要

| 字段 | 值 |
|------|-----|
| 里程碑 | M3（近一期第 16 周） |
| 日期 | 2026-06-05 |
| 范围 | E4 Hub 凭据 + E6 上下文/RAG 骨架 |

## E4 交付

- `ALICE_HUB_ONLY_JIRA=1` 时 Hub 独占 PAT
- 客户端 `buildJiraWriteRequestBody` 可无 `jira_pat`
- 迁移说明：[E4_hub_credentials_migration.md](../../docs/master/E4_hub_credentials_migration.md)

## E6 交付

- E6.1 超长文档骨架模式（`doc_content_extractor`）
- E6.3 浅层记忆按 intent 过滤
- E6.4 作业通道 Issue Key + 诉求摘要注入 ReAct
- E6.2 KB-id / Issue Key 穿透：`catalog_hybrid.boost_catalog_entries`
- E6.5 hybrid：`ALICE_HYBRID_RAG=1` 时目录检索附加 `search_doc_chunks`

## 日常可用标准（勾选）

- [ ] 内部 3 人连续 3 天使用 Hub + 桌面端无阻塞性故障
- [ ] M1 + M2 发布门禁全部通过
- [ ] E4 迁移在测试环境完成一轮

## 签字

| 角色 | 姓名 | 日期 |
|------|------|------|
| 研发负责人 | | |
| 产品 | | |
