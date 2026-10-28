import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerSettingsRoutes } from '../src/routes/settings';
import { DEFAULT_SETTINGS } from '@kaoyan/shared';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

async function createApp(db: DatabaseSync): Promise<{ app: FastifyInstance; cookie: string }> {
  const app = Fastify();
  registerSettingsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  const cookie = await registerAndLogin(app, 'settingsexamdate');
  return { app, cookie };
}

describe('PUT /api/settings examDate 日历严格校验', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let cookie: string;

  beforeEach(async () => {
    db = createRealDb(':memory:');
    const result = await createApp(db);
    app = result.app;
    cookie = result.cookie;
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  it('PUT examDate 为 2024-02-30 返回 400，错误体为 invalid field: examDate，且 settings 表行数为 0', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: { cookie },
      payload: { examDate: '2024-02-30' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'invalid field: examDate' });
    const row = db.prepare(
      `SELECT COUNT(*) as count FROM settings WHERE user_id = (SELECT id FROM users WHERE username = 'settingsexamdate')`
    ).get() as { count: number };
    expect(row.count).toBe(0);
  });

  it('PUT examDate 为 2023-02-29 返回 400（2023 非闰年）', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: { cookie },
      payload: { examDate: '2023-02-29' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'invalid field: examDate' });
  });

  it('PUT examDate 为 2026-04-31 返回 400（4 月无 31 日）', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: { cookie },
      payload: { examDate: '2026-04-31' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'invalid field: examDate' });
  });

  it('PUT examDate 为 2026-13-01 返回 400（月份 13 不存在）', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: { cookie },
      payload: { examDate: '2026-13-01' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'invalid field: examDate' });
  });

  it('PUT examDate 为 2024-02-29 返回 200，响应 examDate 为 2024-02-29，且库里 exam_date 值为 2024-02-29', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: { cookie },
      payload: { examDate: '2024-02-29' },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ examDate: '2024-02-29' });
    const row = db.prepare(
      `SELECT value FROM settings WHERE user_id = (SELECT id FROM users WHERE username = 'settingsexamdate') AND key = 'exam_date'`
    ).get() as { value: string };
    expect(row.value).toBe('2024-02-29');
  });

  it('PUT examDate 为 2026-02-28 返回 200，响应 examDate 为 2026-02-28', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: { cookie },
      payload: { examDate: '2026-02-28' },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ examDate: '2026-02-28' });
  });

  it('混合非法请求不写库：PUT { examDate: 2024-02-30, dailyGoalMinutes: 300 } 返回 400，settings 表行数为 0', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: { cookie },
      payload: { examDate: '2024-02-30', dailyGoalMinutes: 300 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'invalid field: examDate' });
    const row = db.prepare(
      `SELECT COUNT(*) as count FROM settings WHERE user_id = (SELECT id FROM users WHERE username = 'settingsexamdate')`
    ).get() as { count: number };
    expect(row.count).toBe(0);
  });

  it('脏库回退：settings 表插入 exam_date=2024-02-30，GET /api/settings 响应 examDate 为默认值', async () => {
    db.prepare(
      `INSERT INTO settings (user_id, key, value) VALUES ((SELECT id FROM users WHERE username = 'settingsexamdate'), 'exam_date', '2024-02-30')`
    ).run();
    const res = await app.inject({
      method: 'GET',
      url: '/api/settings',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ examDate: DEFAULT_SETTINGS.examDate });
  });
});