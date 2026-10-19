import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../src/app';
import { registerAndLogin } from './test-utils';

function todayLocal(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function addDaysLocal(dateStr: string, n: number): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + n);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, '0');
  const dd = String(dt.getDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}

describe('GET /api/stats/weekly', () => {
  let app: FastifyInstance;
  let authCookie = '';

  beforeAll(async () => {
    app = buildApp({ dbPath: ':memory:' });
    await app.ready();
    authCookie = await registerAndLogin(app, 'weeklytest');
  });

  afterAll(async () => {
    await app.close();
  });

  it('无参数返回本周一与 weekEnd', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    const today = todayLocal();
    const dow = (new Date().getDay() + 6) % 7;
    const expectedStart = addDaysLocal(today, -dow);
    const expectedEnd = addDaysLocal(expectedStart, 7);
    expect(body.weekStart).toBe(expectedStart);
    expect(body.weekEnd).toBe(expectedEnd);
  });

  it('?start=2026-10-12 返回指定周', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly?start=2026-10-12' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe('2026-10-12');
    expect(body.weekEnd).toBe('2026-10-19');
  });

  it('非法 start 返回 400', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly?start=not-a-date' });
    expect(res.statusCode).toBe(400);
  });

  it('专注时长计入 focusMinutes 与 focusBySubject.math', async () => {
    const before = (await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' })).json();
    const post = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 30 },
    });
    expect(post.statusCode).toBe(201);
    const after = (await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' })).json();
    expect(after.focusMinutes - before.focusMinutes).toBe(30);
    expect(after.focusBySubject.math - before.focusBySubject.math).toBe(30);
  });

  it('完成的计划计入 plansDone', async () => {
    const before = (await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' })).json();
    const created = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: { date: todayLocal(), subject: 'english', title: '周报测试计划', plannedMinutes: 20 },
    });
    expect(created.statusCode).toBe(201);
    const { id } = created.json();
    const patched = await app.inject({ headers: { cookie: authCookie },
      method: 'PATCH',
      url: `/api/plans/${id}`,
      payload: { done: true },
    });
    expect(patched.statusCode).toBe(200);
    const after = (await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' })).json();
    expect(after.plansDone - before.plansDone).toBe(1);
  });

  it('focusMinutesByDay 长度为 7 且总和等于 focusMinutes', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' });
    expect(res.statusCode).toBe(200);
    const body = res.json();

    expect(Array.isArray(body.focusMinutesByDay)).toBe(true);
    expect(body.focusMinutesByDay).toHaveLength(7);
    for (const m of body.focusMinutesByDay) {
      expect(Number.isInteger(m)).toBe(true);
      expect(m).toBeGreaterThanOrEqual(0);
    }
    const sum = body.focusMinutesByDay.reduce((a: number, b: number) => a + b, 0);
    expect(sum).toBe(body.focusMinutes);
  });

  it('向本周某天补专注记录后对应下标增加', async () => {
    const before = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' });
    const beforeBody = before.json();
    const target = addDaysLocal(beforeBody.weekStart, 2);

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: {
        subject: 'english',
        minutes: 25,
        startedAt: `${target}T09:00:00`,
      },
    });
    expect(res.statusCode).toBe(201);

    const after = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' });
    const afterBody = after.json();

    expect(afterBody.focusMinutesByDay[2] - beforeBody.focusMinutesByDay[2]).toBe(25);
    expect(afterBody.focusMinutes - beforeBody.focusMinutes).toBe(25);
  });

  it('今天补专注后 currentStreak 至少为 1', async () => {
    const target = todayLocal();

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: {
        subject: 'math',
        minutes: 20,
        startedAt: `${target}T09:00:00`,
      },
    });
    expect(res.statusCode).toBe(201);

    const after = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' });
    expect(after.json().currentStreak).toBeGreaterThanOrEqual(1);
  });

  it('向 -30 天补孤立记录不影响 currentStreak', async () => {
    const before = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' });
    const beforeBody = before.json();
    const target = addDaysLocal(todayLocal(), -30);

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: {
        subject: 'math',
        minutes: 20,
        startedAt: `${target}T09:00:00`,
      },
    });
    expect(res.statusCode).toBe(201);

    const after = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/stats/weekly' });
    const afterBody = after.json();

    expect(afterBody.currentStreak - beforeBody.currentStreak).toBe(0);
    for (let i = 0; i < 7; i++) {
      expect(afterBody.focusMinutesByDay[i] - beforeBody.focusMinutesByDay[i]).toBe(0);
    }
  });

  it('start 格式错误返回 400', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/weekly?start=20261012',
    });
    expect(res.statusCode).toBe(400);
  });
});
