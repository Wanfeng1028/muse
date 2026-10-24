import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerPlansRoutes } from '../src/routes/plans';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: any;
let app: FastifyInstance;
let authCookie: string;
let authCookie2: string;

function localYMD(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

async function createPlan(cookie: string, payload: { date: string; subject: string; title: string; plannedMinutes: number }) {
  const res = await app.inject({ method: 'POST', url: '/api/plans', headers: { cookie }, payload });
  expect(res.statusCode).toBe(201);
  return res.json();
}

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  registerPlansRoutes(app, db);
  await app.ready();
  authCookie = await registerAndLogin(app, 'overdueuser');
  authCookie2 = await registerAndLogin(app, 'overdueuser2');
});

afterEach(async () => {
  await app.close();
});

describe('plans-overdue', () => {
  it('逾期未完成计划被返回', async () => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const ydStr = localYMD(yesterday);

    await createPlan(authCookie, { date: ydStr, subject: 'math', title: 'OverdueTask', plannedMinutes: 30 });

    const res = await app.inject({ method: 'GET', url: '/api/plans/overdue', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.count).toBe(1);
    expect(body.plans[0].title).toBe('OverdueTask');
    expect(body.plans[0].done).toBe(false);
  });

  it('已完成的逾期计划不返回', async () => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const ydStr = localYMD(yesterday);

    const plan = await createPlan(authCookie, { date: ydStr, subject: 'math', title: 'DoneTask', plannedMinutes: 30 });
    await app.inject({ method: 'PATCH', url: `/api/plans/${plan.id}`, headers: { cookie: authCookie }, payload: { done: true } });

    const res = await app.inject({ method: 'GET', url: '/api/plans/overdue', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.count).toBe(0);
  });

  it('今天与未来的计划不返回', async () => {
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    const todayStr = localYMD(today);
    const tmrStr = localYMD(tomorrow);

    await createPlan(authCookie, { date: todayStr, subject: 'math', title: 'TodayTask', plannedMinutes: 30 });
    await createPlan(authCookie, { date: tmrStr, subject: 'math', title: 'FutureTask', plannedMinutes: 30 });

    const res = await app.inject({ method: 'GET', url: '/api/plans/overdue', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.count).toBe(0);
  });

  it('排序为date升序再id升序', async () => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const dayBefore = new Date(today);
    dayBefore.setDate(today.getDate() - 2);
    const ydStr = localYMD(yesterday);
    const dbStr = localYMD(dayBefore);

    await createPlan(authCookie, { date: ydStr, subject: 'math', title: 'B', plannedMinutes: 30 });
    await createPlan(authCookie, { date: ydStr, subject: 'math', title: 'A', plannedMinutes: 30 });
    await createPlan(authCookie, { date: dbStr, subject: 'math', title: 'C', plannedMinutes: 30 });

    const res = await app.inject({ method: 'GET', url: '/api/plans/overdue', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.count).toBe(3);
    const dates = body.plans.map((p: any) => p.date);
    for (let i = 1; i < dates.length; i++) {
      expect(dates[i] >= dates[i - 1]).toBe(true);
    }
    const byDate: Record<string, any[]> = {};
    for (const p of body.plans) {
      if (!byDate[p.date]) byDate[p.date] = [];
      byDate[p.date].push(p);
    }
    for (const group of Object.values(byDate)) {
      for (let i = 1; i < group.length; i++) {
        expect(group[i].id > group[i - 1].id).toBe(true);
      }
    }
  });

  it('用户隔离', async () => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const ydStr = localYMD(yesterday);

    await createPlan(authCookie2, { date: ydStr, subject: 'math', title: 'User2Task', plannedMinutes: 30 });

    const res1 = await app.inject({ method: 'GET', url: '/api/plans/overdue', headers: { cookie: authCookie } });
    expect(res1.statusCode).toBe(200);
    expect(res1.json().count).toBe(0);

    const res2 = await app.inject({ method: 'GET', url: '/api/plans/overdue', headers: { cookie: authCookie2 } });
    expect(res2.statusCode).toBe(200);
    expect(res2.json().count).toBe(1);
  });

  it('空库返回count 0与空数组', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/plans/overdue', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.count).toBe(0);
    expect(body.plans).toEqual([]);
  });

  it('未登录返回401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/plans/overdue' });
    expect(res.statusCode).toBe(401);
  });
});
