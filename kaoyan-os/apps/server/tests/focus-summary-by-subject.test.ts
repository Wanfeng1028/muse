import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerFocusRoutes } from '../src/routes/focus';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: DatabaseSync;
let app: FastifyInstance;
let authCookie: string;

describe('GET /api/focus/summary/by-subject', () => {
  beforeEach(async () => {
    db = createRealDb(':memory:');
    app = Fastify();
    registerFocusRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'focusbysubject');
  });

  afterAll(async () => {
    if (app) await app.close();
  });

  it('空库返回 subjects 为空数组', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus/summary/by-subject',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ subjects: [] });
  });

  it('分科汇总精确值且按 SUBJECTS 顺序排列，零记录科目省略', async () => {
    const insert = (username: string, subject: string, minutes: number) => {
      db.prepare(
        "INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, subject, minutes, '2026-10-25T10:00:00Z');
    };

    // 故意按乱序插入，politics 无记录应被省略
    insert('focusbysubject', 'major', 120);
    insert('focusbysubject', 'english', 30);
    insert('focusbysubject', 'english', 15);
    insert('focusbysubject', 'math', 60);
    insert('focusbysubject', 'math', 25);
    insert('focusbysubject', 'math', 40);

    const res = await app.inject({
      method: 'GET',
      url: '/api/focus/summary/by-subject',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subjects: [
        { subject: 'math', sessions: 3, totalMinutes: 125 },
        { subject: 'english', sessions: 2, totalMinutes: 45 },
        { subject: 'major', sessions: 1, totalMinutes: 120 },
      ],
    });
  });

  it('只统计当前用户，他人专注记录不计入', async () => {
    await registerAndLogin(app, 'focusbysubjectother');

    const insert = (username: string, subject: string, minutes: number) => {
      db.prepare(
        "INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, subject, minutes, '2026-10-26T08:00:00Z');
    };

    insert('focusbysubjectother', 'math', 50);
    insert('focusbysubjectother', 'english', 70);
    insert('focusbysubject', 'math', 30);

    const res = await app.inject({
      method: 'GET',
      url: '/api/focus/summary/by-subject',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subjects: [{ subject: 'math', sessions: 1, totalMinutes: 30 }],
    });
  });

  it('未登录返回 401', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus/summary/by-subject',
    });
    expect(res.statusCode).toBe(401);
  });
});
