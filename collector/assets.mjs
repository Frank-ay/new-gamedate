/**
 * assets.mjs — 下载游戏资产（Icon）到本地
 *
 * 仅下载 icons 目录中尚不存在的 icon，避免重复下载。
 * 截图 URL 已记录在 screenshots 表，不批量下载（节省磁盘）。
 */
import { createWriteStream, existsSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { pipeline } from 'stream/promises';
import { getDb } from './utils/db.mjs';
import { sleep } from './utils/rate-limiter.mjs';
import { logger } from './utils/logger.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ICONS_DIR = process.env.APP_ASSETS_DIR
  || join(__dirname, '../data/assets/icons');

mkdirSync(ICONS_DIR, { recursive: true });

async function downloadFile(url, destPath) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  await pipeline(res.body, createWriteStream(destPath));
}

export async function downloadMissingIcons(limit = 200) {
  const db = getDb();
  const rows = db.prepare(`
    SELECT app_id, icon_url FROM games
    WHERE icon_url IS NOT NULL
    LIMIT ?
  `).all(limit * 5); // 多取一些，过滤掉已存在的

  const toDownload = rows.filter(r => {
    const dest = join(ICONS_DIR, `${r.app_id}.png`);
    return !existsSync(dest);
  }).slice(0, limit);

  logger.info(`Icon 下载: 共 ${toDownload.length} 个待下载`);
  let success = 0, failed = 0;

  for (const { app_id, icon_url } of toDownload) {
    const dest = join(ICONS_DIR, `${app_id}.png`);
    try {
      await downloadFile(icon_url, dest);
      success++;
      await sleep(300);
    } catch (err) {
      failed++;
      logger.warn(`Icon 下载失败 ${app_id}: ${err.message}`);
    }
  }

  logger.info(`Icon 下载完成: 成功 ${success}, 失败 ${failed}`);
  return { success, failed };
}

// 支持直接运行
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  downloadMissingIcons()
    .catch(err => { logger.error(err.message); process.exit(1); });
}
