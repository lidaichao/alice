---
name: squirtle-roadmap
description: >-
  When Squirtle needs to understand which blueprint document governs the
  current development phase, check version cycle status, or update WBS
  progress markers in the blueprint, consult the document hierarchy rules.
---

# Alice 蓝图校准

## 唯一路径文档

| 文档 | 作用 |
|------|------|
| `docs/master/alice三期蓝图计划.md` | 历史 WBS + 里程碑 + 修订记录 |
| `docs/v3.0/ALICE_V3_RESTRUCTURE_PLAN.md` | **v3.0 WBS + 架构方案 + 约束规则**（当前最高优先级） |
| `coordinator-rabbit/docs/ALICE_V3_RESTRUCTURE_PLAN.md` | 兔子工作区版（详细版，以该版为权威） |

## 执行规则

1. 不扩大范围——新 Epic 须先写入蓝图 §5
2. 不引入 Redis/Temporal（C8）
3. 客户端不直连 Jira（E4）
4. 发布前满足 §6.1 门禁（smoke/e2e/eval）

## 进度回写

完成 WBS 项后在 `alice三期蓝图计划.md` 修订记录追加版本号 + 打勾。
