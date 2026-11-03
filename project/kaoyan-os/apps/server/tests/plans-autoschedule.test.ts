import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: DatabaseSync;
let app: FastifyInstance;

beforeEach(async () => {
  db = createRealDb(':memory:');
  app = Fastify();
  registerPlansRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

function randName(prefix: string): string {
  return prefix + Math.random().toString(36).slice(2, 10);
}

describe('GET /api/plans/auto-schedule/preview', () => {
  it('preview 返回排期条目但不写库', async () => {
    const username = randName('sched');
    const cookie = await registerAndLogin(app, username);

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math&dailyMinutes=600&examDate=2026-12-19&startDate=2026-10-20',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ date: string; subject: string; title: string; plannedMinutes: number; kind: string }> };
    expect(body.items.length).toBeGreaterThan(0);
    const new1 = body.items.find((i) => i.title === '智能排期·数学 新学1');
    expect(new1).toBeDefined();
    expect(new1!.date).toBe('2026-10-20');
    expect(new1!.kind).toBe('new');
    expect(new1!.plannedMinutes).toBe(60);

    const review1 = body.items.find((i) => i.title === '智能排期·数学 复习1-1天');
    expect(review1).toBeDefined();
    expect(review1!.date).toBe('2026-10-21');
    expect(review1!.plannedMinutes).toBe(30);
    expect(review1!.kind).toBe('review');

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: { cookie },
    });
    expect(listRes.statusCode).toBe(200);
    expect(listRes.json()).toEqual([]);
  });

  it('参数校验：subjects 缺失/空串、subject 非法、dailyMinutes 非法、examDate 非法、examDate 早于 startDate', async () => {
    const username = randName('sched');
    const cookie = await registerAndLogin(app, username);

    const r1 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?dailyMinutes=600&examDate=2026-12-19',
      headers: { cookie },
    });
    expect(r1.statusCode).toBe(400);
    expect(r1.json()).toEqual({ error: 'subjects 不能为空' });

    const r2 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=&dailyMinutes=600&examDate=2026-12-19',
      headers: { cookie },
    });
    expect(r2.statusCode).toBe(400);
    expect(r2.json()).toEqual({ error: 'subjects 不能为空' });

    const r3 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=nope&dailyMinutes=600&examDate=2026-12-19',
      headers: { cookie },
    });
    expect(r3.statusCode).toBe(400);
    expect(r3.json()).toEqual({ error: 'subject 非法' });

    const r4 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math&dailyMinutes=10&examDate=2026-12-19',
      headers: { cookie },
    });
    expect(r4.statusCode).toBe(400);
    expect(r4.json()).toEqual({ error: 'dailyMinutes 非法' });

    const r5 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math&dailyMinutes=600&examDate=2026-13-01',
      headers: { cookie },
    });
    expect(r5.statusCode).toBe(400);
    expect(r5.json()).toEqual({ error: 'examDate 非法' });

    const r6 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math&dailyMinutes=600&examDate=2026-10-19&startDate=2026-10-20',
      headers: { cookie },
    });
    expect(r6.statusCode).toBe(400);
    expect(r6.json()).toEqual({ error: 'examDate 不能早于 startDate' });
  });
});

describe('POST /api/plans/auto-schedule', () => {
  it('生成并写入：复习日期为 startDate+1/+3/+7/+15/+30', async () => {
    const username = randName('sched');
    const cookie = await registerAndLogin(app, username);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        examDate: '2026-12-19',
        startDate: '2026-10-20',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { created: number; skipped: number; items: Array<{ date: string; title: string; subject: string; plannedMinutes: number; kind?: string }> };
    expect(body.created).toBeGreaterThan(0);
    expect(body.skipped).toBe(0);

    const findByTitle = (t: string) => body.items.find((i) => i.title === t);
    const new1 = findByTitle('智能排期·数学 新学1');
    expect(new1).toBeDefined();
    expect(new1!.date).toBe('2026-10-20');

    expect(findByTitle('智能排期·数学 复习1-1天')!.date).toBe('2026-10-21');
    expect(findByTitle('智能排期·数学 复习1-3天')!.date).toBe('2026-10-23');
    expect(findByTitle('智能排期·数学 复习1-7天')!.date).toBe('2026-10-27');
    expect(findByTitle('智能排期·数学 复习1-15天')!.date).toBe('2026-11-04');
    expect(findByTitle('智能排期·数学 复习1-30天')!.date).toBe('2026-11-19');
  });

  it('幂等：第二次调用 created=0，总数不变', async () => {
    const username = randName('sched');
    const cookie = await registerAndLogin(app, username);

    const payload = {
      subjects: ['math'],
      dailyMinutes: 600,
      examDate: '2026-12-19',
      startDate: '2026-10-20',
    };

    const first = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload,
    });
    expect(first.statusCode).toBe(200);
    const firstBody = first.json() as { created: number; skipped: number };
    expect(firstBody.created).toBeGreaterThan(0);
    expect(firstBody.skipped).toBe(0);

    const listBefore = await app.inject({
      method: 'GET',
      url: '/api/plans?subject=math',
      headers: { cookie },
    });
    const beforeCount = (listBefore.json() as Array<unknown>).length;

    const second = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload,
    });
    expect(second.statusCode).toBe(200);
    const secondBody = second.json() as { created: number; skipped: number };
    expect(secondBody.created).toBe(0);
    expect(secondBody.skipped).toBe(firstBody.created);

    const listAfter = await app.inject({
      method: 'GET',
      url: '/api/plans?subject=math',
      headers: { cookie },
    });
    const afterCount = (listAfter.json() as Array<unknown>).length;
    expect(afterCount).toBe(beforeCount);
  });

  it('边界：examDate 早于 startDate、dailyMinutes=10、subjects=[]、subjects=[\'nope\'] 均 400', async () => {
    const username = randName('sched');
    const cookie = await registerAndLogin(app, username);

    const r1 = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        examDate: '2026-10-19',
        startDate: '2026-10-20',
      },
    });
    expect(r1.statusCode).toBe(400);
    expect(r1.json()).toEqual({ error: 'examDate 不能早于 startDate' });

    const r2 = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 10,
        examDate: '2026-12-19',
        startDate: '2026-10-20',
      },
    });
    expect(r2.statusCode).toBe(400);
    expect(r2.json()).toEqual({ error: 'dailyMinutes 非法' });

    const r3 = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: [],
        dailyMinutes: 600,
        examDate: '2026-12-19',
        startDate: '2026-10-20',
      },
    });
    expect(r3.statusCode).toBe(400);
    expect(r3.json()).toEqual({ error: 'subjects 不能为空' });

    const r4 = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['nope'],
        dailyMinutes: 600,
        examDate: '2026-12-19',
        startDate: '2026-10-20',
      },
    });
    expect(r4.statusCode).toBe(400);
    expect(r4.json()).toEqual({ error: 'subject 非法' });
  });

  it('超出 examDate 的条目被丢弃，返回 items 全部 date <= examDate', async () => {
    const username = randName('sched');
    const cookie = await registerAndLogin(app, username);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        examDate: '2026-12-19',
        startDate: '2026-12-17',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { created: number; skipped: number; discarded: number; items: Array<{ date: string; title: string }> };
    expect(body.discarded).toBeGreaterThan(0);
    for (const item of body.items) {
      expect(item.date <= '2026-12-19').toBe(true);
    }
  });

  it('用户隔离：用户 B 查不到用户 A 的计划', async () => {
    const nameA = randName('sched');
    const nameB = randName('sched');
    const cookieA = await registerAndLogin(app, nameA);
    const cookieB = await registerAndLogin(app, nameB);

    const resA = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieA },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        examDate: '2026-12-19',
        startDate: '2026-10-20',
      },
    });
    expect(resA.statusCode).toBe(200);
    expect((resA.json() as { created: number }).created).toBeGreaterThan(0);

    const listB = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: { cookie: cookieB },
    });
    expect(listB.statusCode).toBe(200);
    expect(listB.json()).toEqual([]);
  }, 30000);
});
