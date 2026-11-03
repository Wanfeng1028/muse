import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { DatabaseSync } from 'node:sqlite';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import * as path from 'node:path';
import { createDb, migrateToMultiUser } from '../src/db';

// 用 BCRYPT_COST=4 让 ensureLocalUser（依赖 auth）走低成本 hash；
// 若 auth 模块在 import 时读取该变量，需在进程级设置。
process.env.BCRYPT_COST = process.env.BCRYPT_COST ?? '4';

let tmpDir: string;

beforeEach(() => {
  tmpDir = mkdtempSync(path.join(tmpdir(), 'kaoyan-migrate-'));
});

afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

// 构造一个"老单用户库"：直接 exec 旧 schema，不经过 initSchema。
function makeLegacyDb(dbPath: string): DatabaseSync {
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA foreign_keys = ON');
  db.exec(`
    CREATE TABLE plans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT NOT NULL,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      planned_minutes INTEGER NOT NULL DEFAULT 0,
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE focus_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      minutes INTEGER NOT NULL DEFAULT 0,
      started_at TEXT NOT NULL,
      note TEXT NULL
    );
    CREATE TABLE mistakes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      content TEXT NOT NULL DEFAULT '',
      analysis TEXT NOT NULL DEFAULT '',
      mastered INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE words (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      word TEXT NOT NULL UNIQUE,
      phonetic TEXT NOT NULL DEFAULT '',
      meaning TEXT NOT NULL DEFAULT '',
      example TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'manual',
      memory_tip TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE srs_state (
      word_id INTEGER PRIMARY KEY,
      ease REAL NOT NULL DEFAULT 2.5,
      interval_days INTEGER NOT NULL DEFAULT 0,
      repetitions INTEGER NOT NULL DEFAULT 0,
      due_date TEXT NOT NULL,
      FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    );
    CREATE TABLE exam_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      paper TEXT NOT NULL,
      score REAL NOT NULL DEFAULT 0,
      total_score REAL NOT NULL DEFAULT 0,
      duration_minutes INTEGER NOT NULL DEFAULT 0,
      taken_at TEXT NOT NULL
    );
    CREATE TABLE settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
  `);
  return db;
}

describe('migrateToMultiUser', () => {
  it('对老单用户库迁移：所有业务表补 user_id 并归 local，关联表 srs_state 保留', () => {
    const dbPath = path.join(tmpDir, 'legacy.db');
    const db = makeLegacyDb(dbPath);

    // 预置老数据
    db.prepare(
      `INSERT INTO plans (date, subject, title, planned_minutes, done) VALUES (?,?,?,?,?)`,
    ).run('2025-01-01', 'math', 'p1', 60, 0);
    db.prepare(
      `INSERT INTO words (word, phonetic, meaning, example, source, memory_tip) VALUES (?,?,?,?,?,?)`,
    ).run('apple', '/æ/', '苹果', '', 'manual', '');
    db.prepare(
      `INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?,?,?,?,?)`,
    ).run(1, 2.5, 0, 0, '2025-02-01');
    db.prepare(`INSERT INTO settings (key, value) VALUES (?, ?)`).run('theme', 'dark');
    db.prepare(
      `INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?,?,?,?,?,?)`,
    ).run('math', '201', 100, 150, 120, '2025-01-02');

    // 释放连接再走 createDb（会 initSchema -> migrateToMultiUser）
    db.close();

    const migrated = createDb(dbPath);

    // local 用户存在
    const local = migrated
      .prepare('SELECT id FROM users WHERE username = ?')
      .get('local') as { id: number } | undefined;
    expect(local).toBeTruthy();
    const localId = local!.id;

    // plans 归 local 且有 NOT NULL user_id
    const plan = migrated
      .prepare('SELECT user_id FROM plans WHERE title = ?')
      .get('p1') as { user_id: number };
    expect(plan.user_id).toBe(localId);

    const planCols = migrated
      .prepare('PRAGMA table_info(plans)')
      .all() as Array<{ name: string; notnull: number }>;
    const planUserIdCol = planCols.find((c) => c.name === 'user_id');
    expect(planUserIdCol).toBeTruthy();
    expect(planUserIdCol!.notnull).toBe(1);

    // words 归 local，且 UNIQUE(user_id, word) 生效：同 user 重复 word 报错
    const word = migrated
      .prepare('SELECT id, user_id FROM words WHERE word = ?')
      .get('apple') as { id: number; user_id: number };
    expect(word.user_id).toBe(localId);

    expect(() =>
      migrated
        .prepare(
          `INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES (?,?,?,?,?,?,?)`,
        )
        .run(localId, 'apple', '', '', '', 'manual', ''),
    ).toThrow();

    // srs_state 未丢，word_id 指向迁移后的 words.id（id 未变）
    const srs = migrated
      .prepare('SELECT word_id, due_date FROM srs_state WHERE word_id = ?')
      .get(word.id) as { word_id: number; due_date: string };
    expect(srs).toBeTruthy();
    expect(srs.due_date).toBe('2025-02-01');

    // settings 归 local
    const setting = migrated
      .prepare('SELECT user_id, value FROM settings WHERE key = ?')
      .get('theme') as { user_id: number; value: string };
    expect(setting.user_id).toBe(localId);
    expect(setting.value).toBe('dark');

    // exam_records 归 local
    const exam = migrated
      .prepare('SELECT user_id FROM exam_records WHERE paper = ?')
      .get('201') as { user_id: number };
    expect(exam.user_id).toBe(localId);

    // 外键已恢复：插入孤儿 srs_state 应失败
    expect(() =>
      migrated
        .prepare(
          `INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?,?,?,?,?)`,
        )
        .run(999999, 2.5, 0, 0, '2025-01-01'),
    ).toThrow();

    migrated.close();
  });

  it('幂等：对已迁移过的库再次调用 migrateToMultiUser 不重复重建、不报错、不重复 local', () => {
    const dbPath = path.join(tmpDir, 'idem.db');
    const db = createDb(dbPath);
    const before = db.prepare('SELECT COUNT(*) AS n FROM users WHERE username = ?').get('local') as { n: number };
    expect(before.n).toBe(1);

    // 直接再跑一次（模拟进程重启）
    expect(() => migrateToMultiUser(db)).not.toThrow();

    const after = db.prepare('SELECT COUNT(*) AS n FROM users WHERE username = ?').get('local') as { n: number };
    expect(after.n).toBe(1);

    // 所有表都已有 user_id 列
    for (const t of ['plans', 'focus_sessions', 'mistakes', 'exam_records', 'words', 'settings']) {
      const cols = db.prepare(`PRAGMA table_info(${t})`).all() as Array<{ name: string }>;
      expect(cols.some((c) => c.name === 'user_id')).toBe(true);
    }

    db.close();
  });

  it('settings 无 user_id 列时才迁移；已有 user_id 列时保留原数据', () => {
    const dbPath = path.join(tmpDir, 'settings-idem.db');
    const db = createDb(dbPath);
    const local = db.prepare('SELECT id FROM users WHERE username = ?').get('local') as { id: number };

    // 已有 user_id 列的 settings：直接插入新用户的行
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES (?,?,?)').run(local.id, 'k1', 'v1');
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES (?,?,?)').run(local.id, 'k2', 'v2');

    // 再次迁移不应破坏
    migrateToMultiUser(db);

    const rows = db
      .prepare('SELECT key, value FROM settings WHERE user_id = ? ORDER BY key')
      .all(local.id) as Array<{ key: string; value: string }>;
    expect(rows).toEqual([
      { key: 'k1', value: 'v1' },
      { key: 'k2', value: 'v2' },
    ]);

    db.close();
  });
});
