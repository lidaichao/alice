# Alice AI Bridge — 产品需求文档 (PRD)

> 版本：v2.1 | 日期：2026-06-04

---

## 一、产品概述

**定位**：游戏研发团队的 AI 工作助手。联通 Jira、SVN、Notion、Google Drive 四大工具链，提供智能检索、代码审查和知识管理。

**核心价值**：
- 一句话查 Jira 任务 + SVN 提交 + 代码 Diff
- 自动关联 Notion 策划文档进行 Code Review
- 反幻觉设计：数据溯源 + 文档标题注入

**代号**：Alice V2.0（内部称 WorkBuddy，开发者代号"可达鸭"）

---

## 二、功能清单

### P0 — 已完成 ✅

| 功能 | 状态 | 说明 |
|------|------|------|
| Jira 任务查询 | ✅ | 元数据 + 关键词搜索 + 本周/个人任务 |
| SVN 提交列表 | ✅ | FishEye 双跳检索，返回版本号/作者/时间/文件数 |
| SVN Diff 分析 | ✅ | VIP 直通车：Python 全检索 + LLM 纯分析 |
| Notion/GDrive 关联 | ✅ | VIP 链路自动检索策划文档，注入 Code Review |
| 意图路由 | ✅ | CODE_COMMIT_LIST / CODE_COMMIT_DIFF / JIRA_QUERY / KNOWLEDGE |
| Nuclear V2 核拦截 | ✅ | 列表查询强制输出表格，防止 LLM 废话 |
| 反幻觉溯源 | ✅ | 文档标题 + 来源注入 prompt，防编造指令 |
| 动态关键词提取 | ✅ | DynamicContextResolver：零硬编码 |
| 日志持久化 | ✅ | RotatingFileHandler → logs/alice_bridge.log (10MB×5) |
| 语义化 Diff 裁剪 | ✅ | 去冗余 → 提纯 +/- 行 |
| SSE 异常兜底 | ✅ | 前端错误气泡 + isGenerating 复位 |
| VIP 离线测试 | ✅ | test_vip_pipeline.py (2/2 PASS) |
| VIP 周报直通车 | ✅ | 动态截止时间字段 + 日期区间 JQL + PM 周报 prompt |
| Admin 默认模型切换 | ✅ | 下拉即保存；API 地址/Key 独立编辑；F5 加载守卫 |
| Admin Jira 字段映射 | ✅ | `JIRA_DEADLINE_FIELD_BY_PROJECT` JSON 配置 |

### P1 — 规划中

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 多项目管理 | 高 | 动态切换 Jira 项目上下文 |
| 企业微信集成 | 高 | Bot 消息推送，状态通知 |
| Admin 监控仪表盘 | 中 | 统计与任务队列可视化增强 |

### P2 — 远期

| 功能 | 说明 |
|------|------|
| Agent 市场 | 可安装的领域专家 Agent |
| 图片多模态 | 截图直接提问 |
| 桌面端 .exe 分发 | electron-builder NSIS 安装包 |

---

## 三、架构选型

| 决策 | 原因 |
|------|------|
| Python Pre-flight RAG | deepseek-v4-flash 不支持标准 tools 参数 |
| VIP 直通车绕过 ReAct | LLM 在工具链末端不可靠 |
| DynamicContextResolver | 消灭硬编码，Jira → user_text → issue_key |
| Electron + React 19 | 现代前端 + 安全 IPC |

---

## 四、版本里程碑

| 版本 | 日期 | 关键功能 |
|------|------|---------|
| v1.0-alpha | 2026-05-29 | 基础对话 + Jira 查询 |
| v1.0-nuclear | 2026-06-02 | Nuclear V2 核拦截、DSML 兼容 |
| v2.0-vip | 2026-06-03 | VIP 直通车、反幻觉溯源、Catalog 直通车 |
| v2.1-infra | 2026-06-03 | 日志持久化、语义裁剪、SSE 兜底、离线测试 |
