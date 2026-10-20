import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('backup replace srs orphan skipped deep4', () => {
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

  function payload() {
    return {
      data: {
        format: 'kaoyan-backup',
        version: 1,
        exportedAt: '2026-01-01T00:00:00.000Z',
        tables: {
          plans: [],
          focus_sessions: [],
          mistakes: [],
          words: [
            { id: 401, word: 'apple', phonetic: '', meaning: '苹果', example: '', source: 'manual' },
          ],
          srs_state: [
            { word_id: 401, ease: 2.5, interval_days: 3, repetitions: 2, due_date: '2026-10-20' },
            { word_id: 9999, ease: 2.0, interval_days: 1, repetitions: 1, due_date: '2026-10-21' },
          ],
          exam_records: [],
          settings: [],
        },
      },
      mode: 'replace',
    };
  }

  it('replace 导入孤儿 srs_state 计数正确', async () => {
    const { cookie } = await newUser('srsorphan');
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: payload(),
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.mode).toBe('replace');
    expect(body.imported.srs_state).toBe(1);
    expect(body.skipped.srs_state).toBe(1);
    expect(body.imported.words).toBe(1);
  });

  it('replace 导入后仅保留属于本次 words 的 srs_state 行', async () => {
    const { cookie, userId } = await newUser('srsorphan');
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: payload(),
    });
    expect(res.statusCode).toBe(200);

    const rows = db
      .prepare(
        'SELECT s.word_id FROM srs_state s JOIN words w ON w.id = s.word_id WHERE w.user_id = ? ORDER BY s.word_id ASC'
      )
      .all(userId) as { word_id: number }[];
    expect(rows.length).toBe(1);
    expect(rows[0].word_id).toBe(401);

    const orphan = db
      .prepare(
        'SELECT s.word_id FROM srs_state s JOIN words w ON w.id = s.word_id WHERE w.user_id = ? AND s.word_id = ?'
      )
      .get(userId, 9999) as { word_id: number } | undefined;
    expect(orphan).toBeUndefined();
  });
});
