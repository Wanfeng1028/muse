import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('backup replace twice stable deep4', () => {
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

  function buildPayload(): Record<string, unknown> {
    return {
      format: 'kaoyan-backup',
      version: 1,
      exportedAt: '2024-01-01T00:00:00.000Z',
      tables: {
        plans: [
          {
            id: 101,
            date: '2024-03-01',
            subject: 'math',
            title: 'plan-a',
            planned_minutes: 60,
            done: 0,
            created_at: '2024-03-01T00:00:00.000Z',
          },
        ],
        focus_sessions: [
          {
            id: 201,
            subject: 'math',
            minutes: 45,
            started_at: '2024-03-01T01:00:00.000Z',
            note: 'focus-a',
          },
        ],
        mistakes: [
          {
            id: 301,
            subject: 'math',
            title: 'mistake-a',
            content: 'content-a',
            analysis: 'analysis-a',
            mastered: 0,
            created_at: '2024-03-01T02:00:00.000Z',
          },
        ],
        words: [
          {
            id: 401,
            word: 'abandon',
            phonetic: 'əˈbændən',
            meaning: '放弃',
            example: 'abandon ship',
            source: 'manual',
          },
        ],
        srs_state: [
          {
            word_id: 401,
            ease: 2.5,
            interval_days: 0,
            repetitions: 0,
            due_date: '2024-03-01',
          },
        ],
        exam_records: [
          {
            id: 501,
            subject: 'math',
            paper: 'paper-a',
            score: 100,
            total_score: 150,
            duration_minutes: 180,
            taken_at: '2024-03-01T03:00:00.000Z',
          },
        ],
        settings: [{ key: 'theme', value: 'dark' }],
      },
    };
  }

  const emptyImported = {
    plans: 0,
    focus_sessions: 0,
    mistakes: 0,
    words: 0,
    srs_state: 0,
    exam_records: 0,
    settings: 0,
  };

  function fullImported(): Record<string, number> {
    return {
      plans: 1,
      focus_sessions: 1,
      mistakes: 1,
      words: 1,
      srs_state: 1,
      exam_records: 1,
      settings: 1,
    };
  }

  it('第一次 replace：imported 七表各为 1，skipped 全 0', async () => {
    const { cookie } = await newUser('replace1');
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { data: buildPayload(), mode: 'replace' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { mode: string; imported: Record<string, number>; skipped: Record<string, number> };
    expect(body.mode).toBe('replace');
    expect(body.imported).toEqual(fullImported());
    expect(body.skipped).toEqual(emptyImported);
  });

  it('第二次 replace 同 payload：imported 与 skipped 与第一次完全一致；db 各表行数不变（无重复）', async () => {
    const { cookie, userId } = await newUser('replace2');
    const first = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { data: buildPayload(), mode: 'replace' },
    });
    expect(first.statusCode).toBe(200);
    const firstBody = first.json() as { mode: string; imported: Record<string, number>; skipped: Record<string, number> };
    expect(firstBody.mode).toBe('replace');
    expect(firstBody.imported).toEqual(fullImported());
    expect(firstBody.skipped).toEqual(emptyImported);

    const countsAfterFirst = {
      plans: (db.prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?').get(userId) as { c: number }).c,
      focus_sessions: (db.prepare('SELECT COUNT(*) AS c FROM focus_sessions WHERE user_id = ?').get(userId) as { c: number }).c,
      mistakes: (db.prepare('SELECT COUNT(*) AS c FROM mistakes WHERE user_id = ?').get(userId) as { c: number }).c,
      words: (db.prepare('SELECT COUNT(*) AS c FROM words WHERE user_id = ?').get(userId) as { c: number }).c,
      srs_state: (db.prepare('SELECT COUNT(*) AS c FROM srs_state s JOIN words w ON w.id = s.word_id WHERE w.user_id = ?').get(userId) as { c: number }).c,
      exam_records: (db.prepare('SELECT COUNT(*) AS c FROM exam_records WHERE user_id = ?').get(userId) as { c: number }).c,
      settings: (db.prepare('SELECT COUNT(*) AS c FROM settings WHERE user_id = ?').get(userId) as { c: number }).c,
    };
    expect(countsAfterFirst).toEqual(fullImported());

    const second = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { data: buildPayload(), mode: 'replace' },
    });
    expect(second.statusCode).toBe(200);
    const secondBody = second.json() as { mode: string; imported: Record<string, number>; skipped: Record<string, number> };
    expect(secondBody.mode).toBe(firstBody.mode);
    expect(secondBody.imported).toEqual(firstBody.imported);
    expect(secondBody.skipped).toEqual(firstBody.skipped);

    const countsAfterSecond = {
      plans: (db.prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?').get(userId) as { c: number }).c,
      focus_sessions: (db.prepare('SELECT COUNT(*) AS c FROM focus_sessions WHERE user_id = ?').get(userId) as { c: number }).c,
      mistakes: (db.prepare('SELECT COUNT(*) AS c FROM mistakes WHERE user_id = ?').get(userId) as { c: number }).c,
      words: (db.prepare('SELECT COUNT(*) AS c FROM words WHERE user_id = ?').get(userId) as { c: number }).c,
      srs_state: (db.prepare('SELECT COUNT(*) AS c FROM srs_state s JOIN words w ON w.id = s.word_id WHERE w.user_id = ?').get(userId) as { c: number }).c,
      exam_records: (db.prepare('SELECT COUNT(*) AS c FROM exam_records WHERE user_id = ?').get(userId) as { c: number }).c,
      settings: (db.prepare('SELECT COUNT(*) AS c FROM settings WHERE user_id = ?').get(userId) as { c: number }).c,
    };
    expect(countsAfterSecond).toEqual(countsAfterFirst);
  });
});
