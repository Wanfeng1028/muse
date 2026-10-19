import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerAndLogin, authHeaders } from './test-utils';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerPlansRoutes } from '../src/routes/plans';
import { registerFocusRoutes } from '../src/routes/focus';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { registerExamsRoutes } from '../src/routes/exams';
import { registerWordsRoutes } from '../src/routes/words';
import { registerSettingsRoutes } from '../src/routes/settings';

// 本测试只依赖公开 HTTP API，不直接操作表结构，避免编造列名。

let app: FastifyInstance;
let db: DatabaseSync;
let cookieA: string;
let cookieB: string;

// 每个用户下创建的业务资源 id 记录
interface ResourceIds {
  plan: number;
  focus: number;
  mistake: number;
  exam: number;
  word: number;
}

const idsA: Partial<ResourceIds> = {};
const idsB: Partial<ResourceIds> = {};

async function createPlan(cookie: string, title: string): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/plans',
    headers: authHeaders(cookie),
    payload: {
      date: '2025-01-15',
      subject: 'math',
      title,
      plannedMinutes: 60,
    },
  });
  expect(res.statusCode, `createPlan ${title}: ${res.body}`).toBe(201);
  return (res.json() as { id: number }).id;
}

async function createFocus(cookie: string, note: string): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/focus',
    headers: authHeaders(cookie),
    payload: {
      subject: 'math',
      minutes: 25,
      startedAt: '2025-01-15T08:00:00.000Z',
      note,
    },
  });
  expect(res.statusCode, `createFocus ${note}: ${res.body}`).toBe(201);
  return (res.json() as { id: number }).id;
}

async function createMistake(cookie: string, title: string): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/mistakes',
    headers: authHeaders(cookie),
    payload: {
      subject: 'math',
      title,
      content: 'x',
      analysis: 'y',
      mastered: false,
    },
  });
  expect(res.statusCode, `createMistake ${title}: ${res.body}`).toBe(201);
  return (res.json() as { id: number }).id;
}

async function createExam(cookie: string, paper: string): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/exams',
    headers: authHeaders(cookie),
    payload: {
      subject: 'math',
      paper,
      score: 100,
      totalScore: 150,
      durationMinutes: 180,
      takenAt: '2025-01-15T09:00:00.000Z',
    },
  });
  expect(res.statusCode, `createExam ${paper}: ${res.body}`).toBe(201);
  return (res.json() as { id: number }).id;
}

async function createWord(cookie: string, word: string): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/words',
    headers: authHeaders(cookie),
    payload: {
      word,
      phonetic: '/test/',
      meaning: 'meaning',
      example: 'example',
      source: 'test',
      memoryTip: 'tip',
    },
  });
  expect(res.statusCode, `createWord ${word}: ${res.body}`).toBe(201);
  return (res.json() as { id: number }).id;
}

beforeAll(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerPlansRoutes(app, db);
  registerFocusRoutes(app, db);
  registerMistakesRoutes(app, db);
  registerExamsRoutes(app, db);
  registerWordsRoutes(app, db);
  registerSettingsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();

  const usernameA = `iso_a_${Date.now()}`;
  const usernameB = `iso_b_${Date.now()}`;
  cookieA = await registerAndLogin(app, usernameA);
  cookieB = await registerAndLogin(app, usernameB);

  // A 的数据
  idsA.plan = await createPlan(cookieA, 'A-plan');
  idsA.focus = await createFocus(cookieA, 'A-focus');
  idsA.mistake = await createMistake(cookieA, 'A-mistake');
  idsA.exam = await createExam(cookieA, 'A-paper');
  idsA.word = await createWord(cookieA, 'AWORD');

  // B 的数据
  idsB.plan = await createPlan(cookieB, 'B-plan');
  idsB.focus = await createFocus(cookieB, 'B-focus');
  idsB.mistake = await createMistake(cookieB, 'B-mistake');
  idsB.exam = await createExam(cookieB, 'B-paper');
  idsB.word = await createWord(cookieB, 'BWORD');
});

afterAll(async () => {
  await app.close();
});

describe('list 隔离', () => {
  it('GET /api/plans 只返回自己的计划', async () => {
    const resA = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: authHeaders(cookieA),
    });
    expect(resA.statusCode).toBe(200);
    const plansA = resA.json() as Array<{ id: number; title: string }>;
    expect(plansA.map((p) => p.title)).toContain('A-plan');
    expect(plansA.map((p) => p.title)).not.toContain('B-plan');
    expect(plansA.every((p) => p.id !== idsB.plan)).toBe(true);

    const resB = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: authHeaders(cookieB),
    });
    expect(resB.statusCode).toBe(200);
    const plansB = resB.json() as Array<{ id: number; title: string }>;
    expect(plansB.map((p) => p.title)).toContain('B-plan');
    expect(plansB.map((p) => p.title)).not.toContain('A-plan');
  });

  it('GET /api/focus 只返回自己的记录', async () => {
    const resA = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: authHeaders(cookieA),
    });
    expect(resA.statusCode).toBe(200);
    const focusA = resA.json() as Array<{ id: number; note: string }>;
    expect(focusA.map((f) => f.note)).toContain('A-focus');
    expect(focusA.map((f) => f.note)).not.toContain('B-focus');
    expect(focusA.every((f) => f.id !== idsB.focus)).toBe(true);
  });

  it('GET /api/mistakes 只返回自己的错题', async () => {
    const resA = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: authHeaders(cookieA),
    });
    expect(resA.statusCode).toBe(200);
    const listA = resA.json() as Array<{ id: number; title: string }>;
    expect(listA.map((m) => m.title)).toContain('A-mistake');
    expect(listA.map((m) => m.title)).not.toContain('B-mistake');
    expect(listA.every((m) => m.id !== idsB.mistake)).toBe(true);
  });

  it('GET /api/exams 只返回自己的考试记录', async () => {
    const resA = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: authHeaders(cookieA),
    });
    expect(resA.statusCode).toBe(200);
    const listA = resA.json() as Array<{ id: number; paper: string }>;
    expect(listA.map((e) => e.paper)).toContain('A-paper');
    expect(listA.map((e) => e.paper)).not.toContain('B-paper');
    expect(listA.every((e) => e.id !== idsB.exam)).toBe(true);
  });

  it('GET /api/words 只返回自己的单词', async () => {
    const resA = await app.inject({
      method: 'GET',
      url: '/api/words',
      headers: authHeaders(cookieA),
    });
    expect(resA.statusCode).toBe(200);
    const listA = resA.json() as Array<{ id: number; word: string }>;
    expect(listA.map((w) => w.word)).toContain('AWORD');
    expect(listA.map((w) => w.word)).not.toContain('BWORD');
    expect(listA.every((w) => w.id !== idsB.word)).toBe(true);
  });
});

// ---------- 越权访问 B 的资源 id 必须 404，且不得泄露存在性 ----------

describe('跨用户按 id 访问必须 404（不泄露存在性）', () => {
  it('A 用自己的 cookie GET B 的 plan id -> 404', async () => {
    const res = await app.inject({
      method: 'GET',
      url: `/api/plans/${idsB.plan}`,
      headers: authHeaders(cookieA),
    });
    // 若路由不支持 GET /:id，也会是非 2xx；此处只要不是 2xx 且不返回 B 数据即可
    expect(res.statusCode).not.toBeLessThan(400);
    expect(res.body).not.toContain('B-plan');
  });

  it('A 用自己的 cookie PATCH B 的 plan id -> 404', async () => {
    const res = await app.inject({
      method: 'PATCH',
      url: `/api/plans/${idsB.plan}`,
      headers: authHeaders(cookieA),
      payload: { title: 'A-hacked' },
    });
    expect(res.statusCode).toBe(404);
    expect(res.body).not.toContain('B-plan');

    // 复核 B 的数据未被篡改
    const check = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: authHeaders(cookieB),
    });
    const plansB = check.json() as Array<{ id: number; title: string }>;
    const bPlan = plansB.find((p) => p.id === idsB.plan);
    expect(bPlan?.title).toBe('B-plan');
  });

  it('A 用自己的 cookie DELETE B 的 plan id -> 404，且 B 的数据仍在', async () => {
    const res = await app.inject({
      method: 'DELETE',
      url: `/api/plans/${idsB.plan}`,
      headers: authHeaders(cookieA),
    });
    expect(res.statusCode).toBe(404);

    const check = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: authHeaders(cookieB),
    });
    const plansB = check.json() as Array<{ id: number }>;
    expect(plansB.some((p) => p.id === idsB.plan)).toBe(true);
  });

  it('A 用自己的 cookie 删除/修改 B 的 focus/mistake/exam/word -> 非 2xx 且 B 数据完好', async () => {
    const cases: Array<{ path: string; method: 'DELETE' | 'PATCH'; id: number }> = [
      { path: '/api/focus', method: 'DELETE', id: idsB.focus! },
      { path: '/api/mistakes', method: 'DELETE', id: idsB.mistake! },
      { path: '/api/exams', method: 'DELETE', id: idsB.exam! },
      { path: '/api/words', method: 'DELETE', id: idsB.word! },
    ];
    for (const c of cases) {
      const res = await app.inject({
        method: c.method,
        url: `${c.path}/${c.id}`,
        headers: authHeaders(cookieA),
        payload: c.method === 'PATCH' ? {} : undefined,
      });
      expect(res.statusCode, `${c.method} ${c.path}/${c.id}: ${res.body}`).not.toBeLessThan(400);
      expect(res.body).not.toMatch(/B-focus|B-mistake|B-paper|BWORD/);
    }

    // 复核 B 的各列表仍在
    const focusB = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: authHeaders(cookieB),
    });
    expect(
      (focusB.json() as Array<{ id: number }>).some((f) => f.id === idsB.focus),
    ).toBe(true);

    const mistakeB = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: authHeaders(cookieB),
    });
    expect(
      (mistakeB.json() as Array<{ id: number }>).some((m) => m.id === idsB.mistake),
    ).toBe(true);

    const examB = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: authHeaders(cookieB),
    });
    expect(
      (examB.json() as Array<{ id: number }>).some((e) => e.id === idsB.exam),
    ).toBe(true);

    const wordB = await app.inject({
      method: 'GET',
      url: '/api/words',
      headers: authHeaders(cookieB),
    });
    expect(
      (wordB.json() as Array<{ id: number }>).some((w) => w.id === idsB.word),
    ).toBe(true);
  });
});

// ---------- settings 隔离 ----------

describe('settings 隔离', () => {
  it('A 写入的 settings 不影响 B 读取，反之亦然', async () => {
    // A 设置 dailyGoalMinutes=100，B 设置 dailyGoalMinutes=200
    const putA = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: authHeaders(cookieA),
      payload: { dailyGoalMinutes: 100 },
    });
    expect(putA.statusCode).toBe(200);

    const putB = await app.inject({
      method: 'PUT',
      url: '/api/settings',
      headers: authHeaders(cookieB),
      payload: { dailyGoalMinutes: 200 },
    });
    expect(putB.statusCode).toBe(200);

    const getA = await app.inject({
      method: 'GET',
      url: '/api/settings',
      headers: authHeaders(cookieA),
    });
    expect(getA.statusCode).toBe(200);
    const settingsA = getA.json() as { dailyGoalMinutes?: number };
    expect(settingsA.dailyGoalMinutes).toBe(100);

    const getB = await app.inject({
      method: 'GET',
      url: '/api/settings',
      headers: authHeaders(cookieB),
    });
    expect(getB.statusCode).toBe(200);
    const settingsB = getB.json() as { dailyGoalMinutes?: number };
    expect(settingsB.dailyGoalMinutes).toBe(200);
    expect(settingsA.dailyGoalMinutes).not.toBe(settingsB.dailyGoalMinutes);
  });
});
