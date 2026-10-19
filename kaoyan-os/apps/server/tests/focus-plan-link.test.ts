/**
 * tests/focus-plan-link.test.ts
 *
 * 覆盖口径（v1.11.0 计划-专注关联）：
 * 1. POST /api/focus 携带合法 planId 时写入关联并回读（返回体 + 列表项均含 planId）。
 * 2. planId 非法值（0/-1/1.5/'abc'）一律 400，error 含 'planId'。
 * 3. planId 指向不存在计划或他人计划 → 404 '计划不存在'，且不产生专注记录。
 * 4. GET /api/plans/summary 的 actualMinutes 按 plan_id 归属聚合专注 minutes（LEFT JOIN），
 *    无关联计划为 0；total/completionRate 手算校验。
 * 5. DELETE /api/plans/:id 先将 focus_sessions.plan_id 置 NULL 再删计划，专注记录保留。
 * 6. 达成率聚合按“关联归属”而非“专注日期”：跨日期 startedAt 仍计入该计划 actualMinutes。
 * 7. 不带 planId 时 planId 为 null 的回归路径（写入 + 回读）。
 */

import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerPlansRoutes } from '../src/routes/plans';
import { registerFocusRoutes } from '../src/routes/focus';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin, authHeaders } from './test-utils';
import { todayStr } from '../src/db';
import type { DatabaseSync } from 'node:sqlite';

// ---------------------------------------------------------------------------
// 响应体类型（严格断言用）
// ---------------------------------------------------------------------------

interface FocusSession {
  id: number;
  subject: string;
  minutes: number;
  planId: number | null;
  startedAt: string;
  note: string | null;
}

interface PlanSummaryItem {
  id: number;
  title: string;
  subject: string;
  plannedMinutes: number;
  actualMinutes: number;
  done: boolean;
}

interface PlanSummary {
  date: string;
  total: number;
  done: number;
  completionRate: number;
  plans: PlanSummaryItem[];
}

interface PlanRow {
  id: number;
  date: string;
  subject: string;
  title: string;
  planned_minutes: number;
  done: number;
  created_at: string;
}

interface FocusRow {
  id: number;
  user_id: number;
  subject: string;
  minutes: number;
  plan_id: number | null;
}

interface ErrorBody {
  error: string;
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

let app: FastifyInstance;
let db: DatabaseSync;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerPlansRoutes(app, db);
  registerFocusRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

// ---------------------------------------------------------------------------
// 辅助
// ---------------------------------------------------------------------------

/** 创建用户并返回其 id 与认证头。 */
async function setupUser(username: string): Promise<{ id: number; headers: Record<string, string> }> {
  const cookie = await registerAndLogin(app, username);
  const row = db.prepare('SELECT id FROM users WHERE username = ?').get(username) as { id: number };
  return { id: row.id, headers: authHeaders(cookie) };
}

/** 创建今日计划，返回其 id。 */
async function createPlan(
  headers: Record<string, string>,
  body: { title: string; subject: string; plannedMinutes: number; date?: string },
): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/plans',
    headers,
    payload: { date: todayStr(), ...body },
  });
  expect(res.statusCode).toBe(201);
  const created = res.json() as { id: number };
  return created.id;
}

/** 发一条 focus，返回响应。 */
async function postFocus(
  headers: Record<string, string>,
  payload: Record<string, unknown>,
) {
  return app.inject({
    method: 'POST',
    url: '/api/focus',
    headers,
    payload,
  });
}

// ---------------------------------------------------------------------------
// 1. 关联写入与读出
// ---------------------------------------------------------------------------

it('1. 携带合法 planId 创建专注：返回体与列表项 planId 均为该计划 id', async () => {
  const { headers } = await setupUser('focuslink_u1');
  const planId = await createPlan(headers, { title: 'Math Plan', subject: 'math', plannedMinutes: 60 });

  const createRes = await postFocus(headers, { subject: 'math', minutes: 40, planId });
  expect(createRes.statusCode).toBe(201);
  const created = createRes.json() as FocusSession;
  expect(created.planId).toBe(planId);
  expect(created.subject).toBe('math');
  expect(created.minutes).toBe(40);

  const listRes = await app.inject({ method: 'GET', url: '/api/focus', headers });
  expect(listRes.statusCode).toBe(200);
  const list = listRes.json() as FocusSession[];
  expect(list.length).toBe(1);
  expect(list[0].planId).toBe(planId);
  expect(list[0].minutes).toBe(40);
});

// ---------------------------------------------------------------------------
// 2. planId 非法值 400
// ---------------------------------------------------------------------------

it('2. planId 非法值 0/-1/1.5/abc 均 400 且 error 含 planId', async () => {
  const { headers } = await setupUser('focuslink_u2');

  const badValues: unknown[] = [0, -1, 1.5, 'abc'];
  for (const planId of badValues) {
    const res = await postFocus(headers, { subject: 'math', minutes: 10, planId });
    expect(res.statusCode).toBe(400);
    const body = res.json() as ErrorBody;
    expect(body.error).toContain('planId');
  }
});

// ---------------------------------------------------------------------------
// 3. planId 指向不存在 / 他人计划 404
// ---------------------------------------------------------------------------

it('3. planId 指向不存在或他人计划：404 计划不存在且不写专注记录', async () => {
  const userA = await setupUser('focuslink_ua');
  const userB = await setupUser('focuslink_ub');

  // 不存在的计划
  const missRes = await postFocus(userB.headers, { subject: 'math', minutes: 10, planId: 999999 });
  expect(missRes.statusCode).toBe(404);
  expect((missRes.json() as ErrorBody).error).toBe('计划不存在');

  // A 的计划被 B 引用
  const aPlanId = await createPlan(userA.headers, { title: 'A Plan', subject: 'math', plannedMinutes: 30 });
  const crossRes = await postFocus(userB.headers, { subject: 'math', minutes: 10, planId: aPlanId });
  expect(crossRes.statusCode).toBe(404);
  expect((crossRes.json() as ErrorBody).error).toBe('计划不存在');

  // B 无任何专注记录
  const bListRes = await app.inject({ method: 'GET', url: '/api/focus', headers: userB.headers });
  expect(bListRes.statusCode).toBe(200);
  const bList = bListRes.json() as FocusSession[];
  expect(bList).toEqual([]);
});

// ---------------------------------------------------------------------------
// 4. summary 聚合达成率
// ---------------------------------------------------------------------------

it('4. summary 按 plan_id 聚合 actualMinutes，无关联计划为 0', async () => {
  const { headers } = await setupUser('focuslink_u4');

  const p1 = await createPlan(headers, { title: 'P1', subject: 'math', plannedMinutes: 60 });
  const p2 = await createPlan(headers, { title: 'P2', subject: 'english', plannedMinutes: 30 });

  // P1 关联 40 + 30，无关联 20
  const r1 = await postFocus(headers, { subject: 'math', minutes: 40, planId: p1 });
  expect(r1.statusCode).toBe(201);
  const r2 = await postFocus(headers, { subject: 'math', minutes: 30, planId: p1 });
  expect(r2.statusCode).toBe(201);
  const r3 = await postFocus(headers, { subject: 'english', minutes: 20 });
  expect(r3.statusCode).toBe(201);

  const sumRes = await app.inject({
    method: 'GET',
    url: `/api/plans/summary?date=${todayStr()}`,
    headers,
  });
  expect(sumRes.statusCode).toBe(200);
  const summary = sumRes.json() as PlanSummary;

  expect(summary.total).toBe(2);
  expect(summary.plans.length).toBe(2);

  const p1Item = summary.plans.find((p) => p.id === p1) as PlanSummaryItem;
  const p2Item = summary.plans.find((p) => p.id === p2) as PlanSummaryItem;
  expect(p1Item.actualMinutes).toBe(70);
  expect(p2Item.actualMinutes).toBe(0);
  expect(p1Item.plannedMinutes).toBe(60);
  expect(p2Item.plannedMinutes).toBe(30);
  expect(p1Item.done).toBe(false);
  expect(p2Item.done).toBe(false);

  // 无 done，完成率 0
  expect(summary.done).toBe(0);
  expect(summary.completionRate).toBe(0);
});

// ---------------------------------------------------------------------------
// 5. 删计划置空不断链
// ---------------------------------------------------------------------------

it('5. DELETE 计划将关联 focus 的 plan_id 置 NULL，专注记录保留，summary 只剩另一计划', async () => {
  const { headers } = await setupUser('focuslink_u5');

  const p1 = await createPlan(headers, { title: 'P1', subject: 'math', plannedMinutes: 60 });
  const p2 = await createPlan(headers, { title: 'P2', subject: 'english', plannedMinutes: 30 });

  // P1 关联 2 条，另 1 条无关联
  const a = await postFocus(headers, { subject: 'math', minutes: 40, planId: p1 });
  expect(a.statusCode).toBe(201);
  const b = await postFocus(headers, { subject: 'math', minutes: 30, planId: p1 });
  expect(b.statusCode).toBe(201);
  const c = await postFocus(headers, { subject: 'english', minutes: 20 });
  expect(c.statusCode).toBe(201);

  const delRes = await app.inject({ method: 'DELETE', url: `/api/plans/${p1}`, headers });
  expect(delRes.statusCode).toBe(200);

  // 3 条 focus 仍在，原先关联 P1 的两条 planId 为 null
  const listRes = await app.inject({ method: 'GET', url: '/api/focus', headers });
  expect(listRes.statusCode).toBe(200);
  const list = listRes.json() as FocusSession[];
  expect(list.length).toBe(3);
  const linked = list.filter((f) => f.planId === null);
  expect(linked.length).toBe(3);
  expect(list.every((f) => f.planId === null)).toBe(true);

  // summary 只剩 P2
  const sumRes = await app.inject({
    method: 'GET',
    url: `/api/plans/summary?date=${todayStr()}`,
    headers,
  });
  expect(sumRes.statusCode).toBe(200);
  const summary = sumRes.json() as PlanSummary;
  expect(summary.plans.length).toBe(1);
  expect(summary.plans[0].id).toBe(p2);
  expect(summary.plans[0].actualMinutes).toBe(0);
  expect(summary.total).toBe(1);
});

// ---------------------------------------------------------------------------
// 6. 关联按 plan_id 不按日期
// ---------------------------------------------------------------------------

it('6. 达成率按关联归属而非专注日期：跨日期 startedAt 仍计入计划 actualMinutes', async () => {
  const { headers } = await setupUser('focuslink_u6');

  const planId = await createPlan(headers, { title: 'Cross Date', subject: 'math', plannedMinutes: 60 });

  // startedAt 为昨日（2026-01-05），仍通过 planId 关联
  const res = await postFocus(headers, {
    subject: 'math',
    minutes: 25,
    planId,
    startedAt: '2026-01-05T10:00:00',
  });
  expect(res.statusCode).toBe(201);
  const created = res.json() as FocusSession;
  expect(created.planId).toBe(planId);
  expect(created.minutes).toBe(25);

  // 今日 summary 仍应统计到该 25 分钟：口径为关联归属，不按专注日期过滤
  const sumRes = await app.inject({
    method: 'GET',
    url: `/api/plans/summary?date=${todayStr()}`,
    headers,
  });
  expect(sumRes.statusCode).toBe(200);
  const summary = sumRes.json() as PlanSummary;
  expect(summary.plans.length).toBe(1);
  const item = summary.plans.find((p) => p.id === planId) as PlanSummaryItem;
  expect(item.actualMinutes).toBe(25);
});

// ---------------------------------------------------------------------------
// 7. 不带 planId 回归
// ---------------------------------------------------------------------------

it('7. 不带 planId 创建专注：返回体与列表项 planId 均为 null', async () => {
  const { headers } = await setupUser('focuslink_u7');

  const res = await postFocus(headers, { subject: 'english', minutes: 15 });
  expect(res.statusCode).toBe(201);
  const created = res.json() as FocusSession;
  expect(created.planId).toBeNull();
  expect(created.subject).toBe('english');
  expect(created.minutes).toBe(15);

  const listRes = await app.inject({ method: 'GET', url: '/api/focus', headers });
  expect(listRes.statusCode).toBe(200);
  const list = listRes.json() as FocusSession[];
  expect(list.length).toBe(1);
  expect(list[0].planId).toBeNull();
});

// ---------------------------------------------------------------------------
// 迁移幂等（附带校验，不计入 7 个 it 口径）
// ---------------------------------------------------------------------------

describe('focus_sessions.plan_id 列存在性', () => {
  it('新库中 focus_sessions 含 plan_id 列且可为 NULL', async () => {
    // 通过 API 行为间接验证：创建不带 planId 的记录后读回为 null
    const { headers } = await setupUser('focuslink_col');
    const res = await postFocus(headers, { subject: 'math', minutes: 5 });
    expect(res.statusCode).toBe(201);
    const created = res.json() as FocusSession;
    expect(created.planId).toBeNull();

    // 直接查库确认列存在
    const db = createDb(':memory:');
    // 触发迁移建表
    const cols = db
      .prepare("PRAGMA table_info('focus_sessions')")
      .all() as Array<{ name: string }>;
    const hasPlanId = cols.some((c) => c.name === 'plan_id');
    expect(hasPlanId).toBe(true);
  });
});
