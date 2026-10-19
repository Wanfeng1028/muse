import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify from 'fastify';
import type { FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

const TEST_USER = 'backupdeep';

interface TestContext {
  app: FastifyInstance;
  db: DatabaseSync;
  authCookie: string;
}

function seedMinimal(db: DatabaseSync): void {
  db.prepare("INSERT INTO plans (user_id, date, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?, ?)").run(
    '2024-02-29',
    'math',
    '闰年计划'
  );
  db.prepare(
    "INSERT INTO focus_sessions (user_id, subject, started_at) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)"
  ).run('math', '2024-02-29T08:00:00.000Z');
  db.prepare("INSERT INTO mistakes (user_id, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)").run(
    'math',
    '错题题干一'
  );
  db.prepare("INSERT INTO words (user_id, word, meaning) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)").run(
    'abandon',
    '放弃'
  );
  db.prepare(
    'INSERT INTO srs_state (word_id, due_date, interval_days) VALUES (?, ?, ?)'
  ).run(1, '2024-03-01T00:00:00.000Z', 1);
  db.prepare(
    "INSERT INTO exam_records (user_id, subject, paper, taken_at) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?, ?)"
  ).run('math', '2024考研数学一', '2024-02-29T00:00:00.000Z');
  db.prepare("INSERT INTO settings (user_id, key, value) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)").run(
    'theme',
    'dark'
  );
}

async function buildTestContext(): Promise<TestContext> {
  const db = createDb(':memory:');
  const app = Fastify();
  registerBackupRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  const authCookie = await registerAndLogin(app, TEST_USER);
  return { app, db, authCookie };
}


async function teardown(ctx: TestContext): Promise<void> {
  await ctx.app.close();
  ctx.db.close();
}

async function exportAll(ctx: TestContext): Promise<{
  format: string;
  version: number;
  tables: Record<string, Record<string, unknown>[]>;
}> {
  const res = await ctx.app.inject({ method: 'GET', url: '/api/backup/export', headers: { cookie: ctx.authCookie } });
  expect(res.statusCode).toBe(200);
  return res.json();
}

async function importData(
  ctx: TestContext,
  data: unknown,
  mode?: string
): Promise<{ statusCode: number; body: Record<string, unknown> }> {
  const body: Record<string, unknown> = { data };
  if (mode !== undefined) {
    body.mode = mode;
  }
  const res = await ctx.app.inject({
    method: 'POST',
    url: '/api/backup/import',
    payload: body,
    headers: { cookie: ctx.authCookie },
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
      .prepare("INSERT INTO plans (user_id, date, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?, ?)")
      .run('2024-02-29', 'math', '闰年计划');
    ctx.db
      .prepare("INSERT INTO plans (user_id, date, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?, ?)")
      .run('2024-03-01', 'english', '跨月计划');

    const exported = await exportAll(ctx);

    const plans = exported.tables.plans as Record<string, unknown>[];
    expect(plans.length).toBe(2);
    expect(plans[0].date).toBe('2024-02-29');
    expect(plans[0].subject).toBe('math');
    expect(plans[1].date).toBe('2024-03-01');
    expect(plans[1].subject).toBe('english');

    const imported = await importData(ctx, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const rows = ctx.db
      .prepare("SELECT date, subject, title FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep') ORDER BY id ASC")
      .all() as Record<string, unknown>[];
    expect(rows.length).toBe(2);

    expect(rows[0].date).toBe('2024-02-29');
    expect(rows[1].date).toBe('2024-03-01');
  });

  it('空计划表导入导出 round-trip 不产生额外行', async () => {
    const exported = await exportAll(ctx);
    const plans = exported.tables.plans as Record<string, unknown>[];
    expect(plans.length).toBe(0);

    const imported = await importData(ctx, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const rows = ctx.db.prepare("SELECT * FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')").all() as Record<

      string,
      unknown
    >[];
    expect(rows.length).toBe(0);
  });

  it('跨月计划：2 月 29 与 3 月 1 同时保留且顺序按 id', async () => {
    ctx.db
      .prepare("INSERT INTO plans (user_id, date, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?, ?)")
      .run('2024-02-29', 'math', 'A');
    ctx.db
      .prepare("INSERT INTO plans (user_id, date, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?, ?)")
      .run('2024-03-01', 'math', 'B');

    const exported = await exportAll(ctx);
    const plans = exported.tables.plans as Record<string, unknown>[];
    const dates = plans.map((p) => p.date);
    expect(dates).toEqual(['2024-02-29', '2024-03-01']);

    const imported = await importData(ctx, exported, 'merge');
    expect(imported.statusCode).toBe(200);

    const count = ctx.db
      .prepare("SELECT COUNT(*) AS c FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')")
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
        "INSERT INTO focus_sessions (user_id, subject, started_at) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)"
      )
      .run('math', '2024-02-29T23:59:59.999Z');

    const exported = await exportAll(ctx);
    const sessions = exported.tables.focus_sessions as Record<string, unknown>[];
    expect(sessions.length).toBe(1);
    expect(sessions[0].started_at).toBe('2024-02-29T23:59:59.999Z');

    const imported = await importData(ctx, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const row = ctx.db
      .prepare("SELECT subject, started_at FROM focus_sessions WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')")
      .get() as Record<string, unknown>;

    expect(row.subject).toBe('math');
    expect(row.started_at).toBe('2024-02-29T23:59:59.999Z');
  });

  it('重复错题按 id 保留全部行，去重交给上层不做隐式合并', async () => {
    ctx.db
      .prepare("INSERT INTO mistakes (user_id, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)")
      .run('math', '同一题干');
    ctx.db
      .prepare("INSERT INTO mistakes (user_id, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)")
      .run('math', '同一题干');

    const exported = await exportAll(ctx);
    const mistakes = exported.tables.mistakes as Record<string, unknown>[];
    expect(mistakes.length).toBe(2);
    expect(mistakes[0].title).toBe('同一题干');
    expect(mistakes[1].title).toBe('同一题干');

    const imported = await importData(ctx, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const count = ctx.db
      .prepare("SELECT COUNT(*) AS c FROM mistakes WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')")
      .get() as Record<string, unknown>;

    expect(count.c).toBe(2);
  });

  it('focus_sessions 缺 started_at 时导入被拒', async () => {
    const tables = makeEmptyTables();
    tables.focus_sessions = [{ subject: 'math' }];
    const payload = makePayload(tables);

    const result = await importData(ctx, payload, 'replace');
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
      .prepare("INSERT INTO words (user_id, word, meaning) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)")
      .run('apple', '苹果');
    ctx.db
      .prepare("INSERT INTO words (user_id, word, meaning) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)")
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

    const exported = await exportAll(ctx);
    const srs = exported.tables.srs_state as Record<string, unknown>[];
    expect(srs.length).toBe(2);
    expect(srs[0].interval_days).toBe(3);
    expect(srs[1].interval_days).toBe(7);

    const imported = await importData(ctx, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const row = ctx.db
      .prepare("SELECT interval_days FROM srs_state WHERE word_id IN (SELECT id FROM words WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep') AND word = 'apple')")
      .get() as Record<string, unknown>;

    expect(row.interval_days).toBe(3);
  });

  it('plans 表里 date 缺失时导入返回 400 并指出表名', async () => {
    const tables = makeEmptyTables();
    tables.plans = [{ subject: 'math', title: '无日期' }];
    const payload = makePayload(tables);

    const result = await importData(ctx, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('plans');
    expect(String(result.body.error)).toContain('date');

  });

  it('plans 表里 subject 非法时导入被拒', async () => {
    const tables = makeEmptyTables();
    tables.plans = [{ date: '2024-02-29', subject: 'unknown', title: 'X' }];
    const payload = makePayload(tables);

    const result = await importData(ctx, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('plans');
    expect(String(result.body.error)).toContain('subject');

  });

  it('tables 里某表不是数组时导入返回 400', async () => {
    const tables = makeEmptyTables();
    (tables as Record<string, unknown>).words = 'not-an-array';
    const payload = makePayload(tables);

    const result = await importData(ctx, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('words');

    expect(String(result.body.error)).toContain('不是数组');
  });

  it('CSV 畸形行含引号与换行时 parseCsv 行为可被导出数据覆盖', async () => {
    ctx.db
      .prepare("INSERT INTO mistakes (user_id, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)")
      .run('english', '含"引号"的题干');
    ctx.db
      .prepare("INSERT INTO mistakes (user_id, subject, title) VALUES ((SELECT id FROM users WHERE username = 'backupdeep'), ?, ?)")
      .run('english', '含,逗号的题干');

    const exported = await exportAll(ctx);
    const mistakes = exported.tables.mistakes as Record<string, unknown>[];
    expect(mistakes.length).toBe(2);
    expect(mistakes[0].title).toBe('含"引号"的题干');
    expect(mistakes[1].title).toBe('含,逗号的题干');

    const imported = await importData(ctx, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const rows = ctx.db
      .prepare("SELECT title FROM mistakes WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep') ORDER BY id ASC")
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
    const exported = await exportAll(ctx);
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

    ctx.db.exec("DELETE FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')");
    ctx.db.exec("DELETE FROM focus_sessions WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')");
    ctx.db.exec("DELETE FROM mistakes WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')");
    ctx.db.exec("DELETE FROM srs_state WHERE word_id IN (SELECT id FROM words WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep'))");
    ctx.db.exec("DELETE FROM words WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')");
    ctx.db.exec("DELETE FROM exam_records WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')");
    ctx.db.exec("DELETE FROM settings WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')");

    const imported = await importData(ctx, exported, 'replace');
    expect(imported.statusCode).toBe(200);

    const plans = ctx.db.prepare("SELECT * FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')").all() as Record<

      string,
      unknown
    >[];
    expect(plans.length).toBe(1);
    expect(plans[0].date).toBe('2024-02-29');
    expect(plans[0].subject).toBe('math');
    expect(plans[0].title).toBe('闰年计划');

    const srs = ctx.db.prepare("SELECT * FROM srs_state WHERE word_id IN (SELECT id FROM words WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep'))").all() as Record<
      string,
      unknown
    >[];
    expect(srs.length).toBe(1);
    expect(srs[0].interval_days).toBe(1);

    const settings = ctx.db.prepare("SELECT * FROM settings WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')").all() as Record<

      string,
      unknown
    >[];
    expect(settings.length).toBe(1);
    expect(settings[0].key).toBe('theme');
    expect(settings[0].value).toBe('dark');
  });

  it('merge 模式把新数据追加到已有数据之后', async () => {
    const exported = await exportAll(ctx);
    const tables = exported.tables as Record<string, Record<string, unknown>[]>;
    tables.plans = [
      { id: 100, date: '2024-12-31', subject: 'english', title: '年末计划' },
    ];
    const payload = makePayload(tables);

    const result = await importData(ctx, payload, 'merge');
    expect(result.statusCode).toBe(200);

    const rows = ctx.db
      .prepare("SELECT date, title FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep') ORDER BY id ASC")
      .all() as Record<string, unknown>[];
    expect(rows.length).toBe(2);

    expect(rows[0].date).toBe('2024-02-29');
    expect(rows[1].date).toBe('2024-12-31');
    expect(rows[1].title).toBe('年末计划');
  });

  it('mode 非法时导入返回 400 且不写库', async () => {
    const exported = await exportAll(ctx);
    const result = await importData(ctx, exported, 'overwrite');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('mode');

    const count = ctx.db
      .prepare("SELECT COUNT(*) AS c FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'backupdeep')")
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

    const result = await importData(ctx, payload, 'replace');
    expect(result.statusCode).toBe(400);
    expect(String(result.body.error)).toContain('format');

  });
});