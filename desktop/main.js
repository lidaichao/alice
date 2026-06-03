/**
 * Main Process — 爱丽丝 Jira AI 桌面端 (Alice V2.0 Thin Client)
 * Electron 28 — React 前端 + PyInstaller 后端
 *
 * 核心生命周期:
 *   app.whenReady → spawnPythonBackend → createWindow
 *   before-quit → killPythonBackend (防僵尸进程!)
 */
const { app, BrowserWindow, ipcMain, dialog, Menu, globalShortcut } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const { spawn } = require('child_process');
const { ConversationStore } = require('./conversations');

let mainWindow;
let settingsWindow; // ← Settings 子窗口引用
let convStore;
let pythonProcess = null; // ← 引用 Python 子进程，防僵尸

// ══════════════ Python 子进程管理 ══════════════

function getBackendPath() {
  const isPackaged = app.isPackaged;
  if (isPackaged) {
    // 打包环境: PyInstaller 产物在 Resources/backend-dist/ai_bridge/
    const base = process.platform === 'darwin'
      ? path.join(process.resourcesPath, 'backend-dist')
      : path.join(process.resourcesPath, 'backend-dist');
    const binary = process.platform === 'win32' ? 'ai_bridge.exe' : 'ai_bridge';
    return path.join(base, 'ai_bridge', binary);
  } else {
    // 开发环境: 直接用 Python 解释器
    return null; // 返回 null 表示用 dev 模式启动
  }
}

function spawnPythonBackend() {
  const bin = getBackendPath();

  if (bin) {
    // ── 打包模式: 启动 PyInstaller 编译后的可执行文件 ──
    console.log('[Main] Spawning packaged backend:', bin);
    pythonProcess = spawn(bin, [], {
      cwd: path.dirname(bin),
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env }
    });

    pythonProcess.stdout?.on('data', (d) => console.log(`[Backend] ${d.toString().trim()}`));
    pythonProcess.stderr?.on('data', (d) => console.error(`[Backend ERR] ${d.toString().trim()}`));
    pythonProcess.on('error', (err) => console.error('[Main] Backend spawn failed:', err));
    pythonProcess.on('exit', (code, sig) => {
      console.log(`[Main] Backend exited (code=${code}, signal=${sig})`);
      // 不是我们主动 kill 的 → 重启
      if (sig !== 'SIGTERM' && sig !== 'SIGKILL' && code !== 0 && mainWindow) {
        console.log('[Main] Backend crashed unexpectedly, restarting in 2s...');
        setTimeout(spawnPythonBackend, 2000);
      }
    });

    // 等待后端就绪
    return waitForBackend();
  } else {
    // ── 开发模式: 不启动子进程, 用户手动运行 ──
    console.log('[Main] Dev mode — expecting backend on :9099');
    return waitForBackend();
  }
}

function waitForBackend(timeout = 15000) {
  const start = Date.now();
  return new Promise((resolve) => {
    const check = () => {
      const http = require('http');
      const req = http.get('http://127.0.0.1:9099/health', (res) => {
        if (res.statusCode === 200) {
          console.log('[Main] Backend ready');
          resolve(true);
        } else {
          retry();
        }
      });
      req.on('error', retry);
      req.setTimeout(2000, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (Date.now() - start > timeout) {
        console.warn('[Main] Backend health check timeout — proceeding anyway');
        resolve(false);
      } else {
        setTimeout(check, 1000);
      }
    };
    check();
  });
}

function killPythonBackend() {
  if (!pythonProcess || pythonProcess.killed) return;
  console.log('[Main] Killing backend process...');

  if (process.platform === 'win32') {
    // Windows: 需要杀掉整个进程树
    try {
      const { execSync } = require('child_process');
      execSync(`taskkill /PID ${pythonProcess.pid} /T /F`, { stdio: 'ignore' });
    } catch { /* 可能已被杀掉 */ }
  } else {
    pythonProcess.kill('SIGTERM');
    setTimeout(() => {
      if (pythonProcess && !pythonProcess.killed) {
        pythonProcess.kill('SIGKILL');
      }
    }, 3000);
  }
  pythonProcess = null;
}

// ══════════════ 自动更新 ══════════════

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
      type: 'error', data: { message: err.message, stack: err.stack },
    });
  });
  autoUpdater.on('download-progress', (progress) => {
    mainWindow?.webContents.send('updater:status', {
      type: 'download-progress',
      data: { percent: progress.percent, speed: progress.bytesPerSecond,
              transferred: progress.transferred, total: progress.total },
    });
  });
  autoUpdater.on('update-downloaded', (info) => {
    mainWindow?.webContents.send('updater:status', { type: 'update-downloaded', data: info });
  });
}

// ══════════════ IPC 注册 ══════════════

function registerIPC() {
  ipcMain.handle('conv:list', () => convStore.list());
  ipcMain.handle('conv:create', (e, title) => convStore.create(title));
  ipcMain.handle('conv:get', (e, id) => convStore.get(id));
  ipcMain.handle('conv:delete', (e, id) => convStore.delete(id));
  ipcMain.handle('conv:rename', (e, id, title) => convStore.rename(id, title));
  ipcMain.handle('conv:setActive', (e, id) => convStore.setActive(id));
  ipcMain.handle('conv:appendMessage', (e, id, msg) => convStore.appendMessage(id, msg));
  ipcMain.handle('conv:clearMessages', (e, id) => convStore.clearMessages(id));
  ipcMain.handle('db:truncateMessages', (e, convId, msgId) => convStore.truncateMessagesFrom(convId, msgId));

  let serverURL = 'http://127.0.0.1:9099';
  ipcMain.handle('config:getServerURL', () => serverURL);
  ipcMain.handle('config:setServerURL', (e, url) => { serverURL = url; return true; });

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

  ipcMain.handle('updater:check', () => autoUpdater.checkForUpdates());
  ipcMain.handle('updater:download', () => autoUpdater.downloadUpdate());
  ipcMain.handle('updater:install', () => autoUpdater.quitAndInstall());

  // ── Settings 子窗口 (Electron IPC 桥接) ──
  ipcMain.on('open-settings', () => {
    if (settingsWindow && !settingsWindow.isDestroyed()) {
      settingsWindow.focus();
      return;
    }
    settingsWindow = new BrowserWindow({
      width: 1000, height: 700,
      title: '爱丽丝控制中心 — 系统配置',
      backgroundColor: '#f4f5f7',
      parent: mainWindow,
      modal: false,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
      }
    });
    settingsWindow.loadURL('http://127.0.0.1:9099/admin.html');
    settingsWindow.on('closed', () => { settingsWindow = null; });
  });
}

// ══════════════ 窗口创建 ══════════════

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

  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://127.0.0.1:5174');
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'));
  }
}

// ══════════════ 生命周期 ══════════════

app.whenReady().then(async () => {
  convStore = new ConversationStore(app.getPath('userData'));
  registerIPC();
  setupUpdaterEvents();

  // ── 启动 Python 后端 (打包模式自动spawn, 开发模式等待) ──
  await spawnPythonBackend();

  createWindow();

  // ── OTA 静默更新: 检查 + 后台下载, 下次重启生效 ──
  if (!isDev) {
    autoUpdater.checkForUpdatesAndNotify();
  }

  globalShortcut.register('Alt+Space', () => {
    if (!mainWindow) return;
    if (mainWindow.isVisible()) {
      if (mainWindow.isFocused()) { mainWindow.hide(); } else { mainWindow.focus(); }
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// ══════════════ 退出 — 强制杀子进程 (防僵尸!) ══════════════

app.on('before-quit', () => {
  killPythonBackend();
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  killPythonBackend(); // 双重保险: will-quit 再次确保杀掉
});
