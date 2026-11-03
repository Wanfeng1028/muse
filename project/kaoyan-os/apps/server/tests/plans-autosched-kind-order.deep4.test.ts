import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule kind order deep4', () => {
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

  it('preview 同日按 kind 排序：new 在 review 之前', async () => {
    const cookie = await registerAndLogin(app, rand('korder'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math,english&dailyMinutes=480&examDate=2026-11-30&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ date: string; subject: string; title: string; plannedMinutes: number; kind: string }> };

    const day1102 = body.items.filter((i) => i.date === '2026-11-02');
    expect(day1102.length).toBe(2);
    expect(day1102[0].title).toBe('智能排期·英语 新学1');
    expect(day1102[0].kind).toBe('new');
    expect(day1102[1].title).toBe('智能排期·数学 复习1-1天');
    expect(day1102[1].kind).toBe('review');

    const day1103 = body.items.filter((i) => i.date === '2026-11-03');
    expect(day1103.length).toBe(2);
    expect(day1103[0].title).toBe('智能排期·数学 新学2');
    expect(day1103[0].kind).toBe('new');
    expect(day1103[1].title).toBe('智能排期·英语 复习1-1天');
    expect(day1103[1].kind).toBe('review');
  });

  it('preview 所有 item kind 合法且每天 new 都排在 review 前', async () => {
    const cookie = await registerAndLogin(app, rand('kfield'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math,english&dailyMinutes=480&examDate=2026-11-30&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ date: string; kind: string }> };

    for (const item of body.items) {
      expect(typeof item.kind).toBe('string');
      expect(item.kind === 'new' || item.kind === 'review').toBe(true);
    }

    const byDate = new Map<string, Array<{ kind: string }>>();
    for (const item of body.items) {
      const arr = byDate.get(item.date) ?? [];
      arr.push(item);
      byDate.set(item.date, arr);
    }

    for (const arr of byDate.values()) {
      let seenReview = false;
      for (const it of arr) {
        if (it.kind === 'review') {
          seenReview = true;
        } else if (it.kind === 'new') {
          expect(seenReview).toBe(false);
        }
      }
    }
  });

  it('POST 与 preview 的 (date,title) 顺序一致且 POST item 无 kind 字段', async () => {
    const cookie = await registerAndLogin(app, rand('kpost'));
    const previewRes = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math,english&dailyMinutes=480&examDate=2026-11-30&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(previewRes.statusCode).toBe(200);
    const previewBody = previewRes.json() as { items: Array<{ date: string; title: string }> };
    const previewKeys = previewBody.items.map((i) => `${i.date}|${i.title}`);

    const postRes = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math', 'english'],
        dailyMinutes: 480,
        examDate: '2026-11-30',
        startDate: '2026-11-01',
      },
    });
    expect(postRes.statusCode).toBe(200);
    const postBody = postRes.json() as { items: Array<Record<string, unknown>> };
    const postKeys = postBody.items.map((i) => `${i.date as string}|${i.title as string}`);
    expect(postKeys).toEqual(previewKeys);

    for (const item of postBody.items) {
      expect('kind' in item).toBe(false);
    }
  });
});
