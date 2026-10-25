import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: DatabaseSync;
let app: FastifyInstance;
let authCookie: string;

describe('GET /api/mistakes/summary/by-subject', () => {
  beforeEach(async () => {
    db = createRealDb(':memory:');
    app = Fastify();
    registerMistakesRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'mistakesbysubject');
  });

  afterAll(async () => {
    if (app) await app.close();
  });

  it('空库返回 subjects 为空数组', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary/by-subject',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ subjects: [] });
  });

  it('分科统计精确值且按 SUBJECTS 顺序排列，零错题科目省略', async () => {
    const insert = (
      username: string,
      subject: string,
      title: string,
      mastered: number,
    ) => {
      db.prepare(
        "INSERT INTO mistakes (user_id, subject, title, mastered) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, subject, title, mastered);
    };

    insert('mistakesbysubject', 'english', `title-en1-${Math.random()}`, 1);
    insert('mistakesbysubject', 'politics', `title-po1-${Math.random()}`, 0);
    insert('mistakesbysubject', 'math', `title-ma1-${Math.random()}`, 1);
    insert('mistakesbysubject', 'math', `title-ma2-${Math.random()}`, 0);
    insert('mistakesbysubject', 'math', `title-ma3-${Math.random()}`, 0);
    insert('mistakesbysubject', 'english', `title-en2-${Math.random()}`, 1);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary/by-subject',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subjects: [
        { subject: 'math', total: 3, mastered: 1, unmastered: 2, masteredRate: 0.3333 },
        { subject: 'english', total: 2, mastered: 2, unmastered: 0, masteredRate: 1 },
        { subject: 'politics', total: 1, mastered: 0, unmastered: 1, masteredRate: 0 },
      ],
    });
  });

  it('只统计当前用户，他人错题不计入', async () => {
    await registerAndLogin(app, 'mistakesbysubjectother');

    const insert = (
      username: string,
      subject: string,
      title: string,
      mastered: number,
    ) => {
      db.prepare(
        "INSERT INTO mistakes (user_id, subject, title, mastered) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, subject, title, mastered);
    };

    insert('mistakesbysubjectother', 'math', `title-other1-${Math.random()}`, 1);
    insert('mistakesbysubjectother', 'math', `title-other2-${Math.random()}`, 1);
    insert('mistakesbysubject', 'math', `title-main1-${Math.random()}`, 0);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary/by-subject',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subjects: [
        { subject: 'math', total: 1, mastered: 0, unmastered: 1, masteredRate: 0 },
      ],
    });
  });

  it('未登录返回 401', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary/by-subject',
    });
    expect(res.statusCode).toBe(401);
  });
});
