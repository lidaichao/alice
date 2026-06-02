/**
 * Main Process — 爱丽丝 Jira AI 桌面端入口
 * Electron 28 CJS — 托管 Python AI Bridge 生命周期 + 自动更新
 */
const { app, BrowserWindow, ipcMain, dialog, Menu, globalShortcut } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn, execSync } = require('child_process');
const path = require('path');
const { ConversationStore } = require('./conversations');

let mainWindow;
let convStore;
let pyProcess = null;

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

// ═══════════════ Python 后端生命周期 ═══════════════

function startPythonService() {
  const isDev = !app.isPackaged;

  const pythonCmd = isDev
    ? path.join(__dirname, '..', '..', '.workbuddy', 'binaries', 'python', 'versions', '3.13.12', 'python.exe')
    : path.join(process.resourcesPath, 'python', 'python.exe');

  const scriptPath = isDev
    ? path.join(__dirname, '..', 'ai-bridge', 'ai_bridge.py')
    : path.join(process.resourcesPath, 'backend', 'ai_bridge.py');

  console.log(`[PythonService] 启动: ${pythonCmd} ${scriptPath}`);
  console.log(`[PythonService] 模式: ${isDev ? 'development' : 'production'}`);

  pyProcess = spawn(pythonCmd, ['-B', scriptPath], {
    windowsHide: true,
    env: { ...process.env },
  });

  pyProcess.stdout.on('data', (data) => {
    console.log(`[Python stdout] ${data.toString().trimEnd()}`);
  });

  pyProcess.stderr.on('data', (data) => {
    console.error(`[Python stderr] ${data.toString().trimEnd()}`);
  });

  pyProcess.on('error', (err) => {
    console.error(`[PythonService] 进程启动失败:`, err.message);
  });

  pyProcess.on('exit', (code, signal) => {
    if (signal) {
      console.warn(`[PythonService] 进程被信号终止 (${signal})`);
    } else if (code !== 0 && code !== null) {
      console.warn(`[PythonService] 进程异常退出，退出码: ${code}`);
    } else {
      console.log(`[PythonService] 进程正常退出`);
    }
  });
}

function stopPythonService() {
  if (!pyProcess) return;

  const pid = pyProcess.pid;
  console.log(`[PythonService] 正在停止进程 (PID: ${pid})...`);

  if (process.platform === 'win32') {
    try {
      execSync(`taskkill /pid ${pid} /T /F`, { stdio: 'ignore' });
      console.log(`[PythonService] 进程树已强制终止 (PID: ${pid})`);
    } catch (e) {
      console.log(`[PythonService] 进程已不存在，无需清理`);
    }
  } else {
    pyProcess.kill('SIGTERM');
    const forceKillTimer = setTimeout(() => {
      if (pyProcess && !pyProcess.killed) {
        pyProcess.kill('SIGKILL');
      }
    }, 3000);
    pyProcess.on('exit', () => clearTimeout(forceKillTimer));
  }

  pyProcess = null;
}

// ═══════════════ 应用退出守护 ═══════════════

app.on('before-quit', () => {
  stopPythonService();
});

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

  mainWindow.loadFile(path.join(__dirname, 'ui', 'index.html'));
}

// ═══════════════ 启动 ═══════════════

app.whenReady().then(() => {
  startPythonService();

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
