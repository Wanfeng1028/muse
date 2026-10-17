import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerSettingsRoutes } from '../src/routes/settings';
import { DEFAULT_SETTINGS } from '@kaoyan/shared';

function createDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:');
  db.exec('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
  return db;
}

async function createApp(db: DatabaseSync): Promise<FastifyInstance> {
  const app = Fastify();
  registerSettingsRoutes(app, db);
  await app.ready();
  return app;
}

describe('settings deep', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;

  beforeEach(async () => {
    db = createDb();
    app = await createApp(db);
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  it('GET 空表时返回全部默认值', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/settings' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.examDate).toBe(DEFAULT_SETTINGS.examDate);
    expect(body.dailyGoalMinutes).toBe(DEFAULT_SETTINGS.dailyGoalMinutes);
    expect(body.pomodoroMinutes).toBe(DEFAULT_SETTINGS.pomodoroMinutes);
    expect(body.breakMinutes).toBe(DEFAULT_SETTINGS.breakMinutes);
    expect(body.theme).toBe(DEFAULT_SETTINGS.theme);
  });

  it('PUT 合法数字字段落库并按整数截断', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { dailyGoalMinutes: 300, pomodoroMinutes: 25, breakMinutes: 5 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.dailyGoalMinutes).toBe(300);
    expect(body.pomodoroMinutes).toBe(25);
    expect(body.breakMinutes).toBe(5);

    const rows = db
      .prepare('SELECT key, value FROM settings ORDER BY key')
      .all() as Array<{ key: string; value: string }>;
    expect(rows).toEqual([
      { key: 'break_minutes', value: '5' },
      { key: 'daily_goal_minutes', value: '300' },
      { key: 'pomodoro_minutes', value: '25' },
    ]);
  });

  it('PUT 数字字段超过上限返回 400 且不写库', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { dailyGoalMinutes: 1441 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('invalid field: dailyGoalMinutes');

    const count = db
      .prepare('SELECT COUNT(*) AS c FROM settings')
      .get() as { c: number };
    expect(count.c).toBe(0);
  });

  it('PUT 数字字段为零或负数返回 400', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { pomodoroMinutes: 0 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('invalid field: pomodoroMinutes');

    const res2 = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { breakMinutes: -3 },
    });
    expect(res2.statusCode).toBe(400);
    expect(res2.json().error).toBe('invalid field: breakMinutes');
  });

  it('PUT examDate 格式错误返回 400，格式正确则落库', async () => {
    const bad = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { examDate: '2025/12/20' },
    });
    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('invalid field: examDate');

    const good = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { examDate: '2025-12-20' },
    });
    expect(good.statusCode).toBe(200);
    expect(good.json().examDate).toBe('2025-12-20');

    const row = db
      .prepare('SELECT value FROM settings WHERE key = ?')
      .get('exam_date') as { value: string };
    expect(row.value).toBe('2025-12-20');
  });

  it('PUT theme 非法值返回 400，合法值落库', async () => {
    const bad = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { theme: 'blue' },
    });
    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('invalid field: theme');

    const good = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { theme: 'dark' },
    });
    expect(good.statusCode).toBe(200);
    expect(good.json().theme).toBe('dark');
  });

  it('PUT 未提供的字段保持原值不变', async () => {
    await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { dailyGoalMinutes: 240, theme: 'dark' },
    });
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { breakMinutes: 10 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.dailyGoalMinutes).toBe(240);
    expect(body.theme).toBe('dark');
    expect(body.breakMinutes).toBe(10);
    expect(body.pomodoroMinutes).toBe(DEFAULT_SETTINGS.pomodoroMinutes);
  });

  it('PUT 重复更新走 upsert 覆盖旧值', async () => {
    await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { pomodoroMinutes: 25 },
    });
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { pomodoroMinutes: 50 },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().pomodoroMinutes).toBe(50);

    const rows = db
      .prepare('SELECT value FROM settings WHERE key = ?')
      .all('pomodoro_minutes') as Array<{ value: string }>;
    expect(rows).toHaveLength(1);
    expect(rows[0].value).toBe('50');
  });

  it('GET 读取时数字字段非数字则回退默认值', async () => {
    db.prepare('INSERT INTO settings(key, value) VALUES(?, ?)').run(
      'daily_goal_minutes',
      'abc'
    );
    db.prepare('INSERT INTO settings(key, value) VALUES(?, ?)').run(
      'pomodoro_minutes',
      '45'
    );
    const res = await app.inject({ method: 'GET', url: '/api/settings' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.dailyGoalMinutes).toBe(DEFAULT_SETTINGS.dailyGoalMinutes);
    expect(body.pomodoroMinutes).toBe(45);
  });

  it('GET 读取时 theme 非法值回退默认值', async () => {
    db.prepare('INSERT INTO settings(key, value) VALUES(?, ?)').run(
      'theme',
      'rainbow'
    );
    const res = await app.inject({ method: 'GET', url: '/api/settings' });
    expect(res.statusCode).toBe(200);
    expect(res.json().theme).toBe(DEFAULT_SETTINGS.theme);
  });

  it('PUT 一次请求部分字段非法则整体拒绝且不落库', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: { dailyGoalMinutes: 200, theme: 'purple' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('invalid field: theme');

    const count = db
      .prepare('SELECT COUNT(*) AS c FROM settings')
      .get() as { c: number };
    expect(count.c).toBe(0);
  });

  it('PUT 空 body 返回默认值且不写库', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      payload: {},
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.examDate).toBe(DEFAULT_SETTINGS.examDate);
    expect(body.theme).toBe(DEFAULT_SETTINGS.theme);

    const count = db
      .prepare('SELECT COUNT(*) AS c FROM settings')
      .get() as { c: number };
    expect(count.c).toBe(0);
  });
});