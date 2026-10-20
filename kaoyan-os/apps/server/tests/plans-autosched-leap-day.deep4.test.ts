import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule leap day deep4', () => {
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

  it('discarded=17、items.length=13', async () => {
    const cookie = await registerAndLogin(app, rand('leap1'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2028-03-06',
        startDate: '2028-02-27',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { created: number; skipped: number; discarded: number; items: Array<{ date: string; subject: string; title: string; plannedMinutes: number }> };
    expect(body.discarded).toBe(17);
    expect(body.items.length).toBe(13);
  });

  it('2028-02-29 存在：新学2、60 分钟', async () => {
    const cookie = await registerAndLogin(app, rand('leap2'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2028-03-06',
        startDate: '2028-02-27',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ date: string; subject: string; title: string; plannedMinutes: number }> };
    const item = body.items.find((i) => i.date === '2028-02-29');
    expect(item).toBeDefined();
    expect(item!.title).toBe('智能排期·数学 新学2');
    expect(item!.plannedMinutes).toBe(60);
  });

  it('2028-03-01 恰好 2 条复习：复习1-3天、复习2-1天', async () => {
    const cookie = await registerAndLogin(app, rand('leap3'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2028-03-06',
        startDate: '2028-02-27',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ date: string; subject: string; title: string; plannedMinutes: number }> };
    const dayItems = body.items.filter((i) => i.date === '2028-03-01');
    expect(dayItems.length).toBe(2);
    const titles = dayItems.map((i) => i.title).sort();
    expect(titles).toEqual(['智能排期·数学 复习1-3天', '智能排期·数学 复习2-1天']);
  });

  it('复习1-7天 落在 2028-03-05，所有 items date <= 2028-03-06', async () => {
    const cookie = await registerAndLogin(app, rand('leap4'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2028-03-06',
        startDate: '2028-02-27',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ date: string; subject: string; title: string; plannedMinutes: number }> };
    const item = body.items.find((i) => i.title === '智能排期·数学 复习1-7天');
    expect(item).toBeDefined();
    expect(item!.date).toBe('2028-03-05');
    for (const i of body.items) {
      expect(i.date <= '2028-03-06').toBe(true);
    }
  });
});
