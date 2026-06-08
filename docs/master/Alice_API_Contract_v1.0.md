# Alice AI Bridge — API 契约文档 (v1.0)

> 版本：**v1.0（已冻结）** | 日期：2026-06-08 | 作者：可达鸭 (Psyduck)
>
> 本文档通过逆向读取 `backend/ai_bridge.py` 中的 Flask 路由装饰器生成。
> ⚠️ SSE 接口标记为 `stream: text/event-stream`。

**相关文档**：[三期蓝图计划（开发校准）](alice三期蓝图计划.md) · [Master 架构](Alice_Master_Architecture_v1.0.md) · [前端组件树](Alice_Frontend_Component_Tree_v1.0.md) · [灰盒 SOP](Alice_Graybox_SOP_v1.0.md)

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
| `/v1/admin/tasks/batch-analysis` | POST | 创建批量分析任务 |
| `/v1/admin/tasks/<task_id>/status` | GET | 查询任务状态 |

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

## 六、API 全量汇总

```
核心业务:
  POST /v1/chat/completions    SSE — 对话主入口
  POST /v1/chat/orchestrate    SSE — 编排对话

Jira 操作:
  GET  /operations/<id>           确认卡详情
  POST /operations/<id>/confirm   确认操作（body 含 jira_pat）
  POST /operations/<id>/reject    拒绝操作
  GET  /operations/pending        待确认列表（?conversation_id=）
  GET  /operations                管控台列表（?status= 逗号分隔）

MCP（中期 M1，只读）:
  GET  /mcp/v1/tools              只读工具清单（registry.yaml risk=readonly）
  POST /mcp/v1/tools/<name>       调用只读工具 { "arguments": {...} }

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
