import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { registerFocusRoutes } from '../src/routes/focus';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('isolation focus planId cross user deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerPlansRoutes(app, db);
    registerFocusRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });

  it('B 使用 A 的 planId 建专注返回 404 计划不存在', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const planRes = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: cookieA },
      payload: {
        title: 'A计划',
        subject: 'math',
        plannedMinutes: 60,
        date: '2026-10-01',
      },
    });
    expect(planRes.statusCode).toBe(201);
    const planA = planRes.json() as { id: number };
    expect(Number.isInteger(planA.id)).toBe(true);

    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: cookieB },
      payload: {
        subject: 'math',
        minutes: 25,
        planId: planA.id,
      },
    });

    expect(res.statusCode).toBe(404);
    expect(res.json()).toEqual({ error: '计划不存在' });
  });

  it('B 使用不存在的 planId=999999 返回 404 与跨用户响应体完全一致', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const planRes = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: cookieA },
      payload: {
        title: 'A计划',
        subject: 'math',
        plannedMinutes: 60,
        date: '2026-10-01',
      },
    });
    expect(planRes.statusCode).toBe(201);
    const planA = planRes.json() as { id: number };

    const crossRes = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: cookieB },
      payload: {
        subject: 'math',
        minutes: 25,
        planId: planA.id,
      },
    });
    expect(crossRes.statusCode).toBe(404);

    const missingRes = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: cookieB },
      payload: {
        subject: 'math',
        minutes: 25,
        planId: 999999,
      },
    });

    expect(missingRes.statusCode).toBe(404);
    expect(missingRes.json()).toEqual(crossRes.json());
    expect(missingRes.json()).toEqual({ error: '计划不存在' });
  });

  it('B 使用自己的 planId 建专注返回 201 且 planId 正确回显', async () => {
    const cookieA = await registerAndLogin(app, rand('a'));
    const cookieB = await registerAndLogin(app, rand('b'));

    const planARes = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: cookieA },
      payload: {
        title: 'A计划',
        subject: 'math',
        plannedMinutes: 60,
        date: '2026-10-01',
      },
    });
    expect(planARes.statusCode).toBe(201);

    const planBRes = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: cookieB },
      payload: {
        title: 'B计划',
        subject: 'math',
        plannedMinutes: 45,
        date: '2026-10-02',
      },
    });
    expect(planBRes.statusCode).toBe(201);
    const planB = planBRes.json() as { id: number };
    expect(Number.isInteger(planB.id)).toBe(true);

    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: cookieB },
      payload: {
        subject: 'math',
        minutes: 25,
        planId: planB.id,
      },
    });

    expect(res.statusCode).toBe(201);
    const session = res.json() as {
      id: number;
      subject: string;
      minutes: number;
      startedAt: string;
      note: string | null;
      planId: number | null;
    };
    expect(session.planId).toBe(planB.id);
    expect(session.subject).toBe('math');
    expect(session.minutes).toBe(25);
    expect(session.note).toBe(null);
  });
});
