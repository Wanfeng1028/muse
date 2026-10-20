import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { registerExamsRoutes } from '../src/routes/exams';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('isolation source exams deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerMistakesRoutes(app, db);
    registerExamsRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });

  it('用户 B 查询用户 A 的错题的 source-exams 返回 404 错题不存在', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'A错题' },
    });
    expect(created.statusCode).toBe(201);
    const mistakeId = created.json().id as number;

    const res = await app.inject({
      method: 'GET',
      url: `/api/mistakes/${mistakeId}/source-exams`,
      headers: { cookie: cookieB },
    });
    expect(res.statusCode).toBe(404);
    expect(res.json()).toEqual({ error: '错题不存在' });
  });

  it('用户 B 查询不存在的错题 id 返回 404，响应体与跨用户用例完全一致', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'A错题' },
    });
    expect(created.statusCode).toBe(201);
    const mistakeId = created.json().id as number;

    const crossUser = await app.inject({
      method: 'GET',
      url: `/api/mistakes/${mistakeId}/source-exams`,
      headers: { cookie: cookieB },
    });
    expect(crossUser.statusCode).toBe(404);

    const missing = await app.inject({
      method: 'GET',
      url: '/api/mistakes/999999/source-exams',
      headers: { cookie: cookieB },
    });
    expect(missing.statusCode).toBe(404);
    expect(missing.json()).toEqual(crossUser.json());
  });

  it('用户 A 查询自己的错题的 source-exams 返回 200 且为数组', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    await registerAndLogin(app, rand('b'));

    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'A错题' },
    });
    expect(created.statusCode).toBe(201);
    const mistakeId = created.json().id as number;

    const res = await app.inject({
      method: 'GET',
      url: `/api/mistakes/${mistakeId}/source-exams`,
      headers: { cookie: cookieA },
    });
    expect(res.statusCode).toBe(200);
    expect(Array.isArray(res.json())).toBe(true);
  });

  it('非法 id 返回 400 id 无效', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    await registerAndLogin(app, rand('b'));

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/xyz/source-exams',
      headers: { cookie: cookieA },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'id 非法' });
  });
});
