# Alice — Jira AI 智能助手

CT（足球小将）项目 WorkBuddy AI 插件的完整工程仓库。

## 项目结构

```
alice/
├── desktop/          ← Electron 桌面客户端 (main.js, preload.js, ui/)
├── ai-bridge/        ← Python AI Bridge 后端 (Flask + Waitress + SSE)
├── plugin/           ← Jira Java OSGi 插件 (jira-workbuddy-plugin)
├── scripts/          ← 构建 & 部署脚本
├── docs/             ← 项目文档
├── workspace/        ← WorkBuddy 工作区 (.workbuddy 记忆/技能/计划)
└── research/         ← 竞品研究 (Claw, LobeHub, Baize)
```

## 技术栈

| 组件 | 技术 | 端口 |
|------|------|:---:|
| 前端 | Electron 28 + Vanilla JS | - |
| 后端 | Python Flask + Waitress + SSE | 9099 |
| AI | DeepSeek V4 Pro (Tool Calling) | - |
| 数据源 | Jira 9.12.5 / SVN / Notion / Google Drive | - |

## 架构

```
Electron (desktop/)           Python (ai-bridge/)
    │ HTTP SSE :9099               │
    ├──────────────────────────────┤
    │                              ├── Jira API (ctjira1.lmdgame.com:8080)
    │  4 原子工具:                  ├── SVN FishEye (双跳 Diff 检索)
    │  query_jira_metadata          ├── Notion (目录→详情 层级检索)
    │  get_issue_commits            ├── Google Drive (目录→详情 层级检索)
    │  search_docs_catalog          └── DeepSeek API (ReAct 循环)
    │  read_specific_doc
```

## 版本

- Alice V2.0 (2026-06-02) — LlamaIndex 层级检索 + 标准 Tool Calling

## 快速启动

```bash
# 后端
cd ai-bridge && python ai_bridge.py

# 前端
cd desktop && npm start
```
