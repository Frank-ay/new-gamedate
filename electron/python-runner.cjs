// electron/python-runner.cjs
// 拉起 Streamlit 子进程,在 127.0.0.1 找一个空闲端口,然后等到它真正监听后再返回 URL。

const { spawn } = require('child_process');
const net = require('net');
const path = require('path');
const fs = require('fs');
const { pythonBin, appRoot, logDir, childEnv } = require('./paths.cjs');

let streamlitProc = null;
let currentPort = null;

function isPortFree(port) {
  return new Promise(resolve => {
    const s = net.createServer();
    s.once('error', () => resolve(false));
    s.once('listening', () => s.close(() => resolve(true)));
    s.listen(port, '127.0.0.1');
  });
}

async function pickFreePort(start = 8501, end = 8550) {
  for (let p = start; p <= end; p++) {
    if (await isPortFree(p)) return p;
  }
  throw new Error(`端口 ${start}-${end} 都被占用,请关闭占用的程序后重试。`);
}

function tcpProbe(port) {
  return new Promise(resolve => {
    const s = net.connect(port, '127.0.0.1');
    s.once('connect', () => { s.end(); resolve(true); });
    s.once('error', () => resolve(false));
  });
}

async function waitForPort(port, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await tcpProbe(port)) return;
    await new Promise(r => setTimeout(r, 200));
  }
  throw new Error(`Streamlit 在 ${timeoutMs}ms 内未能监听 ${port} 端口`);
}

async function startStreamlit() {
  if (streamlitProc) return `http://127.0.0.1:${currentPort}`;

  const port = await pickFreePort();
  const dashboardEntry = path.join(appRoot(), 'dashboard', 'app.py');
  const logPath = path.join(logDir(), 'streamlit.log');
  fs.mkdirSync(logDir(), { recursive: true });
  const out = fs.openSync(logPath, 'a');

  const py = pythonBin();
  if (!fs.existsSync(py)) {
    throw new Error(`找不到 Python 解释器:${py}`);
  }
  if (!fs.existsSync(dashboardEntry)) {
    throw new Error(`找不到 Dashboard 入口:${dashboardEntry}`);
  }

  const args = [
    '-m', 'streamlit', 'run', dashboardEntry,
    '--server.port', String(port),
    '--server.address', '127.0.0.1',
    '--server.headless', 'true',
    '--browser.gatherUsageStats', 'false',
    // 关 file-watch,prod 包是只读的;dev 也无所谓
    '--server.fileWatcherType', 'none',
  ];

  streamlitProc = spawn(py, args, {
    env: childEnv(),
    stdio: ['ignore', out, out],
    detached: false,
  });

  currentPort = port;

  streamlitProc.on('exit', (code, signal) => {
    fs.appendFileSync(logPath, `\n[streamlit] exited code=${code} signal=${signal}\n`);
    streamlitProc = null;
    currentPort = null;
  });

  await waitForPort(port);
  return `http://127.0.0.1:${port}`;
}

function stopStreamlit() {
  if (!streamlitProc) return;
  const proc = streamlitProc;
  streamlitProc = null;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(proc.pid), '/f', '/t']);
    } else {
      proc.kill('SIGTERM');
      setTimeout(() => {
        try { proc.kill('SIGKILL'); } catch (_) {}
      }, 3000);
    }
  } catch (_) {
    // ignore
  }
}

module.exports = { startStreamlit, stopStreamlit };
