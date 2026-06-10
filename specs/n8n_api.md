# n8n REST API · Alice 集成参考

> 来源：https://docs.n8n.io/api/ · Sustainable Use License（开源可自部署）
> 用途：Alice Admin 通过 REST API 管理 n8n 的凭据和工作流，不得自行编造端点

---

## 认证

所有请求需要 API Key：

```
X-N8N-API-KEY: {n8n_api_key}
```

API Key 在 n8n 后台 → Settings → API 中生成。

---

## 一、凭据管理（Credentials）

Alice Admin 用此 API 管理 Jira PAT 等外部凭据。

### POST /api/v1/credentials — 创建凭据

```bash
curl -X POST 'http://localhost:5678/api/v1/credentials' \
  -H 'X-N8N-API-KEY: {api_key}' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Alice Jira PAT",
    "type": "jiraSoftwareApi",
    "data": {
      "url": "http://ctjira1.lmdgame.com:8080",
      "email": "alice-bot@lmdgame.com",
      "apiToken": "your-jira-pat-here"
    }
  }'
```

**凭据类型名（`type` 字段）：**

| 系统 | type |
|------|------|
| Jira | `jiraSoftwareApi` |
| HTTP Basic Auth | `httpBasicAuth` |
| HTTP Header Auth | `httpHeaderAuth` |
| Generic OAuth2 | `oAuth2Api` |

### GET /api/v1/credentials — 列出凭据

```
GET /api/v1/credentials
```

**响应：** 凭据数组（敏感数据会脱敏为 `********`）

### GET /api/v1/credentials/:id — 获取单个凭据

### PATCH /api/v1/credentials/:id — 更新凭据

```bash
curl -X PATCH 'http://localhost:5678/api/v1/credentials/cr-123' \
  -H 'X-N8N-API-KEY: {api_key}' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Alice Jira PAT (Updated)",
    "data": { "apiToken": "new-pat-here" }
  }'
```

### DELETE /api/v1/credentials/:id — 删除凭据

### POST /api/v1/credentials/test — 测试凭据连通性

```bash
curl -X POST 'http://localhost:5678/api/v1/credentials/test' \
  -H 'X-N8N-API-KEY: {api_key}' \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "jiraSoftwareApi",
    "data": {
      "url": "http://ctjira1.lmdgame.com:8080",
      "email": "alice-bot@lmdgame.com",
      "apiToken": "your-jira-pat-here"
    }
  }'
```

---

## 二、工作流管理（Workflows）

### POST /api/v1/workflows — 创建工作流

```bash
curl -X POST 'http://localhost:5678/api/v1/workflows' \
  -H 'X-N8N-API-KEY: {api_key}' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Alice Jira 查询",
    "nodes": [...],
    "connections": {...},
    "settings": { "executionOrder": "v1" }
  }'
```

### GET /api/v1/workflows — 列出工作流

```
GET /api/v1/workflows?limit=50
```

### GET /api/v1/workflows/:id — 获取工作流详情

### PATCH /api/v1/workflows/:id — 更新工作流

### DELETE /api/v1/workflows/:id — 删除工作流

### POST /api/v1/workflows/:id/activate — 激活工作流

### POST /api/v1/workflows/:id/deactivate — 停用工作流

### POST /api/v1/workflows/:id/run — 手动执行工作流

```bash
curl -X POST 'http://localhost:5678/api/v1/workflows/wf-123/run' \
  -H 'X-N8N-API-KEY: {api_key}'
```

---

## 三、执行记录（Executions）

### GET /api/v1/executions — 列出执行记录

```
GET /api/v1/executions?workflowId=wf-123&limit=10
```

### GET /api/v1/executions/:id — 获取单次执行详情

---

## 四、Admin 代理层设计原则

Alice Admin 不直接调 n8n API。流程：

```
Admin 前端 → Alice Admin 后端 → n8n API
```

| Admin 操作 | 调 n8n 哪个端点 |
|-----------|----------------|
| 保存 Jira 凭据 | `POST /api/v1/credentials` |
| 测试 Jira 连接 | `POST /api/v1/credentials/test` |
| 查看 Jira 凭据状态 | `GET /api/v1/credentials` |
| 部署工作流 | `POST /api/v1/workflows` |
| 激活/停用工作流 | `POST /api/v1/workflows/:id/(de)activate` |

---

## 五、Webhook 调用（工作流触发）

n8n 工作流可以通过 Webhook URL 从外部触发。Alice Hub 用 HTTP POST 调用：

```python
# Alice Hub 调用 n8n Webhook 示例
import requests

resp = requests.post(
    "http://n8n:5678/webhook/alice-jira-search",
    json={"jql": "project=CT AND status=Open", "user_id": "zhangsan"},
    timeout=30
)
data = resp.json()
```

---

## 六、不可编造的端点

- n8n API 基础路径是 `/api/v1/`，不是 `/rest/` 或 `/v2/`
- 凭据类型是 `jiraSoftwareApi`，不是 `jira` 或 `jira-software`
- 执行工作流是 `POST /api/v1/workflows/:id/run`，不是 `POST /api/v1/workflows/:id/execute`
