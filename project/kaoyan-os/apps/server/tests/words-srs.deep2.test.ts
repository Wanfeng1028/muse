import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerWordsRoutes } from '../src/routes/words';
import { todayStr, addDays } from '../src/db';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

const TEST_USER = 'wordssrsdeep2';

function seedWord(db: DatabaseSync, word: string, dueDate: string, repetitions = 0): number {
  const info = db
    .prepare(
      "INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES ((SELECT id FROM users WHERE username = 'wordssrsdeep2'), ?, ?, ?, ?, ?, ?)",
    )
    .run(word, '', '测试释义', '', 'core500', '');
  const id = Number(info.lastInsertRowid);
  db.prepare(
    'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
  ).run(id, 2.5, 0, repetitions, dueDate);
  return id;
}

function seedWordCustom(
  db: DatabaseSync,
  word: string,
  dueDate: string,
  intervalDays: number,
  repetitions: number,
  ease: number,
): number {
  const info = db
    .prepare(
      "INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES ((SELECT id FROM users WHERE username = 'wordssrsdeep2'), ?, ?, ?, ?, ?, ?)",
    )
    .run(word, '', '测试释义', '', 'core500', '');
  const id = Number(info.lastInsertRowid);
  db.prepare(
    'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
  ).run(id, ease, intervalDays, repetitions, dueDate);
  return id;
}

let app: FastifyInstance;
let db: DatabaseSync;
let authCookie = '';

beforeEach(async () => {
  db = createRealDb(':memory:');
  app = Fastify({ logger: false });
  registerWordsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  authCookie = await registerAndLogin(app, TEST_USER);
});


afterEach(async () => {
  await app.close();
  db.close();
});

describe('words srs deep2 - SM-2 简化算法第二轮纵深', () => {
  it('grade=2 连续五轮（已修复 ease 上限 2.5）：intervalDays 序列精确为 1,3,8,20,50，ease 恒为 2.5，repetitions 依次 1..5', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'five', meaning: '测试释义' },
      headers: { cookie: authCookie },
    });
    expect(create.statusCode).toBe(201);

    const id = create.json().id as number;

    const expectedIntervals = [1, 3, 8, 20, 50];
    const expectedEase = [2.5, 2.5, 2.5, 2.5, 2.5];

    for (let i = 0; i < 5; i++) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        payload: { grade: 2 },
        headers: { cookie: authCookie },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.state.intervalDays).toBe(expectedIntervals[i]);

      expect(body.state.repetitions).toBe(i + 1);
      expect(body.state.ease).toBeCloseTo(expectedEase[i], 10);
      expect(body.state.dueDate).toBe(addDays(todayStr(), expectedIntervals[i]));
    }
  });

  it('grade=2 的 ease 上钳制在 2.5（已修复）：20 轮后 ease 精确=2.5，interval 收敛不再指数爆炸', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'nocap', meaning: '测试释义' },
      headers: { cookie: authCookie },
    });
    expect(create.statusCode).toBe(201);

    const id = create.json().id as number;

    const expectedIntervals = [
      1, 3, 8, 20, 50, 125, 313, 783, 1958, 4895, 12238, 30595, 76488, 191220, 478050, 1195125,
      2987813, 7469533, 18673833, 46684583,
    ];
    let last: any;
    for (let i = 0; i < 20; i++) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        payload: { grade: 2 },
        headers: { cookie: authCookie },
      });
      expect(res.statusCode).toBe(200);
      last = res.json();
      expect(last.state.intervalDays).toBe(expectedIntervals[i]);

    }

    expect(last.state.ease).toBe(2.5);
    expect(last.state.repetitions).toBe(20);
  });

  it('ease 从低位回升也被钳制在 2.5', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'recovercap', meaning: '测试释义' },
      headers: { cookie: authCookie },
    });
    expect(create.statusCode).toBe(201);
    const id = create.json().id as number;
    const down = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 0 },
      headers: { cookie: authCookie },
    });

    expect(down.statusCode).toBe(200);
    let last: any;
    for (let i = 0; i < 10; i++) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        payload: { grade: 2 },
        headers: { cookie: authCookie },
      });
      expect(res.statusCode).toBe(200);
      last = res.json();
      expect(last.state.ease).toBeLessThanOrEqual(2.5);

    }
    expect(last.state.ease).toBe(2.5);
  });
  it('连续 grade=0 六轮后 ease 钳制在 1.3，第 7 轮仍为 1.3，repetitions 恒 0，intervalDays 恒 1', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'again', meaning: '测试释义' },
      headers: { cookie: authCookie },
    });
    expect(create.statusCode).toBe(201);

    const id = create.json().id as number;

    let last: any;
    for (let i = 0; i < 6; i++) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        payload: { grade: 0 },
        headers: { cookie: authCookie },
      });
      expect(res.statusCode).toBe(200);
      last = res.json();
      expect(last.state.repetitions).toBe(0);
      expect(last.state.intervalDays).toBe(1);
      expect(last.state.ease).toBeGreaterThanOrEqual(1.3);

    }
    expect(last.state.ease).toBeCloseTo(1.3, 10);

    const seventh = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 0 },
      headers: { cookie: authCookie },
    });

    expect(seventh.statusCode).toBe(200);
    const body7 = seventh.json();
    expect(body7.state.repetitions).toBe(0);
    expect(body7.state.intervalDays).toBe(1);
    expect(body7.state.ease).toBeCloseTo(1.3, 10);
  });

  it('答错重置链：grade=2 三次 → grade=0 → 再 grade=2，三步逐段断言', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'chain', meaning: '测试释义' },
      headers: { cookie: authCookie },
    });
    expect(create.statusCode).toBe(201);

    const id = create.json().id as number;

    let res: any;
    for (let i = 0; i < 3; i++) {
      res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        payload: { grade: 2 },
        headers: { cookie: authCookie },
      });
      expect(res.statusCode).toBe(200);
    }
    let body = res.json();

    expect(body.state.repetitions).toBe(3);
    expect(body.state.intervalDays).toBe(8);
    expect(body.state.ease).toBeCloseTo(2.5, 10);

    const wrong = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 0 },
      headers: { cookie: authCookie },
    });

    expect(wrong.statusCode).toBe(200);
    body = wrong.json();
    expect(body.state.repetitions).toBe(0);
    expect(body.state.intervalDays).toBe(1);
    expect(body.state.ease).toBeCloseTo(2.3, 10);

    const again = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
      headers: { cookie: authCookie },
    });

    expect(again.statusCode).toBe(200);
    body = again.json();
    expect(body.state.repetitions).toBe(1);
    expect(body.state.intervalDays).toBe(1);
    expect(body.state.ease).toBeCloseTo(2.35, 10);
  });

  it('grade=1 中段精确值：interval_days=5,reps=3 → 6/4/2.45；interval_days=1,reps=2 → 1/3', async () => {
    const idA = seedWordCustom(db, 'midA', todayStr(), 5, 3, 2.5);
    const resA = await app.inject({
      method: 'POST',
      url: `/api/words/${idA}/review`,
      payload: { grade: 1 },
      headers: { cookie: authCookie },
    });

    expect(resA.statusCode).toBe(200);
    const bodyA = resA.json();
    expect(bodyA.state.intervalDays).toBe(6);
    expect(bodyA.state.repetitions).toBe(4);
    expect(bodyA.state.ease).toBeCloseTo(2.45, 10);

    const idB = seedWordCustom(db, 'midB', todayStr(), 1, 2, 2.5);
    const resB = await app.inject({
      method: 'POST',
      url: `/api/words/${idB}/review`,
      payload: { grade: 1 },
      headers: { cookie: authCookie },
    });

    expect(resB.statusCode).toBe(200);
    const bodyB = resB.json();
    expect(bodyB.state.intervalDays).toBe(1);
    expect(bodyB.state.repetitions).toBe(3);
  });

  it('dueDate 与 intervalDays 严格一致：grade=2 后 dueDate === addDays(todayStr(), intervalDays)', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'dueday', meaning: '测试释义' },
      headers: { cookie: authCookie },
    });
    expect(create.statusCode).toBe(201);
    const id = create.json().id as number;

    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state.dueDate).toBe(addDays(todayStr(), body.state.intervalDays));
  });

  it('review 不存在的 id：POST /api/words/99999/review → 404 且 error 为 单词不存在', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/99999/review',
      payload: { grade: 2 },
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(404);

    expect(res.json().error).toBe('单词不存在');
  });
});