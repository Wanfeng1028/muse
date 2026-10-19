import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb, todayStr, addDays } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerStatsRoutes } from '../src/routes/stats';
import { registerAndLogin, authHeaders, createSeededUser } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

beforeAll(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerStatsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

describe('stats 多用户隔离', () => {

  it('weekly 只统计当前用户的 focus_sessions/plans/mistakes/exams/words', async () => {
    const { cookie: cookieA, userId: userA } = await createSeededUser(db, app, 'statsa');
    const { cookie: cookieB, userId: userB } = await createSeededUser(db, app, 'statsb');

    // 给 A 额外注入一条今天开始的专注，确保 A 有数据
    const today = todayStr();
    db.prepare(
      `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note) VALUES (?, 'math', 42, ?, NULL)`,
    ).run(userA, today + 'T09:00:00');

    const resA = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly',
      headers: authHeaders(cookieA),
    });
    const resB = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly',
      headers: authHeaders(cookieB),
    });
    expect(resA.statusCode).toBe(200);
    expect(resB.statusCode).toBe(200);

    const statsA = resA.json() as any;
    const statsB = resB.json() as any;

    // A 的 focusMinutes 应等于种子 focus_sessions 分钟总和 + 42
    const seedFocusSum = db
      .prepare(`SELECT COALESCE(SUM(minutes),0) AS s FROM focus_sessions WHERE user_id = ?`)
      .get(userA) as { s: number };
    expect(statsA.focusMinutes).toBe(seedFocusSum.s);

    // B 的 focusMinutes 只反映 B 自己的数据，不应包含 A 的 42
    const seedFocusSumB = db
      .prepare(`SELECT COALESCE(SUM(minutes),0) AS s FROM focus_sessions WHERE user_id = ?`)
      .get(userB) as { s: number };
    expect(statsB.focusMinutes).toBe(seedFocusSumB.s);
    expect(statsB.focusMinutes).not.toBe(statsA.focusMinutes + 42);

    // 用户 id 不同
    expect(userA).not.toBe(userB);
  });

  it('heatmap 的 currentStreak 只按当前用户聚合，且与 weekly 的 currentStreak 一致', async () => {
    const { cookie, userId } = await createSeededUser(db, app, 'statsc');

    // 清掉该用户今天之前的 focus，构造：昨天+今天都有专注 → streak=2
    const today = todayStr();
    const yesterday = addDays(today, -1);
    db.prepare(`DELETE FROM focus_sessions WHERE user_id = ?`).run(userId);
    db.prepare(
      `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note) VALUES (?, 'math', 30, ?, NULL)`,
    ).run(userId, yesterday + 'T10:00:00');
    db.prepare(
      `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note) VALUES (?, 'math', 30, ?, NULL)`,
    ).run(userId, today + 'T10:00:00');

    // 另一用户今天也专注，不应污染 streak
    const { userId: otherId } = await createSeededUser(db, app, 'statsd');
    db.prepare(`DELETE FROM focus_sessions WHERE user_id = ?`).run(otherId);
    db.prepare(
      `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note) VALUES (?, 'math', 999, ?, NULL)`,
    ).run(otherId, today + 'T10:00:00');

    const weeklyRes = await app.inject({
      method: 'GET',
      url: '/api/stats/weekly',
      headers: authHeaders(cookie),
    });
    expect(weeklyRes.statusCode).toBe(200);
    expect((weeklyRes.json() as any).currentStreak).toBe(2);

    const heatmapRes = await app.inject({
      method: 'GET',
      url: '/api/stats/heatmap?months=3',
      headers: authHeaders(cookie),
    });
    expect(heatmapRes.statusCode).toBe(200);
    const heatmap = heatmapRes.json() as any;
    expect(heatmap.currentStreak).toBe(2);
    // 今天/昨天的 focusMinutes 应只统计当前用户
    const todayCell = heatmap.days.find((d: any) => d.date === today);
    const yesterdayCell = heatmap.days.find((d: any) => d.date === yesterday);
    expect(todayCell.focusMinutes).toBe(30);
    expect(yesterdayCell.focusMinutes).toBe(30);
  });

  it('heatmap 的 plansDone 按 user_id 隔离', async () => {
    const { cookie: cookieA, userId: userA } = await createSeededUser(db, app, 'statse');
    const { cookie: cookieB, userId: userB } = await createSeededUser(db, app, 'statsf');

    const today = todayStr();
    db.prepare(`DELETE FROM plans WHERE user_id IN (?, ?)`).run(userA, userB);
    db.prepare(
      `INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, 'math', 'p1', 30, 1, ?)`,
    ).run(userA, today, today + 'T00:00:00');
    db.prepare(
      `INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, 'math', 'p2', 30, 0, ?)`,
    ).run(userB, today, today + 'T00:00:00');

    const resA = await app.inject({
      method: 'GET',
      url: '/api/stats/heatmap?months=1',
      headers: authHeaders(cookieA),
    });
    const resB = await app.inject({
      method: 'GET',
      url: '/api/stats/heatmap?months=1',
      headers: authHeaders(cookieB),
    });
    expect(resA.statusCode).toBe(200);
    expect(resB.statusCode).toBe(200);

    const cellA = (resA.json() as any).days.find((d: any) => d.date === today);
    const cellB = (resB.json() as any).days.find((d: any) => d.date === today);
    expect(cellA.plansTotal).toBe(1);
    expect(cellA.plansDone).toBe(1);
    expect(cellB.plansTotal).toBe(1);
    expect(cellB.plansDone).toBe(0);
  });
});
