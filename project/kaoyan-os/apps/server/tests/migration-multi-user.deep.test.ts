import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { DatabaseSync } from 'node:sqlite';
import { initSchema, migrateToMultiUser } from '../src/db';

// 手工建一个单用户老库：没有 users / sessions 表，
// 业务表结构等同于 initSchema 加 user_id 列之前的样子。
function createLegacyDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:');
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
      source TEXT NOT NULL DEFAULT 'manual'
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

  // 老数据
  db.prepare(
    `INSERT INTO plans (date, subject, title, planned_minutes, done) VALUES (?, ?, ?, ?, ?)`,
  ).run('2024-01-01', 'math', 'old plan', 60, 1);
  db.prepare(
    `INSERT INTO focus_sessions (subject, minutes, started_at, note) VALUES (?, ?, ?, ?)`,
  ).run('math', 25, '2024-01-01T00:00:00.000Z', 'old focus');
  db.prepare(
    `INSERT INTO mistakes (subject, title, content, analysis, mastered) VALUES (?, ?, ?, ?, ?)`,
  ).run('math', 'old mistake', 'c', 'a', 0);
  db.prepare(
    `INSERT INTO words (word, phonetic, meaning, example, source) VALUES (?, ?, ?, ?, ?)`,
  ).run('legacy', '/l/', '旧的', 'legacy example', 'manual');
  db.prepare(
    `INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)`,
  ).run(1, 2.6, 3, 2, '2024-02-01');
  db.prepare(
    `INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)`,
  ).run('math', 'p1', 100, 150, 180, '2024-01-01T00:00:00.000Z');
  db.prepare(`INSERT INTO settings (key, value) VALUES (?, ?)`).run('theme', 'dark');

  return db;
}

describe('migrateToMultiUser 深测', () => {
  let db: DatabaseSync;

  beforeEach(() => {
    db = createLegacyDb();
  });

  afterEach(() => {
    db.close();
  });

  it('initSchema 后：users 表出现 local 用户，老数据全部归 local，FK 完整', () => {
    initSchema(db);

    // 1) users 表存在且有且仅有一个 local 用户
    const localUsers = db
      .prepare(`SELECT id, username FROM users WHERE username = 'local'`)
      .all() as Array<{ id: number; username: string }>;
    expect(localUsers.length).toBe(1);
    const localId = localUsers[0].id;
    expect(typeof localId).toBe('number');

    // 2) sessions 表出现（结构存在，无数据）
    const sessionCount = db
      .prepare(`SELECT COUNT(*) AS n FROM sessions`)
      .get() as { n: number };
    expect(sessionCount.n).toBe(0);

    // 3) 全部老数据 user_id = localId
    const tables = ['plans', 'focus_sessions', 'mistakes', 'exam_records', 'words'] as const;
    for (const t of tables) {
      const rows = db
        .prepare(`SELECT id, user_id FROM ${t}`)
        .all() as Array<{ id: number; user_id: number | null }>;
      expect(rows.length).toBe(1);
      expect(rows[0].user_id).toBe(localId);
    }

    // settings 也被归属到 local，主键改为 (user_id, key)
    const settingsRows = db
      .prepare(`SELECT user_id, key, value FROM settings`)
      .all() as Array<{ user_id: number; key: string; value: string }>;
    expect(settingsRows).toEqual([{ user_id: localId, key: 'theme', value: 'dark' }]);

    // 4) srs_state 仍指向重建后的 words.id，且 words.user_id = localId
    const srs = db
      .prepare(
        `SELECT s.word_id, w.user_id AS word_user_id, s.ease, s.interval_days, s.repetitions, s.due_date
         FROM srs_state s JOIN words w ON w.id = s.word_id`,
      )
      .all() as Array<{
        word_id: number;
        word_user_id: number;
        ease: number;
        interval_days: number;
        repetitions: number;
        due_date: string;
      }>;
    expect(srs.length).toBe(1);
    expect(srs[0].word_user_id).toBe(localId);
    expect(srs[0].ease).toBeCloseTo(2.6);
    expect(srs[0].interval_days).toBe(3);
    expect(srs[0].repetitions).toBe(2);
    expect(srs[0].due_date).toBe('2024-02-01');

    // 5) FK 完整：所有 *_new 临时表残留为 0；user_id 外键都能在 users 找到
    const leftovers = db
      .prepare(
        `SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%\\_new' ESCAPE '\\'`,
      )
      .all() as Array<{ name: string }>;
    expect(leftovers).toEqual([]);

    const orphanPlans = db
      .prepare(
        `SELECT COUNT(*) AS n FROM plans p LEFT JOIN users u ON u.id = p.user_id WHERE u.id IS NULL`,
      )
      .get() as { n: number };
    expect(orphanPlans.n).toBe(0);

    // 6) words 的 UNIQUE 已改为 (user_id, word)：同一 user 重名应报错
    expect(() =>
      db
        .prepare(
          `INSERT INTO words (user_id, word) VALUES (?, ?)`,
        )
        .run(localId, 'legacy'),
    ).toThrow();

    // 7) plans.user_id 是 NOT NULL 且有 FK（PRAGMA 检查）
    const plansCols = db
      .prepare(`PRAGMA table_info(plans)`)
      .all() as Array<{ name: string; notnull: number }>;
    const userIdCol = plansCols.find((c) => c.name === 'user_id');
    expect(userIdCol).toBeDefined();
    expect(userIdCol!.notnull).toBe(1);

    const plansFks = db
      .prepare(`PRAGMA foreign_key_list(plans)`)
      .all() as Array<{ table: string; from: string; to: string }>;
    expect(
      plansFks.some((f) => f.table === 'users' && f.from === 'user_id' && f.to === 'id'),
    ).toBe(true);
  });

  it('重复跑迁移幂等：数据不翻倍、local 用户不重复、FK 依然完整', () => {
    initSchema(db);

    const localAfterFirst = db
      .prepare(`SELECT id FROM users WHERE username = 'local'`)
      .all() as Array<{ id: number }>;
    expect(localAfterFirst.length).toBe(1);
    const localId = localAfterFirst[0].id;

    const snapshot = () => {
      const counts: Record<string, number> = {};
      for (const t of ['plans', 'focus_sessions', 'mistakes', 'exam_records', 'words', 'srs_state', 'settings', 'users', 'sessions']) {
        const r = db.prepare(`SELECT COUNT(*) AS n FROM ${t}`).get() as { n: number };
        counts[t] = r.n;
      }
      return counts;
    };

    const before = snapshot();
    expect(before.plans).toBe(1);
    expect(before.focus_sessions).toBe(1);
    expect(before.mistakes).toBe(1);
    expect(before.exam_records).toBe(1);
    expect(before.words).toBe(1);
    expect(before.srs_state).toBe(1);
    expect(before.settings).toBe(1);
    expect(before.users).toBe(1);

    // 再跑一次迁移
    migrateToMultiUser(db);
    const after = snapshot();

    expect(after).toEqual(before);

    // 老数据 user_id 依旧为 local
    for (const t of ['plans', 'focus_sessions', 'mistakes', 'exam_records', 'words']) {
      const rows = db
        .prepare(`SELECT user_id FROM ${t}`)
        .all() as Array<{ user_id: number }>;
      expect(rows.length).toBe(1);
      expect(rows[0].user_id).toBe(localId);
    }

    // 没有残留 _new 表
    const leftovers = db
      .prepare(
        `SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%\\_new' ESCAPE '\\'`,
      )
      .all() as Array<{ name: string }>;
    expect(leftovers).toEqual([]);
  });
});
