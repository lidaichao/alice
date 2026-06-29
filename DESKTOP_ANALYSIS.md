# 白泽 Electron 桌面端深度分析

> 分析时间：2026-05-29 | 目标：评估可借鉴的桌面端实现模式

---

## 一、架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                    Electron 进程模型                          │
│                                                              │
│  ┌─────────────────────┐    IPC(ipcMain/ipcRenderer)        │
│  │   Main Process      │◄─────────────────────────────►     │
│  │   (main.cjs)        │                                    │
│  │                     │    ┌──────────────────────┐        │
│  │  ├─ autoUpdater     │    │  Renderer Process    │        │
│  │  ├─ ipcMain         │    │  (index.html)        │        │
│  │  ├─ sync poll       │    │                      │        │
│  │  └─ window mgmt     │    │  ├─ preload.cjs      │        │
│  └─────────┬───────────┘    │  │  (contextBridge)   │        │
│            │                │  ├─ renderer.js      │        │
│            │ HTTP/SSE       │  │  └─ styles.css     │        │
│            ▼                │  └──────────────────────┘        │
│  ┌─────────────────────┐    │                                 │
│  │  Express Server     │    │  contextIsolation: true         │
│  │  (127.0.0.1:3000)   │    │  nodeIntegration: false         │
│  └─────────────────────┘    │                                 │
└──────────────────────────────────────────────────────────────┘
```

**安全隔离模式**：
- `contextIsolation: true` — 渲染进程无法直接访问 Node API
- `nodeIntegration: false` — 防止 XSS → RCE
- `preload.cjs` — 通过 `contextBridge.exposeInMainWorld` 暴露受控 API

---

## 二、核心模块解析

### 2.1 Main Process (main.cjs) — 中枢控制器

职责：窗口管理、IPC 路由、自动更新、同步轮询、存储管理

```javascript
// 存储层（均基于 app.getPath('userData')）
getConversationStore()  → conversations.json       // 本地会话
getWorkspaceStore()     → workspaces.json          // 工作区授权
getLocalSyncStore()     → sync-events.json         // 事件同步
getJiraConfigStore()    → jira-config (加密存储)   // Jira 凭据
getClaudeCodeSessionStore() → claude-code-sessions.json

// IPC 处理器（~188行，约60个 handler）
registerIpcHandlers() {
  // 设置类: settings:getServerUrl, settings:setServerUrl, settings:getClientId
  // 更新类: update:check, update:download, update:install
  // 窗口类: window:minimize, window:toggleMaximize, window:close
  // 聊天类: baize:chat, baize:chatStream, baize:chatStream:cancel
  // 会话类: conversation:list/create/get/update/delete/appendMessage
  // Jira类: jira:importDrafts, jira:getOperation, jira:confirmOperation...
  // 审计类: audit:confirm, audit:reject
  // 工作区: workspace:list/authorize/setActive/revoke
  // 补丁类: patch:preview, patch:apply
}
```

### 2.2 Preload (preload.cjs) — 安全桥

通过 `contextBridge.exposeInMainWorld('baize', {...})` 暴露 **~40个 API 方法**：

| 分类 | 方法数 | 示例 |
|------|--------|------|
| 设置 | 6 | getServerUrl, setServerUrl, getClientId |
| 更新 | 4 | getUpdateStatus, checkForUpdate, downloadUpdate, installUpdate |
| 窗口 | 3 | minimizeWindow, toggleMaximizeWindow, closeWindow |
| 聊天 | 3 | chat, chatStream, cancelChatStream |
| 会话 | 8 | list/create/get/update/delete/appendConversation... |
| Jira | 8 | createJiraImportDrafts, confirmJiraOperation, reject... |
| 附件 | 3 | uploadAttachmentFile, uploadAttachmentData, remember |
| 审计 | 2 | confirmPluginAudit, rejectPluginAudit |
| 工作区 | 4 | listWorkspaces, authorizeWorkspace, setActive, revoke |
| 补丁 | 2 | previewPatch, applyPatch |

**关键安全设计**：
- 流式取消：`beginCancellableRequest()` 生成 requestId，`cancelChatStream()` 通过 IPC 发送取消
- Jira 确认事件监听：通过 `ipcRenderer.on('jira:confirmOperation:event')` 订阅进度

### 2.3 LocalRuntime — 客户端运行时引擎

**核心路由逻辑**：
```
handleChat(input)
  ├─ 读取服务端配置 readRuntimeConfig(serverUrl)
  ├─ 判断 shouldUseLocalClaudeCode(config)
  │   ├─ YES → localClaudeCode.send() + syncLocalEvents()
  │   └─ NO  → transport.sendChat(serverUrl, input)
```

**Jira 确认卡执行流程**：
```
confirmJiraOperation(operationId)
  → jiraService.confirmJiraOperation(operationId)     // 标记确认
  → localChat.send({ mode: 'jira_confirmed_execution' })
  → executeClientOperation(serverUrl, ...)             // Bridge 执行
  ├─ search_issue     → transport.searchJiraIssues()
  ├─ create_issue     → jiraService.createJiraImportDraftsWithOperation()
  ├─ get_project      → jiraService.getJiraProject()
  ├─ get_create_meta  → jiraService.getJiraCreateMeta()
  ├─ search_user      → jiraService.searchJiraUser()
  └─ create_confirmed_issue → jiraService.createConfirmedJiraIssue()
```

### 2.4 WorkspaceStore — 工作区授权

```javascript
authorizeWorkspace(rootPath)
  → 用户通过 dialog.showOpenDialog 选择目录
  → 规范化路径 + 去重检查
  → 写入 workspaces.json
  → 返回授权信息

// 使用场景
previewPatch({ workspaceId, patch })
  → getWorkspace(workspaceId)
  → 在授权目录内应用 diff
```

### 2.5 自动更新机制

```
启动时: checkForClientUpdate()
  → GET /client/version?platform=windows&version=X.X.X
  → 对比服务端返回的 updateUrl

手动: downloadClientUpdate()
  → autoUpdater.setFeedURL(updateUrl)
  → autoUpdater.checkForUpdates()
  → autoUpdater.downloadUpdate()

事件流:
  checking → available → downloading(进度%) → downloaded → quitAndInstall
```

更新产物：`latest.yml` + `白泽.exe` + `白泽.exe.blockmap`

---

## 三、与我们项目的对位分析

| 能力 | 白泽桌面端 | 我们当前 |
|------|-----------|---------|
| **客户端形态** | Electron 独立应用 | Jira Plugin (浏览器内嵌) |
| **进程安全** | contextIsolation + preload 桥 | 浏览器沙箱 |
| **AI 路由** | 本地 Claude Code ↔ 服务端双路由 | 服务端 DeepSeek 单路由 |
| **Jira 写操作** | 确认卡 + Claude Code 分步执行 | 确认卡 + SSE 事件流（新增） |
| **工作区管理** | 用户明确授权目录 | 无 |
| **自动更新** | electron-updater + latest.yml | Git Tag + 手动 build |
| **本地存储** | JSON 文件（userData） | localStorage + Jira 插件配置 |
| **附件处理** | 拖拽上传 + 客户端图片分析 | 浏览器粘贴上传 |

---

## 四、可借鉴的桌面端模式

### ★★★★ 值得引入

#### 4.1 工作区授权模式
如果未来需要支持代码修改（patch apply），必须引入授权机制：
```python
# 借鉴 workspace-store.cjs
class WorkspaceManager:
    def authorize(self, root_path):
        """用户明确授权目录"""
    def get_active(self):
        """获取当前活跃工作区"""
    def revoke(self, workspace_id):
        """撤销授权"""
```

#### 4.2 进程隔离安全模型
contextIsolation + preload 桥的模式非常安全，如果未来自建桌面端可作为参考。

### ★★★ 可选参考

#### 4.3 本地双路由 AI
白泽支持"本地 Claude Code"和"服务端 Claude"双路由，我们暂时用不上（DeepSeek 只在服务端）。

#### 4.4 自动更新机制
Jira 插件通过 Jira 的 UPM 管理，不需要独立的自动更新。

---

## 五、总结

白泽桌面端的核心价值在于：

1. **本地优先 + 安全隔离** — Electron 的 contextIsolation 确保渲染进程无法直接操作系统
2. **确认卡执行分离** — "AI 决策 → 确认卡 → 用户确认 → 本地执行" 多段安全链
3. **工作区授权** — 代码修改前必须用户显式授权目录
4. **客户端运行时** — local-runtime 作为客户端侧的智能路由器

对我们最有价值的借鉴是**工作区授权模式**和**确认卡执行分离**，这两项与我们的 P0 安全增强理念高度一致。
