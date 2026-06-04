# Jira 准确性基线报告 (Phase 0)

- 用例数: 10
- 可生成 JQL: 10/10

| 问题 | 意图 | 车道(预期/实际) | JQL 片段 |
|------|------|-----------------|----------|
| 帮我查一下本周需要完成的任务有哪些？ | jira_query | structured_search/structured_search | `project = "CT" AND assignee = currentUser() AND status NOT IN ("完成", "关闭", "已解决"` |
| 统计张三本周未完成的 Jira 任务 | jira_query | structured_search/structured_search | `project = "CT" AND (assignee = "张三" OR "任务负责人" = "张三") AND status NOT IN ("完成", ` |
| 项目 CT 有哪些进行中的 bug？ | engineering_readonly | structured_search/structured_search | `project = "CT" AND status in ("进行中", "In Progress") AND issuetype = "Bug" ORDER ` |
| 和球员系统属性有关的 Jira 任务 | ordinary_chat | structured_search/structured_search | `project = "CT" AND (summary ~ "球员" OR description ~ "球员" OR summary ~ "员系" OR de` |
| 查一下 CT-10888 的详情 | jira_query | issue_key_vip/other | `project = "CT" ORDER BY updated DESC` |
| 写一份本周 CT 项目周报 | jira_query | weekly_vip/structured_search | `project = "CT" AND updated >= "2026-06-01" ORDER BY updated DESC` |
| CT-10888 提交了什么代码 | jira_query | react_commits/other | `project = "CT" ORDER BY updated DESC` |
| 帮我创建一个新的 Jira bug | jira_write | write_confirm/other | `project = "CT" AND issuetype = "Bug" ORDER BY updated DESC` |
| 今天 Jira 上没有匹配的任务时 | ordinary_chat | structured_search/structured_search | `project = "CT" AND updated >= "2026-06-04" ORDER BY updated DESC` |
| 李四的任务列表 | ordinary_chat | structured_search/structured_search | `project = "CT" AND (assignee = "李四" OR "任务负责人" = "李四") ORDER BY updated DESC` |

## 与 Baize 差距摘要

- Baize: Claude Code 结构化 query + buildResolvedJql + analyzeIssues 再回答
- Alice (本基线后): 规则 parse_query + build_resolved_jql + 读直通车
- 待 A/B: 同 PAT 下协调者 5–10 条历史问句对比
