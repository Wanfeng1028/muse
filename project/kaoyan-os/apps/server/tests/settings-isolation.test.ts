import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerSettingsRoutes } from '../src/routes/settings';
import { registerAndLogin, authHeaders } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerSettingsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterEach(async () => {
  await app.close();
});

describe('settings 按用户隔离', () => {
  it('A 用户改 theme，不影响 B 用户', async () => {
    const aCookie = await registerAndLogin(app, 'alice');
    const bCookie = await registerAndLogin(app, 'bob');

    const aPut = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: authHeaders(aCookie),
      payload: { theme: 'dark', dailyGoalMinutes: 999 },
    });
    expect(aPut.statusCode).toBe(200);
    expect(aPut.json().theme).toBe('dark');
    expect(aPut.json().dailyGoalMinutes).toBe(999);

    const bGet = await app.inject({
      method: 'GET',
      url: '/api/settings',
      headers: authHeaders(bCookie),
    });
    expect(bGet.statusCode).toBe(200);
    // B 用户拿到默认值，未被 A 污染
    expect(bGet.json().theme).not.toBe('dark');
    expect(bGet.json().dailyGoalMinutes).not.toBe(999); // B 拿默认值 300，不被 A 污染

    const aGet = await app.inject({
      method: 'GET',
      url: '/api/settings',
      headers: authHeaders(aCookie),
    });
    expect(aGet.json().theme).toBe('dark');
    expect(aGet.json().dailyGoalMinutes).toBe(999);

    // 直接查库确认 user_id 隔离
    const rows = db
      .prepare('SELECT user_id, key, value FROM settings WHERE key IN (?, ?) ORDER BY user_id, key')
      .all('theme', 'daily_goal_minutes') as Array<{ user_id: number; key: string; value: string }>;
    const byUser = new Map<number, Record<string, string>>();
    for (const r of rows) {
      const m = byUser.get(r.user_id) ?? {};
      m[r.key] = r.value;
      byUser.set(r.user_id, m);
    }
    // 只有 A 写过 settings（B 只 GET，GET 不落库）：库里恰好 A 的两条记录
    expect(byUser.size).toBe(1);
    const values = [...byUser.values()];
    expect(values.some((v) => v['theme'] === 'dark' && v['daily_goal_minutes'] === '999')).toBe(true);
  });

  it('PUT 非法值返回 400 且不落库', async () => {
    const cookie = await registerAndLogin(app, 'carol');

    const cases: Array<Record<string, unknown>> = [
      { theme: 'blue' },
      { examDate: '2025/01/01' },
      { examDate: '25-01-01' },
      { dailyGoalMinutes: 0 },
      { dailyGoalMinutes: -1 },
      { dailyGoalMinutes: 1441 },
      { pomodoroMinutes: 181 },
      { breakMinutes: 61 },
      { dailyGoalMinutes: '60' as unknown as number },
    ];
    for (const payload of cases) {
      const res = await app.inject({
        method: 'PUT',
        url: '/api/settings',
        headers: authHeaders(cookie),
        payload,
      });
      expect(res.statusCode, `payload=${JSON.stringify(payload)}`).toBe(400);
      expect(res.json().error).toMatch(/^invalid field:/);
    }

    // 确认没有任何一行写入
    const count = db
      .prepare(
        `SELECT COUNT(*) AS c FROM settings
         WHERE user_id = (SELECT id FROM users WHERE username = ?)`,
      )
      .get('carol') as { c: number };
    expect(count.c).toBe(0);

    // 读取时返回默认值
    const get = await app.inject({
      method: 'GET',
      url: '/api/settings',
      headers: authHeaders(cookie),
    });
    expect(get.statusCode).toBe(200);
    expect(get.json().theme === 'dark' || get.json().theme === 'light').toBe(true);
  });
});
