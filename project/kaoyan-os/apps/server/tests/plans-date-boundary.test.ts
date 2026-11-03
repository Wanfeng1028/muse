import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerPlansRoutes } from '../src/routes/plans';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

const DATE_ERR = 'date 格式非法，应为 YYYY-MM-DD';

describe('plans date boundary', () => {
  let app: FastifyInstance;
  let authCookie = '';
  let db: ReturnType<typeof createDb>;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerPlansRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'plansboundary');
  });

  afterEach(async () => {
    await app.close();
  });

  it('闰年 2024-02-29 新建返回 201', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-02-29', subject: 'math', title: 'leap', plannedMinutes: 60 },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body.date).toBe('2024-02-29');
    expect(body.done).toBe(false);
  });

  it('平年 2023-02-29 GET 返回 400 与精确错误文案', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2023-02-29' });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: DATE_ERR });
  });

  it('平年 2023-02-29 POST 返回 400', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2023-02-29', subject: 'math', title: 'x', plannedMinutes: 30 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: DATE_ERR });
  });

  it('世纪闰年 2000-02-29 合法 POST 201', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2000-02-29', subject: 'english', title: 'c1', plannedMinutes: 45 },
    });
    expect(res.statusCode).toBe(201);
    expect(res.json().date).toBe('2000-02-29');
  });

  it('非世纪闰年 1900-02-29 非法 GET 400', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=1900-02-29' });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: DATE_ERR });
  });

  it('2024-02-30 非法、2024-04-31 非法、2024-04-30 合法、2024-02-29 合法', async () => {
    const bad1 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2024-02-30' });
    expect(bad1.statusCode).toBe(400);
    expect(bad1.json()).toEqual({ error: DATE_ERR });

    const bad2 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2024-04-31' });
    expect(bad2.statusCode).toBe(400);
    expect(bad2.json()).toEqual({ error: DATE_ERR });

    const ok1 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2024-04-30' });
    expect(ok1.statusCode).toBe(200);

    const ok2 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2024-02-29' });
    expect(ok2.statusCode).toBe(200);
  });

  it('月份回绕 2024-13-01 与 2024-00-10 均非法 400', async () => {
    const bad1 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2024-13-01' });
    expect(bad1.statusCode).toBe(400);
    expect(bad1.json()).toEqual({ error: DATE_ERR });

    const bad2 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2024-00-10' });
    expect(bad2.statusCode).toBe(400);
    expect(bad2.json()).toEqual({ error: DATE_ERR });
  });

  it('日期回绕 2024-01-00 与 2024-01-32 均非法 400', async () => {
    const bad1 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2024-01-00' });
    expect(bad1.statusCode).toBe(400);
    expect(bad1.json()).toEqual({ error: DATE_ERR });

    const bad2 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans?date=2024-01-32' });
    expect(bad2.statusCode).toBe(400);
    expect(bad2.json()).toEqual({ error: DATE_ERR });
  });

  it('格式变体全部非法 400', async () => {
    const variants = ['2024-1-05', '24-01-05', '2024/01/05', ' 2024-01-05', '2024-01-05 ', ''];
    for (const v of variants) {
      const res = await app.inject({ headers: { cookie: authCookie },
        method: 'GET',
        url: `/api/plans?date=${encodeURIComponent(v)}`,
      });
      expect(res.statusCode, `variant=${JSON.stringify(v)}`).toBe(400);
      expect(res.json()).toEqual({ error: DATE_ERR });
    }
  });

  it('POST 非字符串 date（数字）返回 400', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: { date: 20240105, subject: 'math', title: 'x', plannedMinutes: 30 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: DATE_ERR });
  });

  it('远期远古 0001-01-01 与 9999-12-31 均合法 POST 201', async () => {
    const res1 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: { date: '0001-01-01', subject: 'politics', title: 'a', plannedMinutes: 10 },
    });
    expect(res1.statusCode).toBe(201);
    expect(res1.json().date).toBe('0001-01-01');

    const res2 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: { date: '9999-12-31', subject: 'politics', title: 'b', plannedMinutes: 10 },
    });
    expect(res2.statusCode).toBe(201);
    expect(res2.json().date).toBe('9999-12-31');
  });

  it('PATCH 非法 date 返回 400 且库中原值不变', async () => {
    const created = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-03-15', subject: 'math', title: 'keep', plannedMinutes: 20 },
    });
    expect(created.statusCode).toBe(201);
    const createdBody = created.json();
    const id = createdBody.id as number;

    const patch = await app.inject({ headers: { cookie: authCookie },
      method: 'PATCH',
      url: `/api/plans/${id}`,
      payload: { date: '2023-02-29' },
    });
    expect(patch.statusCode).toBe(400);
    expect(patch.json()).toEqual({ error: DATE_ERR });

    const after = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/plans?date=2024-03-15` });
    expect(after.statusCode).toBe(200);
    const rows = after.json() as Array<{ id: number; date: string }>;
    const found = rows.find((r) => r.id === id);
    expect(found).toBeDefined();
    expect(found?.date).toBe('2024-03-15');

    const gone = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/plans?date=2023-02-29` });
    expect(gone.statusCode).toBe(400);
  });

  it('summary 非法日期 400、合法日期 200 且 body.date 精确', async () => {
    const bad = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans/summary?date=2023-02-29' });
    expect(bad.statusCode).toBe(400);
    expect(bad.json()).toEqual({ error: DATE_ERR });

    const ok = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans/summary?date=2024-02-29' });
    expect(ok.statusCode).toBe(200);
    const okBody = ok.json();
    expect(okBody.date).toBe('2024-02-29');
    expect(okBody.total).toBe(0);
    expect(okBody.done).toBe(0);
    expect(okBody.completionRate).toBe(0);
  });
});