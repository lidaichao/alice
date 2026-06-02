/**
 * Preload — 安全 IPC 桥
 * 参考白泽 preload.cjs contextBridge 模式
 */
const { contextBridge, ipcRenderer } = require('electron');

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
});
