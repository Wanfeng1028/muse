import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerPlansRoutes } from '../src/routes/plans';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';
import { kindOf, computeDayLoads } from '../src/schedule-stats';

let db: any;
let app: FastifyInstance;
let authCookie: string;
let authCookie2: string;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  registerPlansRoutes(app, db);
  await app.ready();
  authCookie = await registerAndLogin(app, 'rangoverload');
});

afterEach(async () => {
  await app.close();
});

async function createPlan(
  cookie: string,
  payload: { date: string; subject: string; title: string; plannedMinutes: number }
) {
  const res = await app.inject({
    method: 'POST',
    url: '/api/plans',
    headers: { cookie },
    payload,
  });
  expect(res.statusCode).toBe(201);
  return res.json();
}

describe('kindOf', () => {
  it('识别 new', () => {
    expect(kindOf('智能排期·数学 新学1')).toBe('new');
  });

  it('识别 review', () => {
    expect(kindOf('智能排期·数学 复习1-3天')).toBe('review');
  });

  it('其他为 manual', () => {
    expect(kindOf('自己加的计划')).toBe('manual');
  });

  it('含 " 新学" 子串也算 new', () => {
    expect(kindOf('智能排期·英语 新学习惯')).toBe('new');
  });
});

describe('computeDayLoads 纯函数', () => {
  it('空天：3 天无计划，每天一条，totalMinutes 0，overloaded false，items 空', () => {
    const loads = computeDayLoads([], 240, '2026-10-21', 3);
    expect(loads).toHaveLength(3);
    expect(loads.map((d) => d.date)).toEqual(['2026-10-21', '2026-10-22', '2026-10-23']);
    for (const d of loads) {
      expect(d.totalMinutes).toBe(0);
      expect(d.overloaded).toBe(false);
      expect(d.items).toEqual([]);
    }
  });

  it('排序：同日两条 30/60 分钟，items[0].plannedMinutes 为 60', () => {
    const plans = [
      {
        id: 1,
        date: '2026-10-21',
        subject: 'math',
        title: 'A',
        plannedMinutes: 30,
        done: false,
      },
      {
        id: 2,
        date: '2026-10-21',
        subject: 'math',
        title: 'B',
        plannedMinutes: 60,
        done: false,
      },
    ] as any;
    const loads = computeDayLoads(plans, 240, '2026-10-21', 1);
    expect(loads[0].items).toHaveLength(2);
    expect(loads[0].items[0].plannedMinutes).toBe(60);
    expect(loads[0].items[1].plannedMinutes).toBe(30);
  });

  it('过滤：区间外计划被丢弃', () => {
    const plans = [
      {
        id: 1,
        date: '2026-10-20',
        subject: 'math',
        title: 'A',
        plannedMinutes: 30,
        done: false,
      },
      {
        id: 2,
        date: '2026-10-22',
        subject: 'math',
        title: 'B',
        plannedMinutes: 60,
        done: false,
      },
    ] as any;
    const loads = computeDayLoads(plans, 240, '2026-10-21', 2);
    expect(loads).toHaveLength(2);
    expect(loads[0].date).toBe('2026-10-21');
    expect(loads[0].items).toHaveLength(0);
    expect(loads[1].date).toBe('2026-10-22');
    expect(loads[1].items).toHaveLength(1);
  });

  it('overloaded 边界：等于 dailyMinutes 不算，多 1 分钟算', () => {
    const equal = computeDayLoads(
      [
        {
          id: 1,
          date: '2026-10-21',
          subject: 'math',
          title: 'A',
          plannedMinutes: 240,
          done: false,
        },
      ] as any,
      240,
      '2026-10-21',
      1
    );
    expect(equal[0].totalMinutes).toBe(240);
    expect(equal[0].overloaded).toBe(false);

    const over = computeDayLoads(
      [
        {
          id: 1,
          date: '2026-10-21',
          subject: 'math',
          title: 'A',
          plannedMinutes: 241,
          done: false,
        },
      ] as any,
      240,
      '2026-10-21',
      1
    );
    expect(over[0].totalMinutes).toBe(241);
    expect(over[0].overloaded).toBe(true);
  });

  it('跨天日期正确：fromDate, fromDate+1...', () => {
    const loads = computeDayLoads([], 240, '2026-10-30', 4);
    expect(loads.map((d) => d.date)).toEqual([
      '2026-10-30',
      '2026-10-31',
      '2026-11-01',
      '2026-11-02',
    ]);
  });
});

describe('GET /api/plans/range', () => {
  it('未登录 401', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/range?from=2026-10-21&to=2026-10-25',
    });
    expect(res.statusCode).toBe(401);
  });

  it('from 格式非法 400 + 精确文案', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/range?from=2026-10&to=2026-10-25',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'from/to 格式非法，应为 YYYY-MM-DD' });
  });

  it('from > to 400 + 精确文案', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/range?from=2026-10-25&to=2026-10-21',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'from 不能晚于 to' });
  });

  it('区间 63 天 400 + 精确文案；62 天 200', async () => {
    const res63 = await app.inject({
      method: 'GET',
      url: '/api/plans/range?from=2026-01-01&to=2026-03-05',
      headers: { cookie: authCookie },
    });
    expect(res63.statusCode).toBe(400);
    expect(res63.json()).toEqual({ error: '区间不能超过 62 天' });

    const res62 = await app.inject({
      method: 'GET',
      url: '/api/plans/range?from=2026-01-01&to=2026-03-03',
      headers: { cookie: authCookie },
    });
    expect(res62.statusCode).toBe(200);
  });

  it('正常：区间内 2 条返回，按 date ASC', async () => {
    await createPlan(authCookie, {
      date: '2026-10-22',
      subject: 'math',
      title: 'P1',
      plannedMinutes: 30,
    });
    await createPlan(authCookie, {
      date: '2026-10-21',
      subject: 'english',
      title: 'P2',
      plannedMinutes: 45,
    });
    await createPlan(authCookie, {
      date: '2026-11-01',
      subject: 'politics',
      title: 'P3',
      plannedMinutes: 60,
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/range?from=2026-10-21&to=2026-10-25',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body).toHaveLength(2);
    expect(body[0].date).toBe('2026-10-21');
    expect(body[1].date).toBe('2026-10-22');
  });

  it('用户隔离：用户2 的计划对用户1 不可见', async () => {
    authCookie2 = await registerAndLogin(app, 'rangoverload2');
    await createPlan(authCookie2, {
      date: '2026-10-21',
      subject: 'math',
      title: 'U2',
      plannedMinutes: 30,
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/range?from=2026-10-21&to=2026-10-25',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual([]);
  });
});

describe('GET /api/plans/overload', () => {
  it('未登录 401', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/overload?weekStart=2026-10-21&dailyMinutes=240',
    });
    expect(res.statusCode).toBe(401);
  });

  it('weekStart 非法 400 + 精确文案；dailyMinutes 非法 400 + 精确文案', async () => {
    const badWeek = await app.inject({
      method: 'GET',
      url: '/api/plans/overload?weekStart=2026-10&dailyMinutes=240',
      headers: { cookie: authCookie },
    });
    expect(badWeek.statusCode).toBe(400);
    expect(badWeek.json()).toEqual({ error: 'weekStart 格式非法，应为 YYYY-MM-DD' });

    for (const dm of ['29', '1441', '2.5', 'abc']) {
      const res = await app.inject({
        method: 'GET',
        url: `/api/plans/overload?weekStart=2026-10-21&dailyMinutes=${dm}`,
        headers: { cookie: authCookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    }
  });

  it('正常：某天 300 分钟，dailyMinutes=240 -> overloaded true，计数正确，weekEnd 正确', async () => {
    await createPlan(authCookie, {
      date: '2026-10-21',
      subject: 'math',
      title: 'A',
      plannedMinutes: 150,
    });
    await createPlan(authCookie, {
      date: '2026-10-21',
      subject: 'english',
      title: 'B',
      plannedMinutes: 150,
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/overload?weekStart=2026-10-21&dailyMinutes=240',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe('2026-10-21');
    expect(body.weekEnd).toBe('2026-10-27');
    expect(body.dailyMinutes).toBe(240);
    expect(body.days).toHaveLength(7);
    expect(body.overloadedDays).toBe(1);
    const d0 = body.days.find((d: any) => d.date === '2026-10-21');
    expect(d0.totalMinutes).toBe(300);
    expect(d0.overloaded).toBe(true);
  });

  it('kind 映射：新学标题的 DayLoadItem.kind 为 new', async () => {
    await createPlan(authCookie, {
      date: '2026-10-21',
      subject: 'math',
      title: '智能排期·数学 新学1',
      plannedMinutes: 30,
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/overload?weekStart=2026-10-21&dailyMinutes=240',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    const d0 = body.days.find((d: any) => d.date === '2026-10-21');
    expect(d0.items).toHaveLength(1);
    expect(d0.items[0].kind).toBe('new');
  });

  it('用户隔离：用户2 的 500 分钟计划不影响用户1', async () => {
    authCookie2 = await registerAndLogin(app, 'rangoverload2');
    await createPlan(authCookie2, {
      date: '2026-10-21',
      subject: 'math',
      title: 'U2',
      plannedMinutes: 500,
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/overload?weekStart=2026-10-21&dailyMinutes=240',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.overloadedDays).toBe(0);
    const d0 = body.days.find((d: any) => d.date === '2026-10-21');
    expect(d0.totalMinutes).toBe(0);
  });

  it('空周：days 长度 7，overloadedDays 0', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/overload?weekStart=2026-10-21&dailyMinutes=240',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.days).toHaveLength(7);
    expect(body.overloadedDays).toBe(0);
    expect(body.weekEnd).toBe('2026-10-27');
  });
});
