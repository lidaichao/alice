# Alice AI Bridge — API 契约文档 (v1.0)

> 版本：v1.0 | 日期：2026-06-03 | 作者：可达鸭 (Psyduck)
>
> 本文档通过逆向读取 `backend/ai_bridge.py` 中的 Flask 路由装饰器生成。
> ⚠️ SSE 接口标记为 `stream: text/event-stream`。

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
| `/v1/admin/config` | GET | 获取当前配置 |
| `/v1/admin/config` | POST | 更新配置（热重载） |
| `/v1/admin/stats` | GET | 获取统计信息 |
| `/v1/admin/verify` | POST | 验证用户权限 |
| `/v1/admin/token` | POST | Token 管理 |

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
| `/v1/admin/models` | GET | 获取模型配置列表 |
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

---

## 五、系统端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康检查 `{"status":"ok","engine":"deepseek-chat"}` |
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
  POST /operations/<id>/confirm   确认操作
  POST /operations/<id>/reject    拒绝操作
  GET  /operations/pending        待确认列表

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
