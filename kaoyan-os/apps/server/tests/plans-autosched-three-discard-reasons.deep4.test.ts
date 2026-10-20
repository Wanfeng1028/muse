import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule three discard reasons deep4', () => {
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

  it('返回 discarded=14、created=4、skipped=0、items.length=4，且 4 条 (date,title) 精确匹配', async () => {
    const cookie = await registerAndLogin(app, rand('sched_a'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 30,
        examDate: '2026-11-06',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      created: number;
      skipped: number;
      discarded: number;
      items: Array<{ date: string; title: string; plannedMinutes: number; kind: string }>;
    };
    expect(body.discarded).toBe(14);
    expect(body.created).toBe(4);
    expect(body.skipped).toBe(0);
    expect(body.items.length).toBe(4);
    expect(body.items.map((i) => [i.date, i.title])).toEqual([
      ['2026-11-02', '智能排期·数学 复习1-1天'],
      ['2026-11-04', '智能排期·数学 复习1-3天'],
      ['2026-11-05', '智能排期·数学 复习2-1天'],
      ['2026-11-06', '智能排期·数学 复习2-3天'],
    ]);
  });

  it('返回的 4 条 title 都含复习且都不含新学，且 plannedMinutes 均为 30', async () => {
    const cookie = await registerAndLogin(app, rand('sched_b'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 30,
        examDate: '2026-11-06',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      items: Array<{ date: string; title: string; plannedMinutes: number }>;
    };
    expect(body.items.length).toBe(4);
    for (const item of body.items) {
      expect(item.title).toContain('复习');
      expect(item.title).not.toContain('新学');
      expect(item.plannedMinutes).toBe(30);
    }
  });

  it('复习3-1天 因顺延超 examDate 被丢弃，且所有返回项 date 均不晚于 2026-11-06', async () => {
    const cookie = await registerAndLogin(app, rand('sched_c'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 30,
        examDate: '2026-11-06',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      items: Array<{ date: string; title: string; plannedMinutes: number; kind: string }>;
    };
    const titles = body.items.map((i) => i.title);
    expect(titles).not.toContain('智能排期·数学 复习3-1天');
    expect(body.items.some((i) => i.title === '智能排期·数学 复习3-1天')).toBe(false);
    for (const item of body.items) {
      expect(item.date <= '2026-11-06').toBe(true);
    }
  });
});
