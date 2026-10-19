import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerPlansRoutes } from '../src/routes/plans';
import { registerAndLogin, authHeaders } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

beforeAll(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerPlansRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

describe('plans 多用户隔离', () => {
  it('summary 只统计当前用户的数据', async () => {
    const cookieA = await registerAndLogin(app, 'plan_user_a');
    const cookieB = await registerAndLogin(app, 'plan_user_b');

    // A 创建 2 条（1 done），B 创建 1 条（0 done），同一天
    const date = '2030-01-01';
    for (const [cookie, title, done] of [
      [cookieA, 'A-1', true],
      [cookieA, 'A-2', false],
      [cookieB, 'B-1', false],
    ] as const) {
      const created = await app.inject({
        method: 'POST',
        url: '/api/plans',
        headers: authHeaders(cookie),
        payload: { date, subject: 'math', title, plannedMinutes: 30 },
      });
      expect(created.statusCode).toBe(201);
      if (done) {
        const id = created.json().id as number;
        const patched = await app.inject({
          method: 'PATCH',
          url: `/api/plans/${id}`,
          headers: authHeaders(cookie),
          payload: { done: true },
        });
        expect(patched.statusCode).toBe(200);
      }
    }

    const sumA = await app.inject({
      method: 'GET',
      url: `/api/plans/summary?date=${date}`,
      headers: authHeaders(cookieA),
    });
    expect(sumA.statusCode).toBe(200);
    const bodyA = sumA.json() as { date: string; total: number; done: number };
    expect(bodyA.total).toBe(2);
    expect(bodyA.done).toBe(1);

    const sumB = await app.inject({
      method: 'GET',
      url: `/api/plans/summary?date=${date}`,
      headers: authHeaders(cookieB),
    });
    expect(sumB.statusCode).toBe(200);
    const bodyB = sumB.json() as { date: string; total: number; done: number };
    expect(bodyB.total).toBe(1);
    expect(bodyB.done).toBe(0);
  });

  it('GET /api/plans 只返回当前用户的计划', async () => {
    const cookieA = await registerAndLogin(app, 'plan_list_a');
    const cookieB = await registerAndLogin(app, 'plan_list_b');

    const date = '2030-02-02';
    await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: authHeaders(cookieA),
      payload: { date, subject: 'english', title: 'A 计划', plannedMinutes: 20 },
    });
    await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: authHeaders(cookieB),
      payload: { date, subject: 'english', title: 'B 计划', plannedMinutes: 20 },
    });

    const listA = await app.inject({
      method: 'GET',
      url: `/api/plans?date=${date}`,
      headers: authHeaders(cookieA),
    });
    expect(listA.statusCode).toBe(200);
    const arrA = listA.json() as Array<{ title: string }>;
    expect(arrA.map((p) => p.title)).toEqual(['A 计划']);

    const listB = await app.inject({
      method: 'GET',
      url: `/api/plans?date=${date}`,
      headers: authHeaders(cookieB),
    });
    expect(listB.statusCode).toBe(200);
    const arrB = listB.json() as Array<{ title: string }>;
    expect(arrB.map((p) => p.title)).toEqual(['B 计划']);
  });

  it('访问他人计划 id 返回 404（不泄露存在性）', async () => {
    const cookieA = await registerAndLogin(app, 'plan_cross_a');
    const cookieB = await registerAndLogin(app, 'plan_cross_b');

    const created = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: authHeaders(cookieA),
      payload: { subject: 'math', title: 'A 私有', plannedMinutes: 10 },
    });
    expect(created.statusCode).toBe(201);
    const id = created.json().id as number;

    const patchByB = await app.inject({
      method: 'PATCH',
      url: `/api/plans/${id}`,
      headers: authHeaders(cookieB),
      payload: { done: true },
    });
    expect(patchByB.statusCode).toBe(404);

    const deleteByB = await app.inject({
      method: 'DELETE',
      url: `/api/plans/${id}`,
      headers: authHeaders(cookieB),
    });
    expect(deleteByB.statusCode).toBe(404);

    // A 仍然拥有该记录且未被改动
    const listA = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: authHeaders(cookieA),
    });
    const arrA = listA.json() as Array<{ id: number; title: string; done: boolean }>;
    const own = arrA.find((p) => p.id === id);
    expect(own).toBeDefined();
    expect(own!.title).toBe('A 私有');
    expect(own!.done).toBe(false);
  });

  it('POST 返回的计划属于当前用户（回查带 user_id 约束）', async () => {
    const cookieA = await registerAndLogin(app, 'plan_post_a');
    const cookieB = await registerAndLogin(app, 'plan_post_b');

    const created = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: authHeaders(cookieA),
      payload: { subject: 'math', title: 'A only', plannedMinutes: 15 },
    });
    expect(created.statusCode).toBe(201);
    const id = created.json().id as number;

    // 直接查库确认归属
    const row = db
      .prepare('SELECT user_id FROM plans WHERE id = ?')
      .get(id) as { user_id: number } | undefined;
    expect(row).toBeDefined();

    const userA = db
      .prepare('SELECT id FROM users WHERE username = ?')
      .get('plan_post_a') as { id: number } | undefined;
    const userB = db
      .prepare('SELECT id FROM users WHERE username = ?')
      .get('plan_post_b') as { id: number } | undefined;
    expect(row!.user_id).toBe(userA!.id);
    expect(row!.user_id).not.toBe(userB!.id);

    // B 无法通过任何方式看到它
    const listB = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: authHeaders(cookieB),
    });
    const arrB = listB.json() as Array<{ id: number }>;
    expect(arrB.some((p) => p.id === id)).toBe(false);
  });
});
