import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerStatsRoutes } from '../src/routes/stats';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('stats weekly start strict validation', () => {
  let db: ReturnType<typeof createDb>;
  let app: FastifyInstance;
  let authCookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerStatsRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'weeklystrict');
  });

  afterEach(async () => {
    await app.close();
  });

  it('returns 400 for 2024-02-30 (invalid date)', async () => {
    const res = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/weekly?start=2024-02-30',
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'start 日期无效' });
  });

  it('returns 400 for 2023-02-29 (not a leap year)', async () => {
    const res = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/weekly?start=2023-02-29',
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'start 日期无效' });
  });

  it('returns 200 with weekStart for 2024-02-29 (leap year)', async () => {
    const res = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/weekly?start=2024-02-29',
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ weekStart: '2024-02-29' });
  });

  it('returns 400 for 2026-04-31 (April has no 31st)', async () => {
    const res = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/weekly?start=2026-04-31',
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'start 日期无效' });
  });

  it('returns 200 with weekStart for 2026-02-28', async () => {
    const res = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/weekly?start=2026-02-28',
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ weekStart: '2026-02-28' });
  });

  it('returns 400 for 2026-13-01 (invalid month)', async () => {
    const res = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/weekly?start=2026-13-01',
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'start 日期无效' });
  });

  it('returns 400 for 2026-1-5 (non-zero-padded)', async () => {
    const res = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/weekly?start=2026-1-5',
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'start 日期格式无效' });
  });
});
