import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerExamsRoutes } from '../src/routes/exams';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('isolation related mistakes deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerExamsRoutes(app, db);
    registerMistakesRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });

  afterEach(async () => {
    await app.close();
  });

  it('B 查 A 的 exam 的 related-mistakes 返回 404 记录不存在', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const created = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: cookieA },
      payload: { subject: 'math', paper: 'p1', score: 80, totalScore: 100 },
    });
    expect(created.statusCode).toBe(201);
    const examId = created.json().id as number;

    const res = await app.inject({
      method: 'GET',
      url: `/api/exams/${examId}/related-mistakes`,
      headers: { cookie: cookieB },
    });
    expect(res.statusCode).toBe(404);
    expect(res.json()).toEqual({ error: '记录不存在' });
  });

  it('B 查不存在的 exam id 响应体与跨用户查询完全一致', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const created = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: cookieA },
      payload: { subject: 'math', paper: 'p1', score: 80, totalScore: 100 },
    });
    expect(created.statusCode).toBe(201);
    const examId = created.json().id as number;

    const crossUser = await app.inject({
      method: 'GET',
      url: `/api/exams/${examId}/related-mistakes`,
      headers: { cookie: cookieB },
    });

    const notExist = await app.inject({
      method: 'GET',
      url: '/api/exams/999999/related-mistakes',
      headers: { cookie: cookieB },
    });

    expect(crossUser.statusCode).toBe(404);
    expect(notExist.statusCode).toBe(404);
    expect(notExist.json()).toEqual(crossUser.json());
    expect(notExist.json()).toEqual({ error: '记录不存在' });
  });

  it('A 查自己的 exam 的 related-mistakes 返回 200 与数组', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    await registerAndLogin(app, rand('b'));

    const created = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: cookieA },
      payload: { subject: 'math', paper: 'p1', score: 80, totalScore: 100 },
    });
    expect(created.statusCode).toBe(201);
    const examId = created.json().id as number;

    const res = await app.inject({
      method: 'GET',
      url: `/api/exams/${examId}/related-mistakes`,
      headers: { cookie: cookieA },
    });
    expect(res.statusCode).toBe(200);
    expect(Array.isArray(res.json())).toBe(true);
  });

  it('id 为 abc 时返回 400 无效的 id', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    await registerAndLogin(app, rand('b'));

    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/abc/related-mistakes',
      headers: { cookie: cookieA },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 id' });
  });
});
