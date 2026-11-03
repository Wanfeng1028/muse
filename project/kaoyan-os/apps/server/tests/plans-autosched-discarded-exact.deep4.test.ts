import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule discarded exact accounting deep4', () => {
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

  const params = {
    subjects: ['math'],
    dailyMinutes: 480,
    examDate: '2026-11-05',
    startDate: '2026-11-01',
  };

  const expected: Array<{ date: string; subject: string; title: string; plannedMinutes: number }> = [
    { date: '2026-11-01', subject: 'math', title: '智能排期·数学 新学1', plannedMinutes: 60 },
    { date: '2026-11-02', subject: 'math', title: '智能排期·数学 复习1-1天', plannedMinutes: 30 },
    { date: '2026-11-03', subject: 'math', title: '智能排期·数学 新学2', plannedMinutes: 60 },
    { date: '2026-11-04', subject: 'math', title: '智能排期·数学 复习1-3天', plannedMinutes: 30 },
    { date: '2026-11-04', subject: 'math', title: '智能排期·数学 复习2-1天', plannedMinutes: 30 },
    { date: '2026-11-05', subject: 'math', title: '智能排期·数学 新学3', plannedMinutes: 60 },
  ];

  it('POST 精确会计：discarded=12、created=6、skipped=0、items.length=6 且逐条四元组精确', async () => {
    const cookie = await registerAndLogin(app, rand('disc_exact'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: params,
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      created: number;
      skipped: number;
      discarded: number;
      items: Array<{ date: string; subject: string; title: string; plannedMinutes: number }>;
    };
    expect(body.discarded).toBe(12);
    expect(body.created).toBe(6);
    expect(body.skipped).toBe(0);
    expect(body.items.length).toBe(6);
    for (let i = 0; i < expected.length; i++) {
      expect(body.items[i].date).toBe(expected[i].date);
      expect(body.items[i].subject).toBe(expected[i].subject);
      expect(body.items[i].title).toBe(expected[i].title);
      expect(body.items[i].plannedMinutes).toBe(expected[i].plannedMinutes);
    }
  });

  it('所有 items 的 date 均不超过 examDate 2026-11-05', async () => {
    const cookie = await registerAndLogin(app, rand('disc_bound'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: params,
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      items: Array<{ date: string; subject: string; title: string; plannedMinutes: number }>;
    };
    expect(body.items.length).toBe(6);
    for (const item of body.items) {
      expect(item.date <= '2026-11-05').toBe(true);
    }
  });

  it('preview 四元组与 POST 顺序一致，preview 每条有 kind 且 POST 条目无 kind', async () => {
    const cookie = await registerAndLogin(app, rand('disc_prev'));
    const previewRes = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview',
      headers: { cookie },
      query: {
        subjects: 'math',
        dailyMinutes: '480',
        examDate: '2026-11-05',
        startDate: '2026-11-01',
      },
    });
    expect(previewRes.statusCode).toBe(200);
    const previewBody = previewRes.json() as {
      items: Array<{
        date: string;
        subject: string;
        title: string;
        plannedMinutes: number;
        kind: string;
      }>;
    };
    expect(previewBody.items.length).toBe(6);

    const postRes = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: params,
    });
    expect(postRes.statusCode).toBe(200);
    const postBody = postRes.json() as {
      items: Array<{ date: string; subject: string; title: string; plannedMinutes: number }>;
    };
    expect(postBody.items.length).toBe(6);

    for (let i = 0; i < 6; i++) {
      expect(previewBody.items[i].date).toBe(postBody.items[i].date);
      expect(previewBody.items[i].subject).toBe(postBody.items[i].subject);
      expect(previewBody.items[i].title).toBe(postBody.items[i].title);
      expect(previewBody.items[i].plannedMinutes).toBe(postBody.items[i].plannedMinutes);
      expect(['new', 'review']).toContain(previewBody.items[i].kind);
      expect('kind' in postBody.items[i]).toBe(false);
    }
  });

  it('丢弃原因纯粹性：新学3条、复习3条，且无任何 plannedMinutes > 480', async () => {
    const cookie = await registerAndLogin(app, rand('disc_pure'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: params,
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      discarded: number;
      items: Array<{ date: string; subject: string; title: string; plannedMinutes: number }>;
    };
    expect(body.discarded).toBe(12);
    expect(body.items.length).toBe(6);

    let newCount = 0;
    let reviewCount = 0;
    for (const item of body.items) {
      if (item.title.includes('新学')) newCount++;
      if (item.title.includes('复习')) reviewCount++;
      expect(item.plannedMinutes <= 480).toBe(true);
    }
    expect(newCount).toBe(3);
    expect(reviewCount).toBe(3);
  });
});
