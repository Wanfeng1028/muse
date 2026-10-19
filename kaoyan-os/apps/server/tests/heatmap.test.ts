import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../src/app';
import { registerAndLogin } from './test-utils';
import { todayStr, addDays } from '../src/db';

let app: FastifyInstance;

  let authCookie = '';
beforeAll(async () => {
  app = await buildApp({ dbPath: ':memory:' });
  await app.ready();

  authCookie = await registerAndLogin(app, 'heatmaptest');});

afterAll(async () => {
  await app.close();
});

async function getHeatmap() {
  const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/heatmap' });
  expect(res.statusCode).toBe(200);
  return res.json();
}

async function postFocus(body: Record<string, unknown>) {
  return app.inject({ headers: { cookie: authCookie }, method: 'POST', url: '/api/focus', payload: body });
}

describe('GET /api/stats/heatmap', () => {
  it('默认 3 个月', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/heatmap' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    const endDate = todayStr();
    const startDate = addDays(endDate, -92);
    expect(body.months).toBe(3);
    expect(body.endDate).toBe(endDate);
    expect(body.startDate).toBe(startDate);
    expect(body.days.length).toBe(93);
    expect(body.days[0].date).toBe(startDate);
    expect(body.days[92].date).toBe(endDate);
  });

  it('months=1 返回 31 天', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=1',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.months).toBe(1);
    expect(body.days.length).toBe(31);
  });

  it('months=0 与 months=7 返回 400', async () => {
    const r0 = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=0',
    });
    expect(r0.statusCode).toBe(400);
    expect(r0.json().error).toBe('months 参数无效');
    const r7 = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=7',
    });
    expect(r7.statusCode).toBe(400);
    expect(r7.json().error).toBe('months 参数无效');
  });

  it('新增 focus 记录后当日 focusMinutes 差值正确', async () => {
    const before = await getHeatmap();
    const today = todayStr();
    const beforeToday = before.days.find((d: any) => d.date === today);
    const beforeMinutes = beforeToday?.focusMinutes ?? 0;

    const res = await postFocus({
      subject: 'math',
      minutes: 45,
      startedAt: `${today}T09:00:00`,
    });
    expect(res.statusCode).toBe(201);

    const after = await getHeatmap();
    const afterToday = after.days.find((d: any) => d.date === today);
    const afterMinutes = afterToday?.focusMinutes ?? 0;

    expect(afterMinutes - beforeMinutes).toBe(45);
  });

  it('新增 plan 后当日 plans 计数差值正确', async () => {
    const before = await getHeatmap();
    const today = todayStr();
    const beforeToday = before.days.find((d: any) => d.date === today);
    const beforePlansTotal = beforeToday?.plansTotal ?? 0;
    const beforePlansDone = beforeToday?.plansDone ?? 0;

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: {
        date: today,
        subject: 'math',
        title: '热力图测试计划',
        plannedMinutes: 20,
      },
    });
    expect(res.statusCode).toBe(201);
    const created = res.json();

    const patchRes = await app.inject({ headers: { cookie: authCookie },
      method: 'PATCH',
      url: `/api/plans/${created.id}`,
      payload: { done: true },
    });
    expect(patchRes.statusCode).toBe(200);

    const after = await getHeatmap();
    const afterToday = after.days.find((d: any) => d.date === today);
    const afterPlansTotal = afterToday?.plansTotal ?? 0;
    const afterPlansDone = afterToday?.plansDone ?? 0;

    expect(afterPlansTotal - beforePlansTotal).toBe(1);
    expect(afterPlansDone - beforePlansDone).toBe(1);
  });

  it('向 -7 天补一条记录后 streak 各 +1', async () => {
    // 先补 -6..-1 六天记录，与今天形成连续 7 天（旧单用户时代靠种子数据隐式提供）
    for (let d = 6; d >= 1; d--) {
      const day = addDays(todayStr(), -d);
      const setup = await postFocus({ subject: 'math', minutes: 20, startedAt: `${day}T09:00:00` });
      expect(setup.statusCode).toBe(201);
    }
    const before = await getHeatmap();
    const target = addDays(todayStr(), -7);

    const res = await postFocus({
      subject: 'math',
      minutes: 20,
      startedAt: `${target}T09:00:00`,
    });
    expect(res.statusCode).toBe(201);

    const after = await getHeatmap();
    expect(after.currentStreak - before.currentStreak).toBe(1);
    expect(after.bestStreak - before.bestStreak).toBe(1);
  });

  it('孤立记录不影响 streak', async () => {
    const before = await getHeatmap();
    const target = addDays(todayStr(), -30);

    const res = await postFocus({
      subject: 'math',
      minutes: 20,
      startedAt: `${target}T09:00:00`,
    });
    expect(res.statusCode).toBe(201);

    const after = await getHeatmap();
    expect(after.currentStreak - before.currentStreak).toBe(0);
    expect(after.bestStreak - before.bestStreak).toBe(0);
    expect(after.activeDays - before.activeDays).toBe(1);
  });
});
