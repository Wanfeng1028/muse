import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule year boundary deep4', () => {
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

  it('跨年排期返回 discarded=15 且 items 长度 9', async () => {
    const cookie = await registerAndLogin(app, rand('ybcount'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-01-05',
        startDate: '2025-12-30',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.discarded).toBe(15);
    expect(body.items.length).toBe(9);
  });

  it('跨年前 8 条条目 date/title/plannedMinutes 精确匹配', async () => {
    const cookie = await registerAndLogin(app, rand('ybitems'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-01-05',
        startDate: '2025-12-30',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    const head = body.items.slice(0, 8).map((i: { date: string; title: string; plannedMinutes: number }) => ({
      date: i.date,
      title: i.title,
      plannedMinutes: i.plannedMinutes,
    }));
    expect(head).toEqual([
      { date: '2025-12-30', title: '智能排期·数学 新学1', plannedMinutes: 60 },
      { date: '2025-12-31', title: '智能排期·数学 复习1-1天', plannedMinutes: 30 },
      { date: '2026-01-01', title: '智能排期·数学 新学2', plannedMinutes: 60 },
      { date: '2026-01-02', title: '智能排期·数学 复习1-3天', plannedMinutes: 30 },
      { date: '2026-01-02', title: '智能排期·数学 复习2-1天', plannedMinutes: 30 },
      { date: '2026-01-03', title: '智能排期·数学 新学3', plannedMinutes: 60 },
      { date: '2026-01-04', title: '智能排期·数学 复习2-3天', plannedMinutes: 30 },
      { date: '2026-01-04', title: '智能排期·数学 复习3-1天', plannedMinutes: 30 },
    ]);
  });

  it('2026-01-01 为新学2 且结果横跨 2025 与 2026 两年', async () => {
    const cookie = await registerAndLogin(app, rand('ybcross'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-01-05',
        startDate: '2025-12-30',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    const jan1 = body.items.filter((i: { date: string }) => i.date === '2026-01-01');
    expect(jan1.length).toBe(1);
    expect(jan1[0].title).toBe('智能排期·数学 新学2');
    expect(jan1[0].plannedMinutes).toBe(60);
    const hasDec31 = body.items.some((i: { date: string }) => i.date === '2025-12-31');
    const hasJan1 = body.items.some((i: { date: string }) => i.date === '2026-01-01');
    expect(hasDec31).toBe(true);
    expect(hasJan1).toBe(true);
  });
});
