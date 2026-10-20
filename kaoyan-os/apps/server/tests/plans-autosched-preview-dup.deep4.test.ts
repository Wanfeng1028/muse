import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule preview duplicate subjects deep4', () => {
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

  it('重复科目 math,math 的两个新学1 分别落在 2026-11-01 与 2026-11-02', async () => {
    const cookie = await registerAndLogin(app, rand('dup'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math,math&dailyMinutes=480&examDate=2026-11-10&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ date: string; subject: string; title: string; kind: string }> };
    const newOnes = body.items.filter((i) => i.title === '智能排期·数学 新学1');
    expect(newOnes.length).toBe(2);
    const dates = newOnes.map((i) => i.date).sort();
    expect(dates).toEqual(['2026-11-01', '2026-11-02']);
    expect(newOnes.every((i) => i.subject === 'math')).toBe(true);
    expect(newOnes.every((i) => i.kind === 'new')).toBe(true);
  });

  it('2026-11-02 当天新学1 排在复习1-1天 之前', async () => {
    const cookie = await registerAndLogin(app, rand('ord'));
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/auto-schedule/preview?subjects=math,math&dailyMinutes=480&examDate=2026-11-10&startDate=2026-11-01',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { items: Array<{ date: string; subject: string; title: string; kind: string }> };
    const day = body.items.filter((i) => i.date === '2026-11-02');
    expect(day.length).toBe(2);
    expect(day[0].title).toBe('智能排期·数学 新学1');
    expect(day[0].kind).toBe('new');
    expect(day[1].title).toBe('智能排期·数学 复习1-1天');
    expect(day[1].kind).toBe('review');
  });
});
