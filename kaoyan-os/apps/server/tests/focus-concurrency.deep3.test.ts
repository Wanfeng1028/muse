import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { registerFocusRoutes } from '../src/routes/focus';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('focus concurrency & deep validation', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let cookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerFocusRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'focusdeep');
  });

  afterEach(async () => {
    await app.close();
  });

  it('concurrent 10 POSTs all succeed, GET returns 10, stats todayMinutes equals sum', async () => {
    const minutesList = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
    const responses = await Promise.all(
      minutesList.map((m) =>
        app.inject({
          method: 'POST',
          url: '/api/focus',
          headers: { cookie },
          payload: { subject: 'math', minutes: m },
        })
      )
    );
    for (const r of responses) {
      expect(r.statusCode).toBe(201);
    }

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: { cookie },
    });
    expect(listRes.statusCode).toBe(200);
    const list = listRes.json() as { id: number; minutes: number }[];
    expect(list.length).toBe(10);
    const ids = list.map((s) => s.id);
    expect(new Set(ids).size).toBe(10);

    const statsRes = await app.inject({
      method: 'GET',
      url: '/api/focus/stats',
      headers: { cookie },
    });
    expect(statsRes.statusCode).toBe(200);
    const stats = statsRes.json() as { todayMinutes: number; totalMinutes: number };
    const expectedSum = minutesList.reduce((a, b) => a + b, 0);
    expect(stats.todayMinutes).toBe(expectedSum);
    expect(stats.totalMinutes).toBe(expectedSum);
  });

  it('minutes=0 returns 400 with exact message', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 0 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'minutes must be an integer between 1 and 1440' });
  });

  it('minutes=1441, 1.5, and "60" all return 400', async () => {
    const res1 = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 1441 },
    });
    expect(res1.statusCode).toBe(400);
    expect(res1.json()).toEqual({ error: 'minutes must be an integer between 1 and 1440' });

    const res2 = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 1.5 },
    });
    expect(res2.statusCode).toBe(400);
    expect(res2.json()).toEqual({ error: 'minutes must be an integer between 1 and 1440' });

    const res3 = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: '60' },
    });
    expect(res3.statusCode).toBe(400);
    expect(res3.json()).toEqual({ error: 'minutes must be an integer between 1 and 1440' });
  });

  it('startedAt longer than 40 chars returns 400 with exact message', async () => {
    const tooLong = '2026-10-20T10:00:00.0000000000000000000000';
    expect(tooLong.length).toBeGreaterThan(40);
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: tooLong },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'startedAt must be a valid date string' });
  });

  it('startedAt="2026-13-45T10:00:00" returns 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: '2026-13-45T10:00:00' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'startedAt must be a valid date string' });
  });

  it('startedAt=123 (number) returns 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: 123 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'startedAt must be a valid date string' });
  });

  it('startedAt="2026-10-20" (date only) returns 201 and echoes exact value', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: '2026-10-20' },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json() as { startedAt: string; minutes: number };
    expect(body.startedAt).toBe('2026-10-20');
    expect(body.minutes).toBe(30);
  });

  it('startedAt="2026-10-20T08:00:00Z" (with timezone) returns 201', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 45, startedAt: '2026-10-20T08:00:00Z' },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json() as { startedAt: string; minutes: number };
    expect(body.startedAt).toBe('2026-10-20T08:00:00Z');
    expect(body.minutes).toBe(45);
  });

  it('note exactly 500 chars ok, 501 chars 400, number 400', async () => {
    const note500 = 'a'.repeat(500);
    const okRes = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, note: note500 },
    });
    expect(okRes.statusCode).toBe(201);
    const okBody = okRes.json() as { note: string | null };
    expect(okBody.note).toBe(note500);
    expect(okBody.note!.length).toBe(500);

    const note501 = 'a'.repeat(501);
    const badRes = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, note: note501 },
    });
    expect(badRes.statusCode).toBe(400);
    expect(badRes.json()).toEqual({ error: 'note must be a string up to 500 chars' });

    const numRes = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, note: 123 },
    });
    expect(numRes.statusCode).toBe(400);
    expect(numRes.json()).toEqual({ error: 'note must be a string up to 500 chars' });
  });

  it('limit boundary: 0→50, 1000→60, abc→50', async () => {
    for (let i = 0; i < 60; i++) {
      const res = await app.inject({
        method: 'POST',
        url: '/api/focus',
        headers: { cookie },
        payload: { subject: 'math', minutes: 1 },
      });
      expect(res.statusCode).toBe(201);
    }

    const limitZero = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=0',
      headers: { cookie },
    });
    expect(limitZero.statusCode).toBe(200);
    expect((limitZero.json() as unknown[]).length).toBe(50);

    const limitBig = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=1000',
      headers: { cookie },
    });
    expect(limitBig.statusCode).toBe(200);
    expect((limitBig.json() as unknown[]).length).toBe(60);

    const limitAbc = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=abc',
      headers: { cookie },
    });
    expect(limitAbc.statusCode).toBe(200);
    expect((limitAbc.json() as unknown[]).length).toBe(50);
  });

  it('stats days boundary: 0→1, 100→31, abc→7', async () => {
    const res0 = await app.inject({
      method: 'GET',
      url: '/api/focus/stats?days=0',
      headers: { cookie },
    });
    expect(res0.statusCode).toBe(200);
    const body0 = res0.json() as { days: unknown[] };
    expect(body0.days.length).toBe(1);

    const res100 = await app.inject({
      method: 'GET',
      url: '/api/focus/stats?days=100',
      headers: { cookie },
    });
    expect(res100.statusCode).toBe(200);
    const body100 = res100.json() as { days: unknown[] };
    expect(body100.days.length).toBe(31);

    const resAbc = await app.inject({
      method: 'GET',
      url: '/api/focus/stats?days=abc',
      headers: { cookie },
    });
    expect(resAbc.statusCode).toBe(200);
    const bodyAbc = resAbc.json() as { days: unknown[] };
    expect(bodyAbc.days.length).toBe(7);
  });

  it('user isolation: A has 2 records, B sees empty list and zero total', async () => {
    const cookieA = cookie;
    const cookieB = await registerAndLogin(app, 'focusother');

    for (let i = 0; i < 2; i++) {
      const res = await app.inject({
        method: 'POST',
        url: '/api/focus',
        headers: { cookie: cookieA },
        payload: { subject: 'math', minutes: 25 },
      });
      expect(res.statusCode).toBe(201);
    }

    const listA = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: { cookie: cookieA },
    });
    expect(listA.statusCode).toBe(200);
    expect((listA.json() as unknown[]).length).toBe(2);

    const listB = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: { cookie: cookieB },
    });
    expect(listB.statusCode).toBe(200);
    expect(listB.json()).toEqual([]);

    const statsB = await app.inject({
      method: 'GET',
      url: '/api/focus/stats',
      headers: { cookie: cookieB },
    });
    expect(statsB.statusCode).toBe(200);
    const statsBBody = statsB.json() as { totalMinutes: number; todayMinutes: number };
    expect(statsBBody.totalMinutes).toBe(0);
    expect(statsBBody.todayMinutes).toBe(0);
  });
});