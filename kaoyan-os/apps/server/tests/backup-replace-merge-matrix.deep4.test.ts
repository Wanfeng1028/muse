import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖 backup import 的 replace / merge 在预置旧数据下的语义矩阵；不与 backup.deep.test.ts（全表导出后 replace 导入完全一致）重叠。
describe('backup replace merge matrix deep4', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

  async function newUser(prefix: string): Promise<{ cookie: string; userId: number }> {
    const name = rand(prefix);
    const cookie = await registerAndLogin(app, name);
    const row = db.prepare('SELECT id FROM users WHERE username = ?').get(name) as { id: number };
    return { cookie, userId: row.id };
  }

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerBackupRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });

  afterEach(async () => {
    await app.close();
  });

  const baseTables = () => ({
    plans: [
      {
        id: 101,
        date: '2026-10-01',
        subject: 'math',
        title: 'P1',
        planned_minutes: 60,
        done: 0,
        created_at: '2026-10-01T00:00:00.000Z',
      },
    ],
    focus_sessions: [
      {
        id: 201,
        subject: 'math',
        minutes: 25,
        started_at: '2026-10-01T10:00:00.000Z',
        note: null,
      },
    ],
    mistakes: [
      {
        id: 301,
        subject: 'english',
        title: 'M1',
        content: 'c',
        analysis: 'a',
        mastered: 0,
        created_at: '2026-10-01T00:00:00.000Z',
      },
    ],
    words: [
      { id: 401, word: 'apple', phonetic: '', meaning: '苹果', example: '', source: 'manual' },
    ],
    srs_state: [
      { word_id: 401, ease: 2.5, interval_days: 3, repetitions: 2, due_date: '2026-10-20' },
    ],
    exam_records: [
      {
        id: 501,
        subject: 'math',
        paper: '真题',
        score: 100,
        total_score: 150,
        duration_minutes: 180,
        taken_at: '2026-10-01',
      },
    ],
    settings: [{ key: 'theme', value: 'dark' }],
  });

  const basePayload = (mode: 'replace' | 'merge') => ({
    data: {
      format: 'kaoyan-backup',
      version: 1,
      exportedAt: '2026-10-20T00:00:00.000Z',
      tables: baseTables(),
    },
    mode,
  });

  function seedLegacy(userId: number): void {
    db.prepare(
      'INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
    ).run(userId, '2026-09-01', 'math', '旧计划', 30, 0, '2026-09-01T00:00:00.000Z');
    db.prepare(
      'INSERT INTO words (user_id, word, phonetic, meaning, example, source) VALUES (?, ?, ?, ?, ?, ?)'
    ).run(userId, 'oldword', '', '旧词', '', 'manual');
  }

  it('replace 清空旧数据后逐行写入基准 payload', async () => {
    const { cookie, userId } = await newUser('rep');
    seedLegacy(userId);

    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: basePayload('replace'),
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.mode).toBe('replace');
    expect(body.imported).toEqual({
      plans: 1,
      focus_sessions: 1,
      mistakes: 1,
      words: 1,
      srs_state: 1,
      exam_records: 1,
      settings: 1,
    });
    expect(body.skipped).toEqual({
      plans: 0,
      focus_sessions: 0,
      mistakes: 0,
      words: 0,
      srs_state: 0,
      exam_records: 0,
      settings: 0,
    });

    const plans = db
      .prepare('SELECT title FROM plans WHERE user_id = ? ORDER BY id ASC')
      .all(userId) as { title: string }[];
    expect(plans.length).toBe(1);
    expect(plans[0].title).toBe('P1');

    const words = db
      .prepare('SELECT word FROM words WHERE user_id = ? ORDER BY id ASC')
      .all(userId) as { word: string }[];
    expect(words.length).toBe(1);
    expect(words[0].word).toBe('apple');
  });

  it('merge 保留旧数据并按基准 payload 追加', async () => {
    const { cookie, userId } = await newUser('mrg');
    seedLegacy(userId);

    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: basePayload('merge'),
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.mode).toBe('merge');
    expect(body.imported).toEqual({
      plans: 1,
      focus_sessions: 1,
      mistakes: 1,
      words: 1,
      srs_state: 0,
      exam_records: 1,
      settings: 1,
    });
    expect(body.skipped).toEqual({
      plans: 0,
      focus_sessions: 0,
      mistakes: 0,
      words: 0,
      srs_state: 1,
      exam_records: 0,
      settings: 0,
    });

    const plans = db
      .prepare('SELECT title FROM plans WHERE user_id = ? ORDER BY id ASC')
      .all(userId) as { title: string }[];
    expect(plans.length).toBe(2);
    expect(plans.map((p) => p.title).sort()).toEqual(['P1', '旧计划']);

    const words = db
      .prepare('SELECT word FROM words WHERE user_id = ? ORDER BY id ASC')
      .all(userId) as { word: string }[];
    expect(words.length).toBe(2);
    expect(words.map((w) => w.word).sort()).toEqual(['apple', 'oldword']);
  });
});
