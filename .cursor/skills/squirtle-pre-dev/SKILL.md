---
name: squirtle-pre-dev
description: >-
  Before any code change: for AliceV2 (Epic AL-301) read the master plan and
  Jira hierarchy; for v3.2 archive work use the legacy three-layer check.
  Always verify assignees and Read target files first.
---

# 开发前检查

接到兔子开发令后，动代码之前必须完成。

## 第⓪检：AliceV2 线（Epic AL-301 · 默认）

```text
1. Read pm-Carroll/AliceV2_开发计划_总纲_v1.0.md — 波次、门禁、验收 E1–E8
2. Read Jira AL-301 + 本波子任务/父任务 description
3. 确认活仓路径 = H:\workbuddy\aliceV2\（无令不得提前创建）
4. 加载 squirtle-alicev2-guard — 首跑 scope 自检
5. 波次 A：先迁移 .cursor/ → aliceV2/，再复制 Baize（见 alicev2-guard 第 0 步）
```

**波次 A（AL-307）顺序**：`.cursor/` 迁移 → Baize 复制 @ `b989830` → example.yaml + `.env` → `npm install/test/start/desktop` → `git init` + 首次 commit。  
Baize 复制排除：`.git/`、`node_modules/`、真实 `baize/runtime/`、含密钥 yaml。

## 第①检：子任务经办人核对

```python
r = requests.get(f"{BASE}/rest/api/2/search", headers=HEADERS,
  params={"jql": "project=AL AND issuetype=10702 AND key in (AL-xx,AL-yy)", "maxResults": 20})
for issue in r.json()["issues"]:
    a = (issue["fields"].get("assignee") or {}).get("name", "未指派")
    if a != "squirtle":
        print(f"❌ {issue['key']} 经办人={a} — 阻断")
```

## 第②检：读需求描述

Epic AL-301 → 任务(10701) → 子任务(10702)。子任务 → 父任务 → Epic scope。

## 第③检：目标文件 Read

动刀前 Read 目标文件，确认签名与现有逻辑。

## 第④检：缺陷单（Bug 时）

`GET /issue/AL-XXX?fields=description,comment` — description + 回归评论全读。

## 第⑤检：搜索已有实现（铁律#8）

Grep + SemanticSearch 复用已有能力，禁止平行链路。

| V2 区域 | 先搜 |
|---------|------|
| Hub / 路由 | `src/server.js` · `routes/` |
| Baize 配置 | `baize/config/` · `*.example.yaml` |
| Jira | `jira.yaml` · ConfirmCard |
| Electron | `client/desktop/` |

## 第⑥检：v3.2 归档线（仅 touch `alice/` 时）

涉及 LangGraph / Dify / n8n → 先读 `alice/specs/` 对应文档。加载 `squirtle-v3-guard`。
