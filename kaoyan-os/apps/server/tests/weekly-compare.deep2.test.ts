import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { registerStatsRoutes } from '../src/routes/stats';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('周报对比纵深测试 /api/stats/weekly', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let authCookie = '';

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerStatsRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'weeklycompare');
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  const cur = '2024-12-30';
  const prev = '2024-12-23';

  it('相邻两周窗口连续不重叠，边界记录只归属本周', async () => {
    db.prepare('INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?)').run(
      'math',
      60,
      '2024-12-30T00:00:00'
    );

    const curRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${cur}` });
    expect(curRes.statusCode).toBe(200);
    const curStats = curRes.json();
    expect(curStats.weekStart).toBe('2024-12-30');
    expect(curStats.weekEnd).toBe('2025-01-06');
    expect(curStats.focusMinutes).toBe(60);
    expect(curStats.focusBySubject.math).toBe(60);

    const prevRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${prev}` });
    expect(prevRes.statusCode).toBe(200);
    const prevStats = prevRes.json();
    expect(prevStats.weekStart).toBe('2024-12-23');
    expect(prevStats.weekEnd).toBe('2024-12-30');
    expect(prevStats.weekEnd).toBe(curStats.weekStart);
    expect(prevStats.focusMinutes).toBe(0);
    expect(prevStats.focusBySubject.math).toBe(0);
  });

  it('上周无数据时本周数据正常，上周各项为空', async () => {
    db.prepare('INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?)').run(
      'math',
      120,
      '2025-01-02T10:00:00'
    );
    const insertPlan = db.prepare(
      'INSERT INTO plans (user_id, date, subject, title, done) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?, ?)'
    );
    insertPlan.run('2025-01-03', 'math', '计划一', 1);
    insertPlan.run('2025-01-03', 'math', '计划二', 1);
    insertPlan.run('2025-01-03', 'math', '计划三', 1);
    insertPlan.run('2025-01-03', 'math', '计划四', 0);

    const curRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${cur}` });
    expect(curRes.statusCode).toBe(200);
    const curStats = curRes.json();
    expect(curStats.focusMinutes).toBe(120);
    expect(curStats.plansTotal).toBe(4);
    expect(curStats.plansDone).toBe(3);

    const prevRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${prev}` });
    expect(prevRes.statusCode).toBe(200);
    const prevStats = prevRes.json();
    expect(prevStats.focusMinutes).toBe(0);
    expect(prevStats.plansTotal).toBe(0);
    expect(prevStats.plansDone).toBe(0);
    expect(prevStats.focusBySubject).toEqual({ math: 0, english: 0, politics: 0, major: 0 });
    expect(prevStats.focusMinutesByDay).toEqual([0, 0, 0, 0, 0, 0, 0]);
  });

  it('本周无数据时上周数据正常，本周各项为空', async () => {
    db.prepare('INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?)').run(
      'english',
      90,
      '2024-12-24T10:00:00'
    );
    const insertPlan = db.prepare(
      'INSERT INTO plans (user_id, date, subject, title, done) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?, ?)'
    );
    insertPlan.run('2024-12-25', 'english', '英语计划一', 0);
    insertPlan.run('2024-12-25', 'english', '英语计划二', 0);

    const curRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${cur}` });
    expect(curRes.statusCode).toBe(200);
    const curStats = curRes.json();
    expect(curStats.focusMinutes).toBe(0);
    expect(curStats.plansTotal).toBe(0);
    expect(curStats.focusMinutesByDay).toEqual([0, 0, 0, 0, 0, 0, 0]);

    const prevRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${prev}` });
    expect(prevRes.statusCode).toBe(200);
    const prevStats = prevRes.json();
    expect(prevStats.focusMinutes).toBe(90);
    expect(prevStats.plansTotal).toBe(2);
    expect(prevStats.plansDone).toBe(0);
  });

  it('跨年周窗口与 plans 闭区间语义正确', async () => {
    db.prepare('INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?)').run(
      'english',
      45,
      '2025-01-01T10:00:00'
    );
    const insertPlan = db.prepare(
      'INSERT INTO plans (user_id, date, subject, title, done) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?, ?)'
    );
    insertPlan.run('2025-01-05', 'math', '周日计划', 0);
    insertPlan.run('2025-01-06', 'math', '下周一计划', 0);

    const curRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${cur}` });
    expect(curRes.statusCode).toBe(200);
    const curStats = curRes.json();
    expect(curStats.focusMinutesByDay).toEqual([0, 0, 45, 0, 0, 0, 0]);
    expect(curStats.weekEnd).toBe('2025-01-06');
    expect(curStats.plansTotal).toBe(1);

    const prevRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${prev}` });
    expect(prevRes.statusCode).toBe(200);
    const prevStats = prevRes.json();
    expect(prevStats.focusMinutes).toBe(0);
  });

  it('focusMinutesByDay 下标与日期严格对应', async () => {
    db.prepare('INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?)').run(
      'math',
      30,
      '2024-12-30T09:00:00'
    );
    db.prepare('INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?)').run(
      'math',
      20,
      '2025-01-04T09:00:00'
    );
    db.prepare('INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'weeklycompare\'), ?, ?, ?)').run(
      'math',
      10,
      '2025-01-05T09:00:00'
    );

    const curRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: `/api/stats/weekly?start=${cur}` });
    expect(curRes.statusCode).toBe(200);
    const curStats = curRes.json();
    expect(curStats.focusMinutesByDay).toEqual([30, 0, 0, 0, 0, 20, 10]);
    expect(curStats.focusMinutes).toBe(60);
  });
});