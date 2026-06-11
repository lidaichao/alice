---
name: squirtle-pre-dev
description: >-
  When Squirtle receives a development order from Rabbit that includes Jira
  subtask IDs (10702), run three mandatory checks before writing any code:
  verify subtask assignees are Squirtle, read parent task descriptions,
  and confirm target files exist. Use before any code change when subtasks
  are mentioned.
---

# 开发前三检

接到兔子开发令（含子任务编号）后，动代码之前必须完成。

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

## 第②检：父任务 description

子任务只写一行简述，父任务含完整上下文（📄需求/📌功能/🎯用户故事/🎨设计）。

```python
sub = requests.get(f"{BASE}/rest/api/2/issue/AL-xx?fields=parent", headers=HEADERS).json()
parent_key = sub["fields"]["parent"]["key"]
parent = requests.get(f"{BASE}/rest/api/2/issue/{parent_key}?fields=description", headers=HEADERS).json()
print(parent["fields"]["description"])
```

## 第③检：目标文件 Read

动刀前用 Read 工具读目标文件，确认函数签名、import、现有逻辑。
