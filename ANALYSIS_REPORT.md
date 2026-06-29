# 白泽 Baize Local Hub - 深度分析报告

> 分析时间：2026-05-29 | 版本：v0.2.27 | 8次提交 | GitHub: 774348172/AI-Project-Manager---AI-

---

## 一、项目概览

白泽是一个**本地优先的 AI 工作中枢**，将 Claude Code、本地记忆、逻辑断言、插件调用、Jira 操作确认等能力整合到一个 Electron 桌面工作台中。

| 维度 | 详情 |
|------|------|
| 作者 | zenghaorang (774348172@qq.com) |
| 技术栈 | Node.js 20+ / Express / Electron 42 / CommonJS |
| AI 模型 | Claude Code (Anthropic) + Anthropic SDK |
| 测试 | Vitest |
| 配置 | YAML |
| 打包 | electron-builder (NSIS) |
| 代码量 | ~163个源文件，~30个测试文件 |

---

## 二、架构深度分析

### 2.1 整体架构

```
┌─────────────────────────────────────────────┐
│           Electron 桌面客户端                  │
│  index.html + renderer.js + preload.cjs      │
│  ┌─────────────────────────────────────┐    │
│  │  main.cjs (IPC + 自动更新 + 同步)    │    │
│  │  ├── conversation-store (本地会话)    │    │
│  │  ├── workspace-store (工作区授权)     │    │
│  │  ├── local-sync-store (事件同步)      │    │
│  │  ├── local-jira-service (Jira本地)   │    │
│  │  ├── local-claude-code (Claude本地)   │    │
│  │  └── local-runtime (运行时引擎)       │    │
│  └─────────────────────────────────────┘    │
│            │  HTTP/SSE                      │
│            ▼                                │
│  ┌─────────────────────────────────────┐    │
│  │     Express 服务端 (Node.js)          │    │
│  │     默认: http://127.0.0.1:3000       │    │
│  │  ┌───────┐ ┌──────┐ ┌───────────┐   │    │
│  │  │ Chat  │ │Memory│ │ Plugins   │   │    │
│  │  │ Routes│ │Routes│ │ Routes    │   │    │
│  │  └──┬────┘ └──┬───┘ └─────┬─────┘   │    │
│  │     │         │           │          │    │
│  │  ┌──┴─────────┴───────────┴──────┐   │    │
│  │  │       Services Layer          │   │    │
│  │  │  ├── baize-chat-service       │   │    │
│  │  │  ├── memory-service           │   │    │
│  │  │  ├── logic-service            │   │    │
│  │  │  ├── jira-*-service (6个)     │   │    │
│  │  │  ├── plugin-gateway-service   │   │    │
│  │  │  ├── engineering-intent       │   │    │
│  │  │  ├── claude-code-service      │   │    │
│  │  │  ├── wecom-service            │   │    │
│  │  │  └── pending-audit/operation  │   │    │
│  │  └───────────────────────────────┘   │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
         │
    ┌────┴────┐
    │ Claude  │  (AI 推理)
    │  Code   │
    └─────────┘
```

### 2.2 核心设计模式

#### 内部智能体分工（五元架构）

白泽内部定义了5个不对外暴露的子智能体：

| 智能体 | 职责 | 配置位置 |
|--------|------|----------|
| memory_officer | 记忆读取/写入/索引管理 | `baize/config/agents/memory-officer.yaml` |
| logic_officer | 逻辑断言执行、规则匹配 | `baize/config/agents/logic-officer.yaml` |
| task_officer | Jira任务管理、操作确认 | `baize/config/agents/task-officer.yaml` |
| integration_officer | 企业微信等外部集成 | `baize/config/agents/integration-officer.yaml` |
| audit_officer | 操作安全审计 | `baize/config/agents/audit-officer.yaml` |

#### 插件注册表系统

```yaml
# baize/skills/registry.yaml
plugins:
  - id: jira         # Jira Software 插件
  - id: wecom        # 企业微信插件
  - id: knowledge_base  # 项目知识库插件
```

每个插件独立配置 `skill.md` + `config.yaml`，不耦合白泽核心逻辑。

#### 工程意图分类管道

用户消息 → `engineering-intent-service.js` → 正则分类 → 路由

```
ordinary_chat        → 普通对话，无需确认
engineering_readonly → 只读工程查询，无需确认
engineering_write    → 写操作，需要确认
ambiguous            → 模糊请求，无需确认
dangerous            → 危险操作(run -rf等)，强制拦截
engineering_test     → 测试/构建，需要确认
```

### 2.3 Jira 确认卡机制（核心亮点）

这是白泽最精巧的设计——Jira 写操作不是直接执行，而是：

```
1. AI 分析需求 → 生成草稿 (draftImport)
2. 草稿预校验 → 补全 projectKey/issueType/assignee
3. 生成确认卡 → 展示给用户 (status: awaiting_confirmation)
4. 用户确认 → 逐条创建 (status: running)
5. 失败恢复 → 自动分析错误类型 + 提供恢复方案
```

**状态机**：
```
awaiting_confirmation → running → created
                    ↘ failed → recovery_required → (retry/reject)
                    ↘ rejected
                    ↘ recovery_required → (cancel/supplement/retry)
```

**失败分类与自动恢复**：
| 错误类型 | 恢复方案 | 分类code |
|---------|---------|----------|
| 缺少 projectKey | 提示用户补充 | JIRA_PROJECT_REQUIRED |
| labels 字段不支持 | 移除labels后重试 | retry_without_labels |
| 未知错误 | 取消操作 | not_recoverable |
| 用户拒绝 | 标记rejected | - |

### 2.4 双层记忆系统

| 层级 | 存储 | 内容 | 文件位置 |
|------|------|------|----------|
| 浅层记忆 | .md 文件 | 摘要、索引、快速回忆 | `baize/memory/shallow/*.md` |
| 深层记忆 | 索引+分区 | 完整分析、附件副本、详细材料 | `baize/memory/deep/indexes/*.md` + `partitions/` |

分类维度：programming / design / art / general / pm / project

---

## 三、与我们当前项目的对比分析

### 3.1 对位对比

| 维度 | 白泽 (Baize) | 我们的项目 (Jira+WorkBuddy) |
|------|-------------|---------------------------|
| **AI 模型** | Claude Code (Anthropic) | DeepSeek V4 |
| **服务端** | Node.js/Express 单进程 | Python/Flask/Waitress 多线程 asyncio |
| **客户端** | Electron 桌面应用 | Jira Plugin (Java Servlet) + 浏览器 |
| **Jira 集成** | 原生 Jira REST API | 原生 Jira REST API + MCP Server |
| **记忆系统** | 双层文件记忆（Markdown） | 三层记忆（Cloud/User_Local/Workspace） |
| **确认机制** | Jira 确认卡 + 失败恢复 | 无（AI Bridge 直接执行） |
| **插件系统** | registry.yaml 统一注册 | 无统一注册表 |
| **意图分类** | 正则工程意图分类 | 无 |
| **安全机制** | 插件网关审计 + 危险操作拦截 | 配置文件级安全 |
| **更新机制** | Electron auto-updater | Git Tag + build脚本 |
| **WeCom** | Webhook 接入（框架） | Bot 回调 + Flask Bridge |
| **Notion** | 无 | 已连接（只读检索） |
| **Google Drive** | 无 | 已连接（只读检索） |
| **SVN** | 无 | CLI + 缓存 |
| **测试** | Vitest（~30个测试文件） | 手动 QA + Selenium |

### 3.2 白泽的优势

1. **Jira 确认卡机制** - 写操作安全防护最完善
2. **工程意图分类** - 用户意图自动路由
3. **插件注册表** - 松耦合、可扩展
4. **失败自动恢复** - 智能错误分类 + 方案推荐
5. **双记忆系统** - 区分摘要和详细材料
6. **桌面客户端** - Electron 原生体验

### 3.3 我们的优势

1. **asyncio 真并发** - L1 多源并发检索比白泽单线程强
2. **MCP 标准协议** - 标准化工具接口
3. **多源集成** - SVN/Notion/GDrive/WeCom 已全部打通
4. **SSE 流式** - 状态感知 + token 流，用户体验更好
5. **AI Decision First** - LLM 决策 JQL/相关性，比白泽的正则匹配更智能
6. **三层记忆** - Cloud + User + Workspace 比白泽的纯本地记忆更持久

---

## 四、值得借鉴/可直接移植的功能点

### ★★★★★ P0 级别 - 强烈建议引入

#### 4.1 Jira 确认卡 + 失败恢复机制

**当前状态**：我们的 AI Bridge 直接执行 Jira 写操作，无用户确认步骤。

**借鉴方案**：在 `ai_bridge.py` 中增加 `JiraOperationManager`，实现确认卡流程：
```
POST /v1/chat/completions → AI 决策创建 Jira
  ↓
生成 OperationCard (status: pending_confirmation)
  ↓ SSE event: {type: "confirm_card", data: {...}}
前端展示确认卡 → 用户点击确认
  ↓ POST /operations/{id}/confirm
Python 逐条创建 → 失败则自动分析 + 生成恢复方案
  ↓ SSE event: {type: "operation_complete"}
```

**可直接复用的代码**：`jira-operation-service.js` 的状态机逻辑、错误分类逻辑（`classifyJiraApiError`）、恢复方案生成（`buildDefaultRecoveryFromFailure`）。

#### 4.2 工程意图分类系统

**当前状态**：所有用户消息统一交给 DeepSeek 决策，无预处理分类。

**借鉴方案**：在 AI Bridge L1 层级前增加意图分类：
```python
# 借鉴 engineering-intent-service.js 的正则规则
INTENT_PATTERNS = {
    "dangerous": [r'\b(rm\s+-rf|reset\s+--hard|force\s+push)\b'],
    "engineering_write": [r'(修改|实现|新增|删除|重构).*(代码|文件|接口)'],
    "engineering_readonly": [r'(看一下|检查|分析|排查).*(代码|项目|问题)'],
    "jira_query": [r'(查|搜索|找|统计|汇总).*(任务|bug|story|问题)'],
}

def classify_intent(text: str) -> IntentResult:
    ...
```

**可直接复用的代码**：`engineering-intent-service.js` 的完整正则规则集。

### ★★★★ P1 级别 - 值得借鉴

#### 4.3 插件注册表系统

**当前状态**：工具/技能分散在各处，无统一管理。

**借鉴方案**：创建 `skills/registry.yaml`：
```yaml
tools:
  - id: jira_query
    owner: L1_search
    capabilities: [jql_search, issue_detail, weekly_summary]
  - id: svn_diff
    owner: L1_search
    capabilities: [commit_history, file_diff]
  - id: wecom_notify
    owner: integration
    capabilities: [send_message, receive_callback]
```

#### 4.4 安全审计网关

**当前状态**：无操作审计机制。

**借鉴方案**：在 AI Bridge 中增加 `AuditGateway`：
```python
class AuditGateway:
    RULES = {
        "jira_create": {
            "require_confirmation": True,
            "max_batch_size": 10,
            "forbidden_fields": ["password", "api_key"]
        }
    }
    
    async def audit(self, plugin, action, context) -> AuditResult:
        ...
```

#### 4.5 本地工作区授权

**当前状态**：直接操作文件，无授权确认。

**借鉴方案**：借鉴 `workspace-store.cjs` 的授权模式，增加工作区目录授权机制。

### ★★★ P2 级别 - 可参考

#### 4.6 双层记忆架构

白泽的浅层/深层记忆可与我们的三层记忆互补：
- 浅层记忆 ↔ 我们的 Workspace Memory (daily log)
- 深层记忆 ↔ 我们的 Cloud Memory (长期总结)

#### 4.7 客户端自动更新

如果未来需要独立客户端，可借鉴 `electron-updater` + `latest.yml` 的自动更新机制。

---

## 五、具体实施建议

### 第一阶段：安全增强（1-2天）

```
1. 创建 Python 版 JiraOperationManager
   - 移植白泽的状态机逻辑
   - 实现确认卡生成/确认/拒绝/恢复流程
   - 前端展示确认卡UI
   
2. 创建 IntentClassifier
   - 移植正则规则
   - 在 L1 之前添加分类管道
   - 危险操作直接拦截
```

### 第二阶段：架构优化（2-3天）

```
3. 创建 Plugin Registry
   - 统一管理所有工具/技能
   - 每个插件独立配置
   
4. 创建 AuditGateway
   - 插件操作审计
   - 敏感操作拦截
```

### 第三阶段：体验提升（可选）

```
5. 双层记忆优化
6. 工作区授权
7. 客户端更新（如需要）
```

---

## 六、可直接复用的代码清单

| 文件 | 可复用内容 | 移植难度 |
|------|-----------|---------|
| `src/services/jira-operation-service.js` | 确认卡状态机、失败分类、恢复方案 | 中等（JS→Python） |
| `src/services/engineering-intent-service.js` | 意图分类正则规则 | 简单 |
| `src/services/plugin-gateway-service.js` | 插件审计框架 | 简单 |
| `src/services/jira-client-service.js` | Jira API 错误分类 | 中等 |
| `src/services/memory-service.js` | 记忆分类和索引结构 | 简单 |
| `baize/skills/registry.yaml` | 插件注册表结构 | 简单 |
| `baize/logic/executable/*.yaml` | 规则配置模板 | 简单 |
| `client/desktop/workspace-store.cjs` | 工作区授权模式 | 简单 |

---

## 七、总结

白泽 Baize 是一个**设计思路优秀但实现尚早**的项目。它最突出的贡献是：

1. **Jira 确认卡** - 解决了 AI 写操作的安全性问题，我们的项目最缺这个
2. **意图分类管道** - 预处理避免 LLM 误判，比全靠 AI 决策更快更安全
3. **插件注册表** - 松耦合架构的典范
4. **失败自动恢复** - 智能错误处理，减少人工干预

建议**优先引入 P0 级别的确认卡和意图分类**，这两项对安全性提升最大、实现成本最低。
