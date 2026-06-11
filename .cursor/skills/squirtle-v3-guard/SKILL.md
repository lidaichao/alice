---
name: squirtle-v3-guard
description: >-
  When Squirtle is about to commit code that touches backend ai_bridge,
  agent_graph, HITL bridges, or n8n integration, run the v3.0 execution
  guard checklist to prevent production failures from mock leakage,
  missing timeouts, SSE zombie connections, or stale imports.
---

# v3.0 执行守卫（提交前自检）

> 来源：`ALICE_V3_RESTRUCTURE_PLAN.md` §八 22 条约束

## 核心检查（触及即查）

| # | 检查项 |
|---|--------|
| 1 | MOCK_N8N 走环境变量，未硬编码 |
| 2 | 路由入口有 Pydantic BaseModel 校验 |
| 3 | idempotency_key 正则清洗过 `[^a-zA-Z0-9\-]` |
| 4 | LLM 调用有 `future.result(timeout=60)` |
| 5 | 前端 useEffect cleanup 有 `AbortController.abort()` |
| 6 | 后端 SSE Generator 捕获了 `GeneratorExit` |
| 7 | 日志用 `loguru` + `TraceID` + `INFO` 级别 + 50MB 滚动 |
| 8 | 无 `import faiss` / `jira_api` / `react_runner` / `workflow_engine` |
| 9 | n8n 工作流 JSON 已导出覆盖 Git |
| 10 | 生产环境禁止开启 `ALICE_MOCK_N8N` |

## 不触发场景

- 纯前端改动不涉及 SSE/API → 不用跑全表
- 纯文档更新 → 跳过
