import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { registerPlansRoutes } from '../src/routes/plans';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { registerExamsRoutes } from '../src/routes/exams';
import { registerWordsRoutes } from '../src/routes/words';
import { registerFocusRoutes } from '../src/routes/focus';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('cross-user 404 oracle deep isolation', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let cookieA: string;
  let cookieB: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerPlansRoutes(app, db);
    registerMistakesRoutes(app, db);
    registerExamsRoutes(app, db);
    registerWordsRoutes(app, db);
    registerFocusRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    cookieA = await registerAndLogin(app, 'alice_oracle');
    cookieB = await registerAndLogin(app, 'bob_oracle');
  });

  afterEach(async () => {
    await app.close();
  });

  it('plans 写隔离：B PATCH/DELETE A 的 plan 均 404，A 的 plan 仍存在', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: cookieA },
      payload: { title: 'A 的计划', subject: 'math', plannedMinutes: 60, date: '2025-01-01' },
    });
    expect(createRes.statusCode).toBe(201);
    const planId = createRes.json().id as number;

    const patchRes = await app.inject({
      method: 'PATCH',
      url: `/api/plans/${planId}`,
      headers: { cookie: cookieB },
      payload: { title: 'B 篡改' },
    });
    expect(patchRes.statusCode).toBe(404);
    expect(patchRes.json()).toEqual({ error: '计划不存在' });

    const delRes = await app.inject({
      method: 'DELETE',
      url: `/api/plans/${planId}`,
      headers: { cookie: cookieB },
    });
    expect(delRes.statusCode).toBe(404);
    expect(delRes.json()).toEqual({ error: '计划不存在' });

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: { cookie: cookieA },
    });
    expect(listRes.statusCode).toBe(200);
    const list = listRes.json() as Array<{ id: number }>;
    expect(list.some((p) => p.id === planId)).toBe(true);
  });

  it('mistakes 写隔离：B PATCH/DELETE A 的错题均 404，A 的错题仍在', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'A 的错题' },
    });
    expect(createRes.statusCode).toBe(201);
    const mistakeId = createRes.json().id as number;

    const patchRes = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${mistakeId}`,
      headers: { cookie: cookieB },
      payload: { mastered: true },
    });
    expect(patchRes.statusCode).toBe(404);
    expect(patchRes.json()).toEqual({ error: '错题不存在' });

    const delRes = await app.inject({
      method: 'DELETE',
      url: `/api/mistakes/${mistakeId}`,
      headers: { cookie: cookieB },
    });
    expect(delRes.statusCode).toBe(404);
    expect(delRes.json()).toEqual({ error: '错题不存在' });

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
    });
    expect(listRes.statusCode).toBe(200);
    const list = listRes.json() as Array<{ id: number }>;
    expect(list.some((m) => m.id === mistakeId)).toBe(true);
  });

  it('exams 写隔离：B DELETE A 的考试记录 404，A 的列表仍包含该记录', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: cookieA },
      payload: {
        subject: 'math',
        paper: 'A 的卷子',
        score: 100,
        totalScore: 150,
        takenAt: '2025-01-01',
      },
    });
    expect(createRes.statusCode).toBe(201);
    const examId = createRes.json().id as number;

    const delRes = await app.inject({
      method: 'DELETE',
      url: `/api/exams/${examId}`,
      headers: { cookie: cookieB },
    });
    expect(delRes.statusCode).toBe(404);
    expect(delRes.json()).toEqual({ error: '记录不存在' });

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: { cookie: cookieA },
    });
    expect(listRes.statusCode).toBe(200);
    const list = listRes.json() as Array<{ id: number }>;
    expect(list.some((e) => e.id === examId)).toBe(true);
  });

  it('exams 联查隔离：B 查 A 的 exam related-mistakes 返回 404 记录不存在', async () => {
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: cookieA },
      payload: {
        subject: 'english',
        paper: 'A 的英语卷',
        score: 80,
        totalScore: 100,
        takenAt: '2025-02-01',
      },
    });
    expect(createRes.statusCode).toBe(201);
    const examId = createRes.json().id as number;

    const relRes = await app.inject({
      method: 'GET',
      url: `/api/exams/${examId}/related-mistakes`,
      headers: { cookie: cookieB },
    });
    expect(relRes.statusCode).toBe(404);
    expect(relRes.json()).toEqual({ error: '记录不存在' });
  });

  it('存在性 oracle 一致性：跨用户真实 id 与随机不存在大 id 的响应完全一致', async () => {
    const planRes = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: cookieA },
      payload: { title: 'oracle plan', subject: 'math', plannedMinutes: 30, date: '2025-03-01' },
    });
    expect(planRes.statusCode).toBe(201);
    const planId = planRes.json().id as number;

    const mistakeRes = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'oracle mistake' },
    });
    expect(mistakeRes.statusCode).toBe(201);
    const mistakeId = mistakeRes.json().id as number;

    const examRes = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: cookieA },
      payload: {
        subject: 'politics',
        paper: 'oracle exam',
        score: 60,
        totalScore: 100,
        takenAt: '2025-03-02',
      },
    });
    expect(examRes.statusCode).toBe(201);
    const examId = examRes.json().id as number;

    const patchPlanReal = await app.inject({
      method: 'PATCH',
      url: `/api/plans/${planId}`,
      headers: { cookie: cookieB },
      payload: { title: 'x' },
    });
    const patchPlanFake = await app.inject({
      method: 'PATCH',
      url: '/api/plans/999999',
      headers: { cookie: cookieB },
      payload: { title: 'x' },
    });
    expect(patchPlanReal.statusCode).toBe(patchPlanFake.statusCode);
    expect(patchPlanReal.json()).toEqual(patchPlanFake.json());

    const patchMistakeReal = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${mistakeId}`,
      headers: { cookie: cookieB },
      payload: { mastered: true },
    });
    const patchMistakeFake = await app.inject({
      method: 'PATCH',
      url: '/api/mistakes/999999',
      headers: { cookie: cookieB },
      payload: { mastered: true },
    });
    expect(patchMistakeReal.statusCode).toBe(patchMistakeFake.statusCode);
    expect(patchMistakeReal.json()).toEqual(patchMistakeFake.json());

    const delExamReal = await app.inject({
      method: 'DELETE',
      url: `/api/exams/${examId}`,
      headers: { cookie: cookieB },
    });
    const delExamFake = await app.inject({
      method: 'DELETE',
      url: '/api/exams/999999',
      headers: { cookie: cookieB },
    });
    expect(delExamReal.statusCode).toBe(delExamFake.statusCode);
    expect(delExamReal.json()).toEqual(delExamFake.json());
  });

  it('list 读隔离：A 五类各建一条，B 的五个列表全部为空数组', async () => {
    const planRes = await app.inject({
      method: 'POST',
      url: '/api/plans',
      headers: { cookie: cookieA },
      payload: { title: 'list plan', subject: 'math', plannedMinutes: 45, date: '2025-04-01' },
    });
    expect(planRes.statusCode).toBe(201);

    const mistakeRes = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'list mistake' },
    });
    expect(mistakeRes.statusCode).toBe(201);

    const examRes = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: cookieA },
      payload: {
        subject: 'major',
        paper: 'list exam',
        score: 70,
        totalScore: 100,
        takenAt: '2025-04-02',
      },
    });
    expect(examRes.statusCode).toBe(201);

    const wordRes = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: { cookie: cookieA },
      payload: { word: 'apple', meaning: '苹果' },
    });
    expect(wordRes.statusCode).toBe(201);

    const focusRes = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: cookieA },
      payload: { subject: 'math', minutes: 60, startedAt: '2025-04-03' },
    });
    expect(focusRes.statusCode).toBe(201);

    for (const url of ['/api/plans', '/api/mistakes', '/api/exams', '/api/words', '/api/focus']) {
      const res = await app.inject({
        method: 'GET',
        url,
        headers: { cookie: cookieB },
      });
      expect(res.statusCode).toBe(200);
      expect(res.json()).toEqual([]);
    }
  });

  it('mistakes summary 隔离：B 的 summary 全部为零', async () => {
    const m1 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'sum1' },
    });
    expect(m1.statusCode).toBe(201);

    const m2 = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      headers: { cookie: cookieA },
      payload: { subject: 'math', title: 'sum2' },
    });
    expect(m2.statusCode).toBe(201);
    const m2Id = m2.json().id as number;

    const markMastered = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${m2Id}`,
      headers: { cookie: cookieA },
      payload: { mastered: true },
    });
    expect(markMastered.statusCode).toBe(200);

    const sumRes = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: cookieB },
    });
    expect(sumRes.statusCode).toBe(200);
    const body = sumRes.json() as {
      subject: string;
      total: number;
      mastered: number;
      unmastered: number;
      masteredRate: number;
    };
    expect(body.total).toBe(0);
    expect(body.mastered).toBe(0);
    expect(body.unmastered).toBe(0);
    expect(body.masteredRate).toBe(0);
  });

  it('focus stats 隔离：B 的 stats 全部为零', async () => {
    const focusRes = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: cookieA },
      payload: { subject: 'math', minutes: 60, startedAt: '2025-05-01' },
    });
    expect(focusRes.statusCode).toBe(201);

    const statsRes = await app.inject({
      method: 'GET',
      url: '/api/focus/stats',
      headers: { cookie: cookieB },
    });
    expect(statsRes.statusCode).toBe(200);
    const body = statsRes.json() as { totalMinutes: number; todayMinutes: number };
    expect(body.totalMinutes).toBe(0);
    expect(body.todayMinutes).toBe(0);
  });
});