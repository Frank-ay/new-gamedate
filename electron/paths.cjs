// electron/paths.cjs
// 统一管理 dev / prod 路径,并生成给子进程的环境变量。
// 这是全栈最核心的约定层 — 所有 Node/Python 模块都通过 APP_* 环境变量读路径。

const path = require('path');
const fs = require('fs');
const { app } = require('electron');

const isDev = !app.isPackaged;

// ─── 资源根 ────────────────────────────────────────
// dev:仓库根目录;prod:Contents/Resources(mac) / resources/(win)
const RESOURCES = isDev
  ? path.join(__dirname, '..')
  : process.resourcesPath;

// ─── Python 解释器 ────────────────────────────────
// dev 走仓库的 .venv;prod 走 extraResources 解压出的 python-build-standalone
function pythonBin() {
  if (isDev) {
    return path.join(__dirname, '..', '.venv', 'bin', 'python3');
  }
  if (process.platform === 'win32') {
    return path.join(RESOURCES, 'python', 'python.exe');
  }
  return path.join(RESOURCES, 'python', 'bin', 'python3');
}

// ─── Node 业务源码根 ───────────────────────────────
// dev:仓库根;prod:app.asar.unpacked 下的同样布局
// asar 内的文件 Python 子进程读不了,所以业务三层都要 unpack
function appRoot() {
  if (isDev) return path.join(__dirname, '..');
  return path.join(process.resourcesPath, 'app.asar.unpacked');
}

// ─── 用户数据(可写)────────────────────────────────
// 所有可变数据(db / logs / icons / 用户改过的 config.yaml)都放 userData
function userData() {
  return app.getPath('userData');
}

const DATA_DIR_NAME = 'data';
const LOG_DIR_NAME = 'logs';
const ASSETS_SUBDIR = path.join('assets', 'icons');

function dataDir()    { return path.join(userData(), DATA_DIR_NAME); }
function logDir()     { return path.join(userData(), LOG_DIR_NAME); }
function assetsDir()  { return path.join(dataDir(), ASSETS_SUBDIR); }
function dbPath()     { return path.join(dataDir(), 'games.db'); }
function configPath() { return path.join(userData(), 'config.yaml'); }

// ─── 首次启动:确保目录存在 + 复制默认配置 ─────────
function ensureUserDirs() {
  for (const d of [dataDir(), logDir(), assetsDir()]) {
    fs.mkdirSync(d, { recursive: true });
  }
  const userConfig = configPath();
  if (!fs.existsSync(userConfig)) {
    const defaultConfig = path.join(RESOURCES, 'config.yaml');
    if (fs.existsSync(defaultConfig)) {
      fs.copyFileSync(defaultConfig, userConfig);
    }
  }
}

// ─── 注入给子进程(streamlit / collector)的环境变量 ─
function childEnv(extra = {}) {
  return {
    ...process.env,
    // 路径
    APP_PYTHON: pythonBin(),
    APP_NODE_BIN: process.execPath,        // Electron exe + ELECTRON_RUN_AS_NODE
    APP_ROOT: appRoot(),
    APP_DATA_DIR: dataDir(),
    APP_LOG_DIR: logDir(),
    APP_DB_PATH: dbPath(),
    APP_ASSETS_DIR: assetsDir(),
    APP_CONFIG_PATH: configPath(),
    APP_RESOURCES: RESOURCES,
    // 让 Streamlit 不弹浏览器、不上传遥测
    STREAMLIT_SERVER_HEADLESS: 'true',
    STREAMLIT_BROWSER_GATHER_USAGE_STATS: 'false',
    ...extra,
  };
}

module.exports = {
  isDev,
  RESOURCES,
  pythonBin,
  appRoot,
  userData,
  dataDir,
  logDir,
  assetsDir,
  dbPath,
  configPath,
  ensureUserDirs,
  childEnv,
};
