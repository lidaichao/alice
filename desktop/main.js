/**
 * Main Process — 爱丽丝 Jira AI 桌面端 (Alice V2.0 Thin Client)
 * Electron 28 CJS — 纯 UI 壳，后端通过 HTTP/SSE 连接服务端 AI Bridge
 */
const { app, BrowserWindow, ipcMain, dialog, Menu, globalShortcut } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const { ConversationStore } = require('./conversations');

let mainWindow;
let convStore;

// ═══════════════ 自动更新配置 ═══════════════

autoUpdater.autoDownload = false;

function setupUpdaterEvents() {
  autoUpdater.on('checking-for-update', () => {
    mainWindow?.webContents.send('updater:status', { type: 'checking-for-update' });
  });

  autoUpdater.on('update-available', (info) => {
    mainWindow?.webContents.send('updater:status', { type: 'update-available', data: info });
  });

  autoUpdater.on('update-not-available', (info) => {
    mainWindow?.webContents.send('updater:status', { type: 'update-not-available', data: info });
  });

  autoUpdater.on('error', (err) => {
    mainWindow?.webContents.send('updater:status', {
      type: 'error',
      data: { message: err.message, stack: err.stack },
    });
  });

  autoUpdater.on('download-progress', (progress) => {
    mainWindow?.webContents.send('updater:status', {
      type: 'download-progress',
      data: {
        percent: progress.percent,
        speed: progress.bytesPerSecond,
        transferred: progress.transferred,
        total: progress.total,
      },
    });
  });

  autoUpdater.on('update-downloaded', (info) => {
    mainWindow?.webContents.send('updater:status', {
      type: 'update-downloaded',
      data: info,
    });
  });
}


// ═══════════════ IPC 注册 ═══════════════

function registerIPC() {
  // 会话
  ipcMain.handle('conv:list', () => convStore.list());
  ipcMain.handle('conv:create', (e, title) => convStore.create(title));
  ipcMain.handle('conv:get', (e, id) => convStore.get(id));
  ipcMain.handle('conv:delete', (e, id) => convStore.delete(id));
  ipcMain.handle('conv:rename', (e, id, title) => convStore.rename(id, title));
  ipcMain.handle('conv:setActive', (e, id) => convStore.setActive(id));
  ipcMain.handle('conv:appendMessage', (e, id, msg) => convStore.appendMessage(id, msg));
  ipcMain.handle('conv:clearMessages', (e, id) => convStore.clearMessages(id));
  ipcMain.handle('db:truncateMessages', (e, convId, msgId) => convStore.truncateMessagesFrom(convId, msgId));

  // 后端地址配置 (支持 B/S 架构演进)
  let serverURL = 'http://127.0.0.1:9099';
  ipcMain.handle('config:getServerURL', () => serverURL);
  ipcMain.handle('config:setServerURL', (e, url) => { serverURL = url; return true; });

  // 窗口
  ipcMain.handle('window:minimize', () => mainWindow?.minimize());
  ipcMain.handle('window:toggleMaximize', () => {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize(); else mainWindow?.maximize();
  });
  ipcMain.handle('window:close', () => mainWindow?.close());

  // 文件
  ipcMain.handle('dialog:openFile', async (e, opts) => {
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openFile'], filters: opts?.filters || [] });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('dialog:openDir', async () => {
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] });
    return result.canceled ? null : result.filePaths[0];
  });

  // 自动更新
  ipcMain.handle('updater:check', () => autoUpdater.checkForUpdates());
  ipcMain.handle('updater:download', () => autoUpdater.downloadUpdate());
  ipcMain.handle('updater:install', () => autoUpdater.quitAndInstall());
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

  // 开发模式: 连接 Vite dev server (前端在 ../frontend/)
  const isDev = process.env.NODE_ENV !== 'production' || !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://127.0.0.1:5174');
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'));
  }
}

// ═══════════════ 启动 ═══════════════

app.whenReady().then(() => {

  convStore = new ConversationStore(app.getPath('userData'));
  registerIPC();
  createWindow();
  setupUpdaterEvents();

  // ── Global Shortcut: Alt+Space Toggle (Spotlight-style) ──
  globalShortcut.register('Alt+Space', () => {
    if (!mainWindow) return;
    if (mainWindow.isVisible()) {
      if (mainWindow.isFocused()) {
        mainWindow.hide();
      } else {
        mainWindow.focus();
      }
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});
