# n8n 工作流 JSON 结构 · Alice 集成参考

> 来源：https://docs.n8n.io · Sustainable Use License
> 用途：杰尼龟编写 n8n 工作流 JSON 文件（通过 API 部署），不得自行编造节点类型

---

## 一、工作流顶层结构

```json
{
  "name": "Alice Jira 查询",
  "nodes": [],
  "connections": {},
  "active": false,
  "settings": {
    "executionOrder": "v1",
    "saveManualExecutions": true,
    "executionTimeout": 60
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 工作流名称 |
| `nodes` | array | 是 | 节点数组 |
| `connections` | object | 是 | 连接关系 |
| `active` | boolean | 否 | 是否激活（默认 false） |
| `settings` | object | 否 | 执行设置 |

---

## 二、节点通用格式

```json
{
  "name": "节点名称（唯一）",
  "type": "n8n-nodes-base.jira",
  "typeVersion": 1,
  "position": [250, 300],
  "parameters": {},
  "credentials": {
    "jiraSoftwareApi": {
      "id": "credential-id",
      "name": "Alice Jira PAT"
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `name` | 节点名称，**必须唯一**，用于 `connections` 引用 |
| `type` | 节点类型（如 `n8n-nodes-base.jira`） |
| `typeVersion` | 节点类型版本 |
| `position` | 画布坐标 `[x, y]` |
| `parameters` | 节点参数（操作、字段等） |
| `credentials` | 凭据引用 |

---

## 三、Webhook 触发器节点

```json
{
  "name": "Webhook",
  "type": "n8n-nodes-base.webhook",
  "typeVersion": 2,
  "position": [250, 300],
  "parameters": {
    "path": "alice-jira-search",
    "httpMethod": "POST",
    "responseMode": "responseNode"
  }
}
```

n8n 生成的 Webhook URL：`http://n8n:5678/webhook/alice-jira-search`

---

## 四、Jira 节点示例

### 4.1 查询 Issues（Search）

```json
{
  "name": "Jira Search",
  "type": "n8n-nodes-base.jira",
  "typeVersion": 1,
  "position": [450, 300],
  "parameters": {
    "resource": "issue",
    "operation": "getAll",
    "jql": "={{ $json.jql }}",
    "returnAll": true,
    "limit": 15
  },
  "credentials": {
    "jiraSoftwareApi": { "id": "jira-cred-id", "name": "Alice Jira PAT" }
  }
}
```

**参数说明：**

| parameters 字段 | 说明 |
|----------------|------|
| `resource` | `issue` / `issueAttachment` / `issueComment` / `user` |
| `operation` | `getAll`（搜索）/ `get`（单条）/ `create`（创建）/ `update`（更新）/ `delete`（删除） |
| `jql` | JQL 查询语句，支持 `={{ $json.jql }}` 动态注入 |
| `returnAll` | `true` = 返回全部结果 |
| `limit` | 当 `returnAll: false` 时生效 |

### 4.2 创建 Issue

```json
{
  "name": "Jira Create",
  "type": "n8n-nodes-base.jira",
  "typeVersion": 1,
  "position": [650, 300],
  "parameters": {
    "resource": "issue",
    "operation": "create",
    "projectKey": "={{ $json.project_key }}",
    "summary": "={{ $json.summary }}",
    "issueType": "={{ $json.issue_type }}",
    "description": "={{ $json.description }}",
    "additionalFields": {
      "assignee": { "id": "={{ $json.assignee }}" },
      "priority": { "id": "={{ $json.priority }}" }
    }
  },
  "credentials": {
    "jiraSoftwareApi": { "id": "jira-cred-id", "name": "Alice Jira PAT" }
  }
}
```

### 4.3 更新 Issue

```json
{
  "name": "Jira Update",
  "type": "n8n-nodes-base.jira",
  "typeVersion": 1,
  "position": [650, 300],
  "parameters": {
    "resource": "issue",
    "operation": "update",
    "issueKey": "={{ $json.issue_key }}",
    "additionalFields": {
      "summary": "={{ $json.summary }}",
      "assignee": { "id": "={{ $json.assignee }}" }
    }
  }
}
```

### 4.4 添加评论

```json
{
  "name": "Jira Comment",
  "type": "n8n-nodes-base.jira",
  "typeVersion": 1,
  "position": [650, 300],
  "parameters": {
    "resource": "issueComment",
    "operation": "add",
    "issueKey": "={{ $json.issue_key }}",
    "comment": "={{ $json.comment }}"
  }
}
```

---

## 五、HTTP Request 节点（调 SVN 代理）

```json
{
  "name": "SVN Log",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 3,
  "position": [450, 450],
  "parameters": {
    "method": "GET",
    "url": "http://svn-proxy:8080/svn/log",
    "queryParameters": {
      "parameters": [
        { "name": "limit", "value": "={{ $json.limit || 20 }}" }
      ]
    },
    "options": {
      "timeout": 30000
    }
  }
}
```

---

## 六、Function 节点（数据清洗）

n8n 内置 JS 引擎，用于在返回 Alice Hub 前裁剪数据：

```json
{
  "name": "Data Cleaner",
  "type": "n8n-nodes-base.function",
  "typeVersion": 1,
  "position": [850, 300],
  "parameters": {
    "functionCode": "// 裁剪 Jira 返回数据，防止撑爆上下文\nconst issues = $input.all();\nconst cleaned = issues.map(i => ({\n  key: i.json.key,\n  summary: (i.json.fields?.summary || '').slice(0, 150),\n  status: i.json.fields?.status?.name || '',\n  assignee: i.json.fields?.assignee?.displayName || '',\n  priority: i.json.fields?.priority?.name || ''\n}));\nreturn { issues: cleaned, total: cleaned.length };\n"
  }
}
```

**清洗规则（硬约束）：**
- Jira 搜索结果：仅保留 key/summary/status/assignee/priority，summary 截断到 150 字
- SVN diff：仅保留文件路径 + 提交注释 + 前 200 行 diff
- 任何返回给 Alice Hub 的数据必须 ≤ 2000 tokens

---

## 七、Response 节点（返回给 Alice Hub）

```json
{
  "name": "Respond to Hub",
  "type": "n8n-nodes-base.respondToWebhook",
  "typeVersion": 1,
  "position": [1050, 300],
  "parameters": {
    "respondWith": "json",
    "responseBody": {
      "values": {
        "string": [
          { "name": "success", "value": "true" },
          { "name": "data", "value": "={{ JSON.stringify($json) }}" }
        ]
      }
    }
  }
}
```

---

## 八、Connections 格式

```json
{
  "connections": {
    "Webhook": {
      "main": [[{ "node": "Jira Search", "type": "main", "index": 0 }]]
    },
    "Jira Search": {
      "main": [[{ "node": "Data Cleaner", "type": "main", "index": 0 }]]
    },
    "Data Cleaner": {
      "main": [[{ "node": "Respond to Hub", "type": "main", "index": 0 }]]
    }
  }
}
```

**规则：**
- Key 是源节点 `name`（不是 id）
- Value 结构：`{ "输出类型": [[ { "node": "目标节点name", "type": "main", "index": 0 } ]] }`
- IF 节点的 true/false 分支用不同 `index`（index=0 是 true，index=1 是 false）

---

## 九、完整的 Alice Jira 查询工作流示例

```json
{
  "name": "Alice Jira 查询与清洗",
  "nodes": [
    {
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [250, 300],
      "parameters": {
        "path": "alice-jira-search",
        "httpMethod": "POST",
        "responseMode": "responseNode"
      }
    },
    {
      "name": "Jira Search",
      "type": "n8n-nodes-base.jira",
      "typeVersion": 1,
      "position": [450, 300],
      "parameters": {
        "resource": "issue",
        "operation": "getAll",
        "jql": "={{ $json.jql }}",
        "returnAll": true,
        "limit": 15
      },
      "credentials": {
        "jiraSoftwareApi": { "id": "jira-cred-id", "name": "Alice Jira PAT" }
      }
    },
    {
      "name": "Data Cleaner",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [650, 300],
      "parameters": {
        "functionCode": "const issues = $input.all();\nconst cleaned = issues.map(i => ({\n  key: i.json.key,\n  summary: (i.json.fields?.summary || '').slice(0, 150),\n  status: i.json.fields?.status?.name || ''\n}));\nreturn { issues: cleaned, total: cleaned.length };\n"
      }
    },
    {
      "name": "Respond to Hub",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1,
      "position": [850, 300],
      "parameters": {
        "respondWith": "json",
        "responseBody": {
          "values": {
            "string": [
              { "name": "success", "value": "true" },
              { "name": "data", "value": "={{ JSON.stringify($json) }}" }
            ]
          }
        }
      }
    }
  ],
  "connections": {
    "Webhook": {
      "main": [[{ "node": "Jira Search", "type": "main", "index": 0 }]]
    },
    "Jira Search": {
      "main": [[{ "node": "Data Cleaner", "type": "main", "index": 0 }]]
    },
    "Data Cleaner": {
      "main": [[{ "node": "Respond to Hub", "type": "main", "index": 0 }]]
    }
  },
  "settings": {
    "executionOrder": "v1",
    "saveManualExecutions": true,
    "executionTimeout": 60
  }
}
```

---

## 十、不可编造的规则

- 节点 `type` 必须使用 n8n 官方名称（如 `n8n-nodes-base.jira`，不是 `jira`）
- 节点 `name` 必须唯一
- `connections` 的 key 是节点 `name`（不是 `id`）
- Webhook 路径以小写字母开头，不含空格
- 凭据引用格式：`{ "jiraSoftwareApi": { "id": "cred-id", "name": "凭据名称" } }`
- 数据清洗必须在 n8n Function 节点内完成，不能回传原始大 payload
