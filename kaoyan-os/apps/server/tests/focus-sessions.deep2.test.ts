import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb, todayStr, addDays } from '../src/db';
import { registerFocusRoutes } from '../src/routes/focus';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('focus sessions 纵深测试（第二轮）', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let authCookie = '';

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerFocusRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'focusdeep');
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  it('跨天归属：当前语义按 started_at 日期整体归属', async () => {
    const y = addDays(todayStr(), -1);

    const res1 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 60, startedAt: y + 'T23:50:00' },
    });
    expect(res1.statusCode).toBe(201);

    const res2 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 30, startedAt: todayStr() + 'T00:10:00' },
    });
    expect(res2.statusCode).toBe(201);

    const statsRes = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/focus/stats?days=2',
    });
    expect(statsRes.statusCode).toBe(200);
    const stats = statsRes.json();
    expect(stats.days).toEqual([
      { date: y, minutes: 60 },
      { date: todayStr(), minutes: 30 },
    ]);
    expect(stats.todayMinutes).toBe(30);
    expect(stats.weekMinutes).toBe(90);
  });

  it('超长会话 1440 分钟不溢出到次日', async () => {
    const y = addDays(todayStr(), -1);

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'english', minutes: 1440, startedAt: y + 'T00:00:00' },
    });
    expect(res.statusCode).toBe(201);

    const statsRes = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/focus/stats?days=2',
    });
    expect(statsRes.statusCode).toBe(200);
    const stats = statsRes.json();
    expect(stats.days[0]).toEqual({ date: y, minutes: 1440 });
    expect(stats.days[1].minutes).toBe(0);

    const res2 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'english', minutes: 1441 },
    });
    expect(res2.statusCode).toBe(400);
    expect(res2.json().error).toBe('minutes must be an integer between 1 and 1440');
  });

  it('零/负/小数/字符串 minutes 全部拒绝且不写库', async () => {
    const values = [0, -30, 25.5, '60'];
    for (const v of values) {
      const res = await app.inject({ headers: { cookie: authCookie },
        method: 'POST',
        url: '/api/focus',
        payload: { subject: 'math', minutes: v },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json().error).toBe('minutes must be an integer between 1 and 1440');
    }

    const listRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/focus' });
    expect(listRes.statusCode).toBe(200);
    expect(listRes.json()).toEqual([]);
  });

  it('note unicode 与 emoji 原样保留、缺省为 null', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 25, note: '数学 📚 冲刺' },
    });
    expect(res.statusCode).toBe(201);
    expect(res.json().note).toBe('数学 📚 冲刺');

    const listRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/focus' });
    expect(listRes.statusCode).toBe(200);
    expect(listRes.json()[0].note).toBe('数学 📚 冲刺');

    const res2 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'english', minutes: 25 },
    });
    expect(res2.statusCode).toBe(201);
    expect(res2.json().note).toBeNull();
  });

  it('startedAt 非法字符串返回 400（已修复）', async () => {
    const res1 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 10, startedAt: 'not-a-date' },
    });
    expect(res1.statusCode).toBe(400);

    const res2 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 10, startedAt: '' },
    });
    expect(res2.statusCode).toBe(400);

    const res3 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 10, startedAt: '2024-13-40T99:99:99' },
    });
    expect(res3.statusCode).toBe(400);

    const list = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/focus',
    });
    expect(list.json()).toEqual([]);
  });

  it('startedAt 合法 ISO 字符串照常 201 并原样回显', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 10, startedAt: '2024-05-01T09:00:00' },
    });
    expect(res.statusCode).toBe(201);
    expect(res.json().startedAt).toBe('2024-05-01T09:00:00');
  });

  it('startedAt 带时区偏移的 ISO 照常 201', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 10, startedAt: '2024-05-01T09:00:00+08:00' },
    });
    expect(res.statusCode).toBe(201);
  });

  it('startedAt 缺省时 201 且自动填充当前时间', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'math', minutes: 10 },
    });
    expect(res.statusCode).toBe(201);
    const startedAt = res.json().startedAt;
    expect(typeof startedAt).toBe('string');
    expect(Number.isNaN(Date.parse(startedAt))).toBe(false);
  });

});