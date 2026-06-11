---
name: squirtle-pre-dev
description: >-
  When Squirtle receives a development order from Rabbit that includes Jira
  subtask IDs (10702), task IDs (10701), or bug IDs (10011), run mandatory
  checks before coding: verify assignees, walk the three-layer (Epic→Task→Subtask)
  hierarchy to read descriptions, and confirm target files. Use before any code
  change.
---

# 开发前检查

接到兔子开发令后，动代码之前必须完成。

## 第①检：子任务经办人核对

```python
# 拉波次所有子任务，确认经办人 = squirtle
r = requests.get(f"{BASE}/rest/api/2/search", headers=HEADERS,
  params={"jql": "project=AL AND issuetype=10702 AND key in (AL-xx,AL-yy)", "maxResults": 20})
for issue in r.json()["issues"]:
    k = issue["key"]
    a = (issue["fields"].get("assignee") or {}).get("name", "未指派")
    if a != "squirtle":
        print(f"❌ {k} 经办人={a} —— 阻断，通知协调者等待兔子指派")
```

## 第②检：读需求描述

Jira 任务三层结构：

```
Epic (10000)          ← 标注开发范围（卡罗尔设 Epic Link）
  └── 任务 (10701)    ← 卡罗尔写入完整设计：📄需求/📌功能/🎯用户故事/🎨设计
        └── 子任务 (10702)  ← 一行简述，上下文靠父任务补充
```

**情况 A — 分配的是子任务(10702)**：先读父任务(10701) description，再读祖父 Epic(10000) scope

```python
# Step 1: 读父任务 description（卡罗尔设计全写在父任务里）
sub = requests.get(f"{BASE}/rest/api/2/issue/AL-xx?fields=parent,issuetype", headers=HEADERS).json()
parent_key = sub["fields"]["parent"]["key"]
parent = requests.get(f"{BASE}/rest/api/2/issue/{parent_key}?fields=description,parent", headers=HEADERS).json()
print("--- 父任务 description ---")
print(parent["fields"]["description"])

# Step 2: 读祖父 Epic summary（标注开发范围，不写具体设计）
epic_ref = (parent["fields"].get("parent") or {})
if epic_ref:
    epic = requests.get(f"{BASE}/rest/api/2/issue/{epic_ref['key']}?fields=summary,description", headers=HEADERS).json()
    print(f"\n--- Epic {epic_ref['key']}: {epic['fields']['summary']} ---")
```

**情况 B — 分配的是任务(10701)**：读自身 description，再读父 Epic scope

```python
task = requests.get(f"{BASE}/rest/api/2/issue/AL-xx?fields=description,issuetype,parent", headers=HEADERS).json()
print("--- 任务 description ---")
print(task["fields"]["description"])

epic_ref = (task["fields"].get("parent") or {})
if epic_ref:
    epic = requests.get(f"{BASE}/rest/api/2/issue/{epic_ref['key']}?fields=summary,description", headers=HEADERS).json()
    print(f"\n--- Epic {epic_ref['key']}: {epic['fields']['summary']} ---")
```

## 第③检：目标文件 Read

动刀前用 Read 工具读目标文件，确认函数签名、import、现有逻辑。

## 第④检：缺陷单 description + 评论（修复 Bug 时必做）

当兔子指令中附带 `🔗 缺陷单：AL-XXX` 时，**在修代码之前**必须读完：
1. **description** — 夏洛克的初次 QA 报告（发现的问题 / 复现步骤 / 预期结果 / 实际结果）
2. **comments** — 若此 Bug 之前修过但回归不通过，夏洛克会在评论中追加补充说明（哪里仍不对、截图、新发现），这是二次修复的关键输入

```python
# 读缺陷单 description + 最新评论（夏洛克的 QA 反馈）
bug = requests.get(f"{BASE}/rest/api/2/issue/AL-XXX?fields=description,summary,comment", headers=HEADERS).json()
print(bug["fields"]["summary"])
print(bug["fields"]["description"])
for c in (bug["fields"].get("comment", {}).get("comments", []) or []):
    who = c.get("author", {}).get("name", "?")
    when = c.get("created", "")[:10]
    print(f"\n--- 评论 by {who} ({when}) ---")
    print(c.get("body", ""))
```

不遵守 → 只看初报不看回归评论 → 漏掉新信息 → 修完仍不通过 → 反复返工。
