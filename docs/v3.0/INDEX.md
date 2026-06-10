# Alice v3.0 方案索引

> 杰尼龟、卡罗尔：v3.0 各文档集中索引。
> **唯一技术方案以兔子（CTO）版本为准**，不要自行发挥。
> 方案文档位置：`coordinator-rabbit/docs/ALICE_V3_RESTRUCTURE_PLAN.md`
> 杰尼龟开发时，对应的 spec 文件和开源仓库必须作为 API 参考逐条对照。

---

## 开源仓库（已克隆到 specs/ 本地）

| 项目 | 路径 | 用途 |
|------|------|------|
| **LangGraph** | `alice/specs/langgraph/` | AI Agent 编排层。看 `libs/cli/examples/graphs/agent.py` 入门 |
| **Dify** | `alice/specs/dify/` | 知识库 RAG。看 API 参考文档定位知识库端点 |

> n8n 未克隆本地（仓库太大 ~800MB）。API 参考来自官方文档 https://docs.n8n.io/api/

---

## Spec 文档

| 文档 | 来源 | 说明 |
|------|------|------|
| **langgraph_api.md** ✨ | 仓库 `agent.py` + `test_pregel_async.py` | StateGraph/HITL/Streaming 完整 API，agent_graph.py 模板 |
| **dify_api.md** | Dify 官方 OpenAPI spec | 知识库 RAG 端点（检索/上传/管理），已废弃对话&工作流章节 |
| **n8n_api.md** | n8n 官方 API 文档 | 凭据/工作流/执行管理 REST API |
| **n8n_workflow.md** | n8n 官方节点文档 | Jira/Webhook/Function 节点 JSON 格式 |

> ⚠️ `dify_workflow_dsl.md` — 已废弃，保留供格式参考。

---

## 杰尼龟开发速览

| 模块 | 技术 | 核心参考 | 代码形式 | 覆盖率 |
|------|------|---------|---------|--------|
| Agent 循环 | LangGraph | `langgraph_api.md` + `specs/langgraph/` 仓库 | `agent_graph.py` | ✅ 100% |
| 知识库 RAG | Dify | `dify_api.md` | Python 调用器 | ✅ 100% |
| Jira/SVN 集成 | n8n | `n8n_api.md` + `n8n_workflow.md` | JSON workflow + Python 桥接 | ✅ 80% |
| 鉴权/RBAC | 保留 | — | 不改 | ✅ |
| Admin 代理 | Flask | `dify_api.md` §四 + `n8n_api.md` §四 | Python 端点 | ✅ 100% |
| ConfirmCard | 保留 | — | 不改 | ✅ |

## 历史文档

| 位置 | 说明 |
|------|------|
| `alice/docs/master/alice三期蓝图计划.md` | 保留 |
| `alice/docs/master/Alice_Master_Architecture_v1.0.md` | 保留 |
| `alice/docs/master/Alice_API_Contract_v1.0.md` | 保留 |
| 其余 master 文档 | 标记 `[DEPRECATED v3.0]` |
| `eval/reports/archive/` | 历史里程碑报告 |
