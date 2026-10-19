import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb, todayStr } from '../src/db';
import { registerBackupRoutes } from '../src/routes/backup';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

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

function backupPayload(tables: Record<string, unknown[]>, mode: 'replace' | 'merge') {
  return {
    data: {
      format: 'kaoyan-backup',
      version: 1,
      tables,
    },
    mode,
  };
}

describe('POST /api/backup/import - merge/replace 纵深第二轮', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let authCookie = '';

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerBackupRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'backupmerge');
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  it('merge 同 id 不同文本：按文本去重，视为新词插入', async () => {
    db.prepare(
      "INSERT INTO words (user_id, id, word, meaning, source) VALUES ((SELECT id FROM users WHERE username = 'backupmerge'), ?, ?, ?, ?)"
    ).run(1, 'abandon', '原释义', 'manual');

    const tables = emptyTables();
    tables.words = [{ id: 1, word: 'abandon2', meaning: '新词释义' }];

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: backupPayload(tables, 'merge'),
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported.words).toBe(1);
    expect(body.skipped.words).toBe(0);

    const old = db
      .prepare('SELECT id, word, meaning FROM words WHERE word = ?')
      .get('abandon') as { id: number; word: string; meaning: string };
    expect(old).toBeDefined();
    expect(old.id).toBe(1);
    expect(old.meaning).toBe('原释义');

    const nw = db
      .prepare('SELECT id, word, meaning FROM words WHERE word = ?')
      .get('abandon2') as { id: number; word: string; meaning: string };
    expect(nw).toBeDefined();
    expect(nw.meaning).toBe('新词释义');
    expect(nw.id).not.toBe(1);
  });

  it('merge 同文本不同 id：本地赢', async () => {
    db.prepare(
      "INSERT INTO words (user_id, id, word, meaning, source) VALUES ((SELECT id FROM users WHERE username = 'backupmerge'), ?, ?, ?, ?)"
    ).run(1, 'abandon', '原释义', 'manual');

    const tables = emptyTables();
    tables.words = [{ id: 999, word: 'abandon', meaning: '新释义' }];

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: backupPayload(tables, 'merge'),
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.skipped.words).toBe(1);
    expect(body.imported.words).toBe(0);

    const row = db
      .prepare('SELECT meaning FROM words WHERE word = ?')
      .get('abandon') as { meaning: string };
    expect(row.meaning).toBe('原释义');

    const count = db.prepare('SELECT COUNT(*) AS c FROM words').get() as {
      c: number;
    };
    expect(count.c).toBe(1);
  });

  it('merge srs_state 同 word_id：备份赢（INSERT OR REPLACE）', async () => {
    db.prepare(
      "INSERT INTO words (user_id, id, word, meaning, source) VALUES ((SELECT id FROM users WHERE username = 'backupmerge'), ?, ?, ?, ?)"
    ).run(1, 'abandon', '原释义', 'manual');
    db.prepare(
      'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)'
    ).run(1, 2.5, 0, 0, todayStr());

    const tables = emptyTables();
    tables.srs_state = [
      {
        word_id: 1,
        ease: 1.3,
        interval_days: 9,
        repetitions: 4,
        due_date: '2024-01-01',
      },
    ];

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: backupPayload(tables, 'merge'),
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported.srs_state).toBe(1);

    const row = db
      .prepare(
        'SELECT ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?'
      )
      .get(1) as {
      ease: number;
      interval_days: number;
      repetitions: number;
      due_date: string;
    };
    expect(row.ease).toBeCloseTo(1.3, 10);
    expect(row.interval_days).toBe(9);
    expect(row.repetitions).toBe(4);
    expect(row.due_date).toBe('2024-01-01');
  });

  it('merge srs_state 指向不存在的 word_id → skipped', async () => {
    const tables = emptyTables();
    tables.srs_state = [
      {
        word_id: 999,
        ease: 1.3,
        interval_days: 1,
        repetitions: 1,
        due_date: '2024-01-01',
      },
    ];

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: backupPayload(tables, 'merge'),
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.skipped.srs_state).toBe(1);
    expect(body.imported.srs_state).toBe(0);
  });

  it('merge plans 同 id 本地赢、settings 同 key 备份赢', async () => {
    db.prepare(
      'INSERT INTO plans (user_id, id, date, subject, title, planned_minutes, done, created_at) VALUES ((SELECT id FROM users WHERE username = \'backupmerge\'), ?, ?, ?, ?, ?, ?, ?)'
    ).run(1, '2024-03-01', 'math', '原计划', 0, 0, '2024-03-01T00:00:00');
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES ((SELECT id FROM users WHERE username = \'backupmerge\'), ?, ?)').run(
      'theme',
      'light'
    );

    const tables = emptyTables();
    tables.plans = [
      { id: 1, date: '2024-01-01', subject: 'math', title: '备份计划' },
    ];
    tables.settings = [{ key: 'theme', value: 'dark' }];

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: backupPayload(tables, 'merge'),
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.skipped.plans).toBe(1);
    expect(body.imported.plans).toBe(0);

    const plan = db
      .prepare('SELECT title FROM plans WHERE id = ?')
      .get(1) as { title: string };
    expect(plan.title).toBe('原计划');

    expect(body.imported.settings).toBe(1);

    const setting = db
      .prepare('SELECT value FROM settings WHERE key = ?')
      .get('theme') as { value: string };
    expect(setting.value).toBe('dark');
  });

  it('replace 事务原子性：中途主键冲突 → 500 且原数据完整', async () => {
    db.prepare(
      'INSERT INTO plans (user_id, id, date, subject, title, planned_minutes, done, created_at) VALUES ((SELECT id FROM users WHERE username = \'backupmerge\'), ?, ?, ?, ?, ?, ?, ?)'
    ).run(1, '2024-03-01', 'math', '原计划', 0, 0, '2024-03-01T00:00:00');

    const tables = emptyTables();
    tables.plans = [
      { id: 5, date: '2024-02-01', subject: 'math', title: 'A' },
      { id: 5, date: '2024-02-02', subject: 'english', title: 'B' },
    ];

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: backupPayload(tables, 'replace'),
    });

    expect(res.statusCode).toBe(500);
    const body = res.json();
    expect(body.error).toBe('导入失败');

    const count = db.prepare('SELECT COUNT(*) AS c FROM plans').get() as {
      c: number;
    };
    expect(count.c).toBe(1);

    const plan = db
      .prepare('SELECT title FROM plans WHERE id = ?')
      .get(1) as { title: string };
    expect(plan.title).toBe('原计划');
  });

  it('merge 部分应用（无事务、逐行 try/catch）：同表内一行成功一行冲突', async () => {
    const tables = emptyTables();
    tables.focus_sessions = [
      {
        id: 7,
        subject: 'math',
        minutes: 30,
        started_at: '2024-03-01T10:00:00',
      },
      {
        id: 7,
        subject: 'english',
        minutes: 20,
        started_at: '2024-03-02T10:00:00',
      },
    ];

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: backupPayload(tables, 'merge'),
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported.focus_sessions).toBe(1);
    expect(body.skipped.focus_sessions).toBe(1);

    const count = db
      .prepare('SELECT COUNT(*) AS c FROM focus_sessions')
      .get() as { c: number };
    expect(count.c).toBe(1);

    const row = db
      .prepare('SELECT minutes FROM focus_sessions')
      .get() as { minutes: number };
    expect(row.minutes).toBe(30);
  });
});