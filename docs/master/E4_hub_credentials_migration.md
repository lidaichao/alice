# E4 — Hub 独占 Jira 凭据迁移指南

> 版本：v1.0 | 日期：2026-06-05

## 目标

- 客户端 **不再必填** `jira_pat`；Jira 读写统一经 Hub 使用 Admin / `global_config.json` 中的 PAT。
- 符合架构宪法 **C1**：客户端不直连 Jira。

## Hub 侧

1. 在 Admin 或 `backend/global_config.json` 配置 `JIRA_PAT`、`JIRA_URL`。
2. 启动 Hub 前设置环境变量（推荐生产）：

```bash
set ALICE_HUB_ONLY_JIRA=1
```

启用后：`parse_user_config` 忽略请求体中的 `jira_pat`，一律使用 Hub 全局 PAT。

## 客户端侧

1. `sessionStorage.alice_runtime_config` 中 **可删除** `jira_pat` 字段。
2. 保留 **Hub URL**（及 DeepSeek Key 若仍由客户端携带）。
3. 确认 / 拒绝 / 草稿提交：`buildJiraWriteRequestBody()` 在无 PAT 时不发送 `jira_pat` 字段。

## 回滚

- 取消 `ALICE_HUB_ONLY_JIRA` 或在客户端恢复 `jira_pat`，即回退到「客户端可携带 PAT」模式。

## 验收

- [ ] 客户端空 `jira_pat` 下可完成 Jira 搜索（经 Hub）
- [ ] 确认卡 `POST /operations/<id>/confirm` 成功
- [ ] 无浏览器直连 `*.atlassian.net` 请求（网络面板）
