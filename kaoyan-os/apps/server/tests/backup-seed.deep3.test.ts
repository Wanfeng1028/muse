import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb, todayStr, addDays } from '../src/db';
import { registerBackupRoutes } from '../src/routes/backup';
import { seedIfEmpty } from '../src/seed';

function emptyTables(): Record<string, unknown[]> {
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

function makePayload(tables: Record<string, unknown[]>, mode?: 'replace' | 'merge') {
  const data = {
    format: 'kaoyan-backup',
    version: 1,
    exportedAt: new Date().toISOString(),
    tables,
  };
  return mode === undefined ? { data } : { data, mode };
}

async function doExport(app: FastifyInstance) {
  const res = await app.inject({ method: 'GET', url: '/api/backup/export' });
  return { statusCode: res.statusCode, body: res.json() as any };
}

async function doImport(app: FastifyInstance, payload: unknown) {
  const res = await app.inject({
    method: 'POST',
    url: '/api/backup/import',
    payload,
  });
  return { statusCode: res.statusCode, body: res.json() as any };
}

function countOf(db: DatabaseSync, table: string): number {
  const r = db.prepare(`SELECT COUNT(*) AS c FROM ${table}`).get() as { c: number };
  return r.c;
}

describe('backup + seed 纵深测试（第三轮）', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerBackupRoutes(app, db);
    await app.ready();
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  it('1. export 结构：format/version/exportedAt 合法且含全部 7 张表；seedIfEmpty 后行数符合播种量', async () => {
    seedIfEmpty(db);
    const { statusCode, body } = await doExport(app);
    expect(statusCode).toBe(200);
    expect(body.format).toBe('kaoyan-backup');
    expect(body.version).toBe(1);
    expect(typeof body.exportedAt).toBe('string');
    expect(Number.isFinite(Date.parse(body.exportedAt))).toBe(true);

    const tables = body.tables as Record<string, unknown[]>;
    const names = [
      'plans',
      'focus_sessions',
      'mistakes',
      'words',
      'srs_state',
      'exam_records',
      'settings',
    ];
    for (const n of names) {
      expect(Array.isArray(tables[n])).toBe(true);
    }
    expect(Object.keys(tables).sort()).toEqual([...names].sort());

    expect(tables.words.length).toBe(24);
    expect(tables.srs_state.length).toBe(24);
    expect(tables.plans.length).toBe(6);
    expect(tables.mistakes.length).toBe(3);
    expect(tables.exam_records.length).toBe(2);
    expect(tables.focus_sessions.length).toBe(8);
    expect(tables.settings.length).toBe(4);
  });

  it('2. export→import replace 全量 round-trip：新库 7 表行数一致且 srs_state 字段逐字段相等', async () => {
    seedIfEmpty(db);
    const { body: exported } = await doExport(app);

    const dbB = createDb(':memory:');
    const appB = Fastify({ logger: false });
    registerBackupRoutes(appB, dbB);
    await appB.ready();
    try {
      const res = await doImport(appB, makePayload(exported.tables));
      expect(res.statusCode).toBe(200);
      expect(res.body.mode).toBe('replace');

      for (const t of [
        'plans',
        'focus_sessions',
        'mistakes',
        'words',
        'srs_state',
        'exam_records',
        'settings',
      ]) {
        expect(countOf(dbB, t)).toBe(countOf(db, t));
      }

      const wordRow = db.prepare("SELECT id FROM words WHERE word = 'abandon'").get() as {
        id: number;
      };
      const aSrs = db
        .prepare(
          'SELECT word_id, ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?'
        )
        .get(wordRow.id) as any;
      const bSrs = dbB
        .prepare(
          'SELECT word_id, ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?'
        )
        .get(wordRow.id) as any;
      expect(bSrs).toEqual(aSrs);
      expect(bSrs.ease).toBe(2.5);
      expect(bSrs.interval_days).toBe(0);
      expect(bSrs.repetitions).toBe(0);
      expect(bSrs.due_date).toBe(todayStr());
    } finally {
      await appB.close();
      dbB.close();
    }
  });

  it('3. replace 清空语义：本地已有计划在 import 不含该计划的备份后消失，imported.plans 等于备份行数', async () => {
    // 本测试 app 只注册了 backup 路由，直接插 DB 造本地计划
    db.prepare(
      'INSERT INTO plans (date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run(todayStr(), 'math', '本地计划X', 30, 0, new Date().toISOString());
    expect(countOf(db, 'plans')).toBe(1);


    const backupPlan = {
      id: 999,
      date: todayStr(),
      subject: 'english',
      title: '备份计划Y',
      planned_minutes: 60,
      done: 0,
      created_at: new Date().toISOString(),
    };
    const tables = emptyTables();
    tables.plans = [backupPlan];

    const { statusCode, body } = await doImport(app, makePayload(tables, 'replace'));
    expect(statusCode).toBe(200);
    expect(body.mode).toBe('replace');
    expect(body.imported.plans).toBe(1);

    const rows = db.prepare('SELECT title FROM plans').all() as Array<{ title: string }>;
    expect(rows.length).toBe(1);
    expect(rows[0].title).toBe('备份计划Y');
    const gone = db
      .prepare("SELECT COUNT(*) AS c FROM plans WHERE title = '本地计划X'")
      .get() as { c: number };
    expect(gone.c).toBe(0);
  });

  it('4. merge words 按 word 去重：已存在词 skipped 且释义不变，新词 imported', async () => {
    seedIfEmpty(db);
    const before = db.prepare("SELECT meaning FROM words WHERE word = 'abandon'").get() as {
      meaning: string;
    };

    const tables = emptyTables();
    tables.words = [
      {
        id: 1,
        word: 'abandon',
        phonetic: '/x/',
        meaning: '被改写的释义',
        example: 'e',
        source: 'manual',
      },
      {
        id: 2,
        word: 'zzznew',
        phonetic: '/z/',
        meaning: '新词释义',
        example: 'ex',
        source: 'manual',
      },
    ];

    const { statusCode, body } = await doImport(app, makePayload(tables, 'merge'));
    expect(statusCode).toBe(200);
    expect(body.mode).toBe('merge');
    expect(body.skipped.words).toBe(1);
    expect(body.imported.words).toBe(1);

    const after = db.prepare("SELECT meaning FROM words WHERE word = 'abandon'").get() as {
      meaning: string;
    };
    expect(after.meaning).toBe(before.meaning);
    expect(after.meaning).toBe('抛弃；放弃');

    const newRow = db.prepare("SELECT meaning FROM words WHERE word = 'zzznew'").get() as {
      meaning: string;
    };
    expect(newRow.meaning).toBe('新词释义');
  });

  it('5. merge srs_state 悬空引用：word_id 不存在 skipped，存在则 upsert 覆盖 ease', async () => {
    seedIfEmpty(db);
    const wordRow = db.prepare("SELECT id FROM words WHERE word = 'abandon'").get() as {
      id: number;
    };
    const beforeSrs = db
      .prepare('SELECT ease FROM srs_state WHERE word_id = ?')
      .get(wordRow.id) as { ease: number };
    expect(beforeSrs.ease).toBe(2.5);

    const tables = emptyTables();
    tables.srs_state = [
      { word_id: 999999, ease: 1.1, interval_days: 5, repetitions: 3, due_date: '2099-01-01' },
      { word_id: wordRow.id, ease: 3.0, interval_days: 7, repetitions: 2, due_date: '2099-02-02' },
    ];

    const { statusCode, body } = await doImport(app, makePayload(tables, 'merge'));
    expect(statusCode).toBe(200);
    expect(body.skipped.srs_state).toBe(1);
    expect(body.imported.srs_state).toBe(1);

    const afterSrs = db
      .prepare(
        'SELECT ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?'
      )
      .get(wordRow.id) as any;
    expect(afterSrs.ease).toBe(3.0);
    expect(afterSrs.interval_days).toBe(7);
    expect(afterSrs.repetitions).toBe(2);
    expect(afterSrs.due_date).toBe('2099-02-02');

    const dangling = db
      .prepare('SELECT COUNT(*) AS c FROM srs_state WHERE word_id = 999999')
      .get() as { c: number };
    expect(dangling.c).toBe(0);
  });

  it('6. merge settings upsert：同 key 不同 value 被覆盖且 imported.settings 计数', async () => {
    seedIfEmpty(db);
    const before = db
      .prepare("SELECT value FROM settings WHERE key = 'exam_date'")
      .get() as { value: string };
    expect(before.value).not.toBe('2099-12-31');

    const tables = emptyTables();
    tables.settings = [{ key: 'exam_date', value: '2099-12-31' }];

    const { statusCode, body } = await doImport(app, makePayload(tables, 'merge'));
    expect(statusCode).toBe(200);
    expect(body.imported.settings).toBe(1);
    expect(body.skipped.settings).toBe(0);

    const after = db
      .prepare("SELECT value FROM settings WHERE key = 'exam_date'")
      .get() as { value: string };
    expect(after.value).toBe('2099-12-31');

    const total = countOf(db, 'settings');
    expect(total).toBe(4);
  });

  it('7. merge 主键冲突转 skipped：同 id 的 plans 行被跳过，库中原 title 不变', async () => {
    const created = db
      .prepare(
        'INSERT INTO plans (date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, ?)'
      )
      .run(todayStr(), 'math', '本地原计划', 45, 0, new Date().toISOString());
    const localId = Number(created.lastInsertRowid);

    const tables = emptyTables();
    tables.plans = [
      {
        id: localId,
        date: todayStr(),
        subject: 'english',
        title: '备份冲突计划',
        planned_minutes: 90,
        done: 1,
        created_at: new Date().toISOString(),
      },
    ];

    const { statusCode, body } = await doImport(app, makePayload(tables, 'merge'));
    expect(statusCode).toBe(200);
    expect(body.skipped.plans).toBe(1);
    expect(body.imported.plans).toBe(0);

    const row = db.prepare('SELECT title FROM plans WHERE id = ?').get(localId) as {
      title: string;
    };
    expect(row.title).toBe('本地原计划');
    expect(countOf(db, 'plans')).toBe(1);
  });

  it('8. import 行级校验：mode/version/tables/行类型/subject 枚举 全部 400 且错误语义正确', async () => {
    const badMode = await doImport(app, { data: makePayload(emptyTables()).data, mode: 'xxx' });
    expect(badMode.statusCode).toBe(400);
    expect(badMode.body.error).toBe('无效的 mode');

    const badVersion = await doImport(app, {
      data: { format: 'kaoyan-backup', version: 2, exportedAt: new Date().toISOString(), tables: emptyTables() },
    });
    expect(badVersion.statusCode).toBe(400);
    expect(badVersion.body.error).toBe('version 无效');

    const tablesNoWords = emptyTables();
    delete (tablesNoWords as Record<string, unknown>).words;
    const missing = await doImport(app, makePayload(tablesNoWords));
    expect(missing.statusCode).toBe(400);
    expect(String(missing.body.error)).toContain('words');

    const tablesBadRow = emptyTables();
    tablesBadRow.words = [{ word: 'ok', meaning: 'ok' }, 123];
    const badRow = await doImport(app, makePayload(tablesBadRow));
    expect(badRow.statusCode).toBe(400);
    expect(String(badRow.body.error)).toContain('第 2 行');

    const tablesBadSubject = emptyTables();
    tablesBadSubject.focus_sessions = [
      { subject: 'art', minutes: 30, started_at: `${todayStr()}T09:00:00`, note: 'n' },
    ];
    const badSubject = await doImport(app, makePayload(tablesBadSubject));
    expect(badSubject.statusCode).toBe(400);
    expect(String(badSubject.body.error)).toContain('focus_sessions');
  });

  it('9. seedIfEmpty 幂等：连续两次调用 7 表行数不变', async () => {
    seedIfEmpty(db);
    const snap1: Record<string, number> = {};
    for (const t of [
      'plans',
      'focus_sessions',
      'mistakes',
      'words',
      'srs_state',
      'exam_records',
      'settings',
    ]) {
      snap1[t] = countOf(db, t);
    }
    seedIfEmpty(db);
    for (const t of Object.keys(snap1)) {
      expect(countOf(db, t)).toBe(snap1[t]);
    }
    expect(countOf(db, 'words')).toBe(24);
    expect(countOf(db, 'settings')).toBe(4);
    expect(countOf(db, 'plans')).toBe(6);
    expect(countOf(db, 'mistakes')).toBe(3);
    expect(countOf(db, 'exam_records')).toBe(2);
    expect(countOf(db, 'focus_sessions')).toBe(8);
    expect(countOf(db, 'srs_state')).toBe(24);
  });

  it('10. seedIfEmpty 不覆盖非空表：exam_date 保持覆盖值，各表独立判断', async () => {
    seedIfEmpty(db);
    db.prepare("UPDATE settings SET value = '2099-01-01' WHERE key = 'exam_date'").run();

    seedIfEmpty(db);
    const after = db
      .prepare("SELECT value FROM settings WHERE key = 'exam_date'")
      .get() as { value: string };
    expect(after.value).toBe('2099-01-01');
    expect(countOf(db, 'settings')).toBe(4);

    const db2 = createDb(':memory:');
    db2
      .prepare(
        'INSERT INTO words (word, phonetic, meaning, example, source) VALUES (?, ?, ?, ?, ?)'
      )
      .run('onlyone', '/o/', 'm', 'e', 'manual');
    expect(countOf(db2, 'settings')).toBe(0);
    seedIfEmpty(db2);
    expect(countOf(db2, 'settings')).toBe(4);
    expect(countOf(db2, 'words')).toBe(1);
    expect(countOf(db2, 'srs_state')).toBe(0);
    expect(countOf(db2, 'plans')).toBe(6);
    db2.close();
  });

  it('11. seed 内容精确：abandon 的 srs 初始值正确，今天 focus_sessions 恰好 2 条', async () => {
    seedIfEmpty(db);

    const wordRow = db
      .prepare("SELECT id, phonetic, meaning, source FROM words WHERE word = 'abandon'")
      .get() as any;
    expect(wordRow).toBeTruthy();
    expect(wordRow.source).toBe('builtin');
    expect(wordRow.meaning).toBe('抛弃；放弃');

    const srs = db
      .prepare(
        'SELECT ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?'
      )
      .get(wordRow.id) as any;
    expect(srs.ease).toBe(2.5);
    expect(srs.interval_days).toBe(0);
    expect(srs.repetitions).toBe(0);
    expect(srs.due_date).toBe(todayStr());

    const today = todayStr();
    const todayFocus = db
      .prepare("SELECT COUNT(*) AS c FROM focus_sessions WHERE started_at LIKE ?")
      .get(`${today}%`) as { c: number };
    expect(todayFocus.c).toBe(2);

    const yesterday = addDays(today, -1);
    const yesterdayFocus = db
      .prepare("SELECT COUNT(*) AS c FROM focus_sessions WHERE started_at LIKE ?")
      .get(`${yesterday}%`) as { c: number };
    expect(yesterdayFocus.c).toBe(1);
  });

  it('12. 空库 export→import：各表为空数组，replace 导入到新库 imported 全 0', async () => {
    const { statusCode, body } = await doExport(app);
    expect(statusCode).toBe(200);
    const tables = body.tables as Record<string, unknown[]>;
    for (const t of [
      'plans',
      'focus_sessions',
      'mistakes',
      'words',
      'srs_state',
      'exam_records',
      'settings',
    ]) {
      expect(Array.isArray(tables[t])).toBe(true);
      expect(tables[t].length).toBe(0);
    }

    const dbB = createDb(':memory:');
    const appB = Fastify({ logger: false });
    registerBackupRoutes(appB, dbB);
    await appB.ready();
    try {
      const res = await doImport(appB, makePayload(tables, 'replace'));
      expect(res.statusCode).toBe(200);
      expect(res.body.mode).toBe('replace');
      for (const t of [
        'plans',
        'focus_sessions',
        'mistakes',
        'words',
        'srs_state',
        'exam_records',
        'settings',
      ]) {
        expect(res.body.imported[t]).toBe(0);
        expect(res.body.skipped[t]).toBe(0);
      }
    } finally {
      await appB.close();
      dbB.close();
    }
  });
});
