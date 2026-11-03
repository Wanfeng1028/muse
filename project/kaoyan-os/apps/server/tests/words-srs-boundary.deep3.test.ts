import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { registerWordsRoutes } from '../src/routes/words';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';
import { todayStr, addDays } from '../src/db';

describe('words SRS boundary deep3', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let cookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerWordsRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'srsdeep3a');
  });

  afterEach(async () => {
    await app.close();
  });

  async function createWord(word: string, meaning: string): Promise<number> {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: { cookie },
      payload: { word, meaning },
    });
    expect(res.statusCode).toBe(201);
    return (res.json() as { id: number }).id;
  }

  it('grade=-1 返回 400 且文案为 grade 必须为 0|1|2', async () => {
    const id = await createWord('boundaryone', '边界一');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: -1 },
    });
    expect(res.statusCode).toBe(400);
    expect((res.json() as { error: string }).error).toBe('grade 必须为 0|1|2');
  });

  it('grade=3 返回 400 且文案为 grade 必须为 0|1|2', async () => {
    const id = await createWord('boundarytwo', '边界二');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 3 },
    });
    expect(res.statusCode).toBe(400);
    expect((res.json() as { error: string }).error).toBe('grade 必须为 0|1|2');
  });

  it('grade=1.5 返回 400 且文案为 grade 必须为 0|1|2', async () => {
    const id = await createWord('boundarythree', '边界三');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 1.5 },
    });
    expect(res.statusCode).toBe(400);
    expect((res.json() as { error: string }).error).toBe('grade 必须为 0|1|2');
  });

  it('grade="2" 字符串返回 400 且文案为 grade 必须为 0|1|2', async () => {
    const id = await createWord('boundaryfour', '边界四');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: '2' },
    });
    expect(res.statusCode).toBe(400);
    expect((res.json() as { error: string }).error).toBe('grade 必须为 0|1|2');
  });

  it('body 为空对象导致 grade 缺失时返回 400 且文案为 grade 必须为 0|1|2', async () => {
    const id = await createWord('boundaryfive', '边界五');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: {},
    });
    expect(res.statusCode).toBe(400);
    expect((res.json() as { error: string }).error).toBe('grade 必须为 0|1|2');
  });

  it('grade=0 连续 10 次后 ease 被钳制在 1.3，intervalDays=1，repetitions=0，dueDate 为明天', async () => {
    const id = await createWord('boundarysix', '边界六');
    const tomorrow = addDays(todayStr(), 1);
    for (let i = 0; i < 10; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: 0 },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as {
        id: number;
        state: { ease: number; intervalDays: number; repetitions: number; dueDate: string };
      };
      expect(body.id).toBe(id);
      expect(body.state.intervalDays).toBe(1);
      expect(body.state.repetitions).toBe(0);
      expect(body.state.dueDate).toBe(tomorrow);
    }
    const row = db
      .prepare('SELECT ease, interval_days, repetitions FROM srs_state WHERE word_id = ?')
      .get(id) as { ease: number; interval_days: number; repetitions: number };
    expect(row.ease).toBeCloseTo(1.3, 4);
    expect(row.interval_days).toBe(1);
    expect(row.repetitions).toBe(0);
  });

  it('grade=1 前两次：intervalDays 恒为 1，repetitions 1→2，ease 2.5→2.45→2.4', async () => {
    const id = await createWord('boundaryseven', '边界七');
    const first = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 1 },
    });
    expect(first.statusCode).toBe(200);
    const firstBody = first.json() as {
      state: { ease: number; intervalDays: number; repetitions: number };
    };
    expect(firstBody.state.repetitions).toBe(1);
    expect(firstBody.state.intervalDays).toBe(1);
    expect(firstBody.state.ease).toBeCloseTo(2.45, 4);

    const second = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 1 },
    });
    expect(second.statusCode).toBe(200);
    const secondBody = second.json() as {
      state: { ease: number; intervalDays: number; repetitions: number };
    };
    expect(secondBody.state.repetitions).toBe(2);
    expect(secondBody.state.intervalDays).toBe(1);
    expect(secondBody.state.ease).toBeCloseTo(2.4, 4);

    const row = db
      .prepare('SELECT ease, interval_days, repetitions FROM srs_state WHERE word_id = ?')
      .get(id) as { ease: number; interval_days: number; repetitions: number };
    expect(row.ease).toBeCloseTo(2.4, 4);
    expect(row.interval_days).toBe(1);
    expect(row.repetitions).toBe(2);
  });

  it('grade=2 连续 5 次：ease 恒为 2.5，intervalDays 1→3→8→20→50，dueDate 单调递增', async () => {
    const id = await createWord('boundaryeight', '边界八');
    const expectedIntervals = [1, 3, 8, 20, 50];
    const dueDates: string[] = [];
    for (let i = 0; i < 5; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: 2 },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as {
        state: { ease: number; intervalDays: number; repetitions: number; dueDate: string };
      };
      expect(body.state.ease).toBeCloseTo(2.5, 4);
      expect(body.state.intervalDays).toBe(expectedIntervals[i]);
      expect(body.state.repetitions).toBe(i + 1);
      expect(body.state.dueDate).toBe(addDays(todayStr(), expectedIntervals[i]));
      dueDates.push(body.state.dueDate);
    }
    for (let i = 1; i < dueDates.length; i += 1) {
      expect(dueDates[i] > dueDates[i - 1]).toBe(true);
    }
  });

  it('POST /api/words/999999/review 返回 404 且文案为 单词不存在', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/999999/review',
      headers: { cookie },
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(404);
    expect((res.json() as { error: string }).error).toBe('单词不存在');
  });

  it('跨用户复习他人单词返回 404 且响应体与不存在 id 完全一致', async () => {
    const id = await createWord('boundarynine', '边界九');
    const cookieB = await registerAndLogin(app, 'srsdeep3b');

    const notFound = await app.inject({
      method: 'POST',
      url: '/api/words/999999/review',
      headers: { cookie },
      payload: { grade: 2 },
    });
    const crossUser = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie: cookieB },
      payload: { grade: 2 },
    });
    expect(crossUser.statusCode).toBe(404);
    expect(crossUser.json()).toEqual(notFound.json());

    const row = db
      .prepare('SELECT repetitions FROM srs_state WHERE word_id = ?')
      .get(id) as { repetitions: number };
    expect(row.repetitions).toBe(0);
  });

  it('DELETE 后 GET /api/words 不含该词且 review 返回 404', async () => {
    const id = await createWord('boundaryten', '边界十');
    const before = await app.inject({
      method: 'GET',
      url: '/api/words',
      headers: { cookie },
    });
    expect(before.statusCode).toBe(200);
    expect((before.json() as Array<{ id: number }>).some((w) => w.id === id)).toBe(true);

    const del = await app.inject({
      method: 'DELETE',
      url: `/api/words/${id}`,
      headers: { cookie },
    });
    expect(del.statusCode).toBe(200);
    expect((del.json() as { ok: boolean }).ok).toBe(true);

    const after = await app.inject({
      method: 'GET',
      url: '/api/words',
      headers: { cookie },
    });
    expect(after.statusCode).toBe(200);
    expect((after.json() as Array<{ id: number }>).some((w) => w.id === id)).toBe(false);

    const review = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 2 },
    });
    expect(review.statusCode).toBe(404);
    expect((review.json() as { error: string }).error).toBe('单词不存在');

    const srsRow = db
      .prepare('SELECT COUNT(*) AS c FROM srs_state WHERE word_id = ?')
      .get(id) as { c: number };
    expect(srsRow.c).toBe(0);
  });

  it('due 按 due_date 升序返回前天、昨天、今天', async () => {
    const idY = await createWord('boundaryeleveny', '边界十一前天');
    const idT = await createWord('boundaryelevent', '边界十一昨天');
    const idM = await createWord('boundaryelevenm', '边界十一今天');
    const dayBeforeYesterday = addDays(todayStr(), -2);
    const yesterday = addDays(todayStr(), -1);
    const today = todayStr();

    db.prepare('UPDATE srs_state SET due_date = ? WHERE word_id = ?').run(dayBeforeYesterday, idY);
    db.prepare('UPDATE srs_state SET due_date = ? WHERE word_id = ?').run(yesterday, idT);
    db.prepare('UPDATE srs_state SET due_date = ? WHERE word_id = ?').run(today, idM);

    const res = await app.inject({
      method: 'GET',
      url: '/api/words/due',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as Array<{ id: number; state: { dueDate: string } }>;
    expect(body.length).toBe(3);
    expect(body.map((w) => w.id)).toEqual([idY, idT, idM]);
    expect(body.map((w) => w.state.dueDate)).toEqual([dayBeforeYesterday, yesterday, today]);
  });
});