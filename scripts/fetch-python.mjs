// scripts/fetch-python.mjs
// 下载 python-build-standalone 嵌入式 Python runtime,解压到 resources/python/。
// 用法:`node scripts/fetch-python.mjs` 或 `npm run fetch:python`。
// 平台自动检测:当前 OS+arch,允许 --platform 覆盖(CI 用)。

import { createHash } from 'crypto';
import { createWriteStream, createReadStream } from 'fs';
import { readFileSync, writeFileSync, mkdirSync, rmSync, existsSync } from 'fs';
import { pipeline } from 'stream/promises';
import { spawnSync } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const CACHE_DIR = join(ROOT, '.cache', 'pbs');
const RUNTIME_DIR = join(ROOT, 'resources', 'python');
const CONFIG_PATH = join(__dirname, 'python-runtime.json');

const RELEASES_BASE = 'https://github.com/indygreg/python-build-standalone/releases/download';

function detectPlatform() {
  const map = {
    'darwin-arm64': 'darwin-arm64',
    'darwin-x64':   'darwin-x64',
    'win32-x64':    'win32-x64',
    'linux-x64':    'linux-x64',
  };
  const key = `${process.platform}-${process.arch}`;
  return map[key] || null;
}

function parseArgs() {
  const args = process.argv.slice(2);
  const out = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i].startsWith('--')) {
      const k = args[i].slice(2);
      const v = args[i + 1] && !args[i + 1].startsWith('--') ? args[++i] : true;
      out[k] = v;
    }
  }
  return out;
}

async function fetchToFile(url, destPath) {
  console.log(`  ⬇  ${url}`);
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  await pipeline(res.body, createWriteStream(destPath));
}

async function fetchText(url) {
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return await res.text();
}

function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const h = createHash('sha256');
    const s = createReadStream(filePath);
    s.on('data', d => h.update(d));
    s.on('end', () => resolve(h.digest('hex')));
    s.on('error', reject);
  });
}

function extractTarGz(archivePath, destDir) {
  // 通用方案:用 system tar(macOS / Linux / Windows 10+ 都自带)
  rmSync(destDir, { recursive: true, force: true });
  mkdirSync(destDir, { recursive: true });
  const r = spawnSync('tar', ['-xzf', archivePath, '-C', destDir, '--strip-components=1'], {
    stdio: 'inherit',
  });
  if (r.status !== 0) {
    throw new Error(`tar 解压失败 (exit ${r.status})。请确认系统 tar 可用。`);
  }
}

async function main() {
  const args = parseArgs();
  const cfg = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
  const platform = args.platform || detectPlatform();
  if (!platform || !cfg.platforms[platform]) {
    throw new Error(`不支持的平台:${platform}。可选:${Object.keys(cfg.platforms).join(', ')}`);
  }

  const { archive } = cfg.platforms[platform];
  const expectedSha = cfg.platforms[platform].sha256 || '';
  const release = cfg.release;
  const url = `${RELEASES_BASE}/${release}/${archive}`;
  const shaUrl = `${url}.sha256`;

  mkdirSync(CACHE_DIR, { recursive: true });
  const localArchive = join(CACHE_DIR, archive);

  console.log(`[fetch-python] 平台 ${platform}, release ${release}, Python ${cfg.pythonVersion}`);

  // 1. 下载主包(已存在且 sha 对得上就跳过)
  let needDownload = true;
  if (existsSync(localArchive) && expectedSha) {
    const actualSha = await sha256File(localArchive);
    if (actualSha === expectedSha) {
      console.log(`  ✓ 缓存命中(SHA256 匹配)`);
      needDownload = false;
    } else {
      console.log(`  ✗ 缓存 SHA256 不一致,重新下载`);
    }
  }
  if (needDownload) {
    await fetchToFile(url, localArchive);
  }

  // 2. 校验 SHA256
  const actualSha = await sha256File(localArchive);
  if (expectedSha && expectedSha !== actualSha) {
    throw new Error(`SHA256 校验失败:期望 ${expectedSha},实际 ${actualSha}`);
  }
  if (!expectedSha) {
    // 首次下载:用 PBS 提供的 sidecar 校验,然后回写到 config
    console.log(`  正在用 PBS 官方 .sha256 sidecar 二次校验...`);
    const sidecar = (await fetchText(shaUrl)).trim().split(/\s+/)[0];
    if (sidecar !== actualSha) {
      throw new Error(`官方 sidecar 校验失败:期望 ${sidecar},实际 ${actualSha}`);
    }
    cfg.platforms[platform].sha256 = actualSha;
    writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2) + '\n', 'utf8');
    console.log(`  ✓ 校验通过,SHA256 已写回 python-runtime.json`);
  } else {
    console.log(`  ✓ SHA256 校验通过`);
  }

  // 3. 解压到 resources/python/
  console.log(`[fetch-python] 解压到 ${RUNTIME_DIR}`);
  extractTarGz(localArchive, RUNTIME_DIR);

  // 4. 确认入口可执行
  const exe = process.platform === 'win32'
    ? join(RUNTIME_DIR, 'python.exe')
    : join(RUNTIME_DIR, 'bin', 'python3');
  if (!existsSync(exe)) {
    throw new Error(`解压后未找到 Python 解释器:${exe}`);
  }
  console.log(`[fetch-python] ✅ 完成,Python 解释器位于 ${exe}`);
}

main().catch(err => {
  console.error(`[fetch-python] ❌ ${err.message}`);
  process.exit(1);
});
