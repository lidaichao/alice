# Jira Plugin → 桌面客户端 重构方案

> 基于白泽 Baize Electron 架构，将当前 Jira 插件改造为独立桌面应用

---

## 一、现状分析

### 当前架构（Plugin 模式）

```
┌──────────────────────────────────────────────────────────┐
│  用户浏览器 → Jira Web (http://ctjira1:8080)             │
│    │                                                     │
│    ├─ admin.html (Jira Plugin 面板)                      │
│    └─ chat-dialog.html (侧栏/全宽聊天)                    │
│         │                                                │
│         ↓ POST /plugins/servlet/wb/chat                  │
│    ChatEndpoint.java (Java, 纯透传 ~88行)                 │
│         │                                                │
│         ↓ HTTP POST :9099/v1/chat/completions            │
│    AI Bridge (Python/Flask/Waitress, :9099)              │
│         │                                                │
│         ├── L0 IntentClassifier                          │
│         ├── L1 asyncio 4源并发检索                        │
│         ├── L2 深度检索                                   │
│         └── DeepSeek API → SSE 流式返回                   │
└──────────────────────────────────────────────────────────┘

问题：
  ✗ 必须打开 Jira Web 才能使用
  ✗ 依赖 Jira Server 运行（Tomcat + Java 插件）
  ✗ 插件部署/更新需重启 Jira
  ✗ 浏览器沙箱限制了文件操作能力
```

### 目标架构（Desktop 模式）

```
┌──────────────────────────────────────────────────────────┐
│  🖥️  白泽桌面客户端 (Electron App, .exe)                 │
│                                                          │
│  ┌─────────────┐  IPC(preload)  ┌─────────────────┐     │
│  │ Main Process │◄──────────────►│ Renderer Process │     │
│  │ (main.js)    │               │ (HTML/JS/CSS)    │     │
│  │              │               │                  │     │
│  │ ├ 启动Bridge │               │ ├ admin.html     │     │
│  │ ├ IPC路由    │               │ ├ chat-dialog    │     │
│  │ ├ 自动更新   │               │ └ 设置面板       │     │
│  │ └ 窗口管理   │               │                  │     │
│  └──────┬───────┘               └────────┬─────────┘     │
│         │                               │               │
│         │ child_process                 │ HTTP/SSE      │
│         ▼                               ▼               │
│  ┌──────────────────────────────────────────────┐       │
│  │    AI Bridge (Python, 子进程)                 │       │
│  │    localhost:9099                            │       │
│  │    ├── L0 IntentClassifier                  │       │
│  │    ├── L1 4源并发检索                        │       │
│  │    ├── L2 深度检索                           │       │
│  │    ├── JiraOperationManager                 │       │
│  │    ├── AuditGateway                         │       │
│  │    └── DeepSeek API → SSE                   │       │
│  └──────────────────────────────────────────────┘       │
│         │                                                │
│         ├── Jira REST API (:8080)                       │
│         ├── SVN / FishEye                               │
│         ├── Notion API                                  │
│         └── Google Drive API                            │
└──────────────────────────────────────────────────────────┘

优势：
  ✅ 独立运行，不依赖 Jira Web
  ✅ 一键启动（自动拉起 Python Bridge）
  ✅ 打包为 .exe，分发简单
  ✅ Electron 提供原生能力（托盘、通知、文件拖拽）
  ✅ 独立更新机制（auto-updater）
```

---

## 二、技术选型

| 层面 | 技术 | 理由 |
|------|------|------|
| **桌面框架** | Electron 42 | 白泽同款，成熟稳定，生态丰富 |
| **打包工具** | electron-builder | 支持 NSIS 安装包、自动更新 |
| **进程管理** | Node child_process | 自动启动/停止 Python Bridge |
| **IPC 通信** | contextBridge + ipcRenderer | 安全隔离模式（白泽同款） |
| **后端引擎** | Python Flask + Waitress | **完全复用**现有 AI Bridge |
| **UI 层** | HTML/CSS/JS | **完全复用** chat-dialog + admin |
| **存储** | electron-store 或 JSON | 配置持久化 |
| **自动更新** | electron-updater | 白泽同款 |

---

## 三、模块复用分析

### 完全复用（零改动）

| 现有模块 | 路径 | 复用方式 |
|----------|------|----------|
| AI Bridge 核心 | `wecom-jira-bridge/ai_bridge.py` | 作为子进程启动，零改动 |
| Jira API 客户端 | `wecom-jira-bridge/jira_api.py` | 被 AI Bridge 导入，零改动 |
| MCP Server | `wecom-jira-bridge/jira_mcp_server.py` | 被 AI Bridge 导入，零改动 |
| IntentClassifier | `wecom-jira-bridge/intent_classifier.py` | 被 AI Bridge 导入，零改动 |
| JiraOperationManager | `wecom-jira-bridge/jira_operation_manager.py` | 被 AI Bridge 导入，零改动 |
| AuditGateway | `wecom-jira-bridge/audit_gateway.py` | 被 AI Bridge 导入，零改动 |
| 插件注册表 | `wecom-jira-bridge/skills/registry.yaml` | 配置复用，零改动 |
| .env 配置 | `wecom-jira-bridge/.env` | 凭据复用，零改动 |

### 需要适配

| 现有模块 | 现状 | 适配内容 |
|----------|------|----------|
| **chat-dialog.html** | Jira Plugin 内嵌 | 去掉 Jira 依赖（`/plugins/servlet/wb/chat`），改为直连 `localhost:9099` |
| **admin.html** | Jira Plugin 面板 | 提取为独立设置页，去掉 Jira 上下文 |
| **ChatEndpoint.java** | Java 透传网关 | **废弃**，Electron preload 替代 |
| **ChatDialogServlet.java** | Java Servlet | **废弃** |
| **HttpUtil.java** | Java HTTP 工具 | **废弃** |

### 新增模块

| 模块 | 功能 | 参照 |
|------|------|------|
| `alice/main.js` | Electron 主进程 | 白泽 main.cjs |
| `alice/preload.js` | 安全 IPC 桥 | 白泽 preload.cjs |
| `alice/bridge-manager.js` | Python 子进程管理 | 新增 |
| `alice/config-store.js` | 配置持久化 | 白泽 settings |
| `package.json` | Electron 项目配置 | 白泽 package.json |

---

## 四、目录结构规划

```
H:\workbuddy\baize-desktop\          # 新项目根目录
├── package.json                     # Electron + 依赖 + 打包配置
├── electron-builder.yml             # 打包详细配置
│
├── alice/                         # Electron 桌面端
│   ├── main.js                      # 主进程（窗口管理/IPC/更新/子进程）
│   ├── preload.js                   # 安全桥（contextBridge）
│   ├── bridge-manager.js            # Python Bridge 子进程管理
│   ├── config-store.js              # 配置持久化
│   └── assets/
│       ├── icon.ico                 # 应用图标
│       └── tray-icon.png            # 托盘图标
│
├── renderer/                        # 渲染进程（UI）
│   ├── index.html                   # 主窗口（聊天界面）
│   ├── settings.html                # 设置面板（管理员配置）
│   ├── chat-dialog.html             # ← 从 Jira Plugin 迁移
│   ├── admin.html                   # ← 从 Jira Plugin 迁移
│   ├── styles.css                   # 样式
│   ├── renderer.js                  # 渲染逻辑
│   └── browser-adapter.js           # 浏览器→Electron API 适配
│
├── bridge/                          # Python AI Bridge（子模块或复制）
│   ├── ai_bridge.py                 # ← 从 wecom-jira-bridge 复制
│   ├── jira_api.py                  # ← 同上
│   ├── jira_mcp_server.py           # ← 同上
│   ├── intent_classifier.py         # ← 同上
│   ├── jira_operation_manager.py    # ← 同上
│   ├── audit_gateway.py             # ← 同上
│   ├── skills/registry.yaml         # ← 同上
│   ├── requirements.txt
│   └── .env                         # 用户配置（gitignore）
│
├── dist/                            # 打包产物（gitignore）
└── README.md
```

---

## 五、核心实现要点

### 5.1 Python Bridge 子进程管理

```javascript
// bridge-manager.js
const { spawn } = require('child_process');
const path = require('path');

class BridgeManager {
  constructor() {
    this.process = null;
    this.port = 9099;
    this.pythonPath = null;  // 自动检测或打包内置
  }

  async start() {
    // 1. 检测 Python 环境（内置或系统）
    // 2. 检测/安装依赖 pip install -r requirements.txt
    // 3. 启动: python ai_bridge.py
    this.process = spawn(this.pythonPath, ['ai_bridge.py'], {
      cwd: path.join(__dirname, '..', 'bridge'),
      env: { ...process.env, AI_BRIDGE_PORT: String(this.port) }
    });

    // 4. 等待 /health 返回 ok
    await this.waitForReady();
  }

  async stop() {
    if (this.process) {
      this.process.kill('SIGTERM');
      this.process = null;
    }
  }
}
```

### 5.2 Preload 安全桥

```javascript
// preload.js
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktopAPI', {
  // Bridge 管理
  getBridgeUrl: () => ipcRenderer.invoke('bridge:getUrl'),
  getBridgeStatus: () => ipcRenderer.invoke('bridge:status'),

  // 配置
  getSettings: () => ipcRenderer.invoke('settings:get'),
  setSettings: (data) => ipcRenderer.invoke('settings:set', data),

  // 聊天（直连 AI Bridge）
  sendChat: (input) => ipcRenderer.invoke('chat:send', input),

  // 文件操作
  selectFile: () => ipcRenderer.invoke('dialog:openFile'),
  selectDir: () => ipcRenderer.invoke('dialog:openDir'),

  // 窗口
  minimize: () => ipcRenderer.invoke('window:minimize'),
  close: () => ipcRenderer.invoke('window:close'),

  // 更新
  checkUpdate: () => ipcRenderer.invoke('update:check'),
  downloadUpdate: () => ipcRenderer.invoke('update:download'),
});
```

### 5.3 主进程窗口管理

```javascript
// main.js
const { app, BrowserWindow } = require('electron');
const { BridgeManager } = require('./bridge-manager');

let mainWindow;
const bridge = new BridgeManager();

app.whenReady().then(async () => {
  // 1. 启动 Python Bridge
  await bridge.start();

  // 2. 创建主窗口（无框，参考白泽）
  mainWindow = new BrowserWindow({
    width: 1100, height: 760,
    minWidth: 860, minHeight: 620,
    frame: false,           // 自定义标题栏
    title: '白泽 - Jira AI',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });

  // 3. 加载聊天界面
  mainWindow.loadFile('renderer/index.html');
});

app.on('before-quit', async () => {
  await bridge.stop();  // 优雅关闭 Python
});
```

### 5.4 打包配置

```yaml
# electron-builder.yml
appId: com.baize.desktop.jira
productName: 白泽-Jira AI
directories:
  output: dist
files:
  - alice/**/*
  - renderer/**/*
  - bridge/**/*
  - package.json
extraResources:
  - from: bridge/
    to: bridge/
win:
  icon: alice/assets/icon.ico
  target: nsis
nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
publish:
  - provider: generic
    url: http://your-update-server/client-updates
```

---

## 六、迁移路径（分阶段）

### Phase 1: 最小可用（1-2天）

```
目标：能启动、能聊天
├── 创建 Electron 项目骨架
├── 实现 BridgeManager（启动/停止 Python）
├── 迁移 chat-dialog.html（去掉 Jira 依赖）
├── 实现 preload 桥（基础消息收发）
└── 验证：发送消息 → AI Bridge → DeepSeek → SSE 渲染
```

### Phase 2: 功能完整（2-3天）

```
目标：功能与 Jira Plugin 版持平
├── 迁移 admin.html（设置面板）
├── 确认卡 UI 集成
├── 实现配置持久化（electron-store）
├── P0/P1 安全模块联调
├── 托盘图标 + 最小化到托盘
└── 快捷键支持
```

### Phase 3: 分发就绪（1-2天）

```
目标：可打包分发
├── electron-builder 配置 + 打包测试
├── 内置 Python 环境（embedded Python 或检测系统 Python）
├── 自动更新机制
├── 安装包测试（安装/卸载/升级）
└── 文档 + 使用说明
```

### Phase 4: 体验增强（可选）

```
├── 文件拖拽上传
├── 深色模式自动切换
├── 多窗口支持
├── 通知提醒
└── 性能优化
```

---

## 七、关键决策

### 决策1：Python 环境方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 内置 embedded Python | 无依赖，开箱即用 | 包体大（+50MB）|
| B. 检测系统 Python | 包体小 | 用户需自行安装 Python |
| C. **PyInstaller 打包 Bridge** | 独立 exe，体积可控 | 构建复杂 |

**推荐 A**：用户体验最好，参考 VS Code / Postman 的做法。

### 决策2：Bridge 端口

固定 `9099`，启动前检查端口占用，冲突时自动选择可用端口并通知渲染进程。

### 决策3：更新策略

- Python Bridge 更新：跟随桌面端一起分发
- 桌面端更新：electron-updater + latest.yml
- 配置/凭据：更新不覆盖

---

## 八、与白泽的差异

| 维度 | 白泽 Baize | 我们的桌面端 |
|------|-----------|-------------|
| AI 引擎 | Claude Code (Node.js) | DeepSeek (Python) |
| 服务端 | Express 同进程 | Flask 子进程 |
| 进程管理 | 无需 | BridgeManager |
| Jira 集成 | 确认卡（同架构） | 确认卡 + 直接 API |
| 代码修改 | workspace-store | 暂不需要 |
| 附件处理 | 拖拽 + Claude 分析 | 粘贴上传 |

---

## 九、文件变更清单

### 新增文件

```
H:\workbuddy\baize-desktop\
├── package.json                          # 项目配置
├── electron-builder.yml                  # 打包配置
├── .gitignore
├── alice/
│   ├── main.js                           # 主进程
│   ├── preload.js                        # 安全桥
│   ├── bridge-manager.js                 # Bridge 子进程管理
│   └── config-store.js                   # 配置存储
├── renderer/
│   ├── index.html                        # 主窗口
│   ├── settings.html                     # 设置页
│   └── styles.css                        # 全局样式
├── bridge/                               # Python Bridge（从现有复制）
│   ├── ... (全部 .py 文件)
│   └── .env.example
└── assets/
    └── icon.png
```

### 废弃/移除文件（从 Jira Plugin 项目）

```
jira-workbuddy-plugin/
├── ChatEndpoint.java      → 废弃
├── ChatDialogServlet.java → 废弃
├── HttpUtil.java          → 废弃
├── chat.js                → 废弃（功能合并到 desktop）
```

---

## 十、启动流程

```
用户双击 白泽.exe
    │
    ▼
Electron Main Process 启动
    │
    ├── 1. 检查 Python 环境
    │       ├── 内置 Python: bridge/python/python.exe
    │       └── 系统 Python: 自动检测 PATH
    │
    ├── 2. 安装/更新 Python 依赖
    │       pip install -r bridge/requirements.txt
    │
    ├── 3. 启动 AI Bridge 子进程
    │       python bridge/ai_bridge.py
    │       等待 http://127.0.0.1:9099/health → ok
    │
    ├── 4. 创建主窗口
    │       BrowserWindow → 加载 renderer/index.html
    │
    └── 5. 检查更新
            GET /client/version → 新版本? → 下载
```

---

## 十一、总结

这次重构的核心思路是**"去 Jira 依赖，保留 AI 引擎，披上 Electron 外壳"**。

| 保留 | 废弃 | 新增 |
|------|------|------|
| AI Bridge（全部Python代码） | Jira Plugin Java层 | Electron 主进程 |
| chat-dialog + admin UI | ChatEndpoint/HttpUtil | BridgeManager |
| P0/P1 安全模块 | Jira 插件部署流程 | 预加载安全桥 |
| .env 配置体系 | - | electron-builder 打包 |

**核心优势**：Python AI 引擎完全不动，只换了一个"壳"，开发成本低、风险可控。
