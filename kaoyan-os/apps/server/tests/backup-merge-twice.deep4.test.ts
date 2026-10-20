import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('backup merge twice skipped matrix deep4', () => {
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
  afterEach(async () => { await app.close(); });

  const basePayload = () => ({
    mode: 'merge',
    data: {
      format: 'kaoyan-backup',
      version: 1,
      exportedAt: '2024-01-01T00:00:00.000Z',
      tables: {
        plans: [
          { id: 101, date: '2024-05-01', subject: 'math', title: 'pl', planned_minutes: 30, done: 0, created_at: '2024-05-01T00:00:00.000Z' },
        ],
        focus_sessions: [
          { id: 201, subject: 'english', minutes: 25, started_at: '2024-05-01T08:00:00.000Z', note: null },
        ],
        mistakes: [
          { id: 301, subject: 'politics', title: 'mk', content: 'c', analysis: 'a', mastered: 0, created_at: '2024-05-01T00:00:00.000Z' },
        ],
        words: [
          { id: 401, word: 'apple', phonetic: 'ae', meaning: 'pingguo', example: 'ex', source: 'manual' },
        ],
        srs_state: [
          { word_id: 401, ease: 2.5, interval_days: 0, repetitions: 0, due_date: '2024-05-02' },
        ],
        exam_records: [
          { id: 501, subject: 'math', paper: 'p1', score: 100, total_score: 150, duration_minutes: 180, taken_at: '2024-05-01T00:00:00.000Z' },
        ],
        settings: [
          { key: 'theme', value: 'dark' },
        ],
      },
    },
  });

  it('first merge imports one row per table with zero skipped', async () => {
    const { cookie } = await newUser('bm1');
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: basePayload(),
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
  });

  it('second merge of same payload skips duplicates and keeps single rows', async () => {
    const { cookie } = await newUser('bm2');
    const first = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: basePayload(),
    });
    expect(first.statusCode).toBe(200);
    const firstBody = first.json();
    expect(firstBody.imported).toEqual({
      plans: 1,
      focus_sessions: 1,
      mistakes: 1,
      words: 1,
      srs_state: 0,
      exam_records: 1,
      settings: 1,
    });
    expect(firstBody.skipped).toEqual({
      plans: 0,
      focus_sessions: 0,
      mistakes: 0,
      words: 0,
      srs_state: 1,
      exam_records: 0,
      settings: 0,
    });

    const second = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: basePayload(),
    });
    expect(second.statusCode).toBe(200);
    const body = second.json();
    expect(body.mode).toBe('merge');
    expect(body.imported).toEqual({
      plans: 0,
      focus_sessions: 0,
      mistakes: 0,
      words: 0,
      srs_state: 0,
      exam_records: 0,
      settings: 0,
    });
    expect(body.skipped).toEqual({
      plans: 1,
      focus_sessions: 1,
      mistakes: 1,
      words: 1,
      srs_state: 1,
      exam_records: 1,
      settings: 1,
    });

    const userId = (db.prepare('SELECT id FROM users WHERE username = ?').get(rand('x')) as { id: number } | undefined)?.id;
    const planCount = db.prepare('SELECT COUNT(*) AS c FROM plans').get() as { c: number };
    const wordCount = db.prepare('SELECT COUNT(*) AS c FROM words').get() as { c: number };
    expect(planCount.c).toBe(1);
    expect(wordCount.c).toBe(1);
    expect(userId).toBeUndefined();
  });
});
