import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('plans auto-schedule four subject offset deep4', () => {
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

  it('四科目排期返回 discarded=18、items.length=6 且 6 条 (date,title) 精确序列', async () => {
    const cookie = await registerAndLogin(app, rand('sched4'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math', 'english', 'politics', 'major'],
        dailyMinutes: 480,
        examDate: '2026-11-03',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      created: number;
      skipped: number;
      discarded: number;
      items: Array<{ date: string; title: string; plannedMinutes: number }>;
    };
    expect(body.discarded).toBe(18);
    expect(body.created).toBe(6);
    expect(body.items.length).toBe(6);
    expect(body.items.map((i) => [i.date, i.title])).toEqual([
      ['2026-11-01', '智能排期·数学 新学1'],
      ['2026-11-02', '智能排期·英语 新学1'],
      ['2026-11-02', '智能排期·数学 复习1-1天'],
      ['2026-11-03', '智能排期·数学 新学2'],
      ['2026-11-03', '智能排期·政治 新学1'],
      ['2026-11-03', '智能排期·英语 复习1-1天'],
    ]);
    expect(body.items.map((i) => i.plannedMinutes)).toEqual([60, 60, 30, 60, 60, 30]);
  });

  it('四科目偏移：math 新学在 11-01 与 11-03，english 在 11-02，politics 在 11-03，major 无条目', async () => {
    const cookie = await registerAndLogin(app, rand('sched4off'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math', 'english', 'politics', 'major'],
        dailyMinutes: 480,
        examDate: '2026-11-03',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      items: Array<{ date: string; subject: string; title: string }>;
    };
    const mathNew = body.items
      .filter((i) => i.subject === 'math' && i.title.includes('新学'))
      .map((i) => i.date);
    expect(mathNew).toEqual(['2026-11-01', '2026-11-03']);
    const englishNew = body.items
      .filter((i) => i.subject === 'english' && i.title.includes('新学'))
      .map((i) => i.date);
    expect(englishNew).toEqual(['2026-11-02']);
    const politicsNew = body.items
      .filter((i) => i.subject === 'politics' && i.title.includes('新学'))
      .map((i) => i.date);
    expect(politicsNew).toEqual(['2026-11-03']);
    expect(body.items.filter((i) => i.subject === 'major').length).toBe(0);
  });

  it('2026-11-03 当天三条顺序为两条新学在前、英语复习1-1天在后', async () => {
    const cookie = await registerAndLogin(app, rand('sched4ord'));
    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math', 'english', 'politics', 'major'],
        dailyMinutes: 480,
        examDate: '2026-11-03',
        startDate: '2026-11-01',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      items: Array<{ date: string; title: string }>;
    };
    const day = body.items.filter((i) => i.date === '2026-11-03');
    expect(day.length).toBe(3);
    expect(day[0].title.includes('新学')).toBe(true);
    expect(day[1].title.includes('新学')).toBe(true);
    expect(day[2].title).toBe('智能排期·英语 复习1-1天');
  });
});
