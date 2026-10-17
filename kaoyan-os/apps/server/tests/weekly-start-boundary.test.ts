import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerStatsRoutes } from '../src/routes/stats';

describe('GET /api/stats/weekly start 参数语义', () => {
  let app: FastifyInstance;
  let db: ReturnType<typeof createDb>;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    registerStatsRoutes(app, db);
    await app.ready();
  });

  afterEach(async () => {
    await app.close();
  });

  it('start 为周日时不归一，weekStart 原样返回且 weekEnd 为 +7 天', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly?start=2026-10-18',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe('2026-10-18');
    expect(body.weekEnd).toBe('2026-10-25');
  });

  it('start=2024-02-30 不存在的日期宽松通过并原样返回', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly?start=2024-02-30',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe('2024-02-30');
    // addDays 用 new Date(2024, 1, 30) 先做 JS 日期归一化：
    // 2024 为闰年，2 月 30 日被归一化为 3 月 1 日，再 +7 天 = 3 月 8 日。
    expect(body.weekEnd).toBe('2024-03-08');
  });

  it('start 带时间后缀违反正则返回 400', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly?start=2026-10-12T00:00:00',
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'start 日期格式无效' });
  });

  it('start=2026-13-01 月份非法返回 400 start 日期无效', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly?start=2026-13-01',
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'start 日期无效' });
  });

  it('远期空周返回全零统计', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly?start=2099-01-01',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe('2099-01-01');
    expect(body.weekEnd).toBe('2099-01-08');
    expect(body.focusMinutes).toBe(0);
    expect(body.plansTotal).toBe(0);
    expect(body.focusMinutesByDay).toEqual([0, 0, 0, 0, 0, 0, 0]);
  });

  it('focusMinutesByDay 下标 0 对应 start 当天', async () => {
    db.prepare(
      `INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`
    ).run('math', 30, '2026-10-18T09:00:00');

    const res = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly?start=2026-10-18',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.focusMinutesByDay).toHaveLength(7);
    expect(body.focusMinutesByDay[0]).toBe(30);
    expect(body.focusMinutesByDay.slice(1)).toEqual([0, 0, 0, 0, 0, 0]);
    expect(body.focusMinutes).toBe(30);
    expect(body.focusBySubject.math).toBe(30);
  });
});
