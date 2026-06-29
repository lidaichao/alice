---
name: squirtle-jira-ops
description: >-
  When Squirtle needs to query, transition, or create Jira issues via the
  REST API (search, read detail, check transitions, change status, add
  comments, create bugs/tasks/subtasks). Includes workflow diagrams, transition
  IDs, issue type IDs, member names, and common pitfalls.
---

# Jira 操作参考手册

## 连接信息

| 项 | 值 |
|----|-----|
| Base URL | `http://ctjira1.lmdgame.com:8080` |
| PAT | 见协调者提供的凭据（每次新会话由协调者注入） |
| 账号 | squirtle (JIRAUSER10904) |
| 项目 | AL |

## Issue Type 速查

| ID | 类型 | 谁创建 |
|-----|------|:--:|
| `10000` | 长篇故事 (Epic) | 卡罗尔 |
| `10701` | 任务（父任务） | 卡罗尔 |
| `10702` | 子任务 | 卡罗尔 |
| `10011` | 缺陷 | 夏洛克 |

## 状态流转对照

### 任务/子任务（IssueType 10701/10702）

```
Open (1) →[61] 开发完成→ 完成 (10012) ← 终态
         →[41] 关闭 → 拒绝/取消
```

### 缺陷（IssueType 10011）

```
待修复 (10121) →[11] 开始处理→ 处理中 (3) →[21] 已处理完成→ 已解决 (10117)
                                                                  →[31] QA通过→ 可发布
                                                                  →[41] 未修复→ 待修复
```

### 杰尼龟常用流转

| IssueType | from → to | id | 需 resolution |
|-----------|-----------|----|:--:|
| 缺陷 | 待修复→处理中 | `11` | 否 |
| 缺陷 | 处理中→已解决 | `21` | **是** (`10000`) |
| 任务/子任务 | Open→完成 | `61` | 否 |

## 已知成员（assignee 用 Jira name）

| name | 角色 |
|------|------|
| rabbit | 兔子 (CTO) |
| carroll | 卡罗尔 (PM) |
| squirtle | 杰尼龟 (Dev) |
| sherlock | 夏洛克 (QA) |

## 踩坑

1. PowerShell `curl` 不兼容 → 一律用 Python `requests`
2. assignee 用 Jira name（`rabbit`），不用 key（`JIRAUSER10903`）
3. description 用 Jira Wiki 标记（`h2.` / `#`），不用 Markdown
4. version 用对象 `{"name": "v3.1-rc6"}`，不用字符串

## 整体工作流

```
卡罗尔创建父任务 + 子任务（经办人=rabbit）
  → 兔子诊断 → 子任务经办人改为 squirtle
    → 协调员转发兔子指令
      → 杰尼龟执行
        → 战报 + 子任务→[61] 完成
          → 父任务同步→[61] 完成
```

## 任务创建模板

```python
import requests

BASE = "http://ctjira1.lmdgame.com:8080"
PAT = "<由协调者提供>"
HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

# 父任务 (10701)
requests.post(f"{BASE}/rest/api/2/issue", headers=HEADERS, json={
    "fields": {
        "project": {"key": "AL"},
        "summary": "【模块】简述",
        "description": "📄 需求：xxx\n📌 概述：xxx",
        "issuetype": {"id": "10701"},
        "priority": {"id": "2"},
        "assignee": {"name": "rabbit"}
    }
})

# 子任务 (10702) 挂在 AL-8 下
requests.post(f"{BASE}/rest/api/2/issue", headers=HEADERS, json={
    "fields": {
        "project": {"key": "AL"},
        "parent": {"key": "AL-8"},
        "summary": "【前端】具体拆解项",
        "issuetype": {"id": "10702"},
        "assignee": {"name": "rabbit"}
    }
})
```
