import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('isolation quiz generate deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerMistakesRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });

  it('B 的 quiz generate 返回空数组，看不到 A 的错题', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const createA1 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'A错1' },
    });
    expect(createA1.statusCode).toBe(201);

    const createA2 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'english', title: 'A错2' },
    });
    expect(createA2.statusCode).toBe(201);

    const res = await app.inject({
      method: 'POST',
      url: '/api/mistakes/quiz/generate',
      headers: { cookie: cookieB },
      payload: {},
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual([]);
  });

  it('A 的 quiz generate 返回自己的 2 条错题', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));
    expect(typeof cookieB).toBe('string');

    const createA1 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'A错1' },
    });
    expect(createA1.statusCode).toBe(201);

    const createA2 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'english', title: 'A错2' },
    });
    expect(createA2.statusCode).toBe(201);

    const res = await app.inject({
      method: 'POST',
      url: '/api/mistakes/quiz/generate',
      headers: { cookie: cookieA },
      payload: {},
    });
    expect(res.statusCode).toBe(200);
    const items = res.json() as Array<{ id: number; title: string }>;
    expect(items.length).toBe(2);
    expect(items.map((i) => i.title)).toEqual(['A错1', 'A错2']);
  });

  it('B 建 1 条后各自只见自己的错题', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const createA1 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'A错1' },
    });
    expect(createA1.statusCode).toBe(201);

    const createA2 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'english', title: 'A错2' },
    });
    expect(createA2.statusCode).toBe(201);

    const createB1 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieB },
      payload: { subject: 'math', title: 'B错1' },
    });
    expect(createB1.statusCode).toBe(201);

    const resB = await app.inject({
      method: 'POST',
      url: '/api/mistakes/quiz/generate',
      headers: { cookie: cookieB },
      payload: {},
    });
    expect(resB.statusCode).toBe(200);
    const itemsB = resB.json() as Array<{ id: number; title: string }>;
    expect(itemsB.length).toBe(1);
    expect(itemsB.map((i) => i.title)).toEqual(['B错1']);

    const resA = await app.inject({
      method: 'POST',
      url: '/api/mistakes/quiz/generate',
      headers: { cookie: cookieA },
      payload: {},
    });
    expect(resA.statusCode).toBe(200);
    const itemsA = resA.json() as Array<{ id: number; title: string }>;
    expect(itemsA.length).toBe(2);
    expect(itemsA.map((i) => i.title)).toEqual(['A错1', 'A错2']);
  });
});
