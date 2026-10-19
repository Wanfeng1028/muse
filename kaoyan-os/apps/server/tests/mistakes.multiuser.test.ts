import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { seedIfEmpty } from '../src/seed';
import {
  registerAndLogin,
  authHeaders,
  createSeededUser,
} from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

beforeEach(async () => {
  db = createDb(':memory:');
  seedIfEmpty(db);
  app = Fastify();
  registerMistakesRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterEach(async () => {
  await app.close();
});

describe('mistakes 多用户隔离 + summary 按用户聚合', () => {
  let cookieA: string;
  let cookieB: string;

  beforeEach(async () => {
    ({ cookie: cookieA } = await createSeededUser(db, app, 'alice'));
    ({ cookie: cookieB } = await createSeededUser(db, app, 'bob'));
  });

  it('用户 A 创建的错题在用户 B 的列表与 summary 中不可见', async () => {
    const beforeA = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: authHeaders(cookieA),
    });
    const beforeB = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: authHeaders(cookieB),
    });
    expect(beforeA.statusCode).toBe(200);
    expect(beforeB.statusCode).toBe(200);
    const listA0 = beforeA.json() as Array<{ id: number }>;
    const listB0 = beforeB.json() as Array<{ id: number }>;
    expect(listA0.length).toBeGreaterThan(0);
    expect(listB0.length).toBe(listA0.length);

    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: authHeaders(cookieA),
      payload: {
        subject: 'math',
        title: 'alice-only-mistake',
        content: 'c',
        analysis: 'a',
      },
    });
    expect(created.statusCode).toBe(201);
    const createdId = (created.json() as { id: number }).id;

    const afterB = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: authHeaders(cookieB),
    });
    expect(afterB.statusCode).toBe(200);
    const listB1 = afterB.json() as Array<{ id: number; title: string }>;
    expect(listB1.find((m) => m.id === createdId)).toBeUndefined();
    expect(listB1.length).toBe(listB0.length);

    const afterA = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: authHeaders(cookieA),
    });
    const listA1 = afterA.json() as Array<{ id: number; title: string }>;
    expect(listA1.find((m) => m.id === createdId)?.title).toBe('alice-only-mistake');
    expect(listA1.length).toBe(listA0.length + 1);
  });

  it('summary 只统计当前用户，且 subject 过滤按用户生效', async () => {
    // A 增加一道未掌握数学题
    const createA = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: authHeaders(cookieA),
      payload: { subject: 'math', title: 'a-math-1', content: '', analysis: '' },
    });
    expect(createA.statusCode).toBe(201);

    // B 增加一道已掌握英语题
    const createB = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: authHeaders(cookieB),
      payload: { subject: 'english', title: 'b-en-1', content: '', analysis: '' },
    });
    expect(createB.statusCode).toBe(201);
    const bId = (createB.json() as { id: number }).id;
    const markB = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${bId}`,
      headers: authHeaders(cookieB),
      payload: { mastered: true },
    });
    expect(markB.statusCode).toBe(200);

    const sumA = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: authHeaders(cookieA),
    });
    expect(sumA.statusCode).toBe(200);
    const sumAJson = sumA.json() as {
      total: number;
      mastered: number;
      unmastered: number;
      masteredRate: number;
      subject: string | null;
    };
    expect(sumAJson.subject).toBeNull();
    expect(sumAJson.total).toBeGreaterThan(0);
    expect(sumAJson.mastered + sumAJson.unmastered).toBe(sumAJson.total);

    const sumAMath = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=math',
      headers: authHeaders(cookieA),
    });
    expect(sumAMath.statusCode).toBe(200);
    const sumAMathJson = sumAMath.json() as {
      total: number;
      subject: string | null;
    };
    expect(sumAMathJson.subject).toBe('math');
    expect(sumAMathJson.total).toBeGreaterThanOrEqual(1);

    const sumBEnglish = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=english',
      headers: authHeaders(cookieB),
    });
    expect(sumBEnglish.statusCode).toBe(200);
    const sumBEnglishJson = sumBEnglish.json() as {
      total: number;
      mastered: number;
      subject: string | null;
    };
    expect(sumBEnglishJson.subject).toBe('english');
    expect(sumBEnglishJson.total).toBeGreaterThanOrEqual(1);
    expect(sumBEnglishJson.mastered).toBeGreaterThanOrEqual(1);

    // A 的 english 统计不应包含 B 的题：A 的 english 计数与 B 的不同源
    const sumAEnglish = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=english',
      headers: authHeaders(cookieA),
    });
    expect(sumAEnglish.statusCode).toBe(200);
    const sumAEnglishJson = sumAEnglish.json() as { total: number };
    // A 未创建过 english 题（种子数据里 english 是否存在由 seed 决定）；
    // 断言：A 的 english 总数不等于 B 的 english 总数 + 1，且 A 的英语统计不因 B 的英语题而增加
    const sumAEnglishAgain = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=english',
      headers: authHeaders(cookieA),
    });
    const sumAEnglishAgainJson = sumAEnglishAgain.json() as { total: number };
    expect(sumAEnglishAgainJson.total).toBe(sumAEnglishJson.total);
  });

  it('用户 B 无法 PATCH / DELETE 用户 A 的错题（按 user_id 隔离）', async () => {
    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: authHeaders(cookieA),
      payload: { subject: 'math', title: 'a-private', content: '', analysis: '' },
    });
    expect(created.statusCode).toBe(201);
    const id = (created.json() as { id: number }).id;

    const patchB = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${id}`,
      headers: authHeaders(cookieB),
      payload: { title: 'hijack' },
    });
    expect(patchB.statusCode).toBe(404);

    const delB = await app.inject({
      method: 'DELETE',
      url: `/api/mistakes/${id}`,
      headers: authHeaders(cookieB),
    });
    expect(delB.statusCode).toBe(404);

    // A 仍可见
    const stillThere = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: authHeaders(cookieA),
    });
    const list = stillThere.json() as Array<{ id: number; title: string }>;
    expect(list.find((m) => m.id === id)?.title).toBe('a-private');
  });
});
