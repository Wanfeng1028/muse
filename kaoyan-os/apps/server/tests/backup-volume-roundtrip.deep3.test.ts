import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { registerBackupRoutes } from '../src/routes/backup';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

interface Row {
  [key: string]: unknown;
}

interface ExportTables {
  plans: Row[];
  focus_sessions: Row[];
  mistakes: Row[];
  words: Row[];
  srs_state: Row[];
  exam_records: Row[];
  settings: Row[];
}

interface ExportBody {
  format: string;
  version: number;
  exportedAt: string;
  tables: ExportTables;
}

interface ImportedCounts {
  plans: number;
  focus_sessions: number;
  mistakes: number;
  words: number;
  srs_state: number;
  exam_records: number;
  settings: number;
}

interface ImportBody {
  mode: string;
  imported: ImportedCounts;
  skipped: ImportedCounts;
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

function tableCounts(tables: ExportTables): Record<keyof ExportTables, number> {
  return {
    plans: tables.plans.length,
    focus_sessions: tables.focus_sessions.length,
    mistakes: tables.mistakes.length,
    words: tables.words.length,
    srs_state: tables.srs_state.length,
    exam_records: tables.exam_records.length,
    settings: tables.settings.length,
  };
}

describe('backup volume roundtrip deep3', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let cookieA: string;
  let cookieB: string;
  let userIdA: number;
  let userIdB: number;
  let backupA: ExportBody;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerBackupRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    cookieA = await registerAndLogin(app, 'vola');
    cookieB = await registerAndLogin(app, 'volb');

    const rowA = db.prepare('SELECT id FROM users WHERE username = ?').get('vola') as
      | { id: number }
      | undefined;
    const rowB = db.prepare('SELECT id FROM users WHERE username = ?').get('volb') as
      | { id: number }
      | undefined;
    if (!rowA || !rowB) {
      throw new Error('seeded users missing');
    }
    userIdA = rowA.id;
    userIdB = rowB.id;

    seedLarge(db, userIdA);

    const exportRes = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieA },
    });
    if (exportRes.statusCode !== 200) {
      throw new Error(`seed export failed: ${exportRes.statusCode}`);
    }
    backupA = exportRes.json() as ExportBody;
  });

  afterEach(async () => {
    await app.close();
  });

  it('round-trips a large dataset from A to B with replace mode', async () => {
    const importRes = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data: backupA, mode: 'replace' },
    });
    expect(importRes.statusCode).toBe(200);
    const importBody = importRes.json() as ImportBody;
    expect(importBody.mode).toBe('replace');
    expect(importBody.imported.plans).toBe(300);
    expect(importBody.imported.focus_sessions).toBe(200);
    expect(importBody.imported.mistakes).toBe(100);
    expect(importBody.imported.words).toBe(200);
    expect(importBody.imported.srs_state).toBe(200);
    expect(importBody.imported.exam_records).toBe(100);
    expect(importBody.imported.settings).toBe(5);

    const exportBRes = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieB },
    });
    expect(exportBRes.statusCode).toBe(200);
    const backupB = exportBRes.json() as ExportBody;

    const countsA = tableCounts(backupA.tables);
    const countsB = tableCounts(backupB.tables);
    expect(countsB).toEqual(countsA);

    const plan299 = backupB.tables.plans.find((r) => r.title === 'vol-plan-299');
    expect(plan299).toBeDefined();
    expect(plan299!.subject).toBe('math');

    const word199 = backupB.tables.words.find((r) => r.word === 'vol-word-199');
    expect(word199).toBeDefined();
    const word199Id = word199!.id as number;

    const srsA = backupA.tables.srs_state.find((r) => r.word_id === word199Id);
    const srsB = backupB.tables.srs_state.find((r) => r.word_id === word199Id);
    expect(srsA).toBeDefined();
    expect(srsB).toBeDefined();
    expect(srsB!.ease as number).toBeCloseTo(srsA!.ease as number, 4);
    expect(srsB!.due_date).toBe(srsA!.due_date);
  });

  it('does not leak user_id in export payload', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieA },
    });
    expect(res.statusCode).toBe(200);
    const text = JSON.stringify(res.json());
    expect(text.includes('"user_id"')).toBe(false);
  });

  it('merge import on B is idempotent for row counts', async () => {
    const replaceRes = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data: backupA, mode: 'replace' },
    });
    expect(replaceRes.statusCode).toBe(200);

    const beforeRes = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieB },
    });
    expect(beforeRes.statusCode).toBe(200);
    const before = tableCounts((beforeRes.json() as ExportBody).tables);

    const mergeRes = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data: backupA, mode: 'merge' },
    });
    expect(mergeRes.statusCode).toBe(200);
    const mergeBody = mergeRes.json() as ImportBody;
    expect(mergeBody.mode).toBe('merge');
    expect(mergeBody.skipped.words).toBe(200);
    expect(mergeBody.skipped.plans).toBe(300);
    expect(mergeBody.skipped.focus_sessions).toBe(200);
    expect(mergeBody.skipped.mistakes).toBe(100);
    expect(mergeBody.skipped.exam_records).toBe(100);
    expect(mergeBody.skipped.settings).toBe(5);
    expect(mergeBody.imported.srs_state).toBe(200);

    const afterRes = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieB },
    });
    expect(afterRes.statusCode).toBe(200);
    const after = tableCounts((afterRes.json() as ExportBody).tables);
    expect(after).toEqual(before);
  });

  it('rejects invalid mode with 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data: backupA, mode: 'xxx' },
    });
    expect(res.statusCode).toBe(400);
    expect((res.json() as { error: string }).error).toBe('无效的 mode');
  });

  it('rejects wrong format and wrong version', async () => {
    const badFormat = {
      format: 'kaoyan-backup-v2',
      version: 1,
      exportedAt: backupA.exportedAt,
      tables: backupA.tables,
    };
    const formatRes = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data: badFormat, mode: 'replace' },
    });
    expect(formatRes.statusCode).toBe(400);
    expect((formatRes.json() as { error: string }).error).toBe('format 无效');

    const badVersion = {
      format: 'kaoyan-backup',
      version: 2,
      exportedAt: backupA.exportedAt,
      tables: backupA.tables,
    };
    const versionRes = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data: badVersion, mode: 'replace' },
    });
    expect(versionRes.statusCode).toBe(400);
    expect((versionRes.json() as { error: string }).error).toBe('version 无效');
  });

  it('rejects missing tables entry with 表 plans 不是数组', async () => {
    const tables = { ...backupA.tables } as Record<string, unknown>;
    delete tables.plans;
    const data = {
      format: 'kaoyan-backup',
      version: 1,
      exportedAt: backupA.exportedAt,
      tables,
    };
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data, mode: 'replace' },
    });
    expect(res.statusCode).toBe(400);
    expect((res.json() as { error: string }).error).toBe('表 plans 不是数组');
  });

  it('rejects invalid subject in plans row 3 with row-scoped error', async () => {
    const plans = backupA.tables.plans.map((r) => ({ ...r }));
    plans[2] = { ...plans[2], subject: 'badsubject' };
    const data = {
      format: 'kaoyan-backup',
      version: 1,
      exportedAt: backupA.exportedAt,
      tables: { ...backupA.tables, plans },
    };
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data, mode: 'replace' },
    });
    expect(res.statusCode).toBe(400);
    const err = (res.json() as { error: string }).error;
    expect(err).toContain('表 plans 第 3 行');
    expect(err).toContain('subject 无效');
  });

  it('B replace import does not affect A rows', async () => {
    const beforeARes = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieA },
    });
    expect(beforeARes.statusCode).toBe(200);
    const beforeA = tableCounts((beforeARes.json() as ExportBody).tables);

    const importRes = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie: cookieB },
      payload: { data: backupA, mode: 'replace' },
    });
    expect(importRes.statusCode).toBe(200);

    const afterARes = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: { cookie: cookieA },
    });
    expect(afterARes.statusCode).toBe(200);
    const afterA = tableCounts((afterARes.json() as ExportBody).tables);
    expect(afterA).toEqual(beforeA);
  });
});