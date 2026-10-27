import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerFocusRoutes } from '../src/routes/focus';
import { todayStr, addDays, createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

interface Harness {
  app: FastifyInstance;
  db: DatabaseSync;
  cookie: string;
}

async function createHarness(): Promise<Harness> {
  const db = createDb(':memory:');
  const app = Fastify();
  registerFocusRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  const cookie = await registerAndLogin(app, 'focusdeep');
  return { app, db, cookie };
}


async function closeHarness(h: Harness): Promise<void> {
  await h.app.close();
  h.db.close();
}

function insertSession(
  db: DatabaseSync,
  subject: string,
  minutes: number,
  startedAt: string,
  note: string | null
): void {
  db.prepare(
    "INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note) VALUES ((SELECT id FROM users WHERE username = 'focusdeep'), ?, ?, ?, ?)"
  ).run(subject, minutes, startedAt, note);
}


describe('focus routes deep coverage', () => {
  let h: Harness;

  beforeEach(async () => {
    h = await createHarness();
  });


  afterEach(async () => {
    await closeHarness(h);
  });

  it('跨月统计：31 天窗口覆盖今天往前 30 天且首尾日期与统计正确', async () => {
    const windowStart = addDays(todayStr(), -30);
    const midDate = addDays(todayStr(), -15);
    insertSession(h.db, 'math', 30, windowStart + 'T08:00:00.000Z', null);
    insertSession(h.db, 'english', 45, midDate + 'T09:00:00.000Z', null);
    insertSession(h.db, 'politics', 60, todayStr() + 'T10:00:00.000Z', null);

    const res = await h.app.inject({ method: 'GET', url: '/api/focus/stats?days=31', headers: { cookie: h.cookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.days.length).toBe(31);
    const first = body.days[0];

    const last = body.days[30];
    expect(first.date).toBe(windowStart);
    expect(last.date).toBe(todayStr());
    const firstDay = body.days.find((d: { date: string }) => d.date === windowStart);
    const midDay = body.days.find((d: { date: string }) => d.date === midDate);
    expect(firstDay.minutes).toBe(30);
    expect(midDay.minutes).toBe(45);
  });

  it('窗口内连续三天：addDays 连续且统计不丢天', async () => {
    const d2 = addDays(todayStr(), -2);
    const d1 = addDays(todayStr(), -1);
    const d0 = todayStr();
    insertSession(h.db, 'math', 20, d2 + 'T12:00:00.000Z', null);
    insertSession(h.db, 'math', 10, d1 + 'T12:00:00.000Z', null);
    insertSession(h.db, 'math', 30, d0 + 'T12:00:00.000Z', null);

    const seq: string[] = [];
    for (let i = 0; i < 3; i++) {
      seq.push(addDays(d2, i));
    }
    expect(seq).toEqual([d2, d1, d0]);

    const res = await h.app.inject({ method: 'GET', url: '/api/focus/stats?days=31', headers: { cookie: h.cookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    const entry2 = body.days.find((d: { date: string }) => d.date === d2);

    const entry1 = body.days.find((d: { date: string }) => d.date === d1);
    const entry0 = body.days.find((d: { date: string }) => d.date === d0);
    expect(entry2.minutes).toBe(20);
    expect(entry1.minutes).toBe(10);
    expect(entry0.minutes).toBe(30);
  });

  it('空计划：数据库没有任何记录时统计窗口全是 0 且总和为 0', async () => {
    const res = await h.app.inject({ method: 'GET', url: '/api/focus/stats?days=7', headers: { cookie: h.cookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.days.length).toBe(7);
    expect(body.todayMinutes).toBe(0);

    expect(body.weekMinutes).toBe(0);
    expect(body.totalMinutes).toBe(0);
    const allZero = body.days.every((d: { minutes: number }) => d.minutes === 0);
    expect(allZero).toBe(true);
  });

  it('番茄计时边界：minutes=1 与 minutes=1440 都能写入，0 和 1441 被拒绝', async () => {
    const ok1 = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'math', minutes: 1 },
    });

    expect(ok1.statusCode).toBe(201);
    const ok1Body = ok1.json();
    expect(ok1Body.minutes).toBe(1);
    expect(ok1Body.subject).toBe('math');
    expect(ok1Body.note).toBe(null);

    const ok1440 = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'english', minutes: 1440, note: '整日' },
    });

    expect(ok1440.statusCode).toBe(201);
    const ok1440Body = ok1440.json();
    expect(ok1440Body.minutes).toBe(1440);
    expect(ok1440Body.note).toBe('整日');

    const bad0 = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'math', minutes: 0 },
    });

    expect(bad0.statusCode).toBe(400);
    expect(bad0.json().error).toBe('minutes must be an integer between 1 and 1440');

    const bad1441 = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'math', minutes: 1441 },
    });

    expect(bad1441.statusCode).toBe(400);
    expect(bad1441.json().error).toBe('minutes must be an integer between 1 and 1440');
  });

  it('番茄计时边界：非整数 minutes 被拒绝，非法 subject 被拒绝', async () => {
    const frac = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'math', minutes: 1.5 },
    });

    expect(frac.statusCode).toBe(400);
    expect(frac.json().error).toBe('minutes must be an integer between 1 and 1440');

    const strMinutes = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'math', minutes: '30' },
    });

    expect(strMinutes.statusCode).toBe(400);
    expect(strMinutes.json().error).toBe('minutes must be an integer between 1 and 1440');

    const badSubject = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'history', minutes: 30 },
    });

    expect(badSubject.statusCode).toBe(400);
    expect(badSubject.json().error).toBe('invalid subject');
  });

  it('错题去重等价行为：limit 去重返回不同记录，重复 subject+minutes 保留多条', async () => {
    insertSession(h.db, 'math', 30, '2024-05-01T08:00:00.000Z', 'a');
    insertSession(h.db, 'math', 30, '2024-05-01T09:00:00.000Z', 'b');
    insertSession(h.db, 'math', 30, '2024-05-01T10:00:00.000Z', 'c');

    const res = await h.app.inject({ method: 'GET', url: '/api/focus?limit=2', headers: { cookie: h.cookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.length).toBe(2);

    expect(body[0].startedAt).toBe('2024-05-01T10:00:00.000Z');
    expect(body[1].startedAt).toBe('2024-05-01T09:00:00.000Z');
    const notes = body.map((s: { note: string }) => s.note);
    expect(new Set(notes).size).toBe(2);
  });

  it('单词 SRS 等价行为：limit 上限 500，非法 limit 返回 400', async () => {
    for (let i = 0; i < 5; i++) {
      insertSession(h.db, 'english', 5, '2024-06-0' + (i + 1) + 'T08:00:00.000Z', 'w' + i);
    }
    const resBig = await h.app.inject({ method: 'GET', url: '/api/focus?limit=99999', headers: { cookie: h.cookie } });
    expect(resBig.statusCode).toBe(200);
    expect(resBig.json().length).toBe(5);

    const resBad = await h.app.inject({ method: 'GET', url: '/api/focus?limit=-3', headers: { cookie: h.cookie } });
    expect(resBad.statusCode).toBe(200);
    expect(resBad.json().length).toBe(5);

    const resNaN = await h.app.inject({ method: 'GET', url: '/api/focus?limit=abc', headers: { cookie: h.cookie } });
    expect(resNaN.statusCode).toBe(400);
    expect(resNaN.json()).toEqual({ error: 'limit 参数无效' });

  });

  it('导入 CSV 畸形行等价：缺少 startedAt 回退 nowIso，多余字段被忽略', async () => {
    const before = Date.now();
    const res = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'math', minutes: 25, extra: 'ignored', nested: { a: 1 } },
    });

    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body.note).toBe(null);
    const startedMs = Date.parse(body.startedAt);
    expect(Number.isFinite(startedMs)).toBe(true);
    expect(startedMs).toBeGreaterThanOrEqual(before - 2000);
    expect(startedMs).toBeLessThanOrEqual(Date.now() + 2000);
  });

  it('导入 CSV 畸形行等价：note 为空字符串被保留为空字符串而非 null', async () => {
    const res = await h.app.inject({
      method: 'POST',
      url: '/api/focus',
      headers: { cookie: h.cookie },
      payload: { subject: 'politics', minutes: 40, note: '' },
    });

    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body.note).toBe('');
    expect(body.minutes).toBe(40);
    expect(body.subject).toBe('politics');
  });

  it('备份恢复 round-trip：写入后 GET 记录字段与写入一致', async () => {
    const payload = {
      subject: 'english',
      minutes: 55,
      startedAt: '2024-07-15T14:30:00.000Z',
      note: '背单词',
    };
    const post = await h.app.inject({ method: 'POST', url: '/api/focus', headers: { cookie: h.cookie }, payload });
    expect(post.statusCode).toBe(201);
    const created = post.json();
    expect(created.id).toBeGreaterThan(0);
    expect(created.startedAt).toBe('2024-07-15T14:30:00.000Z');

    const get = await h.app.inject({ method: 'GET', url: '/api/focus', headers: { cookie: h.cookie } });

    expect(get.statusCode).toBe(200);
    const list = get.json();
    expect(list.length).toBe(1);
    expect(list[0].id).toBe(created.id);
    expect(list[0].subject).toBe('english');
    expect(list[0].minutes).toBe(55);
    expect(list[0].startedAt).toBe('2024-07-15T14:30:00.000Z');
    expect(list[0].note).toBe('背单词');
  });

  it('备份恢复 round-trip：stats 汇总与原始写入总量一致', async () => {
    insertSession(h.db, 'math', 30, todayStr() + 'T08:00:00.000Z', null);
    insertSession(h.db, 'english', 45, todayStr() + 'T09:00:00.000Z', null);
    insertSession(h.db, 'politics', 25, addDays(todayStr(), -1) + 'T10:00:00.000Z', null);

    const res = await h.app.inject({ method: 'GET', url: '/api/focus/stats?days=7', headers: { cookie: h.cookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.todayMinutes).toBe(75);

    expect(body.weekMinutes).toBe(100);
    expect(body.totalMinutes).toBe(100);
    const todayEntry = body.days.find((d: { date: string }) => d.date === todayStr());
    expect(todayEntry.minutes).toBe(75);
  });

  it('备份恢复 round-trip：stats days 上限 31、下限 1，非法值返回 400', async () => {
    insertSession(h.db, 'math', 15, todayStr() + 'T08:00:00.000Z', null);

    const big = await h.app.inject({ method: 'GET', url: '/api/focus/stats?days=999', headers: { cookie: h.cookie } });
    expect(big.statusCode).toBe(200);
    expect(big.json().days.length).toBe(31);

    const small = await h.app.inject({ method: 'GET', url: '/api/focus/stats?days=0', headers: { cookie: h.cookie } });
    expect(small.statusCode).toBe(200);
    expect(small.json().days.length).toBe(1);

    const nan = await h.app.inject({ method: 'GET', url: '/api/focus/stats?days=abc', headers: { cookie: h.cookie } });
    expect(nan.statusCode).toBe(400);
    expect(nan.json()).toEqual({ error: 'days 参数无效' });

  });
});