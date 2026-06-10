# Alice AI Bridge — API 契约文档 (v1.0)

> 版本：**v1.0（已冻结）** | 日期：2026-06-10 | 维护：杰尼龟
>
> 本文档通过逆向读取 `backend/ai_bridge.py` 中的 Flask 路由装饰器生成。
> ⚠️ SSE 接口标记为 `stream: text/event-stream`。v3.0 新增端点（Dify 代理 / n8n 代理）将在 Phase 1-3 追加。

**相关文档**：[三期蓝图计划](alice三期蓝图计划.md) · [技术架构](Alice_Master_Architecture_v1.0.md) · [v3.0 重构方案](../v3.0/ALICE_V3_RESTRUCTURE_PLAN.md)

> `intent_disambiguation` 已合入（蓝图 E5.2）。

---

## 零、v1.0 兼容策略（冻结）

| 规则 | 说明 |
|------|------|
| **版本号** | `GET /health` 返回 `api_version: "1.0"` |
| **Additive-only** | v1.0 客户端可忽略未知 JSON 字段与 SSE `_event` |
| **冻结标识** | `operation_id`、`draft_id`、`conversation_id` 语义与格式不变 |
| **冻结 SSE** | `_event`: `confirm_card`、`draft_card`、`operation_progress`、`intent_disambiguation`、`jira_search_supplement` |
| **Hub-only Jira** | `hub_only_jira: true` 时请求体 **不得** 依赖 `jira_pat`（E4） |
| **破坏性变更** | 须升 `api_version` 主版本并更新本文档 |

---

## 一、核心业务 API

### 1.1 对话接口（SSE 流式）

```
POST /v1/chat/completions (SSE)
```

| 属性 | 值 |
|------|-----|
| **用途** | 核心对话入口，VIP 直通车 + ReAct 循环均通过此端点 |
| **Content-Type** | `application/json` |
| **Response** | `text/event-stream` (SSE 逐 token 流式) |

**Request Body**:

```typescript
interface ChatRequest {
  messages: Message[];         // 对话历史
  config?: FrontendConfig;     // 前端配置
}

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  // 多模态:
  // content: [{ type: "image_url", image_url: { url: string } },
  //           { type: "text", text: string }]
}

interface FrontendConfig {
  jira_url?: string;
  jira_pat?: string;
  deepseek_key?: string;
  deepseek_model?: string;
  max_steps?: number;
  tool_whitelist?: string[];
}
```

**SSE Response Events**:

```
data: {"choices":[{"delta":{"content":"..."}}]}        // 流式回答
data: {"_intent":{"route":"CODE_COMMIT_LIST",...}}    // 意图信息
data: {"_event":"confirm_card","operation":{...}}      // 确认卡
data: {"_event":"intent_disambiguation","prompt":"...","choices":[{"value":"jira_search","label":"..."}],"confidence":0.65}  // 低置信路由消歧（可选）
data: {"_event":"operation_progress","phase":"running","message":"...","percent":45}  // HITL 写 Jira 进度
data: {"custom_type":"agent_step","step":1,...}         // ReAct 步骤
data: {"plugin":{"name":"get_issue_commits","status":"running"}}  // 工具状态
data: [DONE]                                            // 结束
```

**错误响应**:
```json
{"error": "No messages"}
{"error": "缺少 ai_api_key"}
```

---

### 1.2 对话编排接口（新版，SSE）

```
POST /v1/chat/orchestrate (SSE)
```

用途：新版编排对话接口，支持更多前端配置参数。协议与 `/v1/chat/completions` 相同。

---

## 二、Jira 操作 API

### 2.1 确认卡获取

```
GET /operations/<op_id>
```

| 属性 | 值 |
|------|-----|
| **用途** | 获取指定确认卡的当前状态 |

**Response**: 确认卡 JSON 对象（含 `status`, `operation`, `created_at` 等字段）

### 2.2 确认操作

```
POST /operations/<op_id>/confirm
```

| 属性 | 值 |
|------|-----|
| **用途** | 用户确认执行写操作 |

### 2.3 拒绝操作

```
POST /operations/<op_id>/reject
```

| 属性 | 值 |
|------|-----|
| **用途** | 用户拒绝执行写操作 |

### 2.4 待处理确认卡

```
GET /operations/pending
```

| 属性 | 值 |
|------|-----|
| **用途** | 获取所有待确认的操作列表 |

---

## 三、代理/CORS 透传 API (Proxy)

### 3.1 Notion 代理

| 端点 | 方法 | 用途 |
|------|------|------|
| `/proxy/notion/test` | POST | Notion 连接测试 |
| `/proxy/notion/search` | POST | Notion 搜索 |

### 3.2 Jira 代理

| 端点 | 方法 | 用途 |
|------|------|------|
| `/proxy/jira/comment` | POST | 添加 Jira 评论 |
| `/proxy/jira/projects` | POST | 获取项目列表 |
| `/proxy/jira/test` | POST | Jira 连接测试 |

### 3.3 Google Drive 代理

| 端点 | 方法 | 用途 |
|------|------|------|
| `/proxy/gdrive/list` | POST | 列出 GDrive 文件 |

### 3.4 AI 模型代理

| 端点 | 方法 | 用途 |
|------|------|------|
| `/proxy/ai/models` | POST | 获取可用 AI 模型列表 |

### 3.5 本机 IP

| 端点 | 方法 | 用途 |
|------|------|------|
| `/proxy/local_ip` | GET | 获取本机 IP 地址 |

---

## 四、管理后台 API

### 4.1 配置管理

| 端点 | 方法 | 用途 |
|------|------|------|
| `/v1/admin/config` | GET | 获取当前配置（敏感字段掩码 `********`） |
| `/v1/admin/config` | POST | 部分更新配置（merge 到 `global_config.json` 并热重载） |
| `/v1/admin/jira/fields` | GET | 拉取 Jira `/rest/api/2/field` 全站字段列表（query: `url`, `pat`） |
| `/v1/admin/jira/deadline-suggest` | GET | 按项目推荐截止时间字段（query: `project`, `url`, `pat`） |
| `/v1/admin/jira/projects` | GET | PAT 可访问的项目列表（query: `url`, `pat`）→ `{ projects: [{ key, name, id }] }` |
| `/v1/admin/stats` | GET | 获取统计信息 |
| `/v1/admin/verify` | POST | 验证用户权限 |
| `/v1/admin/token` | POST | Token 管理 |

**GET `/v1/admin/config` 响应字段（节选）**：

```json
{
  "DEEPSEEK_URL": "https://api.deepseek.com/v1/chat/completions",
  "DEEPSEEK_KEY": "********",
  "DEEPSEEK_MODEL": "deepseek-v4-pro",
  "saved_model": "deepseek-v4-pro",
  "JIRA_PROJECTS": "CT, PROJ2",
  "JIRA_DEADLINE_FIELD_BY_PROJECT": { "CT": "End date" },
  "JIRA_FIELD_MAPPINGS": { "extraPersonFields": ["任务负责人"] },
  "JIRA_PROJECT_CONFIG": {},
  "JIRA_FIELD_GLOSSARY": [
    {
      "fieldId": "customfield_10042",
      "fieldName": "End date",
      "meaning": "策划排期的业务完成日；用户说「本周要交」时按此字段理解",
      "aliases": ["截止时间", "ddl"]
    }
  ]
}
```

- `JIRA_FIELD_GLOSSARY`：PM 在 Admin「字段含义词典」中维护的业务语义；全 Jira 实例共享（非按项目）。运行时注入 JQL 决策与周报意图提示词。
- `JIRA_FIELD_MAPPINGS.extraPersonFields`：按人名查任务时，在**经办人之外**额外 OR 的 Jira 人物字段；空数组表示仅查经办人。旧键 `taskOwner` 仍可读作单条兼容。
- `JIRA_DEADLINE_FIELD_BY_PROJECT` / `JIRA_PROJECT_CONFIG`：按项目指定截止时间等**功能槽位**（与词典独立）。
- `DEEPSEEK_MODEL` / `saved_model`：由 `_resolved_deepseek_model()` 解析，**文件优先**于环境变量。
- 掩码字段 `********` 在 POST 时会被跳过（表示未修改）。

**POST `/v1/admin/config` 请求体**：支持任意子集字段 merge，例如：

```json
{ "DEEPSEEK_MODEL": "deepseek-reasoner" }
```

或仅 API：

```json
{ "DEEPSEEK_URL": "...", "DEEPSEEK_KEY": "sk-..." }
```

**鉴权**：`Authorization: Bearer <admin-token>`（与 Admin 面板 `localStorage.wb_admin_token` 一致）。

### 4.2 测试与诊断

| 端点 | 方法 | 用途 |
|------|------|------|
| `/v1/admin/test/jira` | POST | Jira 连通性测试 |
| `/v1/admin/test/fisheye` | POST | FishEye 连通性测试 |
| `/v1/admin/test/svn` | POST | SVN 连通性测试 |
| `/v1/admin/test/notion` | POST | Notion 连通性测试 |
| `/v1/admin/test/notion-db` | POST | Notion DB 连通性测试 |
| `/v1/admin/test/gdrive` | POST | GDrive 连通性测试 |
| `/v1/admin/test/deepseek` | POST | DeepSeek 连通性测试 |

### 4.3 模型与逻辑

| 端点 | 方法 | 用途 |
|------|------|------|
| `/v1/admin/models` | GET | 从上游 API `/models` 拉取可用模型 id 列表 |
| `/v1/admin/logic/reload` | POST | 热重载逻辑断言规则 |

### 4.4 评估

| 端点 | 方法 | 用途 |
|------|------|------|
| `/v1/admin/eval/datasets` | GET | 获取评估数据集列表 |
| `/v1/admin/eval/run/<dataset>` | POST | 运行指定评估数据集 |

### 4.5 批量分析

| 端点 | 方法 | 用途 |
|------|------|------|
| `/v1/admin/tasks/batch-analysis` | POST | 创建批量分析任务（M2.8：返回 `admin_batch_task_id`） |
| `/v1/admin/tasks/<admin_batch_task_id>/status` | GET | 查询任务状态 |

### 4.6 管理面板

| 端点 | 方法 | 用途 |
|------|------|------|
| `/admin` | GET | Web 管理后台页面 |
| `/` | GET | 根路由（API 信息） |

**GET `/v1/admin/models` 成功响应**：

```json
{
  "success": true,
  "models": ["deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
  "saved_model": "deepseek-v4-pro"
}
```

已保存但不在上游列表的 `saved_model` 会插入 `models` 数组首位。

---

## 五、系统端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康检查 `{"status":"ok","api_version":"1.0","hub_only_jira":true,...}` |
| `/cache/stats` | GET | 缓存命中统计 |
| `/test` | GET | 基础连通性测试 |

---

## 六、Mailbox 异步任务队列 (M2)

> **存储**：SQLite `backend/data/mailbox.db`（宪法 **C8**：禁止 Redis / 重量级中间件）。
>
> **边界（C4 / M2.6）**：Mailbox **不存储** HITL 审批状态；`mailbox_task_id` 与 `operation_id` 必须区分使用。

### 6.1 三种任务 ID 对照

| 字段 | 用途 | 存储 | 状态机 |
|------|------|------|--------|
| `operation_id` | HITL Jira 写操作审批（确认卡） | `jira_operation_manager` / `operations.json` | `awaiting_confirmation` → `running` → `created` / `failed` / `rejected` |
| `mailbox_task_id` | Agent 异步派工队列（Mailbox） | `mailbox_store` / SQLite `mailbox_tasks` | `pending` → `claimed` → `done` / `failed` |
| `admin_batch_task_id` | Admin 批量分析（内存队列，M2.8 重命名） | `ai_bridge` 进程内 | 管理后台专用 |

- `operation_id` 格式示例：`jira-op-<12 hex>`
- `mailbox_task_id` 格式示例：`mbox-<12 hex>`
- Mailbox 表中 `operation_id` 列仅为**可选引用**（例如任务完成后需关联某次审批），**不得**用其表达 Mailbox 或审批状态。

### 6.2 任务结构体 `MailboxTask`

```typescript
interface MailboxTask {
  id: string;                    // 同 mailbox_task_id
  mailbox_task_id: string;       // 响应字段别名
  status: "pending" | "claimed" | "done" | "failed";
  assignee: string;              // 执行方标识（Agent / Worker 名）
  payload: Record<string, unknown>;  // 派工负载（JSON 对象）
  result?: unknown;              // 回报结果（M2.5 report 写入）
  operation_id?: string | null;  // 可选：关联 HITL operation，非审批状态
  created_at: string;            // ISO-like "YYYY-MM-DDTHH:MM:SS"
  updated_at: string;
}
```

**状态机**：`pending` → `claimed` → `done` | `failed`（非法转移返回 **409**，M2.5 实现）。

### 6.3 派工 API（M2.3）

```
POST /v1/mailbox/dispatch
```

| 属性 | 值 |
|------|-----|
| **用途** | Agent / 编排器投递异步任务，获取 `mailbox_task_id` |
| **Content-Type** | `application/json` |

**Request Body**:

```typescript
interface MailboxDispatchRequest {
  assignee: string;                        // 必填：拉取方标识
  payload: Record<string, unknown>;        // 必填：任务负载
  operation_id?: string;                   // 可选：关联已有 HITL operation
}
```

**Response 200**:

```json
{
  "ok": true,
  "mailbox_task_id": "mbox-a1b2c3d4e5f6",
  "task": {
    "id": "mbox-a1b2c3d4e5f6",
    "status": "pending",
    "assignee": "cursor-agent",
    "payload": { "kind": "kb_sync", "doc_id": "..." },
    "operation_id": null,
    "created_at": "2026-06-08T18:00:00",
    "updated_at": "2026-06-08T18:00:00"
  }
}
```

**错误**：`400` — `assignee` 或 `payload` 缺失/非法。

### 6.4 拉取 API（M2.4）

```
GET /v1/mailbox/tasks?status=pending&assignee=cursor-agent&limit=50
```

| Query | 说明 |
|-------|------|
| `status` | 可选：`pending` \| `claimed` \| `done` \| `failed` |
| `assignee` | 可选：按执行方过滤 |
| `limit` | 可选，默认 50，最大 200 |

**Response 200**:

```json
{
  "ok": true,
  "tasks": [
    {
      "id": "mbox-a1b2c3d4e5f6",
      "mailbox_task_id": "mbox-a1b2c3d4e5f6",
      "status": "pending",
      "assignee": "cursor-agent",
      "payload": { "kind": "kb_sync" },
      "result": null,
      "operation_id": null,
      "created_at": "2026-06-08T18:00:00",
      "updated_at": "2026-06-08T18:00:00"
    }
  ]
}
```

**错误**：`400` — 非法 `status` 或 `limit`。

### 6.5 领取（claim）与回报 API（M2.5）

**标准 Worker 流程**：`dispatch` → `GET tasks?status=pending` → **`POST .../claim`** → 执行负载 → **`POST .../report`**

#### 领取 `pending` → `claimed`

```
POST /v1/mailbox/tasks/<mailbox_task_id>/claim
```

**Response 200**: `{ "ok": true, "task": { ..., "status": "claimed" } }`

**错误**：`404` 任务不存在；`409` 非法状态转移（如已 `claimed`）。

#### 回报 `claimed` → `done` | `failed`

```
POST /v1/mailbox/tasks/<mailbox_task_id>/report
```

**Request Body**:

```typescript
interface MailboxReportRequest {
  status: "done" | "failed";
  result?: Record<string, unknown>;  // status=done 时必填
}
```

**Response 200**:

```json
{
  "ok": true,
  "task": {
    "id": "mbox-a1b2c3d4e5f6",
    "status": "done",
    "result": { "ok": true, "rows": 3 },
    "updated_at": "2026-06-08T18:05:00"
  }
}
```

**错误**：`400` — `status` 非法或 `done` 缺 `result`；`404` — 任务不存在；`409` — 非法状态转移（如 `pending` 直接 `report`）。

### 6.6 MCP Mailbox Worker 工具（M2.7）

通过 `GET /mcp/v1/tools` 与 `POST /mcp/v1/tools/<name>` 调用；实现委托 `mailbox_store`（与 REST 同 Store，无重复 SQL）。`risk: worker`，审计 `origin=mcp`，**非** jira_write 路径。

| 工具名 | 参数 | 成功返回 |
|--------|------|----------|
| `mailbox_list_tasks` | `assignee?`, `status?`, `limit?` | `{ ok, tasks: MailboxTask[] }` |
| `mailbox_claim_task` | `mailbox_task_id` | `{ ok, task }` — `pending→claimed` |
| `mailbox_report_task` | `mailbox_task_id`, `status`(done\|failed), `result?` | `{ ok, task }` — `claimed→done\|failed` |

**HTTP 错误码**：`400` 参数非法；`404` 任务不存在；`409` 非法状态转移。

**调用示例**：

```bash
POST /mcp/v1/tools/mailbox_list_tasks
{ "arguments": { "assignee": "cursor-agent", "status": "pending", "limit": 10 } }

POST /mcp/v1/tools/mailbox_claim_task
{ "arguments": { "mailbox_task_id": "mbox-abc123" } }

POST /mcp/v1/tools/mailbox_report_task
{ "arguments": { "mailbox_task_id": "mbox-abc123", "status": "done", "result": { "ok": true } } }
```

---

## 七、用户身份与审批审计（M4.1–M4.3）

客户端向 Hub 透传操作者身份，用于草稿/确认卡创建绑定与 confirm/reject 审批落盘。**禁止**各 Route 自行解析 header；统一 `user_identity.parse_user_id_from_request`。

### 7.1 请求头与 Body（M4.1）

| 通道 | 字段 | 说明 |
|------|------|------|
| Header | `X-Alice-User-Id` | 优先；前端经 `runtimeConfig.buildAliceUserHeaders()` 注入 |
| Body | `user_id` | 次选；`buildJiraWriteRequestBody()` 同步写入 |
| Body | `user_config.user_id` / `config.user_id` | 聊天 SSE `/v1/chat/completions` 兼容 |

空 `user_id` 允许降级（内网 Hub 过渡期），Hub 打 info 日志。

### 7.2 创建绑定（M4.2）

`POST /drafts`、`create_issues_draft` / `create_operation_card`（tool、plugin_gateway、聊天快车道）将解析到的 `user_id` 写入草稿或 operation 的 `user_id` 字段（creator）。

**`POST /drafts` 响应** 含 `user_id`；**`GET /drafts`** 列表项含 `user_id`。

### 7.3 审批落盘（M4.3）

| 动作 | 写入字段 |
|------|----------|
| `POST /operations/<id>/confirm` | `confirmed_by`（审批人 user_id）、`confirmed_at`（`YYYY-MM-DDTHH:MM:SS`） |
| `POST /operations/<id>/reject` | `rejected_by`、`rejected_at` |

**`GET /operations`** 与 **`GET /operations/<id>`** 响应含 creator + approver：

```json
{
  "id": "jira-op-abc123",
  "status": "rejected",
  "user_id": "rabbit",
  "confirmed_by": null,
  "confirmed_at": null,
  "rejected_by": "pm-alice",
  "rejected_at": "2026-06-08T14:30:00"
}
```

存储仅经 `jira_operation_manager` 状态机（C2：禁止第二套审批状态存储）。

### 7.4 列表/UI 字段（M4.4）

**`GET /operations`** 每条 operation 行含 `operation_audit_fields`：

| 字段 | 含义 |
|------|------|
| `user_id` | 创建者（creator） |
| `confirmed_by` / `confirmed_at` | 审批放行人与时间 |
| `rejected_by` / `rejected_at` | 审批拒绝人与时间 |

管控台 `OperationsConsole` 在待审批/失败列表展示上述字段。

**列表响应片段**：

```json
{
  "ok": true,
  "operations": [
    {
      "id": "jira-op-abc123",
      "status": "awaiting_confirmation",
      "kind": "jira_bulk_create",
      "user_id": "rabbit",
      "confirmed_by": null,
      "confirmed_at": null,
      "rejected_by": null,
      "rejected_at": null,
      "operation": { "type": "bulk_create", "drafts_count": 1 }
    }
  ]
}
```

### 7.5 审批权限（M4.5）

配置来源：`backend/skills/registry.yaml` → `operation_approval`（`enabled`、`approver_user_ids`、`approver_roles`）。

`POST /operations/<id>/confirm|reject` 解析 `X-Alice-User-Id` 后校验白名单；未授权返回 **403**：

```json
{ "ok": false, "error": "用户「xxx」无权执行操作审批（confirm），请联系管理员加入审批白名单" }
```

deny 须写入持久审计（见 §7.6）。

### 7.6 持久审计 API（M4.6）

append-only：`backend/data/audit.log`（JSONL，一行一条；重启不丢；禁止 LangGraph checkpoint 存审计）。

**`GET /v1/audit/logs`**（Hub 内网只读）

| 参数 | 说明 |
|------|------|
| `limit` | 默认 50，最大 500 |
| `operation_id` | 可选，按操作 ID 过滤 |

**响应 200**：

```json
{
  "ok": true,
  "count": 2,
  "logs": [
    {
      "timestamp": "2026-06-08T18:30:00",
      "actor": "e2e-audit-pm",
      "action": "operation_reject",
      "decision": "allow",
      "operation_id": "jira-op-abc123",
      "origin": "http",
      "tool_id": "operation_approval",
      "reason": ""
    }
  ]
}
```

MCP mailbox 等工具调用经 `audit_and_log` 同样落盘 `audit.log`。

---

## 八、API 全量汇总

```
核心业务:
  POST /v1/chat/completions    SSE — 对话主入口
  POST /v1/chat/orchestrate    SSE — 编排对话

Mailbox (M2):
  POST /v1/mailbox/dispatch              派工 → mailbox_task_id
  GET  /v1/mailbox/tasks                拉取（?status=&assignee=&limit=）
  POST /v1/mailbox/tasks/<id>/claim      领取 pending → claimed
  POST /v1/mailbox/tasks/<id>/report     回报 claimed → done|failed

审计 (M4):
  GET  /v1/audit/logs             持久审计日志（?limit=&operation_id=）

Jira 操作:
  GET  /operations/<id>           确认卡详情
  POST /operations/<id>/confirm   确认操作（body 含 jira_pat；未授权 403）
  POST /operations/<id>/reject    拒绝操作（未授权 403）
  GET  /operations/pending        待确认列表（?conversation_id=）
  GET  /operations                管控台列表（?status= 逗号分隔）

角色权限 (RBAC v1.10):
  GET    /v1/admin/roles                 角色列表（含 member_count + permission_defs）
  POST   /v1/admin/roles                 创建/更新角色（整表 { roles: [...] }）
  DELETE /v1/admin/roles/<id>            删除角色（有成员时 409 + 成员列表）
  PUT    /v1/admin/roles/<id>/members    更新角色成员 { members: [...] }
  GET    /v1/admin/permissions           权限矩阵（roles×permission_defs）
  POST   /v1/admin/permissions           更新权限项 { role_id, permission_key, value }
  GET    /v1/user/permissions            当前用户权限 { user_id, role, permissions[] }
                                         支持 ?user_id=XXX 查询指定用户

MCP（M1 readonly + M2.7 mailbox worker）:
  GET  /mcp/v1/tools              工具清单（readonly + worker）
  POST /mcp/v1/tools/<name>       调用工具 { "arguments": {...} }
  # worker: mailbox_list_tasks | mailbox_claim_task | mailbox_report_task

Jira 草稿箱:
  GET  /drafts/<id>               草稿详情
  POST /drafts/<id>/confirm       提交草稿 → operation（返回 drafts[] + warnings）
  POST /drafts/<id>/reject        作废草稿

团队浅层记忆:
  GET    /api/memory/entries      列表 + meta.inject_note
  POST   /api/memory/entries      { text }
  PUT    /api/memory/entries/<id> { text }
  DELETE /api/memory/entries/<id>

代理透传 (9):
  POST /proxy/notion/test|search
  POST /proxy/jira/comment|projects|test
  POST /proxy/gdrive/list
  POST /proxy/ai/models
  GET  /proxy/local_ip

管理后台 (14):
  GET|POST /v1/admin/config
  GET  /v1/admin/stats|models|eval/datasets
  POST /v1/admin/verify|token|logic/reload
  POST /v1/admin/test/* (6 endpoints)
  POST /v1/admin/tasks/batch-analysis
  GET  /v1/admin/tasks/<id>/status
  POST /v1/admin/eval/run/<dataset>
  GET  /admin, /

系统:
  GET /health, /cache/stats, /test
```

**总计**：1 个 SSE 核心 + 3 个确认卡 + 9 个代理透传 + 14 个管理 + 3 个系统 = **30 个端点**

---

## 八、Workflow 工作流模板（M5.2 执行器）

> M5.1 注册表 + 引擎骨架；M5.2 填充 version-day-check steps + execute_template() 执行器。

### 8.1 模板列表

**`GET /v1/workflow/templates`** — 返回所有已注册模板摘要。

**响应 200**：

```json
{
  "ok": true,
  "templates": [
    {
      "id": "version-day-check",
      "name": "版本日检查",
      "description": "版本发布日自动拉取待验证 Issue 清单并生成检查报告（只读）"
    },
    {
      "id": "design-to-subtasks",
      "name": "策划→子任务",
      "description": "将策划案父 Issue 拆解为多个子任务草稿，经 HITL 确认后批量创建"
    }
  ]
}
```

### 8.2 模板详情

**`GET /v1/workflow/templates/<template_id>`** — 返回完整模板（含 steps + params_schema）。

**响应 200**：

```json
{
  "ok": true,
  "template": {
    "id": "version-day-check",
    "name": "版本日检查",
    "description": "版本发布日自动拉取待验证 Issue 清单并生成检查报告（只读）",
    "steps": [
      {"id": "jql_query", "tool": "jira_search", "description": "JQL 查询版本日相关 Issue"},
      {"id": "format_checklist", "tool": "format", "description": "格式化为检查清单"},
      {"id": "summarize", "tool": "llm_summarize", "description": "LLM 汇总检查报告"}
    ]
  }
}
```

**错误**：`404` — `template_id` 不存在或校验未通过。

### 8.3 模板执行（M5.2 新增）

**`GET /v1/workflow/execute?template_id=version-day-check&jql=...`**  
**`POST /v1/workflow/execute`** — 执行工作流模板（JSON 响应，流式留给 M5.4）。

**POST 请求**：

```json
{
  "template_id": "version-day-check",
  "context": {
    "jql": "project=CT AND labels=version-day AND status!=Done",
    "jira_pat": "your-pat",
    "jira_url": "https://your-jira.atlassian.net"
  }
}
```

**响应 200（成功）**：

```json
{
  "ok": true,
  "template_id": "version-day-check",
  "template_name": "版本日检查",
  "steps": [
    {"id": "jql_query", "tool": "jira_search", "status": "done", "result": "JQL 查询... → 共 3 条\n1. CT-101..."},
    {"id": "format_checklist", "tool": "format", "status": "done", "result": "## 版本日检查清单\n| # | Issue | 状态 | 负责人 |\n..."},
    {"id": "summarize", "tool": "llm_summarize", "status": "done", "result": "待处理 2 项，已完成 1 项..."}
  ],
  "execution_log": [
    {"step_id": "jql_query", "tool": "jira_search", "status": "done", "output": "JQL 查询...→ 共 3 条\n..."},
    {"step_id": "format_checklist", "tool": "format", "status": "done", "output": "## 版本日检查清单\n|..."},
    {"step_id": "summarize", "tool": "llm_summarize", "status": "done", "output": "待处理 2 项，已完成 1 项..."}
  ]
}
```

**响应 422（步骤失败）**：

```json
{
  "ok": false,
  "template_id": "version-day-check",
  "failed_step": "jql_query",
  "error": "JQL 查询语句为空，请在 context.jql 中提供或从 Admin 配置读取",
  "steps": [
    {"id": "jql_query", "tool": "jira_search", "status": "failed"},
    {"id": "format_checklist", "tool": "format", "status": "pending"},
    {"id": "summarize", "tool": "llm_summarize", "status": "pending"}
  ],
  "execution_log": [
    {"step_id": "jql_query", "tool": "jira_search", "status": "failed", "error": "JQL 查询语句为空..."}
  ]
}
```

**错误**：`400` — 缺少 `template_id`；`500` — 引擎异常。

### 8.4 模板注册表格式

定义文件：`backend/data/workflow_templates.yaml`。每个模板含 `id`（kebab-case 唯一）、`name`、`description`、`steps`（数组，每步含 `id`/`tool`/`description`/`params_schema`（可选））。

Step tool 类型（M5.3 实现）：
- `jira_search` — 执行 JQL 查询 Jira REST API（M5.2）
- `kb_search` — FAISS 语义检索优先，降级 catalog 关键词（M5.3）
- `jira_create_drafts` — 逐条调 `create_issues_draft` 创建草稿；单条失败不停全局，记录 `partial_failures`（M5.3）
- `format` — 纯 Python 格式化（检查清单 / draft 列表）
- `llm_summarize` — 调 DeepSeek LLM 汇总 / 提取子任务

### 8.5 特殊上下文参数（M5.3）

design-to-subtasks 模板支持的 context 参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `parent_issue_key` | string | 是 | 父 Issue Key，用于定位策划文档 |
| `doc_query` | string | 否 | 搜索策划文档的关键词（优先级高于 parent_issue_key） |
| `project_key` | string | 否 | Jira 项目 Key（默认从 Admin global_config 读取） |
| `issue_type` | string | 否 | 子任务 issueType（默认 Task） |
| `auto_confirm` | boolean | 否 | 调试用，自动 confirm drafts（**仅 ALICE_DEBUG=1 生效**） |
| `user_id` | string | 否 | 创建者 ID |
| `conversation_id` | string | 否 | 会话 ID |

### 8.6 design-to-subtasks 响应示例（M5.3）

```json
{
  "ok": true,
  "template_id": "design-to-subtasks",
  "template_name": "策划→子任务",
  "steps": [
    {"id": "read_design_doc", "tool": "kb_search", "status": "done"},
    {"id": "identify_subtasks", "tool": "llm_summarize", "status": "done"},
    {"id": "create_drafts", "tool": "jira_create_drafts", "status": "done",
     "partial_failures": []},
    {"id": "return_draft_list", "tool": "format", "status": "done"}
  ],
  "execution_log": [
    {"step_id": "read_design_doc", "tool": "kb_search", "status": "done",
     "output": "【FAISS 语义检索结果】\n查询: 策划案\n\n[策划案-球员系统.xlsx] (相似度:0.95)\n..."},
    {"step_id": "identify_subtasks", "tool": "llm_summarize", "status": "done",
     "output": "[{\"summary\":\"实现球员属性系统\",\"issueType\":\"Task\"},{\"summary\":\"实现球员位置管理器\",\"issueType\":\"Task\"}]"},
    {"step_id": "create_drafts", "tool": "jira_create_drafts", "status": "done",
     "output": "{\"total\":2,\"success\":2,\"failed\":0,\"drafts\":[{\"draft_id\":\"draft-abc123\",\"summary\":\"实现球员属性系统\",\"issueType\":\"Task\",\"projectKey\":\"CT\"},{\"draft_id\":\"draft-def456\",\"summary\":\"实现球员位置管理器\",\"issueType\":\"Task\",\"projectKey\":\"CT\"}],\"partial_failures\":[]}"},
    {"step_id": "return_draft_list", "tool": "format", "status": "done",
     "output": "## 策划→子任务 · 草稿列表（待 HITL 审批）\n| # | Draft ID | Summary | Status |\n|---|---|---|---|\n| 1 | `draft-abc123` | 实现球员属性系统 | [确认](/v1/drafts/draft-abc123/confirm) |"}
  ]
}
```

**注意**：`create_drafts` 步骤中 `partial_failures` 非空时 workflow 仍返回 `ok: true`，需逐条检查 failures 列表。**drafts 创建后不自动 confirm**，需人工通过 `/v1/drafts/{draft_id}/confirm` 审批（HITL 闭环）。
