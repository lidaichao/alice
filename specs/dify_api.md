# Dify Knowledge Base API · Alice v3.0 集成参考（仅 RAG）

> 来源：Dify 官方文档 https://docs.dify.ai · 仓库：`alice/specs/dify/` · Apache 2.0
> 版本：v3.0 — Dify 仅用于知识库 RAG。AI 编排层改用 LangGraph（见 `langgraph_api.md`）
> 用途：Alice Hub 通过 REST API 调用 Dify **知识库**检索功能。所有端点来自官方 OpenAPI spec。

---

## 认证

```http
Authorization: Bearer {DIFY_KNOWLEDGE_API_KEY}
```

API Key 在 Dify 后台 → Knowledge → 右上角 Service API 中获取。
**一个 API Key 可访问同一账号下所有知识库。禁止在前端暴露 API Key。**

---

## 一、知识库检索（核心端点）

### POST /datasets/{dataset_id}/retrieve

> 来自 Dify 官方 OpenAPI spec `post /datasets/{dataset_id}/retrieve`

```bash
curl -X POST 'http://localhost:5001/v1/datasets/{dataset_id}/retrieve' \
  -H 'Authorization: Bearer {api_key}' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "怎么配置 Jira 连接",
    "retrieval_model": {
      "search_method": "hybrid_search",
      "reranking_enable": true,
      "reranking_model": {
        "reranking_provider_name": "cohere",
        "reranking_model_name": "rerank-english-v3.0"
      },
      "top_k": 5,
      "score_threshold_enabled": true,
      "score_threshold": 0.5
    }
  }'
```

**请求参数：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 搜索查询文本，最长 250 字符 |
| `retrieval_model.search_method` | string | 否 | `hybrid_search` / `keyword_search` / `semantic_search` |
| `retrieval_model.reranking_enable` | bool | 否 | 是否启用重排序 |
| `retrieval_model.top_k` | int | 否 | 返回最相关片段数 |
| `retrieval_model.score_threshold_enabled` | bool | 否 | 是否启用分数阈值过滤 |
| `retrieval_model.score_threshold` | float | 否 | 最低相似度分数（0-1） |

**响应（200）：**

```json
{
  "query": { "content": "怎么配置 Jira 连接" },
  "records": [
    {
      "segment": {
        "id": "chunk-uuid",
        "position": 1,
        "document_id": "doc-uuid",
        "content": "知识库片段文本内容...",
        "word_count": 128,
        "tokens": 256,
        "hit_count": 3,
        "index_node_hash": "abc123"
      },
      "child_chunks": null,
      "score": 0.89
    }
  ]
}
```

**Alice Hub 使用方式：** 在 Agent 的工具函数中调用此端点，返回的 `records[].segment.content` 作为 LLM 上下文注入。

---

## 二、知识库管理

### GET /datasets — 列出知识库

```bash
curl -X GET 'http://localhost:5001/v1/datasets?page=1&limit=20' \
  -H 'Authorization: Bearer {api_key}'
```

### POST /datasets — 创建知识库

```json
{
  "name": "Alice 项目文档",
  "description": "Alice v3.0 技术方案与产品文档",
  "indexing_technique": "high_quality",
  "permission": "only_me"
}
```

### GET /datasets/{dataset_id} — 获取知识库详情

返回知识库的 embedding_model、检索配置、文档统计等信息。

### DELETE /datasets/{dataset_id} — 删除知识库

---

## 三、文档管理

### POST /datasets/{dataset_id}/documents — 上传文档

通过 `multipart/form-data` 上传文件：
- `file`: 文件内容（支持 .txt, .md, .pdf, .docx）
- `data`: JSON 字符串，含 `indexing_technique`, `process_rule`, `name` 等

### GET /datasets/{dataset_id}/documents — 列出文档

支持分页、关键词搜索、状态过滤。

### DELETE /datasets/{dataset_id}/documents/{document_id} — 删除文档

---

## 四、Admin 代理层设计

Alice Admin 不直接调 Dify API。流程：

```
Admin 前端 → Alice Admin 后端 → Dify Knowledge API
```

| Admin 操作 | 调 Dify 端点 |
|-----------|-------------|
| 上传文档到知识库 | `POST /datasets/{id}/documents` |
| 查看知识库文档列表 | `GET /datasets/{id}/documents` |
| 测试知识库检索 | `POST /datasets/{id}/retrieve` |
| 查看知识库状态 | `GET /datasets/{id}` |
| 创建知识库 | `POST /datasets` |

---

## 五、废弃章节（v3.0 不再使用）

### ~~对话消息 API（Chat Messages）~~ [DEPRECATED]

> v3.0 统一使用 LangGraph 做 AI 对话推理。不再向 Dify 发聊天请求。

### ~~工作流执行 API（Workflow）~~ [DEPRECATED]

> v3.0 Agent 循环由 LangGraph StateGraph 控制，不用 Dify 工作流。

---

## 六、不可编造的端点

| ❌ 错误 | ✅ 正确 |
|---------|--------|
| `POST /v1/datasets/import` | `POST /v1/datasets/{id}/documents`（multipart/form-data） |
| `GET /v1/knowledge/search` | `POST /v1/datasets/{id}/retrieve` |
| `POST /v1/rag/generate` | AI 生成由 LangGraph 负责 |
| `GET /v1/datasets/{id}/chunks` | 使用 `POST /v1/datasets/{id}/retrieve` 检索 |

## 七、外部参考

| 资源 | URL |
|------|-----|
| Dify 官方文档 | https://docs.dify.ai |
| 知识库 API 参考 | https://docs.dify.ai/api-reference/knowledge-bases/retrieve-chunks-from-a-knowledge-base-test-retrieval |
| API 管理指南 | https://docs.dify.ai/en/use-dify/knowledge/manage-knowledge/maintain-dataset-via-api |
| Dify GitHub | https://github.com/langgenius/dify |
