// electron/main.cjs
// Electron 主进程:启动 Streamlit 子进程,等端口可用后在主窗口加载 dashboard。

const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path');
const fs = require('fs');

const { ensureUserDirs, logDir, appRoot } = require('./paths.cjs');
const { startStreamlit, stopStreamlit } = require('./python-runner.cjs');
const { startCollect, isCollecting, stopCollect } = require('./collector-runner.cjs');

// 启动前预热数据库:让 Node 端 better-sqlite3 跑一次 initSchema,
// 确保 Python 端读 games / daily_snapshots 等表时不会因表不存在报错。
async function warmupDatabase() {
  process.env.APP_DB_PATH = require('./paths.cjs').dbPath();
  process.env.APP_DATA_DIR = require('./paths.cjs').dataDir();
  const dbModulePath = path.join(appRoot(), 'collector', 'utils', 'db.mjs');
  const fileUrl = require('url').pathToFileURL(dbModulePath).href;
  const mod = await import(fileUrl);
  const db = mod.getDb();
  // 立刻关掉,避免被 Streamlit / collector 子进程的 sqlite 文件锁冲突
  db.close();
}

let mainWindow = null;
let splashWindow = null;

function createSplash() {
  splashWindow = new BrowserWindow({
    width: 420,
    height: 280,
    frame: false,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    transparent: true,
    backgroundColor: '#00000000',
    show: false,
    skipTaskbar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
  splashWindow.once('ready-to-show', () => splashWindow.show());
}

function createMain(url) {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    backgroundColor: '#0f172a',
    title: 'GameDataMonitor',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(url);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (splashWindow) {
      splashWindow.destroy();
      splashWindow = null;
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function showFatalError(message) {
  if (splashWindow) {
    splashWindow.destroy();
    splashWindow = null;
  }
  const logPath = path.join(logDir(), 'streamlit.log');
  const detail = `日志文件:${logPath}\n\n${message}`;
  const r = dialog.showMessageBoxSync({
    type: 'error',
    title: '启动失败',
    message: 'GameDataMonitor 无法启动',
    detail,
    buttons: ['打开日志目录', '退出'],
    defaultId: 1,
    cancelId: 1,
  });
  if (r === 0) shell.openPath(logDir());
  app.exit(1);
}

async function bootstrap() {
  ensureUserDirs();
  createSplash();
  try {
    await warmupDatabase();
    const url = await startStreamlit();
    createMain(url);
  } catch (err) {
    showFatalError(err && err.stack ? err.stack : String(err));
  }
}

// ─── 单实例锁:重复双击图标时聚焦已有窗口 ──────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(bootstrap);
}

// ─── IPC 通道(预留)─────────────────────────────────
ipcMain.handle('collect:start', () => {
  try {
    return { ok: true, ...startCollect() };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});
ipcMain.handle('collect:status', () => ({ running: isCollecting() }));
ipcMain.handle('collect:stop', () => {
  stopCollect();
  return { ok: true };
});

// ─── 退出清理 ──────────────────────────────────────
function cleanup() {
  try { stopStreamlit(); } catch (_) {}
  try { stopCollect(); } catch (_) {}
}

app.on('window-all-closed', () => {
  cleanup();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', cleanup);
app.on('will-quit', cleanup);

// macOS:Dock 点图标时如果没有窗口就重建
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    bootstrap();
  }
});
