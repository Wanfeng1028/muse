import './bcrypt-test-env';

import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { createDb } from '../src/db';
import { registerBackupRoutes } from '../src/routes/backup';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

interface BackupPayload {
  format: string;
  version: number;
  exportedAt: string;
  tables: {
    plans: unknown[];
    focus_sessions: unknown[];
    mistakes: unknown[];
    words: unknown[];
    srs_state: unknown[];
    exam_records: unknown[];
    settings: unknown[];
  };
}

interface TableCounts {
  plans: number;
  focus_sessions: number;
  mistakes: number;
  words: number;
  srs_state: number;
  exam_records: number;
  settings: number;
}

function seedLarge(db: DatabaseSync, userId: number): void {
  const insertPlan = db.prepare(
    'INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
  );
  for (let i = 0; i < 300; i += 1) {
    insertPlan.run(
      userId,
      `2025-01-${String((i % 28) + 1).padStart(2, '0')}`,
      'math',
      `vol-plan-${i}`,
      i,
      0,
      `2025-01-01T00:00:${String(i % 60).padStart(2, '0')}.000Z`
    );
  }

  const insertFocus = db.prepare(
    'INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note) VALUES (?, ?, ?, ?, ?)'
  );
  for (let i = 0; i < 200; i += 1) {
    insertFocus.run(
      userId,
      'english',
      i,
      `2025-02-01T00:00:${String(i % 60).padStart(2, '0')}.000Z`,
      `vol-focus-${i}`
    );
  }

  const insertMistake = db.prepare(
    'INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
  );
  for (let i = 0; i < 100; i += 1) {
    insertMistake.run(
      userId,
      'politics',
      `vol-mistake-${i}`,
      `content-${i}`,
      `analysis-${i}`,
      0,
      `2025-03-01T00:00:${String(i % 60).padStart(2, '0')}.000Z`
    );
  }

  const insertWord = db.prepare(
    'INSERT INTO words (user_id, word, phonetic, meaning, example, source) VALUES (?, ?, ?, ?, ?, ?)'
  );
  const insertSrs = db.prepare(
    'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)'
  );
  for (let i = 0; i < 200; i += 1) {
    const info = insertWord.run(
      userId,
      `vol-word-${i}`,
      `/f${i}/`,
      `meaning-${i}`,
      `example-${i}`,
      'manual'
    );
    const wordId = Number(info.lastInsertRowid);
    insertSrs.run(
      wordId,
      2.5 + (i % 10) * 0.1,
      i % 30,
      i % 5,
      `2025-04-${String((i % 28) + 1).padStart(2, '0')}`
    );
  }

  const insertExam = db.prepare(
    'INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
  );
  for (let i = 0; i < 100; i += 1) {
    insertExam.run(
      userId,
      'math',
      `vol-paper-${i}`,
      i,
      150,
      180,
      `2025-05-01T00:00:${String(i % 60).padStart(2, '0')}.000Z`
    );
  }

  const insertSetting = db.prepare(
    'INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)'
  );
  for (let i = 0; i < 5; i += 1) {
    insertSetting.run(userId, `vol-key-${i}`, `vol-value-${i}`);
  }
}

function tableCounts(db: DatabaseSync): TableCounts {
  const tables: (keyof TableCounts)[] = [
    'plans',
    'focus_sessions',
    'mistakes',
    'words',
    'srs_state',
    'exam_records',
    'settings',
  ];
  const out = {} as TableCounts;
  for (const t of tables) {
    const row = db.prepare(`SELECT COUNT(*) AS c FROM ${t}`).get() as { c: number };
    out[t] = row.c;
  }
  return out;
}

async function makeFreshApp(): Promise<{ app: FastifyInstance; db: DatabaseSync }> {
  const freshDb = createDb(':memory:');
  const freshApp = Fastify({ logger: false });
  registerBackupRoutes(freshApp, freshDb);
  applyAuthHook(freshApp, freshDb);
  registerAuthRoutes(freshApp, freshDb);
  await freshApp.ready();
  return { app: freshApp, db: freshDb };
}

describe('backup volume roundtrip (deep3)', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let userIdA: number;
  let userIdB: number;
  let cookieA: string;
  let cookieB: string;
  let backupA: BackupPayload;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerBackupRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();

    cookieA = await registerAndLogin(app, 'vola');
    cookieB = await registerAndLogin(app, 'volb');

    const rowA = db.prepare('SELECT id FROM users WHERE username = ?').get('vola') as {
      id: number;
    };
    const rowB = db.prepare('SELECT id FROM users WHERE username = ?').get('volb') as {
      id: number;
    };
    userIdA = rowA.id;
    userIdB = rowB.id;

    seedLarge(db, userIdA);

    const expRes = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieA },
    });
    if (expRes.statusCode !== 200) {
      throw new Error(`export failed: ${expRes.statusCode} ${expRes.body}`);
    }
    backupA = expRes.json() as BackupPayload;
  });

  afterEach(async () => {
    await app.close();
  });

  it('it1 大数据量 replace round-trip（新库恢复）', async () => {
    const { app: appB, db: freshDb } = await makeFreshApp();
    try {
      const freshCookie = await registerAndLogin(appB, 'freshb');

      const impRes = await appB.inject({
        method: 'POST',
        url: '/api/backup/import',
        headers: { cookie: freshCookie },
        payload: { data: backupA, mode: 'replace' },
      });
      expect(impRes.statusCode).toBe(200);
      const impBody = impRes.json();
      const imported = impBody.imported as Record<string, number>;
      expect(imported.plans).toBe(300);
      expect(imported.focus_sessions).toBe(200);
      expect(imported.mistakes).toBe(100);
      expect(imported.words).toBe(200);
      expect(imported.srs_state).toBe(200);
      expect(imported.exam_records).toBe(100);
      expect(imported.settings).toBe(5);

      const expRes2 = await appB.inject({
        method: 'GET',
        url: '/api/backup/export',
        headers: { cookie: freshCookie },
      });
      expect(expRes2.statusCode).toBe(200);
      const backupB = expRes2.json() as BackupPayload;
      expect(tableCounts(freshDb)).toEqual(tableCounts(db));

      const planRow = freshDb
        .prepare('SELECT id, title FROM plans WHERE title = ?')
        .get('vol-plan-299') as { id: number; title: string } | undefined;
      expect(planRow).toBeDefined();
      expect(planRow!.title).toBe('vol-plan-299');

      const wordRow = freshDb
        .prepare(
          'SELECT w.id AS id, w.word AS word, s.ease AS ease FROM words w JOIN srs_state s ON s.word_id = w.id WHERE w.word = ?',
        )
        .get('vol-word-199') as { id: number; word: string; ease: number } | undefined;
      expect(wordRow).toBeDefined();
      expect(wordRow!.word).toBe('vol-word-199');

      const srcSrs = backupA.tables.srs_state as Array<Record<string, unknown>>;
      const srcWords = backupA.tables.words as Array<Record<string, unknown>>;
      const srcWord = srcWords.find((w) => w.word === 'vol-word-199') as
        | Record<string, unknown>
        | undefined;
      expect(srcWord).toBeDefined();
      const srcSrsRow = srcSrs.find((s) => s.word_id === srcWord!.id) as
        | Record<string, unknown>
        | undefined;
      expect(srcSrsRow).toBeDefined();
      expect(wordRow!.ease).toBeCloseTo(srcSrsRow!.ease as number, 6);

      expect(backupB.tables.words.length).toBe(200);
    } finally {
      await appB.close();
    }
  });

  it('it2 export 响应不含 user_id（隐私）', async () => {
    const exportRes = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieA },
    });
    expect(exportRes.statusCode).toBe(200);
    expect(JSON.stringify(exportRes.json())).not.toContain('"user_id"');
  });

  it('it3 merge 幂等（行数不变）', async () => {
    const { app: appB, db: freshDb } = await makeFreshApp();
    try {
      const freshCookie = await registerAndLogin(appB, 'freshb');

      const replaceRes = await appB.inject({
        method: 'POST',
        url: '/api/backup/import',
        headers: { cookie: freshCookie },
        payload: { data: backupA, mode: 'replace' },
      });
      expect(replaceRes.statusCode).toBe(200);

      const exp1 = await appB.inject({
        method: 'GET',
        url: '/api/backup/export',
        headers: { cookie: freshCookie },
      });
      expect(exp1.statusCode).toBe(200);
      const counts1 = tableCounts(freshDb);

      const mergeRes = await appB.inject({
        method: 'POST',
        url: '/api/backup/import',
        headers: { cookie: freshCookie },
        payload: { data: backupA, mode: 'merge' },
      });
      expect(mergeRes.statusCode).toBe(200);

      const exp2 = await appB.inject({
        method: 'GET',
        url: '/api/backup/export',
        headers: { cookie: freshCookie },
      });
      expect(exp2.statusCode).toBe(200);
      const counts2 = tableCounts(freshDb);

      expect(counts2).toEqual(counts1);
    } finally {
      await appB.close();
    }
  });

  it('it4 merge 新增不存在的行', async () => {
    const { app: appB, db: freshDb } = await makeFreshApp();
    try {
      const freshCookie = await registerAndLogin(appB, 'freshb');

      const replaceRes = await appB.inject({
        method: 'POST',
        url: '/api/backup/import',
        headers: { cookie: freshCookie },
        payload: { data: backupA, mode: 'replace' },
      });
      expect(replaceRes.statusCode).toBe(200);

      const newPlan = {
        id: 99999,
        user_id: 0,
        date: '2025-09-09',
        subject: 'english',
        title: 'extra-plan',
        done: 0,
        created_at: new Date().toISOString(),
      };
      const payload = {
        format: 'kaoyan-backup',
        version: 1,
        exportedAt: new Date().toISOString(),
        tables: {
          plans: [newPlan],
          focus_sessions: [],
          mistakes: [],
          words: [],
          srs_state: [],
          exam_records: [],
          settings: [],
        },
      };

      const before = tableCounts(freshDb);
      const mergeRes = await appB.inject({
        method: 'POST',
        url: '/api/backup/import',
        headers: { cookie: freshCookie },
        payload: { data: payload, mode: 'merge' },
      });
      expect(mergeRes.statusCode).toBe(200);
      const after = tableCounts(freshDb);
      expect(after.plans).toBe(before.plans + 1);
      const inserted = freshDb
        .prepare('SELECT id, title FROM plans WHERE title = ?')
        .get('extra-plan') as { id: number; title: string } | undefined;
      expect(inserted).toBeDefined();
      expect(inserted!.title).toBe('extra-plan');
    } finally {
      await appB.close();
    }
  });

  it('it5 replace 后 export 的 payload 结构与原始一致', async () => {
    const { app: appB, db: freshDb } = await makeFreshApp();
    try {
      const freshCookie = await registerAndLogin(appB, 'freshb');

      const impRes = await appB.inject({
        method: 'POST',
        url: '/api/backup/import',
        headers: { cookie: freshCookie },
        payload: { data: backupA, mode: 'replace' },
      });
      expect(impRes.statusCode).toBe(200);

      const expRes = await appB.inject({
        method: 'GET',
        url: '/api/backup/export',
        headers: { cookie: freshCookie },
      });
      expect(expRes.statusCode).toBe(200);
      const backupB = expRes.json() as BackupPayload;

      expect(backupB.format).toBe('kaoyan-backup');
      expect(backupB.version).toBe(1);
      expect(typeof backupB.exportedAt).toBe('string');
      expect(backupB.tables.plans.length).toBe(backupA.tables.plans.length);
      expect(backupB.tables.focus_sessions.length).toBe(backupA.tables.focus_sessions.length);
      expect(backupB.tables.mistakes.length).toBe(backupA.tables.mistakes.length);
      expect(backupB.tables.words.length).toBe(backupA.tables.words.length);
      expect(backupB.tables.srs_state.length).toBe(backupA.tables.srs_state.length);
      expect(backupB.tables.exam_records.length).toBe(backupA.tables.exam_records.length);
      expect(backupB.tables.settings.length).toBe(backupA.tables.settings.length);

      expect(tableCounts(freshDb)).toEqual(tableCounts(db));
    } finally {
      await appB.close();
    }
  });

  it('it6 replace 时用户数据被完整覆盖（无残留）', async () => {
    const { app: appB, db: freshDb } = await makeFreshApp();
    try {
      const freshCookie = await registerAndLogin(appB, 'freshb');

      const strayIns = freshDb.prepare(
        'INSERT INTO plans (user_id, date, subject, title, done, created_at) VALUES (?, ?, ?, ?, 0, ?)',
      );
      const freshRow = freshDb.prepare('SELECT id FROM users WHERE username = ?').get('freshb') as {
        id: number;
      };
      strayIns.run(freshRow.id, '2025-12-31', 'stray', 'stray-plan', Date.now());

      const beforeCounts = tableCounts(freshDb);
      expect(beforeCounts.plans).toBe(1);

      const impRes = await appB.inject({
        method: 'POST',
        url: '/api/backup/import',
        headers: { cookie: freshCookie },
        payload: { data: backupA, mode: 'replace' },
      });
      expect(impRes.statusCode).toBe(200);

      const stray = freshDb
        .prepare('SELECT id FROM plans WHERE title = ?')
        .get('stray-plan') as { id: number } | undefined;
      expect(stray).toBeUndefined();

      const afterCounts = tableCounts(freshDb);
      expect(afterCounts.plans).toBe(300);
    } finally {
      await appB.close();
    }
  });

  it('it7 replace 校验七表 imported 计数', async () => {
    const { app: appB, db: freshDb } = await makeFreshApp();
    try {
      const freshCookie = await registerAndLogin(appB, 'freshb');

      const impRes = await appB.inject({
        method: 'POST',
        url: '/api/backup/import',
        headers: { cookie: freshCookie },
        payload: { data: backupA, mode: 'replace' },
      });
      expect(impRes.statusCode).toBe(200);
      const imported = impRes.json().imported as Record<string, number>;
      expect(imported.plans).toBe(backupA.tables.plans.length);
      expect(imported.focus_sessions).toBe(backupA.tables.focus_sessions.length);
      expect(imported.mistakes).toBe(backupA.tables.mistakes.length);
      expect(imported.words).toBe(backupA.tables.words.length);
      expect(imported.srs_state).toBe(backupA.tables.srs_state.length);
      expect(imported.exam_records).toBe(backupA.tables.exam_records.length);
      expect(imported.settings).toBe(backupA.tables.settings.length);

      const counts = tableCounts(freshDb);
      expect(counts.plans).toBe(backupA.tables.plans.length);
      expect(counts.focus_sessions).toBe(backupA.tables.focus_sessions.length);
      expect(counts.mistakes).toBe(backupA.tables.mistakes.length);
      expect(counts.words).toBe(backupA.tables.words.length);
      expect(counts.srs_state).toBe(backupA.tables.srs_state.length);
      expect(counts.exam_records).toBe(backupA.tables.exam_records.length);
      expect(counts.settings).toBe(backupA.tables.settings.length);
    } finally {
      await appB.close();
    }
  });

  it('it8 replace 只删当前用户的数据', async () => {
    const insPlan = db.prepare(
      'INSERT INTO plans (user_id, date, subject, title, done, created_at) VALUES (?, ?, ?, ?, 0, ?)',
    );
    const now = Date.now();
    insPlan.run(userIdA, '2025-05-01', 'math', 'vol-plan-0', now);
    insPlan.run(userIdA, '2025-05-02', 'math', 'vol-plan-1', now);
    insPlan.run(userIdA, '2025-05-03', 'math', 'vol-plan-2', now);
    insPlan.run(userIdB, '2025-05-04', 'math', 'b-old-plan-0', now);
    insPlan.run(userIdB, '2025-05-05', 'math', 'b-old-plan-1', now);

    const volbPlansBefore = db
      .prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?')
      .get(userIdB) as { c: number };
    expect(volbPlansBefore.c).toBe(2);
    const volaPlansBefore = db
      .prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?')
      .get(userIdA) as { c: number };

    const payload = {
      format: 'kaoyan-backup',
      version: 1,
      exportedAt: new Date().toISOString(),
      tables: {
        plans: [{ date: '2025-06-01', subject: 'math', title: 'b-new-plan' }],
        focus_sessions: [],
        mistakes: [],
        words: [],
        srs_state: [],
        exam_records: [],
        settings: [],
      },
    };

    const impRes = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data: payload, mode: 'replace' },
    });
    expect(impRes.statusCode).toBe(200);

    const volbPlans = db
      .prepare('SELECT title FROM plans WHERE user_id = ? ORDER BY title')
      .all(userIdB) as Array<{ title: string }>;
    expect(volbPlans.length).toBe(1);
    expect(volbPlans[0].title).toBe('b-new-plan');

    const volaPlansAfter = db
      .prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?')
      .get(userIdA) as { c: number };
    expect(volaPlansAfter.c).toBe(volaPlansBefore.c);
    const volaHasSeed = db
      .prepare("SELECT COUNT(*) AS c FROM plans WHERE user_id = ? AND title = 'vol-plan-299'")
      .get(userIdA) as { c: number };
    expect(volaHasSeed.c).toBe(1);
  });
});
