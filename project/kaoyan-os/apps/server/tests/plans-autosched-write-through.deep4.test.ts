import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖 plans 自动排期写入穿透：首次 created/skipped/discarded、GET 落库明细、二次 POST 幂等及无重复写入；不与 deep.test.ts 的第二次 created=0 单点断言重叠。

describe('plans auto-schedule write through idempotent deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerPlansRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });

  const body = {
    subjects: ['math'],
    dailyMinutes: 480,
    examDate: '2026-11-05',
    startDate: '2026-11-01',
  };

  it('首次 POST 返回 created=6 skipped=0 discarded=12', async () => {
    const cookie = await registerAndLogin(app, rand('deep4a'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: body,
    });
    expect(res.statusCode).toBe(200);
    const json = res.json() as { created: number; skipped: number; discarded: number };
    expect(json.created).toBe(6);
    expect(json.skipped).toBe(0);
    expect(json.discarded).toBe(12);
  });

  it('首次 POST 后 GET /api/plans?date=2026-11-04 返回 2 条明细', async () => {
    const cookie = await registerAndLogin(app, rand('deep4b'));
    const post = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: body,
    });
    expect(post.statusCode).toBe(200);

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans?date=2026-11-04',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const rows = res.json() as Array<{
      date: string;
      subject: string;
      title: string;
      plannedMinutes: number;
      done: boolean;
    }>;
    expect(rows.length).toBe(2);
    const titles = rows.map((r) => r.title).sort();
    expect(titles).toEqual(['智能排期·数学 复习1-3天', '智能排期·数学 复习2-1天'].sort());
    for (const r of rows) {
      expect(r.date).toBe('2026-11-04');
      expect(r.subject).toBe('math');
      expect(r.plannedMinutes).toBe(30);
      expect(r.done).toBe(false);
    }
  });

  it('二次 POST 幂等：created=0 skipped=6 discarded=12 且不重复写入', async () => {
    const cookie = await registerAndLogin(app, rand('deep4c'));
    const first = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: body,
    });
    expect(first.statusCode).toBe(200);

    const second = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: body,
    });
    expect(second.statusCode).toBe(200);
    const json = second.json() as { created: number; skipped: number; discarded: number };
    expect(json.created).toBe(0);
    expect(json.skipped).toBe(6);
    expect(json.discarded).toBe(12);

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans?date=2026-11-04',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const rows = res.json() as Array<{ title: string }>;
    expect(rows.length).toBe(2);
  });
});
