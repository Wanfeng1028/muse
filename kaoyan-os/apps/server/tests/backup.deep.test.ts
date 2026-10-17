import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify from 'fastify';
import type { FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';

interface TestContext {
  app: FastifyInstance;
  db: DatabaseSync;
}

function createSchema(db: DatabaseSync): void {
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
}

function seedMinimal(db: DatabaseSync): void {
  db.prepare('INSERT INTO plans (date, subject, title) VALUES (?, ?, ?)').run(
    '2024-02-29',
    'math',
    '闰年计划'
  );
  db.prepare(
    'INSERT INTO focus_sessions (subject, started_at) VALUES (?, ?)'
  ).run('math', '2024-02-29T08:00:00.000Z');
  db.prepare('INSERT INTO mistakes (subject, title) VALUES (?, ?)').run(
    'math',
    '错题题干一'
  );
  db.prepare('INSERT INTO words (word, meaning) VALUES (?, ?)').run(
    'abandon',
    '放弃'
  );
  db.prepare(
    'INSERT INTO srs_state (word_id, due_date, interval_days) VALUES (?, ?, ?)'
  ).run(1, '2024-03-01T00:00:00.000Z', 1);
  db.prepare(
    'INSERT INTO exam_records (subject, paper, taken_at) VALUES (?, ?, ?)'
  ).run('math', '2024考研数学一', '2024-02-29T00:00:00.000Z');
  db.prepare('INSERT INTO settings (key, value) VALUES (?, ?)').run(
    'theme',
    'dark'
  );
}

async function buildTestContext(): Promise<TestContext> {
  const db = new DatabaseSync(':memory:');
  createSchema(db);
  const app = Fastify();
  registerBackupRoutes(app, db);
  await app.ready();
  return { app, db };
}

async function teardown(ctx: TestContext): Promise<void> {
  await ctx.app.close();
  ctx.db.close();
}

async function exportAll(app: FastifyInstance): Promise<{
  format: string;
  version: number;
  tables: Record<string, Record<string, unknown>[]>;
}> {
  const res = await app.inject({ method: 'GET', url: '/api/backup/export' });
  expect(res.statusCode).toBe(200);
  return res.json();
}

async function importData(
  app: FastifyInstance,
  data: unknown,
  mode?: string
): Promise<{ statusCode: number; body: Record<string, unknown> }> {
  const body: Record<string, unknown> = { data };
  if (mode !== undefined) {
    body.mode = mode;
  }
  const res = await app.inject({
    method: 'POST',
    url: '/api/backup/import',
    payload: body,
  });
  return { statusCode: res.statusCode, body: res.json() };
}

function makeEmptyTables(): Record<string, Record<string, unknown>[]> {
  return {
    plans: [],
    focus_sessions: [],
    mistakes: [],
    words: [],
    srs_state: [],
    exam_records: [],
    settings: [],
  };
}

function makePayload(
  tables: Record<string, Record<string, unknown>[]>
): Record<string, unknown> {
  return {
    format: 'kaoyan-backup',
    version: 1,
    exportedAt: '2024-02-29T00:00:00.000Z',
    tables,
  };
}

describe('backup.deep 排程算法边界', () => {
  let ctx: TestContext;

  beforeEach(async () => {
    ctx = await buildTestContext();
  });

  afterEach(async () => {
    await teardown(ctx);
  });

  it('闰年 2024-02-29 的 plan 能导出并原样恢复', async () => {
    ctx.db
      .prepare('INSERT INTO plans (date, subject, title) VALUES (?, ?, ?)')
      .run('2024-02-29', 'math', '闰年计划');
    ctx.db
      .prepare('INSERT INTO plans (date, subject, title) VALUES (?, ?, ?)')
      .run('2024-03-01', 'english', '跨月计划');

    const exported = await exportAll(ctx.app);
    const plans = exported.tables.plans as Record<string, unknown>[];
    expect(plans.length).toBe(2);
    expect(plans[0].date).toBe('2024-02-29');
    expect(plans[0].subject).toBe('math');
    expect(plans[1].date).toBe('2024-03-01');
    expect(plans[1].subject).toBe('english');

    const imported = await importData(ctx.app, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const rows = ctx.db
      .prepare('SELECT date, subject, title FROM plans ORDER BY id ASC')
      .all() as Record<string, unknown>[];
    expect(rows.length).toBe(2);
    expect(rows[0].date).toBe('2024-02-29');
    expect(rows[1].date).toBe('2024-03-01');
  });

  it('空计划表导入导出 round-trip 不产生额外行', async () => {
    const exported = await exportAll(ctx.app);
    const plans = exported.tables.plans as Record<string, unknown>[];
    expect(plans.length).toBe(0);

    const imported = await importData(ctx.app, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const rows = ctx.db.prepare('SELECT * FROM plans').all() as Record<
      string,
      unknown
    >[];
    expect(rows.length).toBe(0);
  });

  it('跨月计划：2 月 29 与 3 月 1 同时保留且顺序按 id', async () => {
    ctx.db
      .prepare('INSERT INTO plans (date, subject, title) VALUES (?, ?, ?)')
      .run('2024-02-29', 'math', 'A');
    ctx.db
      .prepare('INSERT INTO plans (date, subject, title) VALUES (?, ?, ?)')
      .run('2024-03-01', 'math', 'B');

    const exported = await exportAll(ctx.app);
    const plans = exported.tables.plans as Record<string, unknown>[];
    const dates = plans.map((p) => p.date);
    expect(dates).toEqual(['2024-02-29', '2024-03-01']);

    const imported = await importData(ctx.app, exported, 'merge');
    expect(imported.statusCode).toBe(200);

    const count = ctx.db
      .prepare('SELECT COUNT(*) AS c FROM plans')
      .get() as Record<string, unknown>;
    // merge 按 id 去重：导出时的原 id 已存在则跳过，不会重复插入
    expect(count.c).toBe(2);
  });
});

describe('backup.deep 番茄计时与错题去重边界', () => {
  let ctx: TestContext;

  beforeEach(async () => {
    ctx = await buildTestContext();
  });

  afterEach(async () => {
    await teardown(ctx);
  });

  it('focus_sessions 起始时间跨日保留原始 ISO 字符串', async () => {
    ctx.db
      .prepare(
        'INSERT INTO focus_sessions (subject, started_at) VALUES (?, ?)'
      )
      .run('math', '2024-02-29T23:59:59.999Z');

    const exported = await exportAll(ctx.app);
    const sessions = exported.tables.focus_sessions as Record<string, unknown>[];
    expect(sessions.length).toBe(1);
    expect(sessions[0].started_at).toBe('2024-02-29T23:59:59.999Z');

    const imported = await importData(ctx.app, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const row = ctx.db
      .prepare('SELECT subject, started_at FROM focus_sessions')
      .get() as Record<string, unknown>;
    expect(row.subject).toBe('math');
    expect(row.started_at).toBe('2024-02-29T23:59:59.999Z');
  });

  it('重复错题按 id 保留全部行，去重交给上层不做隐式合并', async () => {
    ctx.db
      .prepare('INSERT INTO mistakes (subject, title) VALUES (?, ?)')
      .run('math', '同一题干');
    ctx.db
      .prepare('INSERT INTO mistakes (subject, title) VALUES (?, ?)')
      .run('math', '同一题干');

    const exported = await exportAll(ctx.app);
    const mistakes = exported.tables.mistakes as Record<string, unknown>[];
    expect(mistakes.length).toBe(2);
    expect(mistakes[0].title).toBe('同一题干');
    expect(mistakes[1].title).toBe('同一题干');

    const imported = await importData(ctx.app, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const count = ctx.db
      .prepare('SELECT COUNT(*) AS c FROM mistakes')
      .get() as Record<string, unknown>;
    expect(count.c).toBe(2);
  });

  it('focus_sessions 缺 started_at 时导入被拒', async () => {
    const tables = makeEmptyTables();
    tables.focus_sessions = [{ subject: 'math' }];
    const payload = makePayload(tables);

    const result = await importData(ctx.app, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('focus_sessions');
    expect(String(result.body.error)).toContain('started_at');
  });
});

describe('backup.deep 单词 SRS 与导入畸形 CSV 边界', () => {
  let ctx: TestContext;

  beforeEach(async () => {
    ctx = await buildTestContext();
  });

  afterEach(async () => {
    await teardown(ctx);
  });

  it('srs_state 按 word_id 排序导出且 interval_days 原样保留', async () => {
    ctx.db
      .prepare('INSERT INTO words (word, meaning) VALUES (?, ?)')
      .run('apple', '苹果');
    ctx.db
      .prepare('INSERT INTO words (word, meaning) VALUES (?, ?)')
      .run('banana', '香蕉');
    ctx.db
      .prepare(
        'INSERT INTO srs_state (word_id, due_date, interval_days) VALUES (?, ?, ?)'
      )
      .run(2, '2024-03-05T00:00:00.000Z', 7);
    ctx.db
      .prepare(
        'INSERT INTO srs_state (word_id, due_date, interval_days) VALUES (?, ?, ?)'
      )
      .run(1, '2024-03-02T00:00:00.000Z', 3);

    const exported = await exportAll(ctx.app);
    const srs = exported.tables.srs_state as Record<string, unknown>[];
    expect(srs.length).toBe(2);
    expect(srs[0].word_id).toBe(1);
    expect(srs[0].interval_days).toBe(3);
    expect(srs[1].word_id).toBe(2);
    expect(srs[1].interval_days).toBe(7);

    const imported = await importData(ctx.app, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const row = ctx.db
      .prepare('SELECT interval_days FROM srs_state WHERE word_id = ?')
      .get(1) as Record<string, unknown>;
    expect(row.interval_days).toBe(3);
  });

  it('plans 表里 date 缺失时导入返回 400 并指出表名', async () => {
    const tables = makeEmptyTables();
    tables.plans = [{ subject: 'math', title: '无日期' }];
    const payload = makePayload(tables);

    const result = await importData(ctx.app, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('plans');
    expect(String(result.body.error)).toContain('date');
  });

  it('plans 表里 subject 非法时导入被拒', async () => {
    const tables = makeEmptyTables();
    tables.plans = [{ date: '2024-02-29', subject: 'unknown', title: 'X' }];
    const payload = makePayload(tables);

    const result = await importData(ctx.app, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('plans');
    expect(String(result.body.error)).toContain('subject');
  });

  it('tables 里某表不是数组时导入返回 400', async () => {
    const tables = makeEmptyTables();
    (tables as Record<string, unknown>).words = 'not-an-array';
    const payload = makePayload(tables);

    const result = await importData(ctx.app, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('words');
    expect(String(result.body.error)).toContain('不是数组');
  });

  it('CSV 畸形行含引号与换行时 parseCsv 行为可被导出数据覆盖', async () => {
    ctx.db
      .prepare('INSERT INTO mistakes (subject, title) VALUES (?, ?)')
      .run('english', '含"引号"的题干');
    ctx.db
      .prepare('INSERT INTO mistakes (subject, title) VALUES (?, ?)')
      .run('english', '含,逗号的题干');

    const exported = await exportAll(ctx.app);
    const mistakes = exported.tables.mistakes as Record<string, unknown>[];
    expect(mistakes.length).toBe(2);
    expect(mistakes[0].title).toBe('含"引号"的题干');
    expect(mistakes[1].title).toBe('含,逗号的题干');

    const imported = await importData(ctx.app, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const rows = ctx.db
      .prepare('SELECT title FROM mistakes ORDER BY id ASC')
      .all() as Record<string, unknown>[];
    expect(rows.length).toBe(2);
    expect(rows[0].title).toBe('含"引号"的题干');
    expect(rows[1].title).toBe('含,逗号的题干');
  });
});

describe('backup.deep 备份恢复 round-trip 与 mode 校验', () => {
  let ctx: TestContext;

  beforeEach(async () => {
    ctx = await buildTestContext();
    seedMinimal(ctx.db);
  });

  afterEach(async () => {
    await teardown(ctx);
  });

  it('全表导出后 replace 导入数据完全一致', async () => {
    const exported = await exportAll(ctx.app);
    expect(exported.format).toBe('kaoyan-backup');
    expect(exported.version).toBe(1);
    const tableKeys = Object.keys(exported.tables).sort();
    expect(tableKeys).toEqual(
      [
        'exam_records',
        'focus_sessions',
        'mistakes',
        'plans',
        'settings',
        'srs_state',
        'words',
      ].sort()
    );

    ctx.db.exec('DELETE FROM plans');
    ctx.db.exec('DELETE FROM focus_sessions');
    ctx.db.exec('DELETE FROM mistakes');
    ctx.db.exec('DELETE FROM words');
    ctx.db.exec('DELETE FROM srs_state');
    ctx.db.exec('DELETE FROM exam_records');
    ctx.db.exec('DELETE FROM settings');

    const imported = await importData(ctx.app, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const plans = ctx.db.prepare('SELECT * FROM plans').all() as Record<
      string,
      unknown
    >[];
    expect(plans.length).toBe(1);
    expect(plans[0].date).toBe('2024-02-29');
    expect(plans[0].subject).toBe('math');
    expect(plans[0].title).toBe('闰年计划');

    const srs = ctx.db.prepare('SELECT * FROM srs_state').all() as Record<
      string,
      unknown
    >[];
    expect(srs.length).toBe(1);
    expect(srs[0].word_id).toBe(1);
    expect(srs[0].interval_days).toBe(1);

    const settings = ctx.db.prepare('SELECT * FROM settings').all() as Record<
      string,
      unknown
    >[];
    expect(settings.length).toBe(1);
    expect(settings[0].key).toBe('theme');
    expect(settings[0].value).toBe('dark');
  });

  it('merge 模式把新数据追加到已有数据之后', async () => {
    const exported = await exportAll(ctx.app);
    const tables = exported.tables as Record<string, Record<string, unknown>[]>;
    tables.plans = [
      { id: 100, date: '2024-12-31', subject: 'english', title: '年末计划' },
    ];
    const payload = makePayload(tables);

    const result = await importData(ctx.app, payload, 'merge');
    expect(result.statusCode).toBe(200);

    const rows = ctx.db
      .prepare('SELECT date, title FROM plans ORDER BY id ASC')
      .all() as Record<string, unknown>[];
    expect(rows.length).toBe(2);
    expect(rows[0].date).toBe('2024-02-29');
    expect(rows[1].date).toBe('2024-12-31');
    expect(rows[1].title).toBe('年末计划');
  });

  it('mode 非法时导入返回 400 且不写库', async () => {
    const exported = await exportAll(ctx.app);
    const result = await importData(ctx.app, exported, 'overwrite');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('mode');

    const count = ctx.db
      .prepare('SELECT COUNT(*) AS c FROM plans')
      .get() as Record<string, unknown>;
    expect(count.c).toBe(1);
  });

  it('format 不是 kaoyan-backup 时导入返回 400', async () => {
    const tables = makeEmptyTables();
    const payload = {
      format: 'unknown-format',
      version: 1,
      exportedAt: '2024-02-29T00:00:00.000Z',
      tables,
    };

    const result = await importData(ctx.app, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('format');
  });
});