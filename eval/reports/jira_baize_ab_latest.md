# Alice vs Baize Jira A/B 报告

> 生成时间: 2026-06-04 20:29:31
> Alice: `http://127.0.0.1:9099` | Baize: `未配置 BAIZE_BASE_URL`

## 1. Alice 离线 JQL（规则引擎）
- 通过: **10/10**

| 问句 | JQL 片段 |
|------|----------|
| 帮我查一下本周需要完成的任务有哪些？ | `project = "CT" AND assignee = currentUser() AND status NOT IN ("完成", "` |
| 统计张三本周未完成的 Jira 任务 | `project = "CT" AND (assignee = "张三" OR "任务负责人" = "张三") AND status NOT ` |
| 项目 CT 有哪些进行中的 bug？ | `project = "CT" AND status in ("进行中", "In Progress") AND issuetype = "B` |
| 和球员系统属性有关的 Jira 任务 | `project = "CT" AND (summary ~ "球员" OR description ~ "球员" OR summary ~ ` |
| 查一下 CT-10888 的详情 | `project = "CT" ORDER BY updated DESC` |
| 写一份本周 CT 项目周报 | `project = "CT" AND updated >= "2026-06-01" ORDER BY updated DESC` |
| CT-10888 提交了什么代码 | `project = "CT" ORDER BY updated DESC` |
| 帮我创建一个新的 Jira bug | `project = "CT" AND issuetype = "Bug" ORDER BY updated DESC` |
| 今天 Jira 上没有匹配的任务时 | `project = "CT" AND updated >= "2026-06-04" ORDER BY updated DESC` |
| 李四的任务列表 | `project = "CT" AND (assignee = "李四" OR "任务负责人" = "李四") ORDER BY update` |

## 2. 同问句 Live 搜索（Alice API vs Baize 可选）

| 问句 | Alice total | Alice JQL | Baize |
|------|-------------|-----------|-------|
| 帮我查一下本周需要完成的任务有哪些？ | 0 | `project = "CT" AND assignee = currentUser() AND st` | 跳过 |
| 统计张三本周未完成的 Jira 任务 | 0 | `project = "CT" AND (assignee = "张三" OR "任务负责人" = "` | 跳过 |
| 项目 CT 有哪些进行中的 bug？ | 0 | `project = "CT" AND status in ("进行中", "In Progress"` | 跳过 |
| 和球员系统属性有关的 Jira 任务 | 2594 | `project = "CT" AND (summary ~ "球员" OR description ` | 跳过 |
| 查一下 CT-10888 的详情 | 8331 | `project = "CT" ORDER BY updated DESC` | 跳过 |
| 写一份本周 CT 项目周报 | 316 | `project = "CT" AND updated >= "2026-06-01" ORDER B` | 跳过 |
| CT-10888 提交了什么代码 | 8331 | `project = "CT" ORDER BY updated DESC` | 跳过 |
| 帮我创建一个新的 Jira bug | 0 | `project = "CT" AND issuetype = "Bug" ORDER BY upda` | 跳过 |

## 3. 准确性对齐路线图

| 能力 | Baize | Alice 当前 | 优先级 |
|------|-------|------------|--------|
| NL→结构化 query | Claude Code JSON | 规则 parse_query | P0 逐步加 LLM 槽位 |
| JQL 失败恢复 | LLM jira_search_recovery | 规则 + **LLM recovery**（JIRA_LLM_RECOVERY） | P0 已接入 |
| 负责人字段 | Admin fieldMappings | Admin JIRA_FIELD_MAPPINGS | P0 已加 UI |
| 用户消歧 | LLM 自动选 | 仅 supplement 卡片 | P1 |
| Bug 分析/批量导入 | 完整流水线 | Phase 4 占位 | P2 |

## 4. 对话探针 

协调者可将历史问句追加到 `eval/data/testset_jira_accuracy.csv` 后重跑本脚本。