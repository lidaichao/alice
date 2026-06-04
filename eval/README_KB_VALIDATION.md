# Alice 多数据源知识库自动验证

协调者把「已知正确答案」写进用例表一次，由脚本反复对照 Alice 的回答与快车道，无需在 UI 里手工问遍五源。

## 三层验证

| Tier | 测什么 | 命令 |
|------|--------|------|
| **1** | Jira 离线槽位 / JQL 生成 | `--tier 1` 或 `--offline-only` |
| **2** | 在线快车道 `plugin_state` + 结构化 Oracle | `--tier 2` |
| **3** | LLM 对照 `ground_truth`（仅 `oracle_llm`） | `--tier 3` |

统一入口：

```bash
py -3 scripts/run_kb_regression.py --tier all
py -3 scripts/run_kb_regression.py --tier 2 --filter sources=jira,fisheye
py -3 scripts/run_kb_regression.py --offline-only
```

报告：

- 最新：`eval/reports/kb_regression_latest.md`
- 带时间戳：`eval/reports/kb_regression_<timestamp>.md`

## 环境变量

| 变量 | 用途 |
|------|------|
| `ALICE_BASE_URL` | 默认 `http://127.0.0.1:9099` |
| `JIRA_PAT` | 在线 Jira / FishEye 用例 |
| `JIRA_PROJECTS` | 如 `CT` |
| `DEEPSEEK_KEY` | Tier3 LLM 裁判（或 `backend/global_config.json`） |

启动后端：

```bash
py -3 backend/ai_bridge.py
```

## 用例表

主表：[`eval/data/testset_kb_matrix.csv`](data/testset_kb_matrix.csv)

| 列 | 说明 |
|----|------|
| `ground_truth` | 协调者标准答案（Tier3 / 文档） |
| `verdict_mode` | `oracle_struct` / `oracle_llm` / `human_only` |
| `expected_plugins` | 分号分隔，须命中其一 |
| `forbidden_plugins` | 分号分隔，不得出现 |
| `must_contain_any` | 回答至少含其一 |
| `must_not_contain` | 回答不得含 |

维护流程：FAIL → 判断 `alice_bug` / `stale_oracle` / `flaky_env` → 更新 CSV。

## 相关脚本

| 脚本 | 说明 |
|------|------|
| `scripts/run_kb_regression.py` | **主回归入口** |
| `scripts/test_jira_accuracy_e2e.py` | Jira 专项（已复用 `eval/lib/sse_collect`） |
| `eval/jira_accuracy_baseline.py` | Jira 离线基线报告 |
| `eval/benchmark.py` | 5 道全能黄金题 + 裁判 |
| `eval/run_tests.py` | chaos 题库 LLM 裁判 |

## Admin API（子集）

```http
GET  /v1/admin/eval/datasets
POST /v1/admin/eval/run/kb_matrix
```

数据集：[`backend/eval/datasets/kb_matrix.yaml`](../backend/eval/datasets/kb_matrix.yaml)（5 条冒烟；完整矩阵见 CSV）。

## PASS 定义

- **Tier2**：`expected_plugins` 命中、无 `forbidden_plugins`、`must_contain` / `must_not_contain` 通过
- **oracle_llm**：Tier2 通过且裁判 `faithfulness=1` 且 `relevance=1`
- **human_only**：仅 Tier2 车道；质量列报告为待人工勾选

## 协调者最少人工

1. 全量跑 `--tier all`
2. 只读报告 **Failed cases**
3. 发版前 UI 手测 SOP 5 条冒烟即可
