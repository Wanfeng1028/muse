import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖 auto-schedule 预览/落库接口在"空 subjects 各种形态"下的边界行为；
// 不与 plans-autoschedule-invalid.deep3.test.ts 的非法字段 400 用例重叠。

describe('plans auto-schedule empty subjects edge deep4', () => {
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

  it('preview subjects 全空格返回 400 subjects 不能为空', async () => {
    const cookie = await registerAndLogin(app, rand('pvwsp'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=%20%20%20&dailyMinutes=60&examDate=2026-12-31&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('subjects 不能为空');
  });

  it('preview subjects 全逗号返回 400 subjects 不能为空', async () => {
    const cookie = await registerAndLogin(app, rand('pvwcm'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=,,,&dailyMinutes=60&examDate=2026-12-31&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('subjects 不能为空');
  });

  it('preview subjects 中间含空串返回 200 且含 math 与 english', async () => {
    const cookie = await registerAndLogin(app, rand('pvwmx'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math,,english&dailyMinutes=60&examDate=2026-12-31&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const items = res.json().items as Array<{ subject: string }>;
    expect(items.some((i) => i.subject === 'math')).toBe(true);
    expect(items.some((i) => i.subject === 'english')).toBe(true);
  });

  it('preview subjects 前后空格被 trim 后返回 200', async () => {
    const cookie = await registerAndLogin(app, rand('pvwts'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=%20math%20,%20english%20&dailyMinutes=60&examDate=2026-12-31&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const items = res.json().items as Array<{ subject: string }>;
    expect(items.some((i) => i.subject === 'math')).toBe(true);
    expect(items.some((i) => i.subject === 'english')).toBe(true);
  });

  it('POST 空数组与含空串科目分别返回对应 400', async () => {
    const cookieA = await registerAndLogin(app, rand('pstemp'));
    const emptyRes = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieA },
      payload: { subjects: [], dailyMinutes: 60, examDate: '2026-12-31', startDate: '2026-11-01' },
    });
    expect(emptyRes.statusCode).toBe(400);
    expect(emptyRes.json().error).toBe('subjects 不能为空');

    const cookieB = await registerAndLogin(app, rand('pstbad'));
    const badRes = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: { subjects: ['math', ''], dailyMinutes: 60, examDate: '2026-12-31', startDate: '2026-11-01' },
    });
    expect(badRes.statusCode).toBe(400);
    expect(badRes.json().error).toBe('subject 非法');
  });

  it('POST 重复科目返回 200 且 items 非空', async () => {
    const cookie = await registerAndLogin(app, rand('pstdup'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: { subjects: ['math', 'math'], dailyMinutes: 60, examDate: '2026-12-31', startDate: '2026-11-01' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(Array.isArray(body.items)).toBe(true);
    expect(body.items.length).toBeGreaterThan(0);
  });
});
