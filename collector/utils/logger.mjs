import { appendFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOG_DIR = process.env.APP_LOG_DIR
  || join(__dirname, '../../logs');

let logFile = null;

function getLogFile() {
  if (!logFile) {
    mkdirSync(LOG_DIR, { recursive: true });
    const date = new Date().toISOString().slice(0, 10);
    logFile = join(LOG_DIR, `collect-${date}.log`);
  }
  return logFile;
}

function format(level, msg) {
  const ts = new Date().toISOString();
  return `[${ts}] [${level.toUpperCase()}] ${msg}`;
}

export const logger = {
  info(msg) {
    const line = format('info', msg);
    console.log(line);
    appendFileSync(getLogFile(), line + '\n');
  },
  warn(msg) {
    const line = format('warn', msg);
    console.warn(line);
    appendFileSync(getLogFile(), line + '\n');
  },
  error(msg) {
    const line = format('error', msg);
    console.error(line);
    appendFileSync(getLogFile(), line + '\n');
  },
  summary(stats) {
    const lines = ['=== 采集汇总 ===', ...Object.entries(stats).map(([k, v]) => `  ${k}: ${v}`), '================'];
    lines.forEach(l => this.info(l));
  }
};
