import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('isolation illegal subject mistakes routes deep4', () => {
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

  it('GET /api/mistakes/summary?subject=nope 返回 400 无效的 subject 参数', async () => {
    const cookie = await registerAndLogin(app, rand('sumsub'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=nope',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject 参数' });
  });

  it('GET /api/mistakes?subject=nope 返回 400 无效的 subject', async () => {
    const cookie = await registerAndLogin(app, rand('listsub'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes?subject=nope',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject' });
  });

  it('POST /api/mistakes subject=nope 返回 400 subject 非法', async () => {
    const cookie = await registerAndLogin(app, rand('postsub'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie },
      payload: { subject: 'nope', title: 't' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'subject 非法' });
  });

  it('PATCH /api/mistakes/:id subject=nope 返回 400 subject 非法', async () => {
    const cookie = await registerAndLogin(app, rand('patchsub'));
    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie },
      payload: { subject: 'math', title: 't' },
    });
    expect(created.statusCode).toBe(201);
    const id = created.json().id as number;
    const res = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${id}`,
      headers: { cookie },
      payload: { subject: 'nope' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'subject 非法' });
  });

  it('POST /api/mistakes/quiz/generate subject=nope 返回 400 subject 非法', async () => {
    const cookie = await registerAndLogin(app, rand('gensub'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/mistakes/quiz/generate',
      headers: { cookie },
      payload: { subject: 'nope' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'subject 非法' });
  });
});
