# Jira 查询工具 (query_jira_issues)

## 功能
查询 Jira 系统中的 Issue（任务、缺陷、需求），支持 JQL 语法。

## 执行规则
1. 根据用户意图自动生成 JQL 查询语句
2. 默认最多返回 5 条结果
3. 读操作，不需要用户确认
4. 不要修改或创建任何 Jira Issue

## JQL 参考
- 查我的任务: `assignee = currentUser() ORDER BY updated DESC`
- 查未关闭Bug: `issuetype = Bug AND status != Closed`
- 按优先级排序: `ORDER BY priority DESC`

## 审计规则
- 仅允许 search 操作
- 不允许修改 Issue 字段
- 不允许创建或删除 Issue
