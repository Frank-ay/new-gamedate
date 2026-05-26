/**
 * details.mjs — 增量抓取游戏详情页
 *
 * 策略：
 *   - 新游戏（games 中 updated_at IS NULL）全部抓
 *   - 旧游戏超过 refresh_after_days 天的也重新抓
 *   - 失败的 appId 写入 failed_ids.json，下次优先处理
 */
import gplay from 'google-play-scraper';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { load as yamlLoad } from 'js-yaml';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  getDb, upsertGame, insertSnapshot, insertScreenshots, getRecentlyUpdatedAppIds
} from './utils/db.mjs';
import { throttledCall, withRetry } from './utils/rate-limiter.mjs';
import { logger } from './utils/logger.mjs';

/**
 * 将 Google Play 返回的日期字符串统一转为 ISO 格式 YYYY-MM-DD。
 * 支持 "Apr 1, 2014" → "2014-04-01"，已是 ISO 格式的原样返回。
 */
function toISODate(raw) {
  if (!raw) return null;
  // 已是 ISO 格式（YYYY-MM-DD）
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw.trim())) return raw.trim();
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return raw;
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${mm}-${dd}`;
  } catch {
    return raw;
  }
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const CONFIG_PATH = process.env.APP_CONFIG_PATH
  || join(__dirname, '../config.yaml');
const cfg = yamlLoad(readFileSync(CONFIG_PATH, 'utf8'));
const DATA_DIR = process.env.APP_DATA_DIR
  || join(__dirname, '../data');
const FAILED_IDS_PATH = join(DATA_DIR, 'failed_ids.json');
const TODAY = new Date().toISOString().slice(0, 10);

function loadFailedIds() {
  if (!existsSync(FAILED_IDS_PATH)) return [];
  try {
    return JSON.parse(readFileSync(FAILED_IDS_PATH, 'utf8'));
  } catch {
    return [];
  }
}

function saveFailedIds(ids) {
  writeFileSync(FAILED_IDS_PATH, JSON.stringify([...new Set(ids)], null, 2));
}

/** 抓取单个 app 详情 */
async function fetchDetail(appId) {
  return withRetry(
    () => throttledCall(
      () => gplay.app({ appId, country: cfg.scraper.country, lang: cfg.scraper.lang }),
      cfg.scraper.request_delay * 1000
    ),
    cfg.scraper.max_retries,
    appId
  );
}

/**
 * 主函数：增量抓取详情
 * @param {string[]} appIds 要处理的 appId 列表（来自 charts.mjs 的 uniqueAppIds）
 */
export async function fetchDetails(appIds) {
  const db = getDb();
  const previouslyFailed = loadFailedIds();
  const recentlyUpdated  = getRecentlyUpdatedAppIds(db, cfg.details.refresh_after_days);

  // 优先处理上次失败的，其次处理新增的
  const priorityIds = previouslyFailed.filter(id => appIds.includes(id));
  const newIds      = appIds.filter(id => !recentlyUpdated.has(id) && !priorityIds.includes(id));
  const toProcess   = [...new Set([...priorityIds, ...newIds])];

  logger.info(`详情抓取: 共 ${appIds.length} 个，需抓 ${toProcess.length} 个（跳过近期更新 ${recentlyUpdated.size} 个，优先失败重试 ${priorityIds.length} 个）`);

  let success = 0;
  let failed  = 0;
  const failedIds = [];

  for (const appId of toProcess) {
    try {
      const a = await fetchDetail(appId);

      upsertGame(db, {
        appId:        a.appId,
        title:        a.title,
        developer:    a.developer ?? null,
        developerId:  a.developerId ?? null,
        genre:        a.genre ?? null,
        contentRating: a.contentRating ?? null,
        released:     toISODate(a.released),
        firstSeenAt:  TODAY,
        iconUrl:      a.icon ?? null,
        videoUrl:     a.video?.thumbnailImage ?? null,
        updatedAt:    TODAY,
      });

      insertSnapshot(db, {
        appId,
        snapshotDate:    TODAY,
        score:           a.score ?? null,
        ratings:         a.ratings ?? null,
        reviews:         a.reviews ?? null,
        installs:        a.installs ?? null,
        price:           a.price ?? 0,
        free:            a.free ? 1 : 0,
        containsAds:     a.containsAds ? 1 : 0,
        inAppPurchases:  a.inAppPurchases ? 1 : 0,
      });

      if (a.screenshots?.length) {
        insertScreenshots(db, appId, a.screenshots);
      }

      success++;
      if (success % 50 === 0) {
        logger.info(`  进度: ${success}/${toProcess.length} 成功，${failed} 失败`);
      }
    } catch (err) {
      failed++;
      failedIds.push(appId);
      logger.warn(`  ✗ ${appId}: ${err.message}`);
    }
  }

  saveFailedIds(failedIds);

  logger.summary({
    '需抓取': toProcess.length,
    '成功':   success,
    '失败':   failed,
    '失败率': `${((failed / toProcess.length) * 100).toFixed(1)}%`,
  });

  return { success, failed, failedIds };
}

// 支持直接运行（需传入 appId 列表文件）
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const db = getDb();
  const allAppIds = db.prepare('SELECT app_id FROM games').all().map(r => r.app_id);
  fetchDetails(allAppIds)
    .then(r => logger.info(`完成: 成功 ${r.success}, 失败 ${r.failed}`))
    .catch(err => { logger.error(err.message); process.exit(1); });
}
