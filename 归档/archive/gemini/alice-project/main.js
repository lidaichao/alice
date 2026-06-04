/**
 * Main Process — 爱丽丝 Jira AI 桌面端入口
 * Electron 28 CJS — 纯 UI 壳，无本地 Python
 */
const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron');
const path = require('path');
const { ConversationStore } = require('./conversations');

let mainWindow;
let convStore;

// ═══════════════ IPC 注册 ═══════════════
function registerIPC() {
  ipcMain.handle('conv:list', () => convStore.list());
  ipcMain.handle('conv:create', (e, title) => convStore.create(title));
  ipcMain.handle('conv:get', (e, id) => convStore.get(id));
  ipcMain.handle('conv:delete', (e, id) => convStore.delete(id));
  ipcMain.handle('conv:rename', (e, id, title) => convStore.rename(id, title));
  ipcMain.handle('conv:setActive', (e, id) => convStore.setActive(id));
  ipcMain.handle('conv:appendMessage', (e, id, msg) => convStore.appendMessage(id, msg));
  ipcMain.handle('conv:clearMessages', (e, id) => convStore.clearMessages(id));

  ipcMain.handle('window:minimize', () => mainWindow?.minimize());
  ipcMain.handle('window:toggleMaximize', () => {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize(); else mainWindow?.maximize();
  });
  ipcMain.handle('window:close', () => mainWindow?.close());

  ipcMain.handle('dialog:openFile', async (e, opts) => {
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openFile'], filters: opts?.filters || [] });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('dialog:openDir', async () => {
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] });
    return result.canceled ? null : result.filePaths[0];
  });
}

// ═══════════════ 窗口创建 ═══════════════
function createWindow() {
  Menu.setApplicationMenu(null);
  mainWindow = new BrowserWindow({
    width: 1200, height: 800,
    minWidth: 900, minHeight: 600,
    frame: false,
    title: '爱丽丝 Jira AI',
    backgroundColor: '#f4f5f7',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'ui', 'index.html'));
}

// ═══════════════ 启动 ═══════════════
app.whenReady().then(() => {
  convStore = new ConversationStore(app.getPath('userData'));
  registerIPC();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  app.quit();
});
