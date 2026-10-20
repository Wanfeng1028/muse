import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule minutes and titles deep4', () => {
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

  it('新学条目 plannedMinutes 全=60，复习条目全=30', async () => {
    const cookie = await registerAndLogin(app, rand('minutes'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-11-10',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ title: string; plannedMinutes: number }> };
    expect(body.items.length).toBeGreaterThan(0);
    for (const item of body.items) {
      if (item.title.includes('新学')) {
        expect(item.plannedMinutes).toBe(60);
      } else if (item.title.includes('复习')) {
        expect(item.plannedMinutes).toBe(30);
      }
    }
  });

  it('精确标题存在性：新学1 与 复习1-1天', async () => {
    const cookie = await registerAndLogin(app, rand('titles'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-11-10',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ title: string }> };
    const titles = body.items.map((i) => i.title);
    expect(titles.filter((t) => t === '智能排期·数学 新学1').length).toBe(1);
    expect(titles.filter((t) => t === '智能排期·数学 复习1-1天').length).toBe(1);
  });

  it('复习标题匹配 offset 正则，新学标题匹配序号正则', async () => {
    const cookie = await registerAndLogin(app, rand('regex'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-11-10',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ title: string }> };
    const reviewRe = /^智能排期·数学 复习\d+-(1|3|7|15|30)天$/;
    const newRe = /^智能排期·数学 新学\d+$/;
    let reviewCount = 0;
    let newCount = 0;
    for (const item of body.items) {
      if (item.title.includes('复习')) {
        expect(reviewRe.test(item.title)).toBe(true);
        reviewCount++;
      } else if (item.title.includes('新学')) {
        expect(newRe.test(item.title)).toBe(true);
        newCount++;
      }
    }
    expect(reviewCount).toBeGreaterThan(0);
    expect(newCount).toBeGreaterThan(0);
  });
});
