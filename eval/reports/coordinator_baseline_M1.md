# Coordinator 金标基线 — M1

> **版本**：M1 | **日期**：2026-06-08（首次实跑建档）  
> **数据集**：`backend/eval/datasets/coordinator_m1.yaml`（5 条）

## 如何复现

1. 启动 Hub：`cd backend && py -3 ai_bridge.py`（9099）
2. 配置 `global_config.json`（Jira PAT、DeepSeek Key）
3. 运行：`cd backend && py -3 run_eval.py coordinator_m1`

## M1 基线记录

| 指标 | 值 |
|------|-----|
| 子集用例数 | 5 |
| 通过 / 总数 | **4 / 5（80%）** |
| 平均得分 | **65.0%** |
| 运行命令 | `py -3 backend/run_eval.py coordinator_m1` |
| run_id | eval-1780888450 |

### 分项

| id | 结果 | 得分 | 备注 |
|----|------|------|------|
| coord-001 | ✅ | 100% | |
| coord-003 | ✅ | 85% | |
| coord-004 | ❌ | 0% | 写状态走 HITL 确认卡，未命中旧 rubric「拦截/拒绝」关键词 |
| coord-007 | ✅ | 70% | |
| coord-008 | ✅ | 70% | |

## 发版对比规则

- 发版前 `coordinator_m1` 通过率 **不得低于** 4/5（80%），平均得分不低于 65%。
- coord-004 待 rubric 与 HITL 行为对齐后重评。

## 回归备注

- **2026-06-08**：Hub 实跑建档；coord-004 失败为评测口径与 E2 确认卡行为不一致，非功能回退。
