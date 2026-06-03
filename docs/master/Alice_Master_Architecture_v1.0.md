# Alice AI Bridge — 技术架构文档 (V2.1 Final)

> 版本：v2.1 | 日期：2026-06-03 | 分支：master | 最新提交：2a61258

---

## 【核心约束】奥卡姆剃刀原则

> **Electron (容器) + React (前端视图) + Python (后端大脑) 唯一主干架构**
> Java Jira 插件已归档至 `archive/`

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
| AI 流式 | **Vercel AI SDK (@ai-sdk/react)** | `useChat` + `append` API |
| UI 组件 | **@lobehub/ui (ChatList, CopyButton)** | 商业级聊天皮肤 |
| 状态管理 | **Zustand + idb-keyval (IndexedDB)** | 会话持久化 (突破 5MB) |
| 安全 | IntentRouter + AuditGateway | 多层防护 |

---

## 系统架构

```
用户请求
  │
  ├─ diff意图 (r\d+) → VIP Diff 直通车 (Python全检索 → LLM纯分析)
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
| 意图路由 | `backend/intent_router.py` | 6 类意图 (含 KNOWLEDGE_QUERY) |
| 知识检索 | `backend/knowledge_retriever.py` | SVN/Notion/动态关键词 |
| 评测引擎 | `eval/` | ingest → generate → run_tests → benchmark |

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