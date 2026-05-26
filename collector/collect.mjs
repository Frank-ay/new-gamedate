/**
 * collect.mjs — 每日采集主入口
 *
 * 流程：
 *   1. 抓取榜单   → 获取 uniqueAppIds
 *   2. 抓取详情   → 写入 games / daily_snapshots / screenshots
 *   3. 下载 Icon  → 写入 data/assets/icons/
 *   4. 触发增长分析（调用 Python analysis/growth_scorer.py）
 */
import { execSync } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { fetchAllCharts } from './charts.mjs';
import { fetchDetails }   from './details.mjs';
import { downloadMissingIcons } from './assets.mjs';
import { logger } from './utils/logger.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));

async function main() {
  const startTime = Date.now();
  logger.info('========== 开始每日采集任务 ==========');

  // Step 1: 榜单
  logger.info('--- Step 1: 抓取榜单 ---');
  const { uniqueAppIds } = await fetchAllCharts();

  // Step 2: 详情
  logger.info('--- Step 2: 抓取详情 ---');
  await fetchDetails(uniqueAppIds);

  // Step 3: Icon 下载
  logger.info('--- Step 3: 下载 Icon ---');
  await downloadMissingIcons(300);

  // Step 4: 增长信号计算
  logger.info('--- Step 4: 计算增长信号 ---');
  try {
    const appRoot    = process.env.APP_ROOT || join(__dirname, '..');
    const scorerPath = join(appRoot, 'analysis', 'growth_scorer.py');
    const pythonCmd  = process.env.APP_PYTHON
      || (process.platform === 'win32' ? 'python' : 'python3');
    execSync(`"${pythonCmd}" "${scorerPath}"`, { stdio: 'inherit', timeout: 120_000 });
    logger.info('增长信号计算完成');
  } catch (err) {
    logger.warn(`增长信号计算失败（非致命）: ${err.message}`);
  }

  const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
  logger.info(`========== 采集任务完成，耗时 ${elapsed} 分钟 ==========`);
}

main().catch(err => {
  logger.error(`致命错误: ${err.message}\n${err.stack}`);
  process.exit(1);
});
