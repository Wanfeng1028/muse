import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('isolation autoschedule dedupe per user deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerPlansRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });

  it('A 排期 created=6；B 同参数排期 created=6、skipped=0（跨用户不去重）', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const body = {
      subjects: ['math'],
      dailyMinutes: 480,
      examDate: '2026-11-05',
      startDate: '2026-11-01',
    };

    const resA = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieA },
      payload: body,
    });
    expect(resA.statusCode).toBe(200);
    const jsonA = resA.json() as { created: number; skipped: number; discarded: number };
    expect(jsonA.created).toBe(6);
    expect(jsonA.skipped).toBe(0);
    expect(jsonA.discarded).toBe(12);

    const resB = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: body,
    });
    expect(resB.statusCode).toBe(200);
    const jsonB = resB.json() as { created: number; skipped: number; discarded: number };
    expect(jsonB.created).toBe(6);
    expect(jsonB.skipped).toBe(0);
    expect(jsonB.discarded).toBe(12);
  });

  it('B 第二次同参数排期 created=0、skipped=6、discarded=12（同用户幂等）', async () => {
    const cookieB = await registerAndLogin(app, rand('b'));

    const body = {
      subjects: ['math'],
      dailyMinutes: 480,
      examDate: '2026-11-05',
      startDate: '2026-11-01',
    };

    const first = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: body,
    });
    expect(first.statusCode).toBe(200);
    const firstJson = first.json() as { created: number; skipped: number };
    expect(firstJson.created).toBe(6);
    expect(firstJson.skipped).toBe(0);

    const second = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: body,
    });
    expect(second.statusCode).toBe(200);
    const secondJson = second.json() as { created: number; skipped: number; discarded: number };
    expect(secondJson.created).toBe(0);
    expect(secondJson.skipped).toBe(6);
    expect(secondJson.discarded).toBe(12);
  });

  it('A 查 2026-11-04 的计划仍为 2 条（B 的写入不污染 A）', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const body = {
      subjects: ['math'],
      dailyMinutes: 480,
      examDate: '2026-11-05',
      startDate: '2026-11-01',
    };

    const resA = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieA },
      payload: body,
    });
    expect(resA.statusCode).toBe(200);

    const resB = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: body,
    });
    expect(resB.statusCode).toBe(200);

    const list = await app.inject({
      method: 'GET',
      url: '/api/plans?date=2026-11-04',
      headers: { cookie: cookieA },
    });
    expect(list.statusCode).toBe(200);
    const rows = list.json() as Array<{ id: number; date: string; subject: string }>;
    expect(rows.length).toBe(2);
    for (const r of rows) {
      expect(r.date).toBe('2026-11-04');
      expect(r.subject).toBe('math');
    }
  });
});
