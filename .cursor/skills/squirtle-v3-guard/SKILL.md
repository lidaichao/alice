---
name: squirtle-v3-guard
description: >-
  v3.0 execution guard for alice/ archive touches only (ai_bridge,
  agent_graph, HITL, n8n). Do NOT use for AliceV2 — use
  squirtle-alicev2-guard instead.
---

# v3.0 执行守卫（v3.2 归档线 · 仅 touch `alice/` 时）

> **AliceV2 活仓不适用本 Skill** → 用 `squirtle-alicev2-guard`

> 来源：`ALICE_V3_RESTRUCTURE_PLAN.md` §八

| # | 检查项 |
|---|--------|
| 1 | MOCK_N8N 走环境变量，未硬编码 |
| 2 | 路由入口有 Pydantic BaseModel 校验 |
| 3 | idempotency_key 正则清洗 |
| 4 | LLM 调用有 `future.result(timeout=60)` |
| 5 | 前端 useEffect cleanup 有 `AbortController.abort()` |
| 6 | SSE Generator 捕获 `GeneratorExit` |
| 7 | 日志用 `loguru` + `TraceID` |
| 8 | 无 stale import（faiss/jira_api/react_runner 等） |
| 9 | n8n 工作流 JSON 已导出 |
| 10 | 生产禁止 `ALICE_MOCK_N8N` |

纯文档 / 纯 aliceV2 改动 → 跳过。
