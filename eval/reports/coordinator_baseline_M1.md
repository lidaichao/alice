# Coordinator 金标基线 — M1

> **版本**：M1 | **日期**：2026-06-05  
> **数据集**：`backend/eval/datasets/coordinator_m1.yaml`（5 条）+ 全量 `eval/data/testset_kb_matrix.csv` 中 `coord-*`

## 如何复现

1. 启动 Hub：`cd backend && py -3 ai_bridge.py`（9099）
2. 配置 `global_config.json`（Jira PAT、DeepSeek Key）
3. 运行：
   - 子集：`cd backend && py -3 run_eval.py coordinator_m1`
   - 全量协调者：`py -3 scripts/run_coordinator_eval.py`（同步 questions.txt 并生成 `协调者报告_latest.md`）

## M1 基线记录（首次建档）

| 指标 | 值 |
|------|-----|
| 子集用例数 | 5 |
| 通过 / 总数 | _待 Hub 上跑后填写_ |
| 平均得分 | _待填_ |
| 运行命令 | `py -3 backend/run_eval.py coordinator_m1` |
| run_id | _待填_ |

## 发版对比规则

- 发版前 `coordinator_m1` 通过率 **不得低于** 上表基线。
- 全量协调者回归失败项须记入本文件「回归备注」并评估是否放行。

## 回归备注

_（每次发版后追加）_
