import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerFocusRoutes } from '../src/routes/focus';
import { registerAndLogin, authHeaders } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerFocusRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterEach(async () => {
  await app.close();
  db.close();
});

describe('POST /api/focus startedAt 校验', () => {
  it('拒绝非法日期字符串', async () => {
    const cookie = await registerAndLogin(app, 'u_bad_date');
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookie),
      payload: { subject: 'math', minutes: 30, startedAt: 'not-a-date' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'startedAt must be a valid date string' });
  });

  it('拒绝缺少日期前缀的字符串', async () => {
    const cookie = await registerAndLogin(app, 'u_no_prefix');
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookie),
      payload: { subject: 'math', minutes: 30, startedAt: 'T12:00:00Z' },
    });
    expect(res.statusCode).toBe(400);
  });

  it('拒绝超长字符串', async () => {
    const cookie = await registerAndLogin(app, 'u_too_long');
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookie),
      payload: {
        subject: 'math',
        minutes: 30,
        startedAt: '2024-01-01T00:00:00.000Z' + 'x'.repeat(50),
      },
    });
    expect(res.statusCode).toBe(400);
  });

  it('接受合法 ISO 日期并原样落库', async () => {
    const cookie = await registerAndLogin(app, 'u_ok_iso');
    const iso = '2024-03-15T08:30:00.000Z';
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookie),
      payload: { subject: 'math', minutes: 45, startedAt: iso, note: 'ok' },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json() as { id: number; startedAt: string; note: string | null };
    expect(body.startedAt).toBe(iso);
    expect(body.note).toBe('ok');

    const row = db
      .prepare('SELECT started_at, note FROM focus_sessions WHERE id = ?')
      .get(body.id) as { started_at: string; note: string | null };
    expect(row.started_at).toBe(iso);
    expect(row.note).toBe('ok');
  });

  it('未提供 startedAt 时使用 nowIso 且格式合法', async () => {
    const cookie = await registerAndLogin(app, 'u_default_date');
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookie),
      payload: { subject: 'math', minutes: 10 },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json() as { startedAt: string };
    expect(/^\d{4}-\d{2}-\d{2}T/.test(body.startedAt)).toBe(true);
    expect(Number.isNaN(Date.parse(body.startedAt))).toBe(false);
  });
});

describe('POST /api/focus note 校验', () => {
  it('拒绝非字符串 note', async () => {
    const cookie = await registerAndLogin(app, 'u_note_num');
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookie),
      payload: { subject: 'math', minutes: 30, note: 123 as unknown as string },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'note must be a string up to 500 chars' });
  });

  it('拒绝超长 note', async () => {
    const cookie = await registerAndLogin(app, 'u_note_long');
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookie),
      payload: { subject: 'math', minutes: 30, note: 'x'.repeat(501) },
    });
    expect(res.statusCode).toBe(400);
  });

  it('note 缺省落库为 NULL', async () => {
    const cookie = await registerAndLogin(app, 'u_note_null');
    const res = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookie),
      payload: { subject: 'math', minutes: 20 },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json() as { id: number; note: string | null };
    expect(body.note).toBeNull();
    const row = db
      .prepare('SELECT note FROM focus_sessions WHERE id = ?')
      .get(body.id) as { note: string | null };
    expect(row.note).toBeNull();
  });
});

describe('focus user 隔离', () => {
  it('用户 A 创建的专注记录不会出现在用户 B 的列表中', async () => {
    const cookieA = await registerAndLogin(app, 'u_iso_a');
    const cookieB = await registerAndLogin(app, 'u_iso_b');

    const created = await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookieA),
      payload: { subject: 'math', minutes: 30, startedAt: '2024-05-01T00:00:00.000Z' },
    });
    expect(created.statusCode).toBe(201);

    const listB = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: authHeaders(cookieB),
    });
    expect(listB.statusCode).toBe(200);
    const arrB = listB.json() as Array<{ id: number }>;
    expect(arrB.find((r) => r.id === (created.json() as { id: number }).id)).toBeUndefined();

    const listA = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: authHeaders(cookieA),
    });
    const arrA = listA.json() as Array<{ id: number }>;
    expect(arrA.some((r) => r.id === (created.json() as { id: number }).id)).toBe(true);
  });

  it('stats 仅统计当前用户数据', async () => {
    const cookieA = await registerAndLogin(app, 'u_stats_a');
    const cookieB = await registerAndLogin(app, 'u_stats_b');

    await app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: authHeaders(cookieA),
      payload: { subject: 'math', minutes: 60 },
    });

    const statsB = await app.inject({
      method: 'GET',
      url: '/api/focus/stats',
      headers: authHeaders(cookieB),
    });
    expect(statsB.statusCode).toBe(200);
    const bodyB = statsB.json() as { totalMinutes: number; weekMinutes: number };
    expect(bodyB.totalMinutes).toBe(0);
    expect(bodyB.weekMinutes).toBe(0);

    const statsA = await app.inject({
      method: 'GET',
      url: '/api/focus/stats',
      headers: authHeaders(cookieA),
    });
    const bodyA = statsA.json() as { totalMinutes: number };
    expect(bodyA.totalMinutes).toBe(60);
  });
});
