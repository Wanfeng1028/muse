import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('words SRS missing row grade0 deep4', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerWordsRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });

  afterEach(async () => {
    await app.close();
  });

  it('deletes srs row then grade=0 returns 200 with state (0, 1, 2.3)', async () => {
    const cookie = await registerAndLogin(app, rand('deep4a'));

    const created = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: { cookie },
      payload: { word: 'abandon', meaning: 'v. 放弃' },
    });
    expect(created.statusCode).toBe(201);
    const createdBody = created.json() as { id: number };
    const id = createdBody.id;

    db.prepare('DELETE FROM srs_state WHERE word_id = ?').run(id);

    const before = db
      .prepare('SELECT COUNT(*) AS c FROM srs_state WHERE word_id = ?')
      .get(id) as { c: number };
    expect(before.c).toBe(0);

    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 0 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      state: { repetitions: number; intervalDays: number; ease: number };
    };
    expect(body.state.repetitions).toBe(0);
    expect(body.state.intervalDays).toBe(1);
    expect(body.state.ease).toBe(2.3);
  });

  it('recreates an srs_state row for the word id after grade=0', async () => {
    const cookie = await registerAndLogin(app, rand('deep4b'));

    const created = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: { cookie },
      payload: { word: 'benefit', meaning: 'n. 益处' },
    });
    expect(created.statusCode).toBe(201);
    const createdBody = created.json() as { id: number };
    const id = createdBody.id;

    db.prepare('DELETE FROM srs_state WHERE word_id = ?').run(id);

    const removed = db
      .prepare('SELECT COUNT(*) AS c FROM srs_state WHERE word_id = ?')
      .get(id) as { c: number };
    expect(removed.c).toBe(0);

    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 0 },
    });
    expect(res.statusCode).toBe(200);

    const after = db
      .prepare('SELECT COUNT(*) AS c FROM srs_state WHERE word_id = ?')
      .get(id) as { c: number };
    expect(after.c).toBe(1);
  });
});
