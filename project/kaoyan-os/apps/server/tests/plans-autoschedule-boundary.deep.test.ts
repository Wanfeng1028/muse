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

afterAll(async () => { await app.close(); });

function randName(prefix: string): string { return prefix + Math.random().toString(36).slice(2, 10); }

describe('GET /api/plans/auto-schedule/preview 边界', () => {
  it('缺 subjects、空串、非法值均返回 400', async () => {
    const cookie = await registerAndLogin(app, randName('x'));

    const res1 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?dailyMinutes=600&examDate=2026-12-19&startDate=2026-10-20',
      headers: { cookie }
    });
    expect(res1.statusCode).toBe(400);

    const res2 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=&dailyMinutes=600&examDate=2026-12-19&startDate=2026-10-20',
      headers: { cookie }
    });
    expect(res2.statusCode).toBe(400);

    const res3 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math,xxx&dailyMinutes=600&examDate=2026-12-19&startDate=2026-10-20',
      headers: { cookie }
    });
    expect(res3.statusCode).toBe(400);
    expect(JSON.parse(res3.body).error).toContain('subject');
  });

  it('dailyMinutes 越界、小数、非数字均返回 400', async () => {
    const cookie = await registerAndLogin(app, randName('x'));
    const base = '/api/plans/auto-schedule/preview?subjects=math&examDate=2026-12-19&startDate=2026-10-20';

    const res1 = await app.inject({
      method: 'GET',
      url: base + '&dailyMinutes=29',
      headers: { cookie }
    });
    expect(res1.statusCode).toBe(400);

    const res2 = await app.inject({
      method: 'GET',
      url: base + '&dailyMinutes=1441',
      headers: { cookie }
    });
    expect(res2.statusCode).toBe(400);

    const res3 = await app.inject({
      method: 'GET',
      url: base + '&dailyMinutes=60.5',
      headers: { cookie }
    });
    expect(res3.statusCode).toBe(400);

    const res4 = await app.inject({
      method: 'GET',
      url: base + '&dailyMinutes=abc',
      headers: { cookie }
    });
    expect(res4.statusCode).toBe(400);
  });

  it('examDate 非法日期与 startDate 非法格式返回 400', async () => {
    const cookie = await registerAndLogin(app, randName('x'));

    const res1 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math&dailyMinutes=600&examDate=2024-02-30&startDate=2026-10-20',
      headers: { cookie }
    });
    expect(res1.statusCode).toBe(400);

    const res2 = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math&dailyMinutes=600&examDate=2026-12-19&startDate=not-a-date',
      headers: { cookie }
    });
    expect(res2.statusCode).toBe(400);
  });

  it('examDate 早于 startDate 返回 400 且 error 含早于', async () => {
    const cookie = await registerAndLogin(app, randName('x'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math&dailyMinutes=600&examDate=2026-10-19&startDate=2026-10-20',
      headers: { cookie }
    });
    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body).error).toContain('早于');
  });

  it('多科目 math,english 返回 200 且 items 包含两种 subject', async () => {
    const cookie = await registerAndLogin(app, randName('x'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math,english&dailyMinutes=600&examDate=2026-12-19&startDate=2026-10-20',
      headers: { cookie }
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body.items)).toBe(true);
    const subjects = new Set(body.items.map((item: any) => item.subject));
    expect(subjects.has('math')).toBe(true);
    expect(subjects.has('english')).toBe(true);
  });
});

describe('POST /api/plans/auto-schedule 边界', () => {
  it('subjects 非数组或空数组返回 400', async () => {
    const cookie = await registerAndLogin(app, randName('x'));

    const res1 = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie, 'content-type': 'application/json' },
      payload: {
        subjects: 'math',
        dailyMinutes: 120,
        examDate: '2026-12-19',
        startDate: '2026-10-20'
      }
    });
    expect(res1.statusCode).toBe(400);

    const res2 = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie, 'content-type': 'application/json' },
      payload: {
        subjects: [],
        dailyMinutes: 120,
        examDate: '2026-12-19',
        startDate: '2026-10-20'
      }
    });
    expect(res2.statusCode).toBe(400);
  });

  it('dailyMinutes 传字符串返回 400', async () => {
    const cookie = await registerAndLogin(app, randName('x'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie, 'content-type': 'application/json' },
      payload: {
        subjects: ['math'],
        dailyMinutes: '600',
        examDate: '2026-12-19',
        startDate: '2026-10-20'
      }
    });
    expect(res.statusCode).toBe(400);
  });

  it('成功创建后 GET /api/plans 列表条数增加', async () => {
    const cookie = await registerAndLogin(app, randName('x'));

    const before = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: { cookie }
    });
    expect(before.statusCode).toBe(200);
    const beforeCount = JSON.parse(before.body).length;

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie, 'content-type': 'application/json' },
      payload: {
        subjects: ['math'],
        dailyMinutes: 120,
        examDate: '2026-12-19',
        startDate: '2026-10-20'
      }
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.created).toBeGreaterThan(0);
    expect(typeof body.skipped).toBe('number');

    const after = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: { cookie }
    });
    expect(after.statusCode).toBe(200);
    const afterCount = JSON.parse(after.body).length;
    expect(afterCount).toBeGreaterThan(beforeCount);
  });

  it('preview 不写库，前后列表条数不变', async () => {
    const cookie = await registerAndLogin(app, randName('x'));

    const before = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: { cookie }
    });
    expect(before.statusCode).toBe(200);
    const beforeCount = JSON.parse(before.body).length;

    const preview = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math&dailyMinutes=600&examDate=2026-12-19&startDate=2026-10-20',
      headers: { cookie }
    });
    expect(preview.statusCode).toBe(200);

    const after = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: { cookie }
    });
    expect(after.statusCode).toBe(200);
    const afterCount = JSON.parse(after.body).length;
    expect(afterCount).toBe(beforeCount);
  });

  it('discarded 为数组（考后复习节点被丢弃）', async () => {
    const cookie = await registerAndLogin(app, randName('x'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie, 'content-type': 'application/json' },
      payload: {
        subjects: ['math'],
        dailyMinutes: 30,
        examDate: '2026-12-19',
        startDate: '2026-12-16'
      }
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(typeof body.discarded).toBe('number');
  });
});