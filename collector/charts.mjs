/**
 * charts.mjs — 抓取 Google Play 美国市场游戏榜单
 *
 * 每次运行拉取：
 *   collections × categories 的所有榜单组合
 *   返回 {rankings: [...], uniqueAppIds: Set}
 */
import gplay from 'google-play-scraper';
import { readFileSync } from 'fs';
import { load as yamlLoad } from 'js-yaml';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { getDb, insertChartRankings, upsertGame } from './utils/db.mjs';
import { throttledCall, withRetry } from './utils/rate-limiter.mjs';
import { logger } from './utils/logger.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const CONFIG_PATH = process.env.APP_CONFIG_PATH
  || join(__dirname, '../config.yaml');
const cfg = yamlLoad(readFileSync(CONFIG_PATH, 'utf8'));

const TODAY = new Date().toISOString().slice(0, 10);

/** 获取单个榜单，带限速和重试 */
async function fetchChartPage(collection, category, num) {
  return withRetry(
    () => throttledCall(
      () => gplay.list({
        collection: gplay.collection[collection],
        category:   gplay.category[category],
        country:    cfg.scraper.country,
        lang:       cfg.scraper.lang,
        num,
        fullDetail: false,
      }),
      cfg.scraper.request_delay * 1000
    ),
    cfg.scraper.max_retries,
    `${collection}/${category}`
  );
}

/**
 * 主函数：抓取全部榜单组合，写入 DB
 * @returns {{ uniqueAppIds: string[], totalRankings: number }}
 */
export async function fetchAllCharts() {
  const db = getDb();
  const uniqueAppIds = new Set();
  let totalRankings = 0;
  let failedCombos = 0;

  const collections = cfg.charts.collections;
  const categories  = cfg.charts.categories;

  for (const collection of collections) {
    for (const category of categories) {
      // GAME 总榜用更大的 num，子品类用较小的
      const num = category === 'GAME' ? cfg.charts.top_n : cfg.charts.category_n;
      logger.info(`正在抓取 ${collection}/${category} Top ${num}...`);

      try {
        const apps = await fetchChartPage(collection, category, num);

        // 写入 games 主档（minimal 信息，详情后续补全）
        for (const a of apps) {
          if (!db.prepare('SELECT 1 FROM games WHERE app_id=?').get(a.appId)) {
            upsertGame(db, {
              appId:        a.appId,
              title:        a.title,
              developer:    a.developer ?? null,
              developerId:  a.developerId ?? null,
              genre:        null,
              contentRating: null,
              released:     null,
              firstSeenAt:  TODAY,
              iconUrl:      a.icon ?? null,
              videoUrl:     null,
              updatedAt:    null,
            });
          }
          uniqueAppIds.add(a.appId);
        }

        // 写入榜单排名
        const rankings = apps.map((a, idx) => ({
          snapshotDate: TODAY,
          chartType:    collection,
          category,
          rank:         idx + 1,
          appId:        a.appId,
        }));
        insertChartRankings(db, rankings);
        totalRankings += rankings.length;
        logger.info(`  ✓ ${apps.length} 条，累计 unique appId: ${uniqueAppIds.size}`);
      } catch (err) {
        failedCombos++;
        logger.error(`  ✗ ${collection}/${category} 失败: ${err.message}`);
      }
    }
  }

  logger.summary({
    '榜单组合总数': collections.length * categories.length,
    '失败组合数':   failedCombos,
    'unique appId': uniqueAppIds.size,
    '写入排名记录': totalRankings,
  });

  return { uniqueAppIds: [...uniqueAppIds], totalRankings };
}

// 支持直接运行
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  fetchAllCharts()
    .then(r => logger.info(`完成，共 ${r.uniqueAppIds.length} 个 appId`))
    .catch(err => { logger.error(err.message); process.exit(1); });
}
