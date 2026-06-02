# 爱丽丝 Jira AI 桌面客户端 — 技术架构文档

> 版本：v1.0 | 日期：2026-05-29

---

## 一、技术栈

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 桌面框架 | Electron | 42.1.0 | 跨平台桌面应用 |
| 后端引擎 | Python Flask + Waitress | 3.13 | AI 服务 + 数据检索 |
| AI 模型 | DeepSeek API | V3/R1 | 对话生成 + 意图理解 |
| 前端 UI | HTML5 + CSS3 + Vanilla JS | — | 无框架依赖，极轻量 |
| IPC 通信 | contextBridge + ipcRenderer | — | 进程安全隔离 |
| 配置存储 | electron-store | 8.2 | JSON 本地持久化 |
| 会话存储 | 自定义 JSON Store | — | 多会话历史管理 |
| 安全 | 意图分类 + 确认卡 + 审计 | — | 自研安全体系 |

---

## 二、系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Electron 桌面应用                          │
│                                                              │
│  ┌──────────────┐   IPC(preload)   ┌────────────────────┐   │
│  │ Main Process  │◄────────────────►│ Renderer Process   │   │
│  │  main.js      │                 │  ui/index.html     │   │
│  │               │                 │                    │   │
│  │ • BridgeMgr   │                 │ • 多会话侧栏       │   │
│  │ • ConvStore   │                 │ • 聊天区(SSE流式)  │   │
│  │ • IPC 路由    │                 │ • 设置面板         │   │
│  │ • 窗口管理    │                 │ • 确认卡 UI        │   │
│  └──────┬────────┘                 └────────┬───────────┘   │
│         │ child_process                     │ HTTP/SSE      │
│         ▼                                   ▼               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │        Python AI Bridge (Flask :9099)                │   │
│  │                                                      │   │
│  │  ┌──────────────┐  ┌──────────────────┐             │   │
│  │  │ L0 Intent    │  │ L1 并发检索       │             │   │
│  │  │ Classifier   │  │ asyncio 4源并行   │             │   │
│  │  │ (5类意图)    │  │ Jira/SVN/Notion/  │             │   │
│  │  │              │  │ Google Drive      │             │   │
│  │  └──────────────┘  └────────┬─────────┘             │   │
│  │                              │                       │   │
│  │  ┌──────────────┐  ┌────────▼─────────┐             │   │
│  │  │ AuditGateway │  │ L2 深度检索       │             │   │
│  │  │ 审计+限流     │  │ 详情+Diff+文档    │             │   │
│  │  └──────────────┘  └────────┬─────────┘             │   │
│  │                              │                       │   │
│  │  ┌──────────────────────────▼───────────────────┐   │   │
│  │  │  DeepSeek API → SSE 逐 token 流式返回       │   │   │
│  │  │  语义缓存 + 智能截断 + TTFT 0.1s             │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│         │                                                    │
│    ┌────┴────┬──────────┬──────────┐                        │
│    │ Jira    │ SVN/     │ Notion   │ Google                  │
│    │ REST    │ FishEye  │ API      │ Drive                   │
│    └─────────┴──────────┴──────────┴──────────┘              │
└──────────────────────────────────────────────────────────────┘
```

---

## 三、模块详解

### 3.1 桌面端（alice/）

#### main.js — 主进程
```javascript
// 入口流程
app.whenReady()
  → ConversationStore 初始化
  → registerIPC()  // 注册 ~20 个 IPC 处理器
  → BridgeManager.start()  // 启动 Python 子进程
  → createWindow()  // 创建 BrowserWindow + 加载 UI
```

**IPC 处理器分类：**

| 分类 | 处理器 | 功能 |
|------|--------|------|
| bridge | getUrl, status | Python 服务状态查询 |
| conv | list/create/get/delete/rename/append | 多会话 CRUD |
| settings | get/set/getKey/setKey | 配置读写 |
| window | minimize/toggleMaximize/close | 窗口控制 |
| dialog | openFile/openDir | 文件选择器 |

#### preload.js — 安全桥
```
contextBridge.exposeInMainWorld('desktopAPI', {
  // 20+ 方法，通过 ipcRenderer.invoke 调用主进程
})
```
安全策略：`contextIsolation: true`, `nodeIntegration: false`

#### conversations.js — 会话管理
- 存储：`app.getPath('userData')/conversations.json`
- 结构：`{ conversations: [...], activeId: "..." }`
- 自动命名：用第一条用户消息的前 30 字符

#### bridge-manager.js — Python 子进程管理
- 启动：`spawn(python, ['ai_bridge.py'])`
- 健康检查：轮询 `http://127.0.0.1:9099/health`
- 自动重启：崩溃后最多重试 3 次
- 优雅关闭：`SIGTERM` → 2s 等待 → `SIGKILL`

### 3.2 AI Bridge（wecom-jira-bridge/）

#### ai_bridge.py — 核心引擎（77547 行）
```
POST /v1/chat/completions
  → L0: IntentClassifier.classify(text)
      ├── dangerous     → 直接拒绝，返回拦截消息
      ├── jira_write    → 生成确认卡 SSE 事件
      ├── write         → 标记需确认
      └── readonly/chat → 正常流程
  → L1: asyncio.wait() 4 源并发检索
      ├── Jira: JQL 查询 + 本周汇总
      ├── SVN: svn log --search 关键词
      ├── Notion: POST /search
      └── GDrive: files.list
  → LLM 决策：DeepSeek 打分 + 生成 JQL
  → L2: 针对高分源拉取详情
  → DeepSeek API: SSE 逐 token 流式返回
```

**REST 端点：**

| 端点 | 方法 | 功能 |
|------|------|------|
| `/v1/chat/completions` | POST | 核心聊天（SSE 流式） |
| `/operations/<id>` | GET | 获取确认卡详情 |
| `/operations/<id>/confirm` | POST | 确认创建 |
| `/operations/<id>/reject` | POST | 拒绝操作 |
| `/health` | GET | 健康检查 |

**缓存体系：**
- BoundedCache: LRU + TTL（300s）
- 语义缓存: Jaccard 相似度匹配（120s）
- SVN 缓存: 5min TTL

#### intent_classifier.py — 意图分类
```
8 层优先级规则匹配：
  DANGEROUS > TEST > JIRA_WRITE > ENGINEERING_WRITE
  > ENGINEERING_READONLY > JIRA_QUERY > AMBIGUOUS > CHAT
```

#### jira_operation_manager.py — 确认卡状态机
```
awaiting_confirmation → running → created
                                 → failed → recovery_required
                                 → rejected
```
5 种错误分类 + 自动恢复方案

#### audit_gateway.py — 审计网关
- 敏感字段检测（password/secret/token 等）
- 禁止关键词过滤
- 速率限制（per_minute / per_hour）
- 批量上限控制

### 3.3 前端 UI（alice/ui/）

#### index.html — 主界面
```
三栏布局：
  ├── 左侧：会话列表（搜索 + 筛选 + CRUD）
  ├── 中央：聊天区（消息流 + 输入框 + 快捷发言）
  └── 右侧：上下文面板（可折叠）

设置面板（6 标签页）：
  连接 → AI 模型 → 偏好 → 角色 → 快捷 → 关于
```

#### styles.css — 样式
- 800+ 行，Atlassian 配色体系
- 支持滑块、下拉菜单、折叠面板
- 自定义标题栏（无框窗口）

---

## 四、数据流

### 4.1 一次完整对话的数据流

```
[用户输入] "查CT项目本周Bug"
    │
    ▼
[Renderer] fetch POST /v1/chat/completions
    │  {messages: [{role:"user", content:"..."}], config:{...}}
    ▼
[Python Bridge]
    │ L0: classify → "jira_query" (放行)
    │ L1: Jira 查询 → 12 issues
    │ LLM: 相关性评分 → jira:9/10, svn:3/10
    │ L2: 拉取 issues 详情
    │ DeepSeek API → 生成回答
    ▼
[SSE 流式]
    │ data: {"_intent":{"route":"jira_query"}}
    │ data: {"choices":[{"delta":{"content":"本周"}}]}
    │ data: {"choices":[{"delta":{"content":"CT项目"}}]}
    │ ...
    │ data: [DONE]
    ▼
[Renderer] 逐 token 渲染 Markdown
    │ 追加到 conversationStore
    ▼
[用户看到完整回答]
```

### 4.2 写操作安全流

```
[用户] "创建Bug: 登录页崩溃"
    │
    ▼
[L0] classify → "jira_write"
    │
    ▼
[SSE] data: {"_event":"confirm_card", "operation":{...}}
    │
    ▼
[确认卡 UI] 🛡️ Jira 操作确认
    │  标题: 登录页崩溃
    │  类型: Bug | 项目: CT
    │  [✅ 确认创建] [✕ 取消]
    │
    ▼ 用户点确认
[POST /operations/<id>/confirm]
    │ AuditGateway.check()
    │ Jira API → POST /rest/api/2/issue
    │
[SSE] 创建成功 ✅ CT-9999
```

---

## 五、安全架构

### 5.1 分层防护

```
用户消息
  →
L0: IntentClassifier (规则引擎)
  ├── ⛔ 直接拦截
  │     rm -rf, force push, .env 泄露, SQL 注入
  ├── 🛡️ 确认卡
  │     Jira 创建/更新, 企业微信发送
  └── ✅ 放行
  │
  ▼
AuditGateway (操作审计)
  ├── 敏感字段扫描
  ├── 禁止关键词过滤
  ├── 速率限制
  └── 批量上限
  │
  ▼
JiraOperationManager (状态机)
  ├── 确认卡生命周期
  ├── 失败自动分类
  └── 恢复方案生成
```

### 5.2 数据安全

| 数据 | 存储位置 | 加密 |
|------|---------|------|
| Jira PAT | electron-store (本地加密) | ✅ OS 级别 |
| DeepSeek Key | electron-store | ✅ OS 级别 |
| Notion/GDrive Key | electron-store | ✅ OS 级别 |
| 会话历史 | JSON 文件（userData） | ❌ 明文 |
| SVN 密码 | electron-store | ✅ OS 级别 |

---

## 六、开发指南

### 6.1 环境要求

| 工具 | 最低版本 |
|------|---------|
| Node.js | 18+ |
| Python | 3.10+ |
| npm | 9+ |

### 6.2 项目结构

```
H:\workbuddy\jira\
├── alice/                     # Electron 桌面端
│   ├── main.js                # 主进程入口
│   ├── preload.js             # IPC 安全桥
│   ├── bridge-manager.js      # Python 子进程管理
│   ├── conversations.js       # 多会话存储
│   ├── package.json           # 依赖 + 打包配置
│   ├── dev.bat                # 一键开发启动
│   └── ui/                    # 渲染进程 UI
│       ├── index.html         # 主界面
│       └── styles.css         # 样式
│
├── wecom-jira-bridge/         # Python AI 引擎
│   ├── ai_bridge.py           # 核心服务 (77547行)
│   ├── jira_api.py            # Jira REST 客户端
│   ├── jira_mcp_server.py     # MCP 工具服务
│   ├── intent_classifier.py   # 意图分类器
│   ├── jira_operation_manager.py  # 确认卡状态机
│   ├── audit_gateway.py       # 安全审计网关
│   ├── skills/registry.yaml   # 插件注册表
│   └── .env                   # 凭据配置(gitignore)
│
├── jira-workbuddy-plugin/     # Jira 插件(Web备份)
│   └── src/main/resources/static/
│       ├── chat-dialog.html   # Web 聊天界面
│       └── admin.html         # Web 配置面板
│
└── docs/                      # 设计文档
    ├── PRD.md                 # 产品需求文档
    ├── TECHNICAL.md           # 技术架构文档
    ├── desktop_app_plan.md    # 桌面端重构方案
    ├── alice_ux_optimization.md   # UX 优化方案
    └── project_audit.md       # 项目审计报告
```

### 6.3 启动方式

```bash
# 1. 启动 Python AI Bridge（独立窗口）
cd wecom-jira-bridge
python ai_bridge.py          # 监听 :9099

# 2. 启动 Electron（另一个窗口 / 双击 dev.bat）
cd alice
dev.bat                      # 或 npx electron main.js
```

### 6.4 开发热更新

| 场景 | 操作 | 耗时 |
|------|------|------|
| HTML/CSS 修改 | 按 `Ctrl+R` | < 1秒 |
| main.js 修改 | 关闭窗口重开 dev.bat | < 3秒 |
| Python 修改 | 在 Bridge 窗口 `Ctrl+C` 重启 | < 5秒 |

### 6.5 打包分发

```bash
cd alice
npm run dist    # electron-builder 打包为 .exe 安装包
# 产物在 alice/dist/
```

---

## 七、API 参考

### 7.1 AI Bridge REST API

#### POST /v1/chat/completions
```json
// 请求
{
  "messages": [
    {"role": "system", "content": "系统提示词"},
    {"role": "user", "content": "用户问题"}
  ],
  "config": {
    "jira_url": "http://jira:8080",
    "jira_pat": "xxx",
    "_wbUserId": "user-id"
  }
}

// 响应: SSE 流
data: {"_intent":{"route":"jira_query","matched":"查询"}}
data: {"choices":[{"delta":{"content":"根据查询结果..."}}]}
data: [DONE]
```

#### GET /health
```json
{"ok": true, "cache_hits": 42, "uptime": 3600}
```

### 7.2 IPC API（preload 暴露）

```javascript
// 渲染进程中调用
window.desktopAPI.getBridgeUrl()       // → "http://127.0.0.1:9099"
window.desktopAPI.listConversations()  // → {conversations:[...], activeId:"..."}
window.desktopAPI.createConversation("标题")
window.desktopAPI.getSettings()        // → {jiraUrl, modelName, ...}
```

---

## 八、测试

### 8.1 自动化测试

| 模块 | 用例 | 通过率 |
|------|------|--------|
| intent_classifier.py | 20/20 | 100% |
| jira_operation_manager.py | 11/11 | 100% |
| audit_gateway.py | 9/9 | 100% |
| ai_bridge.py (语法) | — | ✅ |
| alice/*.js (语法) | 4/4 | 100% |

运行：`python intent_classifier.py` / `python jira_operation_manager.py` / `python audit_gateway.py`

### 8.2 人工测试清单

- [ ] 桌面端窗口正常打开
- [ ] Jira 连接测试通过
- [ ] 发送消息 → AI 回复流式展示
- [ ] 确认卡弹出/确认/拒绝流程
- [ ] 多会话创建/切换/删除
- [ ] 设置面板保存后生效
- [ ] 危险操作被拦截

---

## 九、常见问题

**Q: Electron 启动闪退？**
A: 确保已运行 `npm install`，且 Python 环境可用。

**Q: AI Bridge 连接失败？**
A: 检查是否启动了 `python ai_bridge.py`，端口 9099 是否被占用。

**Q: Jira 查询无结果？**
A: 检查 Jira 地址和 PAT 是否正确，`测试连接` 按钮验证。

**Q: 如何切换 DeepSeek 模型？**
A: 设置 → AI 模型 → 下拉选择 V3 或 R1。
