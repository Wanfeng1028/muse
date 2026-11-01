import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify from 'fastify';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerFocusRoutes } from '../src/routes/focus';
import { registerAndLogin } from './test-utils';

describe('POST /api/focus 与 POST /api/import/focus startedAt 真实日历日期校验', () => {
  let db: ReturnType<typeof createDb>;
  let app: Fastify.FastifyInstance;
  let cookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerFocusRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'focusstartedatcalendar');
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  it('rejects 2024-02-30', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: '2024-02-30T08:00:00.000Z' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.body).toBe('{"error":"startedAt must be a valid date string"}');
  });

  it('rejects 2023-02-29', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: '2023-02-29T08:00:00.000Z' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.body).toBe('{"error":"startedAt must be a valid date string"}');
  });

  it('rejects 2026-04-31', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: '2026-04-31T08:00:00.000Z' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.body).toBe('{"error":"startedAt must be a valid date string"}');
  });

  it('accepts 2024-02-29 leap day', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: '2024-02-29T08:00:00.000Z' },
    });
    expect(res.statusCode).toBe(201);
    const body = JSON.parse(res.body);
    expect(body.startedAt).toBe('2024-02-29T08:00:00.000Z');
  });

  it('accepts 2024-05-01 regression', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'math', minutes: 30, startedAt: '2024-05-01T09:00:00.000Z' },
    });
    expect(res.statusCode).toBe(201);
  });

  it('import rejects 2024-02-30 row', async () => {
    const csv = 'subject,minutes,started_at\nmath,30,2024-02-30';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/focus',
      headers: { cookie },
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toHaveLength(1);
    expect(body.errors[0].row).toBe(2);
    expect(body.errors[0].message).toBe('started_at 格式非法');
    const listRes = await app.inject({ method: 'GET', url: '/api/focus', headers: { cookie } });
    expect(JSON.parse(listRes.body).length).toBe(0);
  });

  it('import accepts 2024-02-29 row', async () => {
    const csv = 'subject,minutes,started_at\nmath,30,2024-02-29';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/focus',
      headers: { cookie },
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.imported).toBe(1);
    expect(body.errorRows).toBe(0);
  });

  it('import mixed valid and invalid rows', async () => {
    const csv = 'subject,minutes,started_at\nmath,30,2024-05-01\nmath,30,2023-02-29';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/focus',
      headers: { cookie },
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.imported).toBe(1);
    expect(body.errorRows).toBe(1);
    expect(body.errors[0].row).toBe(3);
    const listRes = await app.inject({ method: 'GET', url: '/api/focus', headers: { cookie } });
    expect(JSON.parse(listRes.body).length).toBe(1);
  });
});
