---
name: squirtle-pre-dev
description: >-
  When Squirtle receives a development order from Rabbit that includes Jira
  subtask IDs (10702), task IDs (10701), or bug IDs (10011), run mandatory
  checks before coding: verify assignees, walk the three-layer (Epic→Task→Subtask)
  hierarchy to read descriptions, consult alice/specs/ for any involved open-source
  project (LangGraph/Dify/n8n), and confirm target files. Use before any code
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

**情况 A — 分配的是子任务(10702)**：子任务自身 description → 父任务(10701) description → 祖父 Epic(10000) scope

```python
# Step 0: 读子任务自身 description（卡罗尔也会在子任务中写技术约束/备注）
sub = requests.get(f"{BASE}/rest/api/2/issue/AL-xx?fields=description,summary,parent,issuetype", headers=HEADERS).json()
print("--- 子任务自身 ---")
print(sub["fields"]["summary"])
print(sub["fields"].get("description") or "(无描述)")

# Step 1: 读父任务 description（卡罗尔设计全写在父任务里）
parent_key = sub["fields"]["parent"]["key"]
parent = requests.get(f"{BASE}/rest/api/2/issue/{parent_key}?fields=description,parent", headers=HEADERS).json()
print("\n--- 父任务 description ---")
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

## 第⑥检：搜索已有实现（防重复造轮子 · 铁律#10）

**在新建任何函数/类/常量之前**，先用 `Grep` + `SemanticSearch` 搜索代码库：

```python
# 必做：按功能关键词搜索已有实现
# 示例 — 当你需要创建 Jira Issue 时：
Grep("create_issue|JiraClient|jira_api", path="backend/")         # 找已有类/函数
Grep("draft_to_fields|global_config|issuetype", path="backend/")  # 找已有字段处理
SemanticSearch("How does Alice create Jira issues?", target_directories=["backend/"])
```

| 你要做什么 | 先搜什么 |
|------|------|
| Jira 操作（创建/查询/流转） | `JiraClient` · `jira_api` · `create_issue` · `search_issues` |
| n8n 交互 | `n8n_webhook` · `n8n_bridge` · `webhook_call` |
| 读配置 | `global_config` · `load_global_config` · `tenant_synonyms` |
| 字段映射/校验 | `draft_to_fields` · `issuetype` · `JIRA_ISSUETYPE_MAP` |
| SVN 操作 | `svn_proxy` · `svn_log` |
| Dify RAG | `dify_rag` · `dataset` · `retrieve` |

**发现已有能力 → 复用扩展。绝不重写一条平行链路。**

> 本检因 2026-06-13 事故新增：n8n 阻塞后绕过已有 `JiraClient.create_issue_from_draft()` 重复造了 `jira_create_direct`，硬编码 labels/issueType，违反 admin 配置。

## 第⑤检：开源项目源码/文档（涉及 LangGraph / Dify / n8n 时必做）

`alice/specs/` 存放 Alice 所依赖开源项目的源码和 API 文档。开发任何涉及以下三方库的功能时，**必须先读对应文档**，禁止凭记忆猜 API 参数或行为。

| Alice 代码区域 | 需读的 specs 文件 | 说明 |
|------|------|------|
| `agent_graph.py` / LangGraph 编排 | `specs/langgraph_api.md` | StateGraph、HITL interrupt、tool 定义、streaming 完整模板 |
| Dify 知识库 RAG 检索 | `specs/dify_api.md` | `/v1/datasets/{id}/retrieve` 参数、响应格式、权限头部 |
| n8n Webhook / REST 调用 | `specs/n8n_api.md` | 凭证管理、工作流激活、execution 查询 |
| n8n 工作流节点设计 | `specs/n8n_workflow.md` | Webhook trigger、Jira 节点、HTTP Request 节点、JSON 结构 |
| Dify 前端/后端适配 | `specs/dify/` 子树 | 优先读 `AGENTS.md`（编码规范）；按需读 `web/docs/`、`api/controllers/`、`dify-agent/docs/` |

> 如果 rabbit 指令点名了新三方（如 Composer SDK），先确认 `specs/` 是否有对应文档；若无 → 先用 `WebSearch` 查官方文档，再动手。
