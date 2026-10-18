import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb, todayStr, addDays } from '../src/db';
import { registerWordsRoutes } from '../src/routes/words';
import type { DatabaseSync } from 'node:sqlite';

let db: DatabaseSync;
let app: FastifyInstance;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerWordsRoutes(app, db);
  await app.ready();
});

afterEach(async () => {
  await app.close();
});

async function createWord(word: string, meaning: string): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/words',
    payload: { word, meaning },
  });
  expect(res.statusCode).toBe(201);
  return res.json().id as number;
}

describe('POST /api/words/:id/review - ease 下限钳制', () => {
  it('连续 10 次 grade=0 复习后 ease 恒 >= 1.3 且 repetitions 恒为 0', async () => {
    const id = await createWord('clamp', '钳制');
    for (let i = 0; i < 10; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        payload: { grade: 0 },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.state.ease).toBeGreaterThanOrEqual(1.3);
      expect(body.state.repetitions).toBe(0);
    }
    const row = db
      .prepare('SELECT ease FROM srs_state WHERE word_id = ?')
      .get(id) as { ease: number };
    expect(row.ease).toBeGreaterThanOrEqual(1.3);
    expect(row.ease).toBeCloseTo(1.3, 10);
  });
});

describe('POST /api/words/:id/review - grade=1 首评分支', () => {
  it('repetitions=0 时 grade=1 使 intervalDays=1 且 ease 下降 0.05', async () => {
    const id = await createWord('firstHard', '首评困难');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 1 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state.intervalDays).toBe(1);
    expect(body.state.repetitions).toBe(1);
    expect(body.state.ease).toBeCloseTo(2.45, 10);
  });
});

describe('POST /api/words/:id/review - grade=2 精确进阶', () => {
  it('reps=0 -> intervalDays=1, ease=2.5（上限钳制）', async () => {
    const id = await createWord('advA', '进阶A');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state.repetitions).toBe(1);
    expect(body.state.intervalDays).toBe(1);
    expect(body.state.ease).toBeCloseTo(2.5, 10);
  });

  it('reps=1 -> intervalDays=3, ease=2.5（上限钳制）', async () => {
    const id = await createWord('advB', '进阶B');
    await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
    });
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state.repetitions).toBe(2);
    expect(body.state.intervalDays).toBe(3);
    expect(body.state.ease).toBeCloseTo(2.5, 10);
  });

  it('reps=2 -> intervalDays = Math.round(3 * ease)', async () => {
    const id = await createWord('advC', '进阶C');
    await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
    });
    await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
    });
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state.repetitions).toBe(3);
    expect(body.state.ease).toBeCloseTo(2.5, 10);
    expect(body.state.intervalDays).toBe(Math.round(3 * body.state.ease));
  });
});

describe('POST /api/words/:id/review - grade 类型与范围校验', () => {
  it.each([
    ['3', 3],
    ['-1', -1],
    ["'2' 字符串", '2'],
    ['null', null],
  ])('grade=%s 返回 400 且错误文案为 grade 必须为 0|1|2', async (_label, grade) => {
    const id = await createWord(`badgrade${String(_label)}`, '非法成绩');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('grade 必须为 0|1|2');
  });

  it('缺失 grade 字段返回 400 且错误文案为 grade 必须为 0|1|2', async () => {
    const id = await createWord('missinggrade', '缺成绩');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: {},
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('grade 必须为 0|1|2');
  });
});

describe('POST /api/words/:id/review - 缺 srs_state 行的 INSERT 分支', () => {
  it('无 srs_state 的词 grade=2 返回 200 并插入 srs_state 行', async () => {
    const info = db
      .prepare("INSERT INTO words (word, meaning) VALUES ('ghostword', '幽灵词')")
      .run();
    const ghostId = Number(info.lastInsertRowid);

    const before = db
      .prepare('SELECT COUNT(*) AS c FROM srs_state WHERE word_id = ?')
      .get(ghostId) as { c: number };
    expect(before.c).toBe(0);

    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${ghostId}/review`,
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state.repetitions).toBe(1);
    expect(body.state.intervalDays).toBe(1);
    expect(body.state.ease).toBeCloseTo(2.5, 10);

    const after = db
      .prepare(
        'SELECT ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?',
      )
      .get(ghostId) as {
      ease: number;
      interval_days: number;
      repetitions: number;
      due_date: string;
    };
    expect(after).toBeDefined();
    expect(after.ease).toBeCloseTo(2.5, 10);
    expect(after.interval_days).toBe(1);
    expect(after.repetitions).toBe(1);
    expect(after.due_date).toBe(addDays(todayStr(), 1));
  });
});

describe('DELETE /api/words/:id - id 格式与不存在', () => {
  it.each([
    ['abc', 'abc'],
    ['0', '0'],
    ['-1', '-1'],
    ['1.5', '1.5'],
  ])('id=%s 返回 400 且错误文案为 id 无效', async (_label, rawId) => {
    const res = await app.inject({
      method: 'DELETE',
      url: `/api/words/${rawId}`,
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('id 无效');
  });

  it('不存在的 id 返回 404 且错误文案为 单词不存在', async () => {
    const res = await app.inject({
      method: 'DELETE',
      url: '/api/words/999999',
    });
    expect(res.statusCode).toBe(404);
    expect(res.json().error).toBe('单词不存在');
  });
});

describe('GET /api/words/due - 未来 due_date 排除与排序', () => {
  it('due_date 改为明天的词不出现在 due 列表，按 due_date、id 升序', async () => {
    const pastId = await createWord('duePast', '过去到期');
    const todayId = await createWord('dueToday', '今天到期');
    const futureId = await createWord('dueFuture', '未来到期');

    const today = todayStr();
    const tomorrow = addDays(today, 1);
    const yesterday = addDays(today, -1);

    db.prepare('UPDATE srs_state SET due_date = ? WHERE word_id = ?').run(
      yesterday,
      pastId,
    );
    db.prepare('UPDATE srs_state SET due_date = ? WHERE word_id = ?').run(
      today,
      todayId,
    );
    db.prepare('UPDATE srs_state SET due_date = ? WHERE word_id = ?').run(
      tomorrow,
      futureId,
    );

    const res = await app.inject({ method: 'GET', url: '/api/words/due' });
    expect(res.statusCode).toBe(200);
    const list = res.json() as Array<{ id: number; state: { dueDate: string } }>;
    const ids = list.map((w) => w.id);
    expect(ids).toContain(pastId);
    expect(ids).toContain(todayId);
    expect(ids).not.toContain(futureId);

    const pastIndex = ids.indexOf(pastId);
    const todayIndex = ids.indexOf(todayId);
    expect(pastIndex).toBeLessThan(todayIndex);
    expect(list[pastIndex].state.dueDate).toBe(yesterday);
    expect(list[todayIndex].state.dueDate).toBe(today);
  });
});