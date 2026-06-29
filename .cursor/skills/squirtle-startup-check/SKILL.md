---
name: squirtle-startup-check
description: >-
  When starting a new Cursor session or when the coordinator forwards a
  Rabbit change notification, run startup verification against cross-repo
  documents. AliceV2 is the active line; v3.2 alice/ is archive read-only.
---

# 会话开工检查

每次新对话开始时（优先级最高）。

## AliceV2 活仓（默认）

1. 读 `coordinator-rabbit/SOURCE_OF_TRUTH.md` → 确认文档路径与权限
2. 读 `pm-Carroll/AliceV2_开发计划_总纲_v1.0.md` → 已定决策、首跑范围、八步门禁
3. 读 `coordinator-rabbit/CURRENT_SPRINT.md` → Epic AL-301 进度
4. 读 `coordinator-rabbit/TEAM_CHANNEL.md` 首条 @杰尼龟 → 最新令与门禁状态

## v3.2 归档线（仅维护旧仓时）

1. 读 `alice/docs/v3.0/INDEX.md`
2. 读 `coordinator-rabbit/docs/ALICE_V3_RESTRUCTURE_PLAN.md`

## 权限边界

| 可改 | 只读 |
|------|------|
| `H:\workbuddy\aliceV2/` 全部 | `pm-Carroll/*` 总纲 |
| `alice/.cursor/rules/` | `coordinator-rabbit/docs/*` |
| `alice/` **仅** tag/快照/export | `coordinator-rabbit/.cursor/rules/rabbit-*` |

**禁止**在 `alice/` 写 AliceV2 功能。禁止复制方案文档到 alice 仓库。

## 收到兔子变更通知

协调者转发后，立刻读变更涉及文档，确认 V2 / 归档线方向对齐。
