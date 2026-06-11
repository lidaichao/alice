---
name: squirtle-startup-check
description: >-
  When starting a new Cursor session or when the coordinator forwards a
  Rabbit change notification, run the three-point startup verification
  against cross-repo documents to confirm version alignment and file
  integrity. Use at the very beginning of every new conversation.
---

# 会话开工三检

每次新对话开始时（优先级最高）。

## 三步

1. 读 `alice/docs/v3.0/INDEX.md` → 确认文档权威位置
2. 读 `coordinator-rabbit/docs/ALICE_V3_RESTRUCTURE_PLAN.md` → 确认版本号、WBS 阶段
3. 读 `coordinator-rabbit/SOURCE_OF_TRUTH.md` → 对照注册表检查 alice 仓库：缺了去问、多了过期就删

## 单一真源

所有方案文档以兔子工作区 `H:\workbuddy\coordinator-rabbit` 为唯一权威。
禁止自行复制方案文档到 alice 仓库。

## 权限边界

| 可改 | 只读 |
|------|------|
| `alice/backend/` 所有 .py | `coordinator-rabbit/docs/*` |
| `alice/frontend/` | `alice/specs/*.md` |
| `alice/.cursor/rules/` | `coordinator-rabbit/.cursor/rules/rabbit-*.mdc` |

## 收到兔子变更通知

协调者转发「🔔 兔子变更通知」后，立刻读取变更涉及的文档，确认方向对齐。
