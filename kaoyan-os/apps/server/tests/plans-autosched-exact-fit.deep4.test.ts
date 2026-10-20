import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule exact fit boundary deep4', () => {
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

  it('dailyMinutes 等于 90 时数学复习1-1天 落在 2026-11-02，当天两条合计 90', async () => {
    const cookie = await registerAndLogin(app, rand('exact90'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math', 'english'],
        dailyMinutes: 90,
        examDate: '2026-11-30',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { created: number; skipped: number; discarded: number; items: Array<{ date: string; subject: string; title: string; plannedMinutes: number; kind: string }> };
    const mathReview = body.items.find((i) => i.title === '智能排期·数学 复习1-1天');
    expect(mathReview).toBeDefined();
    expect(mathReview!.date).toBe('2026-11-02');
    expect(mathReview!.plannedMinutes).toBe(30);
    const dayItems = body.items.filter((i) => i.date === '2026-11-02');
    const sum = dayItems.reduce((acc, i) => acc + i.plannedMinutes, 0);
    expect(sum).toBe(90);
  });

  it('dailyMinutes 等于 89 时数学复习1-1天 顺延至 2026-11-03，数学新学2 顺延至 2026-11-04', async () => {
    const cookie = await registerAndLogin(app, rand('exact89'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math', 'english'],
        dailyMinutes: 89,
        examDate: '2026-11-30',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { created: number; skipped: number; discarded: number; items: Array<{ date: string; subject: string; title: string; plannedMinutes: number; kind: string }> };
    const mathReview = body.items.find((i) => i.title === '智能排期·数学 复习1-1天');
    expect(mathReview).toBeDefined();
    expect(mathReview!.date).toBe('2026-11-03');
    const mathNew2 = body.items.find((i) => i.title === '智能排期·数学 新学2');
    expect(mathNew2).toBeDefined();
    expect(mathNew2!.date).toBe('2026-11-04');
  });

  it('严格大于才顺延：90 时数学新学2 在 2026-11-03，89 时同条目被挤到 2026-11-04', async () => {
    const cookieA = await registerAndLogin(app, rand('strict90'));
    const resA = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieA },
      payload: {
        subjects: ['math', 'english'],
        dailyMinutes: 90,
        examDate: '2026-11-30',
        startDate: '2026-11-01',
      },
    });
    expect(resA.statusCode).toBe(200);
    const bodyA = resA.json() as { items: Array<{ date: string; title: string }> };
    const a = bodyA.items.find((i) => i.title === '智能排期·数学 新学2');
    expect(a).toBeDefined();
    expect(a!.date).toBe('2026-11-03');

    const cookieB = await registerAndLogin(app, rand('strict89'));
    const resB = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: {
        subjects: ['math', 'english'],
        dailyMinutes: 89,
        examDate: '2026-11-30',
        startDate: '2026-11-01',
      },
    });
    expect(resB.statusCode).toBe(200);
    const bodyB = resB.json() as { items: Array<{ date: string; title: string }> };
    const b = bodyB.items.find((i) => i.title === '智能排期·数学 新学2');
    expect(b).toBeDefined();
    expect(b!.date).toBe('2026-11-04');
  });
});
