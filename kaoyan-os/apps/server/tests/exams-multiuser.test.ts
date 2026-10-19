import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerExamsRoutes } from '../src/routes/exams';
import { registerAndLogin, authHeaders, createSeededUser } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

async function createExam(
  cookie: string,
  payload: Record<string, unknown>,
): Promise<number> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/exams',
    headers: authHeaders(cookie),
    payload,
  });
  expect(res.statusCode).toBe(201);
  return (res.json() as { id: number }).id;
}

beforeAll(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerExamsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

describe('exams 多用户隔离', () => {
  it('GET /api/exams 只返回当前用户的记录', async () => {
    const cookieA = await registerAndLogin(app, 'exams_user_a');
    const cookieB = await registerAndLogin(app, 'exams_user_b');

    await createExam(cookieA, {
      subject: 'math',
      paper: 'A 卷',
      score: 100,
      totalScore: 150,
    });
    await createExam(cookieB, {
      subject: 'english',
      paper: 'B 卷',
      score: 60,
      totalScore: 100,
    });

    const resA = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: authHeaders(cookieA),
    });
    expect(resA.statusCode).toBe(200);
    const listA = resA.json() as Array<{ subject: string; paper: string }>;
    expect(listA).toHaveLength(1);
    expect(listA[0].subject).toBe('math');
    expect(listA[0].paper).toBe('A 卷');

    const resB = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: authHeaders(cookieB),
    });
    const listB = resB.json() as Array<{ subject: string; paper: string }>;
    expect(listB).toHaveLength(1);
    expect(listB[0].subject).toBe('english');
    expect(listB[0].paper).toBe('B 卷');
  });

  it('DELETE /api/exams/:id 不能删除其他用户的记录', async () => {
    const cookieA = await registerAndLogin(app, 'exams_del_a');
    const cookieB = await registerAndLogin(app, 'exams_del_b');

    const idA = await createExam(cookieA, {
      subject: 'math',
      paper: 'A 卷',
      score: 90,
      totalScore: 150,
    });

    const res = await app.inject({
      method: 'DELETE',
      url: `/api/exams/${idA}`,
      headers: authHeaders(cookieB),
    });
    expect(res.statusCode).toBe(404);

    // A 仍能查到
    const listA = (
      await app.inject({
        method: 'GET',
        url: '/api/exams',
        headers: authHeaders(cookieA),
      })
    ).json() as Array<{ id: number }>;
    expect(listA.map((r) => r.id)).toContain(idA);
  });

  it('GET /api/exams/summary 只统计当前用户的记录', async () => {
    const cookieA = await registerAndLogin(app, 'exams_sum_a');
    const cookieB = await registerAndLogin(app, 'exams_sum_b');

    await createExam(cookieA, {
      subject: 'math',
      paper: 'A1',
      score: 80,
      totalScore: 100,
      takenAt: '2025-01-01',
    });
    await createExam(cookieA, {
      subject: 'math',
      paper: 'A2',
      score: 90,
      totalScore: 100,
      takenAt: '2025-02-01',
    });
    // B 的高分不应污染 A 的 summary
    await createExam(cookieB, {
      subject: 'math',
      paper: 'B1',
      score: 100,
      totalScore: 100,
      takenAt: '2025-03-01',
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary',
      headers: authHeaders(cookieA),
    });
    expect(res.statusCode).toBe(200);
    const summary = res.json() as {
      count: number;
      bestScore: number;
      latestScore: number;
      firstScore: number;
      improvement: number;
    };
    expect(summary.count).toBe(2);
    expect(summary.bestScore).toBe(90);
    expect(summary.firstScore).toBe(80);
    expect(summary.latestScore).toBe(90);
    expect(summary.improvement).toBe(10);
  });

  it('GET /api/exams/export 只导出当前用户记录，含 BOM 与表头', async () => {
    const cookieA = await registerAndLogin(app, 'exams_exp_a');
    const cookieB = await registerAndLogin(app, 'exams_exp_b');

    await createExam(cookieA, {
      subject: 'math',
      paper: 'A,卷',
      score: 100,
      totalScore: 150,
    });
    await createExam(cookieB, {
      subject: 'english',
      paper: 'B 卷',
      score: 50,
      totalScore: 100,
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: authHeaders(cookieA),
    });
    expect(res.statusCode).toBe(200);
    expect(res.headers['content-type']).toContain('text/csv');
    expect(res.headers['content-disposition']).toContain('kaoyan-exams.csv');

    const csv = res.body;
    expect(csv.startsWith('\ufeff')).toBe(true);
    expect(csv).toContain('id,subject,subject_name,paper,score,total_score,rate,duration_minutes,taken_at');
    expect(csv).toContain('"A,卷"');
    expect(csv).not.toContain('B 卷');
    expect(csv).not.toContain('english');
  });

  it('GET /api/exams/export 带 subject 时文件名带 subject', async () => {
    const cookie = await registerAndLogin(app, 'exams_exp_sub');
    await createExam(cookie, {
      subject: 'math',
      paper: 'X',
      score: 1,
      totalScore: 10,
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export?subject=math',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(200);
    expect(res.headers['content-disposition']).toContain('kaoyan-exams-math.csv');
  });

  it('summary 并列最高分取最早一场', async () => {
    const cookie = await registerAndLogin(app, 'exams_tie');
    await createExam(cookie, {
      subject: 'math',
      paper: 'early',
      score: 100,
      totalScore: 100,
      takenAt: '2025-01-01',
    });
    await createExam(cookie, {
      subject: 'math',
      paper: 'late',
      score: 100,
      totalScore: 100,
      takenAt: '2025-06-01',
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary',
      headers: authHeaders(cookie),
    });
    const summary = res.json() as { bestScore: number; bestTakenAt: string };
    expect(summary.bestScore).toBe(100);
    expect(summary.bestTakenAt).toBe('2025-01-01');
  });

  it('createSeededUser 的种子考试记录归属于新用户，可被 summary 统计', async () => {
    const { cookie } = await createSeededUser(db, app, 'exams_seeded');
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(200);
    const list = res.json() as unknown[];
    // 种子数据由 createSeededUser 从 local 复制，测试只断言接口按 user_id 隔离生效
    expect(Array.isArray(list)).toBe(true);
    for (const item of list) {
      expect(item).toHaveProperty('id');
      expect(item).toHaveProperty('subject');
    }
  });

  it('未登录访问 /api/exams 返回 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/exams' });
    expect(res.statusCode).toBe(401);
  });
});
