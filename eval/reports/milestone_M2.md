# 里程碑 M2 — 自动化交付记录（E1 + E2 + E5）

| 字段 | 值 |
|------|-----|
| 里程碑 | M2（近一期第 8 周） |
| 版本 | v1.0.6 |
| 完成条件 | CI_GATE_OK + WBS `[x]`（无人工签字） |

## 交付摘要

- **E1** 编排绞杀者：`chat_orchestrator`、`plugin_gateway`、`react_runner`
- **E2** HITL：progress SSE、F5 草稿恢复、recovery（含 submit_supplement）
- **E5** 路由消歧：confidence 门槛、`intent_disambiguation` SSE

## 自动化门禁

```text
py -3 scripts/ci_gate.py  →  CI_GATE_OK
```

集成（Hub `9099` 在线时）：

```text
set ALICE_RUN_INTEGRATION=1
py -3 scripts/ci_gate.py
```
