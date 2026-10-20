import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerExamsRoutes } from '../src/routes/exams';
import { registerFocusRoutes } from '../src/routes/focus';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('isolation illegal subject exams focus routes deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerExamsRoutes(app, db);
    registerFocusRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });

  it('GET /api/exams 非法 subject 返回 400 无效的 subject 参数', async () => {
    const cookie = await registerAndLogin(app, rand('exams_list_bad'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams?subject=nope',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject 参数' });
  });

  it('GET /api/exams/trend 非法 subject 返回 400 无效的 subject 参数', async () => {
    const cookie = await registerAndLogin(app, rand('exams_trend_bad'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/trend?subject=nope',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject 参数' });
  });

  it('GET /api/exams/summary 非法 subject 返回 400 无效的 subject 参数', async () => {
    const cookie = await registerAndLogin(app, rand('exams_sum_bad'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary?subject=nope',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject 参数' });
  });

  it('GET /api/exams/export 非法 subject 返回 400 无效的 subject 参数', async () => {
    const cookie = await registerAndLogin(app, rand('exams_export_bad'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export?subject=nope',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject 参数' });
  });

  it('POST /api/exams 非法 subject 返回 400 无效的 subject', async () => {
    const cookie = await registerAndLogin(app, rand('exams_post_bad'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie },
      payload: { subject: 'nope', paper: 'p', score: 10, totalScore: 100 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject' });
  });

  it('POST /api/focus 非法 subject 返回 400 invalid subject', async () => {
    const cookie = await registerAndLogin(app, rand('focus_post_bad'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie },
      payload: { subject: 'nope', minutes: 25 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'invalid subject' });
  });
});
