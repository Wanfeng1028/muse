import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('backup import row validation deep4', () => {
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

  function basePayload() {
    return {
      format: 'kaoyan-backup',
      version: 1,
      exportedAt: '2024-01-01T00:00:00.000Z',
      tables: {
        plans: [
          { date: '2024-01-01', subject: 'math', title: 'p1' },
        ],
        focus_sessions: [
          { subject: 'math', started_at: '2024-01-01T00:00:00.000Z' },
        ],
        mistakes: [
          { subject: 'math', title: 'm1' },
        ],
        words: [
          { word: 'w1', meaning: 'm1' },
        ],
        srs_state: [
          { word_id: 1, due_date: '2024-01-02' },
        ],
        exam_records: [
          { subject: 'math', paper: 'p1', taken_at: '2024-01-01T00:00:00.000Z' },
        ],
        settings: [
          { key: 'k1', value: 'v1' },
        ],
      },
    };
  }

  it('rejects mistakes row with invalid subject', async () => {
    const { cookie, userId } = await newUser('deep4_mis_sub');
    const payload = basePayload();
    payload.tables.mistakes = [{ subject: 'nope', title: 'm1' }];
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { mode: 'replace', data: payload },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '表 mistakes 第 1 行：subject 无效' });
    const count = db.prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?').get(userId) as { c: number };
    expect(count.c).toBe(0);
  });

  it('rejects words row with empty word', async () => {
    const { cookie, userId } = await newUser('deep4_words_word');
    const payload = basePayload();
    payload.tables.words = [{ word: '', meaning: 'm1' }];
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { mode: 'replace', data: payload },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '表 words 第 1 行：word 缺失或类型不对' });
    const count = db.prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?').get(userId) as { c: number };
    expect(count.c).toBe(0);
  });

  it('rejects exam_records row with empty paper', async () => {
    const { cookie, userId } = await newUser('deep4_exam_paper');
    const payload = basePayload();
    payload.tables.exam_records = [{ subject: 'math', paper: '', taken_at: '2024-01-01T00:00:00.000Z' }];
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { mode: 'replace', data: payload },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '表 exam_records 第 1 行：paper 缺失或类型不对' });
    const count = db.prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?').get(userId) as { c: number };
    expect(count.c).toBe(0);
  });

  it('rejects settings row with empty key', async () => {
    const { cookie, userId } = await newUser('d4setkey');
    const payload = basePayload();
    payload.tables.settings = [{ key: '', value: 'v1' }];
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { mode: 'replace', data: payload },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '表 settings 第 1 行：key 缺失或类型不对' });
    const count = db.prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?').get(userId) as { c: number };
    expect(count.c).toBe(0);
  });

  it('rejects srs_state row with empty due_date', async () => {
    const { cookie, userId } = await newUser('deep4_srs_due');
    const payload = basePayload();
    payload.tables.srs_state = [{ word_id: 1, due_date: '' }];
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { mode: 'replace', data: payload },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '表 srs_state 第 1 行：due_date 缺失或类型不对' });
    const count = db.prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?').get(userId) as { c: number };
    expect(count.c).toBe(0);
  });

  it('rejects focus_sessions row with invalid subject', async () => {
    const { cookie, userId } = await newUser('deep4_focus_sub');
    const payload = basePayload();
    payload.tables.focus_sessions = [{ subject: 'nope', started_at: '2024-01-01T00:00:00.000Z' }];
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: { mode: 'replace', data: payload },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '表 focus_sessions 第 1 行：subject 无效' });
    const count = db.prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?').get(userId) as { c: number };
    expect(count.c).toBe(0);
  });
});
