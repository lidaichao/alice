# Alice AI Bridge — 技术架构文档 (V2.2)

> 版本：v2.4 | 日期：2026-06-08 | 分支：master

**相关文档**：[三期蓝图计划（开发校准）](alice三期蓝图计划.md) · [Master PRD](Alice_Master_PRD_v1.0.md) · [文档索引](README.md) · [技术说明 TECHNICAL](TECHNICAL.md) · [API 契约](Alice_API_Contract_v1.0.md) · [MCP 接入](M1_MCP_Cursor_setup.md) · [灰盒 SOP](Alice_Graybox_SOP_v1.0.md) · [上游参考：白泽 Baize 架构](Baize_Architecture_v1.0.md)

> **排期与模块拆分顺序**以蓝图为准（近期 E1 绞杀者：`chat_orchestrator` / `plugin_gateway`）。

---

## 【核心约束】奥卡姆剃刀原则

> **Electron (容器) + React (前端视图) + Python (后端大脑) 唯一主干架构**
> Java Jira 插件已归档至 `归档/archive/jira-workbuddy-plugin/`

---

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 桌面框架 | Electron 28 | 跨平台容器 |
| 后端引擎 | Python Flask + Waitress 10-thread | AI 服务 |
| AI 模型 | DeepSeek V4 Flash | 对话 + 分析 |
| 智能体 | **LangGraph Plan-and-Execute** | V2.0 图状大脑 |
| 向量检索 | **FAISS + DeepSeek Embedding** | V2.1 RAG 语义搜索 |
| 前端 | React 19 + TypeScript + Vite + Tailwind | SPA UI |
| AI 流式 | **原生 fetch + ReadableStream + SSE** | doSendMessage 内置引擎 |
| UI 组件 | **@lobehub/ui (ChatList)** | 聊天皮肤（需 meta: {title,avatar}） |
| 状态管理 | **Zustand + idb-keyval (IndexedDB)** | 会话持久化 (突破 5MB) |
| 安全 | IntentRouter + AuditGateway | 多层防护 |

---

## 系统架构

```
用户请求
  │
  ├─ diff意图 (r\d+) → VIP Diff 直通车 (Python全检索 → LLM纯分析)
  ├─ 周报/日报意图 → VIP Weekly 直通车 (动态 End date JQL → 表格 → LLM)
  ├─ ALICE_ENGINE=v2 → LangGraph Plan-and-Execute
  │   ├─ Planner (意图分诊: doc_only / cross_domain / chat)
  │   ├─ Executor (工具路由: Jira / SVN / search_doc_chunks)
  │   └─ Synthesizer (汇总分析 → SSE)
  └─ 其他 → ReAct 循环 (降级方案)
         │
    ┌────┴────┬──────────┬──────────┐
    │ Jira    │ SVN      │ Notion   │ FAISS RAG
    │ REST    │ FishEye  │ API      │ search_doc_chunks
    └─────────┴──────────┴──────────┴──────────┘
```

---

## 核心模块

| 模块 | 路径 | 职责 |
|------|------|------|
| AI Bridge | `backend/ai_bridge.py` | 主引擎 + Flask 路由 |
| LangGraph Agent | `backend/agent/` | V2.0 Planner/Executor/Synthesizer |
| RAG 引擎 | `backend/rag_engine.py` | FAISS 向量索引 + search_doc_chunks |
| 意图路由 | `backend/intent_router.py` | 作业通道分诊；KB 列举走通用 L1（C9） |
| 聊天编排 | `backend/chat_orchestrator.py` | VIP / ReAct 统一入口（E1） |
| GDrive 知识库 | `backend/gdrive_knowledge.py` | catalog → read；表头槽位筛选（L2） |
| MCP 注册 | `backend/mcp_registry.py` | Hub MCP 工具暴露（M1） |
| 知识检索 | `backend/knowledge_retriever.py` | SVN/Notion/动态关键词 |
| 评测引擎 | `eval/` | ingest → generate → run_tests → benchmark |
| 全局配置 | `backend/global_config.json` | Admin POST merge；`DEEPSEEK_MODEL` 驱动默认对话模型 |
| Admin UI | `backend/admin.html` | Vue 3 CDN；模型即时保存 + API 分轨编辑 |

---

## Admin 配置流

```
Admin 下拉切换模型
  → POST /v1/admin/config { DEEPSEEK_MODEL }
  → global_config.json + os.environ 热重载
  → 新对话 parse_user_config() 读取 global_cfg.DEEPSEEK_MODEL

F5 刷新
  → GET /v1/admin/config (saved_model)
  → await GET /v1/admin/models
  → hydratingModel 守卫，禁止加载期误 POST
```

---

## 基准性能 (V2.1)

| 指标 | V1 | V2.1 |
|------|:--:|:--:|
| 平均延迟 | ~20s | 17.8s |
| 平均上下文 | 15k+ chars | 765 chars |
| 忠实度 | 20% | 40% |
| 相关性 | 30% | 40% |

---

## 关键设计决策

| 决策 | 原因 |
|------|------|
| LangGraph Plan-and-Execute | 替代手搓 while 循环 |
| FAISS search_doc_chunks | Token 节省 95% |
| doc_only 意图分诊 | 杜绝跨系统幽灵调用 |
| tool_choice: required | 强制 LLM 调用工具 |
| Stop Interceptor | 第一轮话痨拦截 |
| 行级 DSML 过滤 | 修复跨行 .*? 吞噬全文 bug |

---

## 上游参考：白泽（Baize）

Alice 的 Jira 确定性查询、确认卡、工程意图拦截等能力，语义上移植自 **白泽 Baize**（Node.js + Claude Code 本地 Hub）。对照与模块映射见 [Baize_Architecture_v1.0.md](Baize_Architecture_v1.0.md) §11；Jira 准确性 A/B 见 [eval/reports/jira_baize_ab_latest.md](../../eval/reports/jira_baize_ab_latest.md)。