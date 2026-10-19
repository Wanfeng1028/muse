import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb, todayStr, addDays } from '../src/db';
import { registerStatsRoutes } from '../src/routes/stats';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('GET /api/stats/heatmap - streak 纵深测试（第二轮）', () => {
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
    authCookie = await registerAndLogin(app, 'heatmapdeep');
  });

  afterEach(async () => {
    await app.close();
    db.close();
    vi.useRealTimers();
  });

  it('闰年 2-29：months=6 返回 186 天且 startDate/endDate 与 2-29 记录精确', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-03-01T12:00:00Z'));

    db.prepare(
      'INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'heatmapdeep\'), ?, ?, ?)'
    ).run('math', 30, '2024-02-29T10:00:00');

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=6',
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      months: number;
      startDate: string;
      endDate: string;
      days: { date: string; focusMinutes: number }[];
    };

    expect(body.days.length).toBe(186);
    expect(body.startDate).toBe('2023-08-29');
    expect(body.endDate).toBe('2024-03-01');

    const leapDay = body.days.find((d) => d.date === '2024-02-29');
    expect(leapDay).toBeDefined();
    expect(leapDay!.focusMinutes).toBe(30);
  });

  it('连续 60 天记录：currentStreak 与 bestStreak 均为 60，activeDays >= 60', async () => {
    const today = todayStr();
    const stmt = db.prepare(
      'INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'heatmapdeep\'), ?, ?, ?)'
    );
    for (let i = 0; i < 60; i++) {
      const d = addDays(today, -i);
      stmt.run('math', 30, d + 'T10:00:00');
    }

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=6',
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      currentStreak: number;
      bestStreak: number;
      activeDays: number;
    };

    expect(body.currentStreak).toBe(60);
    expect(body.bestStreak).toBe(60);
    expect(body.activeDays >= 60).toBe(true);
  });

  it('months=1 与 months=6 的精确天数与边界日期', async () => {
    const res1 = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=1',
    });
    expect(res1.statusCode).toBe(200);
    const body1 = res1.json() as {
      months: number;
      startDate: string;
      endDate: string;
      days: unknown[];
    };
    expect(body1.days.length).toBe(31);
    expect(body1.months).toBe(1);
    expect(body1.endDate).toBe(todayStr());
    expect(body1.startDate).toBe(addDays(body1.endDate, -30));

    const res6 = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=6',
    });
    expect(res6.statusCode).toBe(200);
    const body6 = res6.json() as {
      months: number;
      startDate: string;
      endDate: string;
      days: unknown[];
    };
    expect(body6.days.length).toBe(186);
    expect(body6.months).toBe(6);
    expect(body6.startDate).toBe(addDays(body6.endDate, -185));
  });

  it('months 非法值：1.5 / abc / -1 均返回 400', async () => {
    const res1 = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=1.5',
    });
    expect(res1.statusCode).toBe(400);

    const res2 = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=abc',
    });
    expect(res2.statusCode).toBe(400);

    const res3 = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=-1',
    });
    expect(res3.statusCode).toBe(400);
  });

  it('今日零记录从昨日倒数；今日有记录则为 1', async () => {
    const today = todayStr();
    const stmt = db.prepare(
      'INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'heatmapdeep\'), ?, ?, ?)'
    );
    stmt.run('math', 30, addDays(today, -1) + 'T10:00:00');
    stmt.run('math', 30, addDays(today, -2) + 'T10:00:00');

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=6',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      currentStreak: number;
      days: { date: string; focusMinutes: number }[];
    };
    expect(body.currentStreak).toBe(2);
    expect(body.days[body.days.length - 1].focusMinutes).toBe(0);

    const db2 = createDb(':memory:');
    const app2 = Fastify({ logger: false });
    applyAuthHook(app2, db2);
    registerAuthRoutes(app2, db2);
    registerStatsRoutes(app2, db2);
    await app2.ready();
    const authCookie2 = await registerAndLogin(app2, 'heatmapdeep2');
    db2
      .prepare(
        'INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'heatmapdeep2\'), ?, ?, ?)'
      )
      .run('math', 30, today + 'T10:00:00');
    const res2 = await app2.inject({ headers: { cookie: authCookie2 },
      method: 'GET',
      url: '/api/stats/heatmap?months=6',
    });
    expect(res2.statusCode).toBe(200);
    const body2 = res2.json() as { currentStreak: number };
    expect(body2.currentStreak).toBe(1);
    await app2.close();
    db2.close();
  });

  it('中断后 bestStreak 取最长段：currentStreak=4，bestStreak=10', async () => {
    const today = todayStr();
    const stmt = db.prepare(
      'INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = \'heatmapdeep\'), ?, ?, ?)'
    );
    for (let i = 17; i >= 8; i--) {
      stmt.run('math', 30, addDays(today, -i) + 'T10:00:00');
    }
    for (let i = 4; i >= 1; i--) {
      stmt.run('math', 30, addDays(today, -i) + 'T10:00:00');
    }

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=6',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      currentStreak: number;
      bestStreak: number;
    };
    expect(body.currentStreak).toBe(4);
    expect(body.bestStreak).toBe(10);
  });
});