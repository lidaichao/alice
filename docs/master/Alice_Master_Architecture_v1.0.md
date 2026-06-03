# Alice AI Bridge — 核心架构技术文档 (Master Architecture)

> 版本：v1.0 Master | 日期：2026-06-03 | 作者：可达鸭 (Psyduck)
>
> 本文档基于仓库 `H:\workbuddy\alice` 全部实际代码和配置文件汇编而成。所有图表使用 Mermaid.js。

---

## 一、全局系统架构

```mermaid
graph TB
    subgraph 用户入口层
        A1[Electron 桌面<br/>desktop/main.js]
        A2[Jira 插件内嵌<br/>Java OSGi Plugin]
        A3[Web 管理后台<br/>:9099/admin]
    end

    subgraph 前端渲染层
        B1[React 19 + TS + Vite<br/>ai-bridge/src/]
        B2[原生 HTML/JS<br/>desktop/ui/]
        B3[插件 HTML 面板<br/>static/]
        B4[Zustand 状态管理<br/>chatSlice.ts]
        B5[Dexie IndexedDB<br/>会话/配置持久化]
    end

    subgraph IPC 通信层
        C1[contextBridge<br/>preload.js]
        C2[IPC Router<br/>20+ handlers]
        C3[Bridge Manager<br/>Python 子进程管理]
    end

    subgraph Python AI Bridge :9099
        D1[VIP 预检入口<br/>generate_stream]
        D2[VIP Diff 直通车<br/>Pre-flight RAG]
        D3[VIP Catalog 直通车<br/>文档搜索]
        D4[ReAct 循环<br/>5轮 max]
        D5[IntentRouter<br/>4类意图]
        D6[Nuclear V2<br/>核拦截+表决议]
        D7[Final Stream 安全网<br/>SSE 回退]
        D8[AuditGateway<br/>安全审计]
        D9[RotatingFileHandler<br/>持久化日志]
    end

    subgraph 工具执行层
        E1[6原子工具<br/>tools/registry.yaml]
        E2[knowledge_retriever.py<br/>SVN CLI / Notion / 动态关键词]
        E3[DynamicContextResolver<br/>Jira→user_text→issue_key]
        E4[JiraOperationManager<br/>确认卡状态机]
    end

    subgraph 外部服务
        F1[Jira Server 9.12.5<br/>ctjira1.lmdgame.com:8080]
        F2[SVN FishEye<br/>192.168.8.34:8060]
        F3[SVN CLI<br/>branches/v3]
        F4[Notion API<br/>策划文档V4]
        F5[Google Drive API<br/>需求文件]
        F6[DeepSeek V4 Flash<br/>文本生成]
    end

    A1 --> C1 --> C3 --> D1
    A2 --> B3 --> D1
    A3 --> D1
    B1 --> B4 --> B5

    D1 --> D2 --> E1 --> E2 --> F3
    D1 --> D3 --> E1 --> E2 --> F4
    D1 --> D4 --> D5
    D4 --> E1 --> E2
    D4 --> D6 --> D1
    D7 --> D1

    D2 --> F6
    D3 --> F6
    D4 --> F6

    E2 --> F1
    E2 --> F2
    E2 --> F5
    E3 --> F1

    D8 --> E4
    E4 --> F1
```

---

## 二、三端交付形态详解

### 2.1 Python AI Bridge (`ai-bridge/`)

```
ai-bridge/
├── ai_bridge.py              # 主引擎: VIP 入口 + ReAct 循环 + Flask 路由
├── knowledge_retriever.py    # 知识检索: SVN CLI, Notion, 动态关键词
├── intent_router.py          # 意图路由: 4 类意图正则匹配
├── prompt_manager.py         # 提示词引擎: CORE_SYSTEM_PROMPT_V2
├── intent_classifier.py      # 安全分类: dangerous/write/readonly (20/20 测试)
├── jira_api.py               # Jira REST 客户端
├── jira_mcp_server.py        # MCP 工具服务
├── jira_operation_manager.py # 确认卡状态机 (11/11 测试)
├── audit_gateway.py          # 安全审计网关 (9/9 测试)
├── logic_engine.py           # 业务逻辑与断言规则
├── eval_engine.py            # 评估引擎
├── tools/
│   └── registry.yaml         # 6 原子工具注册表
├── skills/
│   └── registry.yaml         # 插件注册表 (8 个工具)
├── tests/
│   └── test_vip_pipeline.py  # VIP 离线测试 (2/2 PASS)
├── logs/
│   └── alice_bridge.log      # 持久化日志 (10MB×5)
├── src/                      # React 19 前端 (App.tsx, chatSlice.ts, etc.)
├── static/                   # 静态资源
└── eval/                     # 评估数据集
```

### 2.2 Jira 插件 (`plugin/jira-workbuddy-plugin/`)

基于 Atlassian OSGi 架构的 Jira Server 9.12.5 插件。通过 Tampermonkey 脚本注入聊天面板。

```
jira-workbuddy-plugin/
├── pom.xml                   # Maven 依赖
├── atlassian-plugin.xml      # OSGi 插件描述
├── ConfigService.java        # 配置服务
├── AdminServlet.java         # 管理页面
├── ChatDialogServlet.java    # 聊天面板
├── ChatEndpoint.java         # WebSocket 端点
├── HttpUtil.java             # HTTP 工具
└── static/                   # HTML/CSS/JS 静态资源
```

### 2.3 Electron 桌面端 (`desktop/`)

```
desktop/
├── main.js                   # 主进程: 窗口管理 + IPC 路由
├── preload.js                # contextBridge 安全桥
├── conversations.js          # 多会话 JSON 存储
├── bridge-manager.js         # Python 子进程启动/健康检查/重启
├── package.json              # electron-builder 配置
├── dev.bat                   # 一键开发启动
├── ui/                       # HTML/CSS 渲染进程
└── dist/                     # 打包产物
```

---

## 三、一次标准指令执行的完整时序

```mermaid
sequenceDiagram
    participant User as 用户 (Electron/插件)
    participant UI as 前端 React/HTML
    participant IPC as contextBridge
    participant Bridge as Python AI Bridge
    participant Router as IntentRouter
    participant Tool as 工具执行器
    participant Jira as Jira API
    participant SVN as SVN/FishEye
    participant LLM as DeepSeek V4 Flash

    User->>UI: "CT-10888 最近提交了啥?"
    UI->>IPC: POST /v1/chat/completions
    Note over IPC: 转发 HTTP/SSE

    IPC->>Bridge: request body + user_config
    Bridge->>Bridge: VIP 预检: 无 diff/doc 意图
    Bridge->>Router: classify_query_type("CT-10888最近提交了啥?")
    Router-->>Bridge: CODE_COMMIT_LIST
    Note over Router: 分配工具: [query_jira_metadata, get_issue_commits]

    Bridge->>Tool: query_jira_metadata("CT-10888")
    Tool->>Jira: GET /issue/CT-10888?fields=summary,status
    Jira-->>Tool: {summary: "【系统】新增-阵型养成", status: "规划中"}
    Tool-->>Bridge: metadata

    Bridge->>Tool: get_issue_commits("CT-10888")
    Tool->>SVN: FishEye 双跳检索
    SVN-->>Tool: [r40312, r40379, r40414, r40415, r40538]
    Tool-->>Bridge: 5 条提交记录

    Note over Bridge: Nuclear V2 核拦截触发
    Bridge-->>UI: SSE: 【Alice 查询结果】表格
    Note over UI: 版本 | 作者 | 时间 | 文件数 | 说明
    UI-->>User: 5 条真实提交记录表格

    rect rgba(200, 220, 240, 0.3)
        Note over User,LLM: --- 追问: Diff 分析 (VIP 直通车) ---
        User->>UI: "分析一下 r40538 的代码 diff"
        UI->>Bridge: POST /v1/chat/completions
        Bridge->>Bridge: VIP 预检: _diff_rev="40538" ✅
        Note over Bridge: 进入 VIP Diff 直通车 (完全绕过 ReAct)

        Bridge->>SVN: get_single_commit_diff("40538")
        SVN-->>Bridge: raw_diff (语义裁剪后 3000 chars)

        Bridge->>Jira: DynamicContextResolver → summary → "新增-阵型养成"

        Bridge->>Bridge: search_docs_catalog("阵型养成") → Notion
        Bridge->>Bridge: read_specific_doc(first result) → doc_content

        Bridge->>Bridge: 组装 final_prompt:
        Note over Bridge: 【业务背景】NOTION 《战术系统设计案》<br/>【Diff】...<br/>【防幻觉指令】如实回答

        Bridge->>LLM: stream=True, tools=∅, temp=0.1
        LLM-->>Bridge: SSE 逐 token 流式 Code Review
        Bridge-->>UI: 实时 Markdown 渲染
        UI-->>User: 2200+ chars 专业分析
    end
```

---

## 四、核心设计模式与关键决策

### 4.1 VIP Express > ReAct Loop

```
传统 ReAct:
  User → LLM决策工具 → Python执行 → LLM决策工具 → ... → 回答
  问题: deepseek-v4-flash 在工具链末端输出 DSML 文本, 全部被过滤

VIP Express:
  User → Python全检索 (无LLM参与) → 组装Prompt → LLM纯文本流式
  优势: 零工具调用, 零DSML泄漏, 零幻觉, 稳定可靠
```

### 4.2 DeepSeek V4 Flash 适配策略

| 问题 | 方案 |
|------|------|
| 不支持 `tools` 参数 | VIP 路径用 Python 预检索, LLM 纯文本 |
| 输出 `<\|DSML\|>` 文本 | DSML 检测 + 清洗正则 + retry 逻辑 |
| 列表查询编造数据 | Nuclear V2 核拦截, 直接输出工具数据 |
| Final Stream 输出 tool_calls | Final Stream 安全网: 回退到工具数据 |

### 4.3 反幻觉三级防护

```
Layer 1: DynamicContextResolver — 零硬编码关键词
Layer 2: 文档溯源注入 — 标题+来源+防编造指令
Layer 3: Final Stream 安全网 — 过滤后回退到真实工具数据
```

---

## 五、数据与缓存层

| 缓存 | 策略 | TTL |
|------|------|-----|
| SVN 提交缓存 | `safe_get_commits()` | 60s |
| 语义缓存 | Jaccard 字符相似度 | 120s |
| LRU 缓存 | `BoundedCache` | 300s |
| 前端会话 | Dexie IndexedDB | 持久化 |
| 用户配置 | `electron-store` | OS 级加密 |

---

## 六、安全架构

```
用户消息
  →
L0: IntentClassifier (规则引擎)
  ├── ⛔ 直接拦截: rm -rf, force push, .env 泄露, SQL 注入
  ├── 🛡️ 确认卡: Jira 创建/更新, 企业微信发送
  └── ✅ 放行
  │
  ▼
AuditGateway (操作审计)
  ├── 敏感字段扫描 (password/secret/token)
  ├── 禁止关键词过滤
  ├── 速率限制 (per_minute / per_hour)
  └── 批量上限控制
  │
  ▼
JiraOperationManager (状态机)
  ├── awaiting_confirmation → running → created/failed/rejected
  └── 5 种错误分类 + 自动恢复方案
```

---

## 七、已知盲区与技术债

| # | 发现 | 影响 |
|---|------|------|
| 1 | `desktop_app_plan.md` 的 React 前端实际在 `ai-bridge/src/`，`desktop/` 仍用原生 HTML | 双轨前端 |
| 2 | `retrieval-architecture-plan.md` 的 Plan-and-Execute (S0→L4) 过于复杂 | 代码简化文档过时 |
| 3 | Java 插件与 Electron 桌面功能重叠 | 维护负担双倍 |
| 4 | React 19 前端不在项目根 `src/` 而在 `ai-bridge/src/` | 结构不直观 |
| 5 | `测试连接` 按钮未实现 | 用户无法自检 |
