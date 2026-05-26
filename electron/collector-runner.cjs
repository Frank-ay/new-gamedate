// electron/collector-runner.cjs
// IPC 触发 collector(预留模块)。当前 dashboard/app.py 已经能直接 spawn Node,
// 此模块留作"主进程菜单触发采集"这类未来需求的入口。

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { appRoot, logDir, childEnv } = require('./paths.cjs');

let running = null;

function isCollecting() {
  return !!running;
}

function startCollect(onEvent) {
  if (running) {
    throw new Error('已有采集任务在跑');
  }

  const entry = path.join(appRoot(), 'collector', 'collect.mjs');
  if (!fs.existsSync(entry)) {
    throw new Error(`找不到 collector 入口:${entry}`);
  }

  fs.mkdirSync(logDir(), { recursive: true });
  const today = new Date().toISOString().slice(0, 10);
  const logPath = path.join(logDir(), `collect-${today}.log`);

  const proc = spawn(process.execPath, [entry], {
    env: childEnv({ ELECTRON_RUN_AS_NODE: '1' }),
    stdio: ['ignore', 'pipe', 'pipe'],
    cwd: appRoot(),
  });

  const out = fs.openSync(logPath, 'a');
  proc.stdout.on('data', d => {
    fs.writeSync(out, d);
    if (onEvent) onEvent('stdout', d.toString());
  });
  proc.stderr.on('data', d => {
    fs.writeSync(out, d);
    if (onEvent) onEvent('stderr', d.toString());
  });
  proc.on('exit', code => {
    running = null;
    if (onEvent) onEvent('exit', String(code));
  });

  running = { proc, startedAt: Date.now() };
  return { pid: proc.pid };
}

function stopCollect() {
  if (!running) return;
  const { proc } = running;
  running = null;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(proc.pid), '/f', '/t']);
    } else {
      proc.kill('SIGTERM');
    }
  } catch (_) {
    // ignore
  }
}

module.exports = { startCollect, isCollecting, stopCollect };
