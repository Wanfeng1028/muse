import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖 plans 全路由 subject 非法矩阵（列表过滤、创建、更新、预览、自动排期），不与 isolation-subject-400-plans.deep1/2/3.test.ts 重叠

describe('isolation illegal subject plans routes deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerPlansRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });

  afterEach(async () => { await app.close(); });

  it('GET /api/plans 过滤 subject=nope 返回 400', async () => {
    const cookie = await registerAndLogin(app, rand('subj_list'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans?subject=nope',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'subject 非法' });
  });

  it('POST /api/plans subject=nope 返回 400', async () => {
    const cookie = await registerAndLogin(app, rand('subj_create'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie },
      payload: { title: 't', subject: 'nope', plannedMinutes: 60, date: '2026-10-01' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'subject 非法' });
  });

  it('PATCH /api/plans/:id subject=nope 返回 400', async () => {
    const cookie = await registerAndLogin(app, rand('subj_patch'));
    const created = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie },
      payload: { title: 'ok', subject: 'math', plannedMinutes: 60, date: '2026-10-01' },
    });
    expect(created.statusCode).toBe(201);
    const planId = created.json().id as number;
    const res = await app.inject({
      method: 'PATCH',
      url: `/api/plans/${planId}`,
      headers: { cookie },
      payload: { subject: 'nope' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'subject 非法' });
  });

  it('GET /api/plans/auto-schedule/preview subjects=nope 返回 400', async () => {
    const cookie = await registerAndLogin(app, rand('subj_prev'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=nope&dailyMinutes=60&examDate=2026-12-31&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'subject 非法' });
  });

  it('POST /api/plans/auto-schedule subjects=[nope] 返回 400', async () => {
    const cookie = await registerAndLogin(app, rand('subj_auto'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: { subjects: ['nope'], dailyMinutes: 60, examDate: '2026-12-31', startDate: '2026-11-01' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'subject 非法' });
  });
});
