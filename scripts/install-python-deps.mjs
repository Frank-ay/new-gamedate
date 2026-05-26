// scripts/install-python-deps.mjs
// 用 resources/python/ 下嵌入的 Python 解释器,把 requirements.txt 中的依赖
// 直接装到该 Python 自带的 site-packages,这样打包时整个 resources/python/ 目录就是
// 自包含的运行时。

import { spawnSync } from 'child_process';
import { existsSync, readdirSync, statSync, rmSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const RUNTIME_DIR = join(ROOT, 'resources', 'python');
const REQUIREMENTS = join(ROOT, 'requirements.txt');

const STRIP = process.argv.includes('--strip');

// 在嵌入式 Python 安装完依赖后裁剪掉对 prod 无用的内容,
// 在 dev 验证时(不加 --strip)保留全量以便调试。
const STRIP_DIRS = [
  'tests', 'test', '__pycache__',
];
const STRIP_FILES = [
  '.pyc', '.pyo',
];

function rmrf(p) {
  try { rmSync(p, { recursive: true, force: true }); } catch (_) {}
}

function walkAndStrip(dir) {
  let removed = 0;
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    let st;
    try { st = statSync(full); } catch { continue; }
    if (st.isDirectory()) {
      if (STRIP_DIRS.includes(entry)) {
        rmrf(full);
        removed++;
      } else {
        removed += walkAndStrip(full);
      }
    } else if (st.isFile()) {
      if (STRIP_FILES.some(suf => entry.endsWith(suf))) {
        rmrf(full);
        removed++;
      }
    }
  }
  return removed;
}

function stripSitePackages() {
  const sp = process.platform === 'win32'
    ? join(RUNTIME_DIR, 'Lib', 'site-packages')
    : join(RUNTIME_DIR, 'lib', 'python3.11', 'site-packages');
  if (!existsSync(sp)) {
    console.log(`[strip] 跳过:site-packages 不存在 (${sp})`);
    return;
  }
  console.log(`[strip] 裁剪 ${sp}...`);
  const n = walkAndStrip(sp);
  console.log(`[strip] 删除 ${n} 个 tests/__pycache__/.pyc 条目`);
}

function pythonBin() {
  if (process.platform === 'win32') {
    return join(RUNTIME_DIR, 'python.exe');
  }
  return join(RUNTIME_DIR, 'bin', 'python3');
}

function run(cmd, args) {
  console.log(`  $ ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, { stdio: 'inherit' });
  if (r.status !== 0) {
    throw new Error(`命令失败 (exit ${r.status}): ${cmd} ${args.join(' ')}`);
  }
}

async function main() {
  const py = pythonBin();
  if (!existsSync(py)) {
    throw new Error(`嵌入式 Python 不存在:${py}\n请先运行 npm run fetch:python`);
  }
  if (!existsSync(REQUIREMENTS)) {
    throw new Error(`找不到 ${REQUIREMENTS}`);
  }

  console.log(`[install-py-deps] 使用 Python: ${py}`);
  // 升级 pip(可选)
  run(py, ['-m', 'pip', 'install', '--upgrade', 'pip', '--no-warn-script-location']);
  // 安装依赖
  run(py, [
    '-m', 'pip', 'install',
    '-r', REQUIREMENTS,
    '--no-warn-script-location',
    '--no-cache-dir',
  ]);

  // 简单验证 streamlit 能 import
  run(py, ['-c', 'import streamlit, pandas, plotly, requests; print("OK:", streamlit.__version__)']);

  // 可选裁剪(--strip):删除 tests/、__pycache__、.pyc 等
  if (STRIP) {
    stripSitePackages();
  } else {
    console.log('[install-py-deps] 提示:加 --strip 参数可裁剪 site-packages 减小包体');
  }

  console.log('[install-py-deps] ✅ 完成');
}

main().catch(err => {
  console.error(`[install-py-deps] ❌ ${err.message}`);
  process.exit(1);
});
