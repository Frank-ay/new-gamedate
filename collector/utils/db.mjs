import Database from 'better-sqlite3';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { mkdirSync } from 'fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DB_PATH = process.env.APP_DB_PATH
  || join(__dirname, '../../data/games.db');
const DATA_DIR = process.env.APP_DATA_DIR
  || join(__dirname, '../../data');

let _db = null;

export function getDb() {
  if (_db) return _db;
  mkdirSync(DATA_DIR, { recursive: true });
  _db = new Database(DB_PATH);
  _db.pragma('journal_mode = WAL');
  _db.pragma('foreign_keys = ON');
  initSchema(_db);
  return _db;
}

function initSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS games (
      app_id        TEXT PRIMARY KEY,
      title         TEXT,
      developer     TEXT,
      developer_id  TEXT,
      genre         TEXT,
      content_rating TEXT,
      released      TEXT,
      first_seen_at TEXT NOT NULL,
      icon_url      TEXT,
      video_url     TEXT,
      updated_at    TEXT
    );

    CREATE TABLE IF NOT EXISTS daily_snapshots (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      app_id        TEXT NOT NULL REFERENCES games(app_id),
      snapshot_date TEXT NOT NULL,
      score         REAL,
      ratings       INTEGER,
      reviews       INTEGER,
      installs      TEXT,
      price         REAL,
      free          INTEGER,
      contains_ads  INTEGER,
      in_app_purchases INTEGER,
      UNIQUE(app_id, snapshot_date)
    );

    CREATE TABLE IF NOT EXISTS chart_rankings (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      snapshot_date TEXT NOT NULL,
      chart_type    TEXT NOT NULL,
      category      TEXT NOT NULL,
      rank          INTEGER NOT NULL,
      app_id        TEXT NOT NULL REFERENCES games(app_id)
    );
    CREATE INDEX IF NOT EXISTS idx_chart_date ON chart_rankings(snapshot_date);
    CREATE INDEX IF NOT EXISTS idx_chart_app  ON chart_rankings(app_id);

    CREATE TABLE IF NOT EXISTS screenshots (
      app_id  TEXT NOT NULL REFERENCES games(app_id),
      url     TEXT NOT NULL,
      PRIMARY KEY(app_id, url)
    );

    CREATE TABLE IF NOT EXISTS growth_signals (
      id                  INTEGER PRIMARY KEY AUTOINCREMENT,
      app_id              TEXT NOT NULL REFERENCES games(app_id),
      signal_date         TEXT NOT NULL,
      rank_delta_7d       INTEGER,
      reviews_growth_7d   REAL,
      is_new_game         INTEGER DEFAULT 0,
      days_since_release  INTEGER,
      days_to_chart       INTEGER,
      new_game_burst_score REAL,
      growth_score        REAL,
      UNIQUE(app_id, signal_date)
    );
  `);

  // 向旧表补列（忽略"列已存在"错误）
  for (const col of [
    'days_since_release INTEGER',
    'days_to_chart INTEGER',
    'today_heat_score REAL',
  ]) {
    try { db.exec(`ALTER TABLE growth_signals ADD COLUMN ${col}`); } catch {}
  }
}

// 插入或更新 games 主档
export function upsertGame(db, game) {
  const stmt = db.prepare(`
    INSERT INTO games (app_id, title, developer, developer_id, genre, content_rating,
                       released, first_seen_at, icon_url, video_url, updated_at)
    VALUES (@appId, @title, @developer, @developerId, @genre, @contentRating,
            @released, @firstSeenAt, @iconUrl, @videoUrl, @updatedAt)
    ON CONFLICT(app_id) DO UPDATE SET
      title         = excluded.title,
      developer     = excluded.developer,
      developer_id  = excluded.developer_id,
      genre         = excluded.genre,
      content_rating = excluded.content_rating,
      released      = excluded.released,
      icon_url      = excluded.icon_url,
      video_url     = excluded.video_url,
      updated_at    = excluded.updated_at
  `);
  stmt.run(game);
}

// 插入每日快照（忽略重复）
export function insertSnapshot(db, snapshot) {
  const stmt = db.prepare(`
    INSERT OR IGNORE INTO daily_snapshots
      (app_id, snapshot_date, score, ratings, reviews, installs, price, free, contains_ads, in_app_purchases)
    VALUES (@appId, @snapshotDate, @score, @ratings, @reviews, @installs, @price, @free, @containsAds, @inAppPurchases)
  `);
  stmt.run(snapshot);
}

// 批量插入榜单记录
export function insertChartRankings(db, rankings) {
  const stmt = db.prepare(`
    INSERT INTO chart_rankings (snapshot_date, chart_type, category, rank, app_id)
    VALUES (@snapshotDate, @chartType, @category, @rank, @appId)
  `);
  const insertMany = db.transaction((rows) => {
    for (const row of rows) stmt.run(row);
  });
  insertMany(rankings);
}

// 批量插入截图 URL（忽略重复）
export function insertScreenshots(db, appId, urls) {
  const stmt = db.prepare(`
    INSERT OR IGNORE INTO screenshots (app_id, url) VALUES (?, ?)
  `);
  const insertMany = db.transaction((list) => {
    for (const url of list) stmt.run(appId, url);
  });
  insertMany(urls);
}

// 查询已有详情的 appId 集合（最近 N 天内更新过的）
export function getRecentlyUpdatedAppIds(db, withinDays = 7) {
  const since = new Date();
  since.setDate(since.getDate() - withinDays);
  const rows = db.prepare(`
    SELECT app_id FROM games WHERE updated_at >= ?
  `).all(since.toISOString().slice(0, 10));
  return new Set(rows.map(r => r.app_id));
}
