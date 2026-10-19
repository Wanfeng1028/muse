
import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

function insertMistake(
  db: DatabaseSync,
  subject: string,
  mastered: number,
): void {
  db.prepare(
    "INSERT INTO mistakes (user_id, subject, title, mastered) VALUES ((SELECT id FROM users WHERE username = 'mistakessummary'), ?, ?, ?)",
  ).run(subject, `t-${subject}-${mastered}-${Math.random()}`, mastered);
}


describe('GET /api/mistakes/summary', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let authCookie: string;

  beforeEach(async () => {
    db = createRealDb(':memory:');
    app = Fastify();
    registerMistakesRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'mistakessummary');
  });


  afterAll(async () => {
    if (app) {
      await app.close();
    }
  });

  it('空库返回 total=0, masteredRate=0, subject=null', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subject: null,
      total: 0,
      mastered: 0,
      unmastered: 0,
      masteredRate: 0,
    });

  });

  it('非法 subject 返回 400', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=invalid',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject 参数' });
  });

  it('混合 mastered 统计精确值', async () => {
    insertMistake(db, 'math', 1);
    insertMistake(db, 'math', 1);
    insertMistake(db, 'english', 0);
    insertMistake(db, 'politics', 0);
    insertMistake(db, 'major', 1);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subject: null,
      total: 5,
      mastered: 3,
      unmastered: 2,
      masteredRate: 0.6,
    });

  });

  it('masteredRate 保留 4 位小数（1/3=0.3333）', async () => {
    insertMistake(db, 'math', 1);
    insertMistake(db, 'math', 0);
    insertMistake(db, 'math', 0);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subject: null,
      total: 3,
      mastered: 1,
      unmastered: 2,
      masteredRate: 0.3333,
    });

  });

  it('subject=math 过滤', async () => {
    insertMistake(db, 'math', 1);
    insertMistake(db, 'math', 0);
    insertMistake(db, 'english', 1);
    insertMistake(db, 'english', 1);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=math',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subject: 'math',
      total: 2,
      mastered: 1,
      unmastered: 1,
      masteredRate: 0.5,
    });
  });

  it('subject 回显且空过滤结果为 0', async () => {
    insertMistake(db, 'english', 1);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=politics',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subject: 'politics',
      total: 0,
      mastered: 0,
      unmastered: 0,
      masteredRate: 0,
    });
  });
});
