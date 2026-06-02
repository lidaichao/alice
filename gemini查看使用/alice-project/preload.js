/**
 * Preload — 安全 IPC 桥
 * 参考白泽 preload.cjs contextBridge 模式
 */
const { contextBridge, ipcRenderer, clipboard } = require('electron');

contextBridge.exposeInMainWorld('desktopAPI', {
  // 多会话管理
  listConversations: () => ipcRenderer.invoke('conv:list'),
  createConversation: (title) => ipcRenderer.invoke('conv:create', title),
  getConversation: (id) => ipcRenderer.invoke('conv:get', id),
  deleteConversation: (id) => ipcRenderer.invoke('conv:delete', id),
  renameConversation: (id, title) => ipcRenderer.invoke('conv:rename', id, title),
  setActiveConversation: (id) => ipcRenderer.invoke('conv:setActive', id),
  appendMessage: (id, msg) => ipcRenderer.invoke('conv:appendMessage', id, msg),
  clearMessages: (id) => ipcRenderer.invoke('conv:clearMessages', id),

  // 窗口控制
  minimizeWindow: () => ipcRenderer.invoke('window:minimize'),
  toggleMaximize: () => ipcRenderer.invoke('window:toggleMaximize'),
  closeWindow: () => ipcRenderer.invoke('window:close'),

  // 文件
  selectFile: (opts) => ipcRenderer.invoke('dialog:openFile', opts),
  selectDir: () => ipcRenderer.invoke('dialog:openDir'),

  // 自动更新
  updater: {
    check: () => ipcRenderer.invoke('updater:check'),
    download: () => ipcRenderer.invoke('updater:download'),
    install: () => ipcRenderer.invoke('updater:install'),
    onStatus: (callback) => ipcRenderer.on('updater:status', (_event, payload) => callback(payload)),
    removeAllListeners: () => ipcRenderer.removeAllListeners('updater:status'),
  },

  // 剪贴板
  clipboard: {
    readText: () => clipboard.readText(),
  },

  // 数据库操作
  db: {
    truncateMessages: (convId, msgId) => ipcRenderer.invoke('db:truncateMessages', convId, msgId),
  },
});
