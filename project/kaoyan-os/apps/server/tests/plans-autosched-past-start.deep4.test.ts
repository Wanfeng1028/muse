import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule past start date deep4', () => {
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

  it('accepts a past startDate and returns the exact schedule', async () => {
    const cookie = await registerAndLogin(app, rand('past_start'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2025-06-05',
        startDate: '2025-06-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { created: number; skipped: number; discarded: number; items: Array<{ date: string; title: string }> };
    expect(body.discarded).toBe(12);
    expect(body.items.length).toBe(6);
    expect(body.created).toBe(6);
    expect(body.items.map((i) => [i.date, i.title])).toEqual([
      ['2025-06-01', '智能排期·数学 新学1'],
      ['2025-06-02', '智能排期·数学 复习1-1天'],
      ['2025-06-03', '智能排期·数学 新学2'],
      ['2025-06-04', '智能排期·数学 复习1-3天'],
      ['2025-06-04', '智能排期·数学 复习2-1天'],
      ['2025-06-05', '智能排期·数学 新学3'],
    ]);
  });

  it('persists the scheduled plans into the database', async () => {
    const cookie = await registerAndLogin(app, rand('past_persist'));
    const scheduleRes = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2025-06-05',
        startDate: '2025-06-01',
      },
    });
    expect(scheduleRes.statusCode).toBe(200);

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans?date=2025-06-04',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const plans = res.json() as Array<{ date: string; title: string; done: boolean }>;
    expect(plans.length).toBe(2);
    expect(plans.map((p) => p.title)).toEqual([
      '智能排期·数学 复习1-3天',
      '智能排期·数学 复习2-1天',
    ]);
    expect(plans.every((p) => p.done === false)).toBe(true);
  });
});
