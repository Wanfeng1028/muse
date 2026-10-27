import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import Fastify, { type FastifyInstance } from 'fastify'
import { createDb } from '../src/db'
import { applyAuthHook, registerAuthRoutes } from '../src/auth'
import { registerAndLogin } from './test-utils'
import { registerPlansRoutes } from '../src/routes/plans';

type PlanId = string | number;

interface SubjectSummary {
  subject: string;
  total: number;
  done: number;
  plannedMinutes: number;
}

let app: FastifyInstance;
let db: ReturnType<typeof createDb>;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  registerPlansRoutes(app, db);
  await app.ready();
});

afterEach(async () => {
  await app.close();
});

function dateStr(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

async function createPlan(
  cookie: string,
  payload: { date: string; subject: string; title: string; plannedMinutes: number },
): Promise<PlanId> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/plans',
    headers: { cookie },
    payload,
  });
  expect(res.statusCode).toBe(201);
  return (res.json() as { id: PlanId }).id;
}

async function markDone(cookie: string, id: PlanId): Promise<void> {
  const res = await app.inject({
    method: 'PATCH',
    url: `/api/plans/${id}`,
    headers: { cookie },
    payload: { done: true },
  });
  expect(res.statusCode).toBe(200);
}

async function seedPlans(cookie: string): Promise<void> {
  const today = dateStr(0);
  const sixDaysAgo = dateStr(6);
  const sevenDaysAgo = dateStr(7);
  const fortyDaysAgo = dateStr(40);

  const p1 = await createPlan(cookie, { date: today, subject: 'math', title: 'math today 1', plannedMinutes: 120 });
  await createPlan(cookie, { date: today, subject: 'math', title: 'math today 2', plannedMinutes: 30 });
  await createPlan(cookie, { date: today, subject: 'english', title: 'english today', plannedMinutes: 60 });
  const p4 = await createPlan(cookie, { date: sixDaysAgo, subject: 'math', title: 'math 6d ago', plannedMinutes: 90 });
  await createPlan(cookie, { date: sevenDaysAgo, subject: 'english', title: 'english 7d ago', plannedMinutes: 45 });
  const p6 = await createPlan(cookie, { date: fortyDaysAgo, subject: 'math', title: 'math 40d ago', plannedMinutes: 240 });
  await createPlan(cookie, { date: fortyDaysAgo, subject: 'english', title: 'english 40d ago', plannedMinutes: 200 });

  await markDone(cookie, p1);
  await markDone(cookie, p4);
  await markDone(cookie, p6);
}

async function fetchSummary(cookie: string, query: string): Promise<SubjectSummary[]> {
  const res = await app.inject({
    method: 'GET',
    url: `/api/plans/summary/by-subject${query}`,
    headers: { cookie },
  });
  expect(res.statusCode).toBe(200);
  const subjects = (res.json() as { subjects: SubjectSummary[] }).subjects
  return subjects.map((s) => ({ subject: s.subject, total: s.total, done: s.done, plannedMinutes: s.plannedMinutes }))
}

describe('GET /api/plans/summary/by-subject days 参数', () => {
  it('days=7 时排除 7 天前及更早的计划，仅统计今天与 6 天前', async () => {
    const cookie = await registerAndLogin(app, 'plansbysubjectdays');
    await seedPlans(cookie);

    const subjects = await fetchSummary(cookie, '?days=7');

    expect(subjects).toEqual([
      { subject: 'math', total: 3, done: 2, plannedMinutes: 240 },
      { subject: 'english', total: 1, done: 0, plannedMinutes: 60 },
    ]);
    expect(subjects[0].subject).toBe('math');
    expect(subjects[1].subject).toBe('english');
  });

  it('days=1 时只统计今天的计划', async () => {
    const cookie = await registerAndLogin(app, 'plansbysubjectdays');
    await seedPlans(cookie);

    const subjects = await fetchSummary(cookie, '?days=1');

    expect(subjects).toEqual([
      { subject: 'math', total: 2, done: 1, plannedMinutes: 150 },
      { subject: 'english', total: 1, done: 0, plannedMinutes: 60 },
    ]);
    expect(subjects[0].subject).toBe('math');
    expect(subjects[1].subject).toBe('english');
  });

  it('days 超过 31 时钳制为 31（40 天前排除、6 天前保留，days=100 与 days=31 结果相同）', async () => {
    const cookie = await registerAndLogin(app, 'plansbysubjectdays');
    await seedPlans(cookie);

    const subjects100 = await fetchSummary(cookie, '?days=100');
    expect(subjects100).toEqual([
      { subject: 'math', total: 3, done: 2, plannedMinutes: 240 },
      { subject: 'english', total: 2, done: 0, plannedMinutes: 105 },
    ]);
    expect(subjects100[0].subject).toBe('math');
    expect(subjects100[1].subject).toBe('english');

    const subjects31 = await fetchSummary(cookie, '?days=31');
    expect(subjects31).toEqual(subjects100);
  });

  it('days 非法（abc、1.5、1x、空串）时返回 400', async () => {
    const cookie = await registerAndLogin(app, 'plansbysubjectdays');
    await seedPlans(cookie);

    for (const q of ['abc', '1.5', '1x', '']) {
      const res = await app.inject({
        method: 'GET',
        url: `/api/plans/summary/by-subject?days=${q}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect((res.json() as { error: string }).error).toBe('days 参数无效');
    }
  });

  it('days 不传时统计全部历史，40 天前的计划也计入', async () => {
    const cookie = await registerAndLogin(app, 'plansbysubjectdays');
    await seedPlans(cookie);

    const subjects = await fetchSummary(cookie, '');

    expect(subjects).toEqual([
      { subject: 'math', total: 4, done: 3, plannedMinutes: 480 },
      { subject: 'english', total: 3, done: 0, plannedMinutes: 305 },
    ]);
    expect(subjects[0].subject).toBe('math');
    expect(subjects[1].subject).toBe('english');
  });

  it('未登录访问返回 401', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/summary/by-subject?days=7',
    });
    expect(res.statusCode).toBe(401);
  });
});