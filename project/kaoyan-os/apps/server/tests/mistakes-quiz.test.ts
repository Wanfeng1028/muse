import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: ReturnType<typeof createDb>;
let app: FastifyInstance;
let authCookie: string;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  registerMistakesRoutes(app, db);
  await app.ready();
  authCookie = await registerAndLogin(app, 'quiztest');
});

afterEach(async () => {
  await app.close();
});

async function createMistake(
  cookie: string,
  payload: { subject: string; title: string; content: string },
): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/mistakes',
    headers: { cookie },
    payload,
  });
  expect(res.statusCode).toBe(201);
  return res.json().id;
}

async function setMastered(cookie: string, id: number, mastered: boolean) {
  const res = await app.inject({
    method: 'PATCH',
    url: `/api/mistakes/${id}`,
    headers: { cookie },
    payload: { mastered },
  });
  expect(res.statusCode).toBe(200);
}

async function generateQuiz(cookie: string, payload: Record<string, unknown>) {
  return app.inject({
    method: 'POST',
    url: '/api/mistakes/quiz/generate',
    headers: { cookie },
    payload,
  });
}

async function gradeQuiz(cookie: string, payload: Record<string, unknown>) {
  return app.inject({
    method: 'POST',
    url: '/api/mistakes/quiz/grade',
    headers: { cookie },
    payload,
  });
}

describe('POST /api/mistakes/quiz/generate', () => {
  it('未登录返回 401', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/mistakes/quiz/generate',
      payload: {},
    });
    expect(res.statusCode).toBe(401);
  });

  it('subject 非法返回 400 精确文案；limit 非法返回 400 精确文案', async () => {
    const resSubject = await generateQuiz(authCookie, { subject: 'xx' });
    expect(resSubject.statusCode).toBe(400);
    expect(resSubject.json()).toEqual({ error: 'subject 非法' });

    for (const limit of [0, 101, 2.5]) {
      const res = await generateQuiz(authCookie, { limit });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'limit 非法' });
    }
  });

  it('from 格式非法与 from > to 返回 400 精确文案', async () => {
    const resFormat = await generateQuiz(authCookie, { from: '2026-13-01' });
    expect(resFormat.statusCode).toBe(400);
    expect(resFormat.json()).toEqual({
      error: 'from/to 格式非法，应为 YYYY-MM-DD',
    });

    const resRange = await generateQuiz(authCookie, {
      from: '2026-03-01',
      to: '2026-01-01',
    });
    expect(resRange.statusCode).toBe(400);
    expect(resRange.json()).toEqual({ error: 'from 不能晚于 to' });
  });

  it('缺省只返回未掌握，且不含 analysis 字段', async () => {
    const id1 = await createMistake(authCookie, {
      subject: 'math',
      title: 't1',
      content: 'c1',
    });
    const id2 = await createMistake(authCookie, {
      subject: 'math',
      title: 't2',
      content: 'c2',
    });
    const id3 = await createMistake(authCookie, {
      subject: 'math',
      title: 't3',
      content: 'c3',
    });
    await setMastered(authCookie, id3, true);

    const res = await generateQuiz(authCookie, {});
    expect(res.statusCode).toBe(200);
    const items = res.json();
    expect(items).toHaveLength(2);
    const ids = items.map((i: any) => i.id).sort((a: number, b: number) => a - b);
    expect(ids).toEqual([id1, id2].sort((a, b) => a - b));
    for (const item of items) {
      expect('analysis' in item).toBe(false);
    }
  });

  it('unmasteredOnly=false 返回全部，未掌握排在前面', async () => {
    const id1 = await createMistake(authCookie, {
      subject: 'math',
      title: 't1',
      content: 'c1',
    });
    const id2 = await createMistake(authCookie, {
      subject: 'math',
      title: 't2',
      content: 'c2',
    });
    const id3 = await createMistake(authCookie, {
      subject: 'math',
      title: 't3',
      content: 'c3',
    });
    await setMastered(authCookie, id1, true);
    await setMastered(authCookie, id3, true);

    const res = await generateQuiz(authCookie, { unmasteredOnly: false });
    expect(res.statusCode).toBe(200);
    const items = res.json();
    expect(items).toHaveLength(3);
    expect(items[0].id).toBe(id2);
  });

  it('subject 过滤只返回对应学科', async () => {
    const mathId = await createMistake(authCookie, {
      subject: 'math',
      title: 't1',
      content: 'c1',
    });
    await createMistake(authCookie, {
      subject: 'english',
      title: 't2',
      content: 'c2',
    });

    const res = await generateQuiz(authCookie, { subject: 'math' });
    expect(res.statusCode).toBe(200);
    const items = res.json();
    expect(items).toHaveLength(1);
    expect(items[0].id).toBe(mathId);
    expect(items[0].subject).toBe('math');
  });

  it('limit 生效', async () => {
    for (let i = 0; i < 5; i++) {
      await createMistake(authCookie, {
        subject: 'math',
        title: `t${i}`,
        content: `c${i}`,
      });
    }

    const res = await generateQuiz(authCookie, { limit: 2 });
    expect(res.statusCode).toBe(200);
    const items = res.json();
    expect(items).toHaveLength(2);
  });

  it('用户隔离：其他用户错题不出现', async () => {
    await createMistake(authCookie, {
      subject: 'math',
      title: 'mine',
      content: 'c1',
    });
    const authCookie2 = await registerAndLogin(app, 'quiztest2');
    await createMistake(authCookie2, {
      subject: 'math',
      title: 'theirs',
      content: 'c2',
    });

    const res = await generateQuiz(authCookie, {});
    expect(res.statusCode).toBe(200);
    const items = res.json();
    expect(items).toHaveLength(1);
    expect(items[0].title).toBe('mine');
  });
});

describe('POST /api/mistakes/quiz/grade', () => {
  it('未登录返回 401', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/mistakes/quiz/grade',
      payload: { results: [] },
    });
    expect(res.statusCode).toBe(401);
  });

  it('results 非法情况返回 400 精确文案', async () => {
    const resEmpty = await gradeQuiz(authCookie, { results: [] });
    expect(resEmpty.statusCode).toBe(400);
    expect(resEmpty.json()).toEqual({ error: 'results 不能为空' });

    const resMissing = await gradeQuiz(authCookie, {});
    expect(resMissing.statusCode).toBe(400);
    expect(resMissing.json()).toEqual({ error: 'results 不能为空' });

    const bigResults = Array.from({ length: 201 }, (_, i) => ({
      mistakeId: i + 1,
      correct: true,
    }));
    const resBig = await gradeQuiz(authCookie, { results: bigResults });
    expect(resBig.statusCode).toBe(400);
    expect(resBig.json()).toEqual({ error: 'results 不能超过 200 条' });

    const resBadItem = await gradeQuiz(authCookie, {
      results: [{ mistakeId: 1.5, correct: true }],
    });
    expect(resBadItem.statusCode).toBe(400);
    expect(resBadItem.json()).toEqual({ error: 'results 项非法' });

    const resDup = await gradeQuiz(authCookie, {
      results: [
        { mistakeId: 1, correct: true },
        { mistakeId: 1, correct: false },
      ],
    });
    expect(resDup.statusCode).toBe(400);
    expect(resDup.json()).toEqual({ error: 'mistakeId 不能重复' });
  });

  it('不存在的 id 返回 404 精确文案', async () => {
    const res = await gradeQuiz(authCookie, {
      results: [{ mistakeId: 99999, correct: true }],
    });
    expect(res.statusCode).toBe(404);
    expect(res.json()).toEqual({ error: '错题不存在' });
  });

  it('原子性：含不存在 id 时全部不更新', async () => {
    const id = await createMistake(authCookie, {
      subject: 'math',
      title: 't1',
      content: 'c1',
    });

    const res = await gradeQuiz(authCookie, {
      results: [
        { mistakeId: id, correct: true },
        { mistakeId: 99999, correct: true },
      ],
    });
    expect(res.statusCode).toBe(404);
    expect(res.json()).toEqual({ error: '错题不存在' });

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: { cookie: authCookie },
    });
    expect(listRes.statusCode).toBe(200);
    const items = listRes.json();
    const target = items.find((i: any) => i.id === id);
    expect(target.mastered).toBe(false);
  });

  it('用户隔离：提交他人错题返回 404', async () => {
    const authCookie2 = await registerAndLogin(app, 'quiztest2');
    const otherId = await createMistake(authCookie2, {
      subject: 'math',
      title: 'theirs',
      content: 'c1',
    });

    const res = await gradeQuiz(authCookie, {
      results: [{ mistakeId: otherId, correct: true }],
    });
    expect(res.statusCode).toBe(404);
    expect(res.json()).toEqual({ error: '错题不存在' });
  });

  it('correct=true 将 mastered 置为 true 并计入 updatedIds', async () => {
    const id = await createMistake(authCookie, {
      subject: 'math',
      title: 't1',
      content: 'c1',
    });

    const res = await gradeQuiz(authCookie, {
      results: [{ mistakeId: id, correct: true }],
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.total).toBe(1);
    expect(body.correct).toBe(1);
    expect(body.wrong).toBe(0);
    expect(body.updatedIds).toEqual([id]);

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: { cookie: authCookie },
    });
    const items = listRes.json();
    const target = items.find((i: any) => i.id === id);
    expect(target.mastered).toBe(true);
  });

  it('correct=false 将已掌握错题置回未掌握并计入 updatedIds', async () => {
    const id = await createMistake(authCookie, {
      subject: 'math',
      title: 't1',
      content: 'c1',
    });
    await setMastered(authCookie, id, true);

    const res = await gradeQuiz(authCookie, {
      results: [{ mistakeId: id, correct: false }],
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.total).toBe(1);
    expect(body.correct).toBe(0);
    expect(body.wrong).toBe(1);
    expect(body.updatedIds).toEqual([id]);

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: { cookie: authCookie },
    });
    const items = listRes.json();
    const target = items.find((i: any) => i.id === id);
    expect(target.mastered).toBe(false);
  });

  it('无变化不计入 updatedIds 但计数正常', async () => {
    const id = await createMistake(authCookie, {
      subject: 'math',
      title: 't1',
      content: 'c1',
    });
    await setMastered(authCookie, id, true);

    const res = await gradeQuiz(authCookie, {
      results: [{ mistakeId: id, correct: true }],
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.total).toBe(1);
    expect(body.correct).toBe(1);
    expect(body.wrong).toBe(0);
    expect(body.updatedIds).toEqual([]);
  });
});
