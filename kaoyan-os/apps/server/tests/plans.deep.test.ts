import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

async function makeApp(): Promise<{ app: FastifyInstance; db: DatabaseSync; cookie: string }> {
  const db = createDb(':memory:');
  const app = Fastify();
  registerPlansRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  const cookie = await registerAndLogin(app, 'plansdeep');
  return { app, db, cookie };
}


describe('plans routes deep', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let authCookie: string;

  beforeEach(async () => {
    const built = await makeApp();
    app = built.app;
    db = built.db;
    authCookie = built.cookie;
  });


  afterEach(async () => {
    await app.close();
    db.close();
  });

  it('跨月排程：2 月 28 日与 3 月 1 日按日期升序返回', async () => {
    const created = [];
    for (const [date, title] of [
      ['2025-03-01', '三月第一天'],
      ['2025-02-28', '二月最后一天'],
    ] as const) {
      const res = await app.inject({
        method: 'POST',
        url: '/api/plans',
        headers: { cookie: authCookie },
        payload: { date, subject: 'math', title, plannedMinutes: 60 },
      });

      expect(res.statusCode).toBe(201);
      created.push(res.json());
    }
    const list = await app.inject({ method: 'GET', url: '/api/plans', headers: { cookie: authCookie } });
    expect(list.statusCode).toBe(200);
    const rows = list.json() as Array<{ date: string; title: string }>;
    expect(rows.length).toBe(2);

    expect(rows[0].date).toBe('2025-02-28');
    expect(rows[0].title).toBe('二月最后一天');
    expect(rows[1].date).toBe('2025-03-01');
    expect(rows[1].title).toBe('三月第一天');
  });

  it('闰年 2 月 29 日合法，2 月 30 日非法', async () => {
    const ok = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2024-02-29', subject: 'english', title: '闰年多一天', plannedMinutes: 30 },
    });

    expect(ok.statusCode).toBe(201);
    expect(ok.json().date).toBe('2024-02-29');

    const bad = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2024-02-30', subject: 'english', title: '不存在的日期', plannedMinutes: 30 },
    });

    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('date 格式非法，应为 YYYY-MM-DD');
  });

  it('空计划汇总：total 为 0，completionRate 为 0', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/summary?date=2025-01-01',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as { date: string; total: number; done: number; completionRate: number };
    expect(body.date).toBe('2025-01-01');
    expect(body.total).toBe(0);
    expect(body.done).toBe(0);
    expect(body.completionRate).toBe(0);
  });

  it('汇总：3 条完成 2 条，completionRate 为 0.6667', async () => {
    const ids: number[] = [];
    for (const title of ['A', 'B', 'C']) {
      const res = await app.inject({
        method: 'POST',
        url: '/api/plans',
        headers: { cookie: authCookie },
        payload: { date: '2025-06-01', subject: 'politics', title, plannedMinutes: 45 },
      });

      expect(res.statusCode).toBe(201);
      ids.push(res.json().id as number);
    }
    for (const id of ids.slice(0, 2)) {
      const patch = await app.inject({
        method: 'PATCH',
        url: `/api/plans/${id}`,
        headers: { cookie: authCookie },
        payload: { done: true },
      });

      expect(patch.statusCode).toBe(200);
      expect(patch.json().done).toBe(true);
    }
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/summary?date=2025-06-01',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as { total: number; done: number; completionRate: number };
    expect(body.total).toBe(3);
    expect(body.done).toBe(2);
    expect(body.completionRate).toBe(0.6667);
  });

  it('plannedMinutes 边界：0 与 1441 被拒，1 与 1440 通过', async () => {
    const low = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-05-05', subject: 'math', title: '零分钟', plannedMinutes: 0 },
    });

    expect(low.statusCode).toBe(400);
    expect(low.json().error).toBe('plannedMinutes 必须为 1~1440 的数字');

    const high = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-05-05', subject: 'math', title: '超过一天', plannedMinutes: 1441 },
    });

    expect(high.statusCode).toBe(400);
    expect(high.json().error).toBe('plannedMinutes 必须为 1~1440 的数字');

    const min = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-05-05', subject: 'math', title: '一分钟', plannedMinutes: 1 },
    });

    expect(min.statusCode).toBe(201);
    expect(min.json().plannedMinutes).toBe(1);

    const max = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-05-05', subject: 'math', title: '一整天', plannedMinutes: 1440 },
    });

    expect(max.statusCode).toBe(201);
    expect(max.json().plannedMinutes).toBe(1440);
  });

  it('查询过滤：date 非法返回 400，subject 非法返回 400，合法组合只返回匹配项', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-04-01', subject: 'math', title: '数学一', plannedMinutes: 60 },
    });
    await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-04-01', subject: 'english', title: '英语一', plannedMinutes: 60 },
    });
    await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-04-02', subject: 'math', title: '数学二', plannedMinutes: 60 },
    });

    const badDate = await app.inject({ method: 'GET', url: '/api/plans?date=2025-13-40', headers: { cookie: authCookie } });
    expect(badDate.statusCode).toBe(400);
    expect(badDate.json().error).toBe('date 格式非法，应为 YYYY-MM-DD');

    const badSubject = await app.inject({ method: 'GET', url: '/api/plans?subject=physics', headers: { cookie: authCookie } });
    expect(badSubject.statusCode).toBe(400);
    expect(badSubject.json().error).toBe('subject 非法');

    const filtered = await app.inject({
      method: 'GET',
      url: '/api/plans?date=2025-04-01&subject=math',
      headers: { cookie: authCookie },
    });

    expect(filtered.statusCode).toBe(200);
    const rows = filtered.json() as Array<{ title: string; subject: string; date: string }>;
    expect(rows.length).toBe(1);
    expect(rows[0].title).toBe('数学一');
    expect(rows[0].subject).toBe('math');
    expect(rows[0].date).toBe('2025-04-01');
  });

  it('更新：不存在的 id 返回 404，非法 id 返回 400', async () => {
    const missing = await app.inject({
      method: 'PATCH',
      url: '/api/plans/99999',
      headers: { cookie: authCookie },
      payload: { done: true },
    });

    expect(missing.statusCode).toBe(404);
    expect(missing.json().error).toBe('计划不存在');

    const bad = await app.inject({
      method: 'PATCH',
      url: '/api/plans/abc',
      headers: { cookie: authCookie },
      payload: { done: true },
    });

    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('id 非法');
  });

  it('删除：先删返回 200，重复删返回 404', async () => {
    const created = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-07-07', subject: 'english', title: '待删除', plannedMinutes: 20 },
    });

    expect(created.statusCode).toBe(201);
    const id = created.json().id as number;

    const first = await app.inject({ method: 'DELETE', url: `/api/plans/${id}`, headers: { cookie: authCookie } });
    expect(first.statusCode).toBe(200);

    const second = await app.inject({ method: 'DELETE', url: `/api/plans/${id}`, headers: { cookie: authCookie } });
    expect(second.statusCode).toBe(404);
    expect(second.json().error).toBe('计划不存在');

    const list = await app.inject({ method: 'GET', url: '/api/plans', headers: { cookie: authCookie } });
    expect(list.json().length).toBe(0);

  });

  it('新建缺省日期使用今天，返回 createdAt 为 ISO 字符串', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { subject: 'politics', title: '无日期计划', plannedMinutes: 90 },
    });

    expect(res.statusCode).toBe(201);
    const body = res.json() as { date: string; createdAt: string; done: boolean };
    const today = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const expectToday = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
    expect(body.date).toBe(expectToday);
    expect(body.done).toBe(false);
    expect(typeof body.createdAt).toBe('string');
    expect(new Date(body.createdAt).toISOString()).toBe(body.createdAt);
  });

  it('title 空白被拒，subject 非法被拒', async () => {
    const blank = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-08-08', subject: 'math', title: '   ', plannedMinutes: 30 },
    });

    expect(blank.statusCode).toBe(400);
    expect(blank.json().error).toBe('title 不能为空');

    const badSubject = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: authCookie },
      payload: { date: '2025-08-08', subject: 'physics', title: '物理计划', plannedMinutes: 30 },
    });

    expect(badSubject.statusCode).toBe(400);
    expect(badSubject.json().error).toBe('subject 非法');
  });
});