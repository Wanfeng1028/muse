import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../src/app';

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

  beforeAll(async () => {
    app = buildApp({ dbPath: ':memory:' });
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  it('无参数返回本周一与 weekEnd', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly' });
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
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=2026-10-12' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe('2026-10-12');
    expect(body.weekEnd).toBe('2026-10-19');
  });

  it('非法 start 返回 400', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=not-a-date' });
    expect(res.statusCode).toBe(400);
  });

  it('专注时长计入 focusMinutes 与 focusBySubject.math', async () => {
    const before = (await app.inject({ method: 'GET', url: '/api/stats/weekly' })).json();
    const post = await app.inject({
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 30 },
    });
    expect(post.statusCode).toBe(201);
    const after = (await app.inject({ method: 'GET', url: '/api/stats/weekly' })).json();
    expect(after.focusMinutes - before.focusMinutes).toBe(30);
    expect(after.focusBySubject.math - before.focusBySubject.math).toBe(30);
  });

  it('完成的计划计入 plansDone', async () => {
    const before = (await app.inject({ method: 'GET', url: '/api/stats/weekly' })).json();
    const created = await app.inject({
      method: 'POST',
      url: '/api/plans',
      payload: { date: todayLocal(), subject: 'english', title: '周报测试计划', plannedMinutes: 20 },
    });
    expect(created.statusCode).toBe(201);
    const { id } = created.json();
    const patched = await app.inject({
      method: 'PATCH',
      url: `/api/plans/${id}`,
      payload: { done: true },
    });
    expect(patched.statusCode).toBe(200);
    const after = (await app.inject({ method: 'GET', url: '/api/stats/weekly' })).json();
    expect(after.plansDone - before.plansDone).toBe(1);
  });
});
