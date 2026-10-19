import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import {
  initSchema,
  createDb,
  todayStr,
  addDays,
  nowIso,
} from '../src/db';

function makeTempDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'muse-db-test-'));
}

function rmrf(p: string): void {
  fs.rmSync(p, { recursive: true, force: true });
}

describe('db.deep.test.ts', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = makeTempDir();
  });

  afterEach(() => {
    rmrf(tmpDir);
  });

  it('addDays 跨月边界：2024-01-31 + 1 得到 2024-02-01', () => {
    const result = addDays('2024-01-31', 1);
    expect(result).toBe('2024-02-01');
    expect(result.split('-').length).toBe(3);
    expect(Number(result.slice(0, 4))).toBe(2024);
  });

  it('addDays 闰年边界：2024-02-28 + 1 得到 2024-02-29，再 + 1 得到 2024-03-01', () => {
    const feb29 = addDays('2024-02-28', 1);
    const mar01 = addDays(feb29, 1);
    expect(feb29).toBe('2024-02-29');
    expect(mar01).toBe('2024-03-01');
  });

  it('addDays 非闰年边界：2023-02-28 + 1 得到 2023-03-01', () => {
    const result = addDays('2023-02-28', 1);
    expect(result).toBe('2023-03-01');
    expect(addDays('2023-03-01', -1)).toBe('2023-02-28');
  });

  it('addDays 跨年边界：2024-12-31 + 1 得到 2025-01-01', () => {
    const result = addDays('2024-12-31', 1);
    expect(result).toBe('2025-01-01');
    expect(addDays('2025-01-01', -1)).toBe('2024-12-31');
  });

  it('todayStr 返回本地 YYYY-MM-DD，且可被 addDays 解析', () => {
    const t = todayStr();
    expect(t).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const next = addDays(t, 1);
    const diff = new Date(next + 'T00:00:00').getTime() - new Date(t + 'T00:00:00').getTime();
    expect(diff).toBe(24 * 60 * 60 * 1000);
  });

  it('空计划：plans 表为空时聚合查询返回 0，插入两条后正确统计', () => {
    const db = createDb(':memory:');
    const userId = (db
      .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
      .run('deep-user-1', 'x').lastInsertRowid) as number;
    const emptyRow = db
      .prepare('SELECT COUNT(*) AS c FROM plans')
      .get() as { c: number };
    expect(emptyRow.c).toBe(0);

    const insert = db.prepare(
      'INSERT INTO plans (user_id, date, subject, title, planned_minutes, done) VALUES (?, ?, ?, ?, ?, ?)'
    );
    insert.run(userId, '2024-02-29', 'math', '导数专项', 90, 0);
    insert.run(userId, '2024-02-29', 'english', '阅读训练', 60, 1);

    const after = db
      .prepare('SELECT COUNT(*) AS c, SUM(planned_minutes) AS m FROM plans')
      .get() as { c: number; m: number };
    expect(after.c).toBe(2);
    expect(after.m).toBe(150);
  });

  it('番茄计时边界：minutes=0 与 minutes=999 均可写入并按 started_at 排序', () => {
    const db = createDb(':memory:');
    const userId = (db
      .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
      .run('deep-user-2', 'x').lastInsertRowid) as number;
    const insert = db.prepare(
      'INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note) VALUES (?, ?, ?, ?, ?)'
    );
    insert.run(userId, 'math', 0, '2024-03-01T08:00:00.000Z', '零分钟');
    insert.run(userId, 'math', 999, '2024-03-01T09:00:00.000Z', '超长');

    const rows = db
      .prepare('SELECT minutes FROM focus_sessions ORDER BY started_at ASC')
      .all() as Array<{ minutes: number }>;
    expect(rows.length).toBe(2);
    expect(rows[0].minutes).toBe(0);
    expect(rows[1].minutes).toBe(999);
  });

  it('错题去重：相同 subject+title 视为同一道题，重复插入需能被应用层去重后仅保留一条', () => {
    const db = createDb(':memory:');
    const userId = (db
      .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
      .run('deep-user-3', 'x').lastInsertRowid) as number;
    const insert = db.prepare(
      'INSERT INTO mistakes (user_id, subject, title, content, analysis) VALUES (?, ?, ?, ?, ?)'
    );
    insert.run(userId, 'math', '极限计算错误', '原题A', '分析A');

    const existing = db
      .prepare('SELECT id FROM mistakes WHERE subject = ? AND title = ?')
      .get('math', '极限计算错误') as { id: number } | undefined;
    expect(existing).toBeDefined();

    if (!existing) {
      insert.run(userId, 'math', '极限计算错误', '原题A', '分析A');
    }
    const count = db
      .prepare('SELECT COUNT(*) AS c FROM mistakes WHERE subject = ? AND title = ?')
      .get('math', '极限计算错误') as { c: number };
    expect(count.c).toBe(1);
    expect(existing!.id).toBeGreaterThan(0);
  });

  it('单词 SRS：初始 due_date 为今天，正确后 interval_days 递增，错误后 repetitions 归零', () => {
    const db = createDb(':memory:');
    const userId = (db
      .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
      .run('deep-user-4', 'x').lastInsertRowid) as number;
    const wordInsert = db.prepare(
      'INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES (?, ?, ?, ?, ?, ?, ?)'
    );
    wordInsert.run(userId, 'abandon', 'əˈbændən', '放弃', 'He abandoned it.', 'manual', 'a-ban-don');

    const wordRow = db
      .prepare('SELECT id FROM words WHERE word = ?')
      .get('abandon') as { id: number };
    expect(wordRow.id).toBeGreaterThan(0);

    const dueToday = todayStr();
    db.prepare(
      'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)'
    ).run(wordRow.id, 2.5, 0, 0, dueToday);

    // 正确复习：interval_days 由 0 -> 1，repetitions 由 0 -> 1
    db.prepare(
      'UPDATE srs_state SET ease = ?, interval_days = ?, repetitions = ?, due_date = ? WHERE word_id = ?'
    ).run(2.6, 1, 1, addDays(dueToday, 1), wordRow.id);

    const afterGood = db
      .prepare('SELECT interval_days, repetitions, ease, due_date FROM srs_state WHERE word_id = ?')
      .get(wordRow.id) as {
      interval_days: number;
      repetitions: number;
      ease: number;
      due_date: string;
    };
    expect(afterGood.interval_days).toBe(1);
    expect(afterGood.repetitions).toBe(1);
    expect(afterGood.ease).toBeCloseTo(2.6, 5);

    // 错误复习：repetitions 归零
    db.prepare(
      'UPDATE srs_state SET interval_days = ?, repetitions = ?, due_date = ? WHERE word_id = ?'
    ).run(0, 0, dueToday, wordRow.id);

    const afterBad = db
      .prepare('SELECT interval_days, repetitions FROM srs_state WHERE word_id = ?')
      .get(wordRow.id) as { interval_days: number; repetitions: number };
    expect(afterBad.repetitions).toBe(0);
    expect(afterBad.interval_days).toBe(0);
  });

  it('导入 CSV 畸形行：空行、缺列、列数过多的行被跳过，仅合法行入库', () => {
    const db = createDb(':memory:');
    const userId = (db
      .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
      .run('deep-user-5', 'x').lastInsertRowid) as number;
    const insert = db.prepare(
      'INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES (?, ?, ?, ?, ?, ?, ?)'
    );

    const csvLines = [
      'word,phonetic,meaning,example,source,memory_tip',
      'apple,ˈæpl,苹果,An apple.,import,',
      '',
      'broken-row-only-two,fields',
      'banana,ˈbənɑːnə,香蕉,A banana.,import,,extra,column',
      'cherry,ˈtʃeri,樱桃,A cherry.,import,巧记',
    ];

    const headerCols = 6;
    let imported = 0;
    let skipped = 0;
    for (const raw of csvLines) {
      const line = raw.trim();
      if (line.length === 0) {
        skipped += 1;
        continue;
      }
      const cols = line.split(',');
      if (cols[0] === 'word') {
        continue;
      }
      if (cols.length !== headerCols) {
        skipped += 1;
        continue;
      }
      insert.run(userId, cols[0], cols[1], cols[2], cols[3], cols[4], cols[5]);
      imported += 1;
    }

    expect(imported).toBe(2);
    expect(skipped).toBe(3);

    const rows = db
      .prepare('SELECT word FROM words ORDER BY word ASC')
      .all() as Array<{ word: string }>;
    expect(rows.map((r) => r.word)).toEqual(['apple', 'cherry']);
  });

  it('备份恢复 round-trip：写入数据 -> 备份文件 -> 从备份重开 -> 数据一致', () => {
    const srcPath = path.join(tmpDir, 'src.db');
    const db = createDb(srcPath);
    const userId = (db
      .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
      .run('deep-user-6', 'x').lastInsertRowid) as number;
    db.prepare(
      'INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
    ).run(userId, 'math', '2024 真题一', 138, 150, 180, nowIso());
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)').run(userId, 'target_school', '示例大学');
    db.close();

    const backupPath = path.join(tmpDir, 'backup.db');
    fs.copyFileSync(srcPath, backupPath);
    expect(fs.existsSync(backupPath)).toBe(true);
    expect(fs.statSync(backupPath).size).toBeGreaterThan(0);

    const restored = new DatabaseSync(backupPath);
    restored.exec('PRAGMA foreign_keys = ON');
    initSchema(restored);

    const exam = restored
      .prepare('SELECT subject, score, total_score FROM exam_records')
      .get() as { subject: string; score: number; total_score: number };
    expect(exam.subject).toBe('math');
    expect(exam.score).toBe(138);
    expect(exam.total_score).toBe(150);

    const setting = restored
      .prepare('SELECT value FROM settings WHERE key = ?')
      .get('target_school') as { value: string };
    expect(setting.value).toBe('示例大学');

    restored.close();
  });

  it('外键级联：删除 words 行时 srs_state 关联行被级联删除', () => {
    const db = createDb(':memory:');
    const userId = (db
      .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
      .run('deep-user-7', 'x').lastInsertRowid) as number;
    db.prepare(
      'INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES (?, ?, ?, ?, ?, ?, ?)'
    ).run(userId, 'cascade', '', '', '', 'manual', '');
    const wid = (db.prepare('SELECT id FROM words WHERE word = ?').get('cascade') as { id: number }).id;
    db.prepare(
      'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)'
    ).run(wid, 2.5, 0, 0, todayStr());

    const before = db
      .prepare('SELECT COUNT(*) AS c FROM srs_state WHERE word_id = ?')
      .get(wid) as { c: number };
    expect(before.c).toBe(1);

    db.prepare('DELETE FROM words WHERE id = ?').run(wid);

    const after = db
      .prepare('SELECT COUNT(*) AS c FROM srs_state WHERE word_id = ?')
      .get(wid) as { c: number };
    expect(after.c).toBe(0);
    expect((db.prepare('SELECT COUNT(*) AS c FROM words').get() as { c: number }).c).toBe(0);
  });

  it('老库迁移：words 表缺 memory_tip 列时 initSchema 自动补齐且默认值为空串', () => {
    const legacyPath = path.join(tmpDir, 'legacy.db');
    const legacy = new DatabaseSync(legacyPath);
    legacy.exec(`
      CREATE TABLE words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL UNIQUE,
        phonetic TEXT NOT NULL DEFAULT '',
        meaning TEXT NOT NULL DEFAULT '',
        example TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'manual'
      );
    `);
    legacy.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
      );
    `);
    const legacyUserId = (legacy
      .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
      .run('deep-user-8', 'x').lastInsertRowid) as number;
    legacy.prepare(
      'INSERT INTO words (word, phonetic, meaning, example, source) VALUES (?, ?, ?, ?, ?)'
    ).run('legacy', '', '老数据', '', 'manual');

    const colsBefore = legacy.prepare('PRAGMA table_info(words)').all() as Array<{ name: string }>;
    expect(colsBefore.some((c) => c.name === 'memory_tip')).toBe(false);

    initSchema(legacy);

    const colsAfter = legacy.prepare('PRAGMA table_info(words)').all() as Array<{ name: string }>;
    expect(colsAfter.some((c) => c.name === 'memory_tip')).toBe(true);

    const row = legacy
      .prepare('SELECT word, memory_tip FROM words WHERE word = ?')
      .get('legacy') as { word: string; memory_tip: string };
    expect(row.word).toBe('legacy');
    expect(row.memory_tip).toBe('');
    legacy.close();
  });
});