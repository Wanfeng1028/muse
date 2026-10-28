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

function localToday(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

describe('GET /api/focus/summary/by-subject?days=', () => {
  beforeEach(async () => {
    db = createRealDb(':memory:');
    app = Fastify();
    registerFocusRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'focusbysubjectdays');
  });

  afterAll(async () => {
    if (app) await app.close();
  });

  function insert(username: string, subject: string, minutes: number, startedAt: string) {
    db.prepare(
      "INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
    ).run(username, subject, minutes, startedAt);
  }

  it('days=1 只统计今天，旧记录被排除；不传 days 时旧记录仍计入', async () => {
    const today = localToday();
    insert('focusbysubjectdays', 'math', 60, `${today}T10:00:00`);
    insert('focusbysubjectdays', 'math', 999, '2026-01-05T10:00:00');
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus/summary/by-subject?days=1',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ subjects: [{ subject: 'math', sessions: 1, totalMinutes: 60 }] });
    const all = await app.inject({
      method: 'GET',
      url: '/api/focus/summary/by-subject',
      headers: { cookie: authCookie },
    });
    expect(all.json()).toEqual({ subjects: [{ subject: 'math', sessions: 2, totalMinutes: 1059 }] });
  });

  it('days 越界返回 400，合法边界仍 200', async () => {
    const today = localToday();
    insert('focusbysubjectdays', 'english', 30, `${today}T10:00:00`);
    for (const days of [0, -1, 32, 100, 999]) {
      const invalid = await app.inject({
        method: 'GET',
        url: `/api/focus/summary/by-subject?days=${days}`,
        headers: { cookie: authCookie },
      });
      expect(invalid.statusCode).toBe(400);
      expect(invalid.json()).toEqual({ error: 'days 参数无效' });
    }
    for (const days of [1, 31]) {
      const valid = await app.inject({
        method: 'GET',
        url: `/api/focus/summary/by-subject?days=${days}`,
        headers: { cookie: authCookie },
      });
      expect(valid.statusCode).toBe(200);
      expect(valid.json()).toEqual({ subjects: [{ subject: 'english', sessions: 1, totalMinutes: 30 }] });
    }
  });

  it('窗口内只统计当前用户，他人记录不计入', async () => {
    await registerAndLogin(app, 'focusbysubjectdaysother');
    const today = localToday();
    insert('focusbysubjectdaysother', 'math', 50, `${today}T08:00:00`);
    insert('focusbysubjectdays', 'math', 30, `${today}T09:00:00`);
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus/summary/by-subject?days=7',
      headers: { cookie: authCookie },
    });
    expect(res.json()).toEqual({ subjects: [{ subject: 'math', sessions: 1, totalMinutes: 30 }] });
  });

  it('未登录返回 401', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus/summary/by-subject?days=7',
    });
    expect(res.statusCode).toBe(401);
  });
});
