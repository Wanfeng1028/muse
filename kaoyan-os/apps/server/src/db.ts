import { DatabaseSync } from 'node:sqlite';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { ensureLocalUser } from './auth';

// 初始化所有表结构（IF NOT EXISTS，包含默认值）
export function initSchema(db: DatabaseSync): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS plans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT NOT NULL,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      planned_minutes INTEGER NOT NULL DEFAULT 0,
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS focus_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      minutes INTEGER NOT NULL DEFAULT 0,
      started_at TEXT NOT NULL,
      note TEXT NULL,
      plan_id INTEGER NULL
    );

    CREATE TABLE IF NOT EXISTS mistakes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      content TEXT NOT NULL DEFAULT '',
      analysis TEXT NOT NULL DEFAULT '',
      mastered INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS words (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      word TEXT NOT NULL UNIQUE,
      phonetic TEXT NOT NULL DEFAULT '',
      meaning TEXT NOT NULL DEFAULT '',
      example TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'manual',
      memory_tip TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS srs_state (
      word_id INTEGER PRIMARY KEY,
      ease REAL NOT NULL DEFAULT 2.5,
      interval_days INTEGER NOT NULL DEFAULT 0,
      repetitions INTEGER NOT NULL DEFAULT 0,
      due_date TEXT NOT NULL,
      FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS exam_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      paper TEXT NOT NULL,
      score REAL NOT NULL DEFAULT 0,
      total_score REAL NOT NULL DEFAULT 0,
      duration_minutes INTEGER NOT NULL DEFAULT 0,
      taken_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      token_hash TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
      expires_at TEXT NOT NULL,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
  `);

  // 老库迁移：words 表补 memory_tip 列
  const cols = db.prepare('PRAGMA table_info(words)').all() as Array<{ name: string }>;
  // NOTE: 硬编码表名，避免任何字符串拼接进入 PRAGMA

  if (!cols.some((c) => c.name === 'memory_tip')) {
    db.exec("ALTER TABLE words ADD COLUMN memory_tip TEXT NOT NULL DEFAULT ''");
  }

  // 老库迁移：focus_sessions 表补 plan_id 列（v1.11.0 专注-计划联动）
  const focusCols = db.prepare('PRAGMA table_info(focus_sessions)').all() as Array<{ name: string }>;
  if (!focusCols.some((c) => c.name === 'plan_id')) {
    db.exec('ALTER TABLE focus_sessions ADD COLUMN plan_id INTEGER NULL');
  }

  // 老库迁移：settings 表在多用户迁移前先确保存在（IF NOT EXISTS 已在上面创建）
  // 注：不在 initSchema 里做 settings 重建，交给 migrateToMultiUser 处理

  // 多用户迁移
  migrateToMultiUser(db);
}

// 表是否已有 user_id 列
const ALLOWED_TABLES = new Set([
  'plans', 'focus_sessions', 'mistakes', 'words', 'srs_state',
  'exam_records', 'settings', 'users', 'sessions',
]);

function hasUserIdColumn(db: DatabaseSync, table: string): boolean {
  if (!ALLOWED_TABLES.has(table)) {
    throw new Error(`hasUserIdColumn: unexpected table name: ${table}`);
  }
  const cols = db.prepare(`PRAGMA table_info(${table})`).all() as Array<{ name: string }>;
  return cols.some((c) => c.name === 'user_id');
}

function assertTableName(table: string): void {
  if (!ALLOWED_TABLES.has(table)) {
    throw new Error(`unexpected table name: ${table}`);
  }
}

// 通用重建：用 newDef 建新表 -> 按 columns 列表倒数据 -> 删旧表 -> 改名
function rebuildTable(db: DatabaseSync, table: string, newDef: string, columns: string): void {
  db.exec(`CREATE TABLE ${table}_new (${newDef})`);
  db.exec(`INSERT INTO ${table}_new (${columns}) SELECT ${columns} FROM ${table}`);
  // DROP TABLE 在 foreign_keys=ON 时会做隐式 DELETE FROM 并触发级联（如 words -> srs_state），
  // 重建期间先关闭外键，改名完成后再恢复
  db.exec('PRAGMA foreign_keys = OFF');
  try {
    db.exec(`DROP TABLE ${table}`);
    db.exec(`ALTER TABLE ${table}_new RENAME TO ${table}`);
  } finally {
    db.exec('PRAGMA foreign_keys = ON');
  }
}

export function migrateToMultiUser(db: DatabaseSync): void {
  // 0) 确保 local 保留用户存在
  const localId = ensureLocalUser(db);

  // 1) plans / focus_sessions / mistakes / exam_records：加列 -> 回填 -> 重建
  const simpleTables: Array<{ table: string; cols: string }> = [
    { table: 'plans', cols: 'id, user_id, date, subject, title, planned_minutes, done, created_at' },
    { table: 'focus_sessions', cols: 'id, user_id, subject, minutes, started_at, note' },
    { table: 'mistakes', cols: 'id, user_id, subject, title, content, analysis, mastered, created_at' },
    { table: 'exam_records', cols: 'id, user_id, subject, paper, score, total_score, duration_minutes, taken_at' },
  ];
  const newDefs: Record<string, string> = {
    plans: `id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      planned_minutes INTEGER NOT NULL DEFAULT 0,
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`,
    focus_sessions: `id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      subject TEXT NOT NULL,
      minutes INTEGER NOT NULL DEFAULT 0,
      started_at TEXT NOT NULL,
      note TEXT NULL,
      plan_id INTEGER NULL,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`,
    mistakes: `id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      content TEXT NOT NULL DEFAULT '',
      analysis TEXT NOT NULL DEFAULT '',
      mastered INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`,
    exam_records: `id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      subject TEXT NOT NULL,
      paper TEXT NOT NULL,
      score REAL NOT NULL DEFAULT 0,
      total_score REAL NOT NULL DEFAULT 0,
      duration_minutes INTEGER NOT NULL DEFAULT 0,
      taken_at TEXT NOT NULL,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`,
  };
  for (const { table, cols } of simpleTables) {
    if (!hasUserIdColumn(db, table)) {
      db.exec(`ALTER TABLE ${table} ADD COLUMN user_id INTEGER`);
      db.prepare(`UPDATE ${table} SET user_id = ? WHERE user_id IS NULL`).run(localId);
      let copyCols = cols;
      if (table === 'focus_sessions') {
        const fc = db.prepare('PRAGMA table_info(focus_sessions)').all() as Array<{ name: string }>;
        if (fc.some((c) => c.name === 'plan_id')) {
          copyCols = cols + ', plan_id';
        }
      }
      rebuildTable(db, table, newDefs[table], copyCols);
    }
  }

  // 2) words：加列 -> 回填 -> 重建（UNIQUE 改为 (user_id, word)）
  let wordsRebuilt = false;
  if (!hasUserIdColumn(db, 'words')) {
    db.exec('ALTER TABLE words ADD COLUMN user_id INTEGER');
    db.prepare('UPDATE words SET user_id = ? WHERE user_id IS NULL').run(localId);
    rebuildTable(
      db,
      'words',
      `id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      word TEXT NOT NULL,
      phonetic TEXT NOT NULL DEFAULT '',
      meaning TEXT NOT NULL DEFAULT '',
      example TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'manual',
      memory_tip TEXT NOT NULL DEFAULT '',
      UNIQUE (user_id, word),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`,
      'id, user_id, word, phonetic, meaning, example, source, memory_tip',
    );
    wordsRebuilt = true;
  }

  // 3) srs_state：words 重建过才重建（恢复外键），本身不加 user_id
  if (wordsRebuilt) {
    rebuildTable(
      db,
      'srs_state',
      `word_id INTEGER PRIMARY KEY,
      ease REAL NOT NULL DEFAULT 2.5,
      interval_days INTEGER NOT NULL DEFAULT 0,
      repetitions INTEGER NOT NULL DEFAULT 0,
      due_date TEXT NOT NULL,
      FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE`,
      'word_id, ease, interval_days, repetitions, due_date',
    );
  }

  // 4) settings：无 user_id 列则重建为 PRIMARY KEY (user_id, key)，老行归 local
  if (!hasUserIdColumn(db, 'settings')) {
    db.exec(`CREATE TABLE settings_new (
      user_id INTEGER NOT NULL,
      key TEXT NOT NULL,
      value TEXT NOT NULL,
      PRIMARY KEY (user_id, key),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )`);
    db.prepare(
      'INSERT INTO settings_new (user_id, key, value) SELECT ?, key, value FROM settings'
    ).run(localId);
    db.exec('DROP TABLE settings');
    db.exec('ALTER TABLE settings_new RENAME TO settings');
  }
}

// 创建并初始化数据库连接
export function createDb(dbPath: string): DatabaseSync {
  // 非内存数据库时，确保父目录存在
  if (dbPath !== ':memory:') {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  }
  const db = new DatabaseSync(dbPath);
  // 开启外键约束
  db.exec('PRAGMA foreign_keys = ON');
  initSchema(db);
  return db;
}

// 返回本地时区的今天日期 YYYY-MM-DD
export function todayStr(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// 在日期字符串上加减天数，返回 YYYY-MM-DD
export function addDays(dateStr: string, n: number): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + n);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, '0');
  const dd = String(dt.getDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}

// 返回当前时间的 ISO 字符串
export function nowIso(): string {
  return new Date().toISOString();
}
