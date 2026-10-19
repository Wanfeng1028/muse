import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerExamsRoutes } from '../src/routes/exams';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

const TEST_USER = 'examsdeep';
let authCookie = '';

async function buildApp(db: DatabaseSync): Promise<FastifyInstance> {
  const app = Fastify();
  registerExamsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  authCookie = await registerAndLogin(app, TEST_USER);
  return app;
}

describe('exams routes deep', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;

  beforeAll(async () => {
    db = createRealDb(':memory:');
    app = await buildApp(db);
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  it('GET /api/exams 按 taken_at 降序且同日按 id 降序返回', async () => {
    const insert = db.prepare(
      "INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES ((SELECT id FROM users WHERE username = 'examsdeep'), ?, ?, ?, ?, ?, ?)"
    );
    insert.run('math', 'A卷', 100, 150, 120, '2024-01-01');
    insert.run('math', 'B卷', 110, 150, 120, '2024-03-15');
    insert.run('math', 'C卷', 90, 150, 120, '2024-03-15');
    insert.run('english', 'D卷', 80, 100, 90, '2024-02-20');

    const res = await app.inject({ method: 'GET', url: '/api/exams', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.length).toBe(4);
    expect(body[0].paper).toBe('C卷');
    expect(body[1].paper).toBe('B卷');
    expect(body[2].paper).toBe('D卷');
    expect(body[3].paper).toBe('A卷');
    expect(body[0].subject).toBe('math');
    expect(body[3].takenAt).toBe('2024-01-01');
  });

  it('GET /api/exams 带 subject 过滤并拒绝无效 subject', async () => {
    const ok = await app.inject({ method: 'GET', url: '/api/exams?subject=math', headers: { cookie: authCookie } });
    expect(ok.statusCode).toBe(200);
    const mathBody = ok.json();
    expect(mathBody.length).toBe(3);
    expect(mathBody.every((r: { subject: string }) => r.subject === 'math')).toBe(true);

    const bad = await app.inject({ method: 'GET', url: '/api/exams?subject=physics', headers: { cookie: authCookie } });
    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('无效的 subject 参数');
  });

  it('GET /api/exams/trend 按 taken_at 升序并正确计算 rate', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/exams/trend', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.length).toBe(4);
    expect(body[0].takenAt).toBe('2024-01-01');
    expect(body[3].takenAt).toBe('2024-03-15');
    const c = body.find((p: { paper: string }) => p.paper === 'C卷');
    expect(c.score).toBe(90);
    expect(c.totalScore).toBe(150);
    expect(c.rate).toBe(0.6);
  });

  it('GET /api/exams/trend total_score 为 0 时 rate 返回 0', async () => {
    db.prepare(
      "INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES ((SELECT id FROM users WHERE username = 'examsdeep'), ?, ?, ?, ?, ?, ?)"
    ).run('politics', '零分卷', 0, 0, 0, '2024-04-01');

    const res = await app.inject({ method: 'GET', url: '/api/exams/trend?subject=politics', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.length).toBe(1);
    expect(body[0].rate).toBe(0);
    expect(body[0].paper).toBe('零分卷');
  });

  it('POST /api/exams 创建成功返回 201 与完整记录', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: authCookie },
      payload: {
        subject: 'english',
        paper: 'E卷',
        score: 77.5,
        totalScore: 100,
        durationMinutes: 95.8,
        takenAt: '2024-05-05',
      },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body.subject).toBe('english');
    expect(body.paper).toBe('E卷');
    expect(body.score).toBe(77.5);
    expect(body.totalScore).toBe(100);
    expect(body.durationMinutes).toBe(95);
    expect(body.takenAt).toBe('2024-05-05');
    expect(typeof body.id).toBe('number');
  });

  it('POST /api/exams 拒绝空请求体、无效 subject 与空 paper', async () => {
    const empty = await app.inject({ method: 'POST', url: '/api/exams', headers: { cookie: authCookie }, payload: {} });
    expect(empty.statusCode).toBe(400);
    expect(empty.json().error).toBe('无效的 subject');

    const badSubject = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: authCookie },
      payload: { subject: 'nope', paper: 'X', score: 1, totalScore: 10 },
    });
    expect(badSubject.statusCode).toBe(400);
    expect(badSubject.json().error).toBe('无效的 subject');

    const blankPaper = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: authCookie },
      payload: { subject: 'math', paper: '   ', score: 1, totalScore: 10 },
    });
    expect(blankPaper.statusCode).toBe(400);
    expect(blankPaper.json().error).toBe('paper 不能为空');
  });

  it('POST /api/exams 校验分数与时长边界', async () => {
    const zeroTotal = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: authCookie },
      payload: { subject: 'math', paper: 'X', score: 0, totalScore: 0 },
    });
    expect(zeroTotal.statusCode).toBe(400);
    expect(zeroTotal.json().error).toBe('totalScore 必须大于 0');

    const scoreTooHigh = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: authCookie },
      payload: { subject: 'math', paper: 'X', score: 101, totalScore: 100 },
    });
    expect(scoreTooHigh.statusCode).toBe(400);
    expect(scoreTooHigh.json().error).toBe('score 必须在 0 到 totalScore 之间');

    const negativeDuration = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: authCookie },
      payload: { subject: 'math', paper: 'X', score: 50, totalScore: 100, durationMinutes: -1 },
    });
    expect(negativeDuration.statusCode).toBe(400);
    expect(negativeDuration.json().error).toBe('durationMinutes 必须大于等于 0');
  });

  it('POST /api/exams 未传 durationMinutes 与 takenAt 时使用默认值', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: authCookie },
      payload: { subject: 'math', paper: 'F卷', score: 60, totalScore: 100 },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body.durationMinutes).toBe(0);
    expect(typeof body.takenAt).toBe('string');
    expect(body.takenAt.length).toBe(10);
  });

  it('DELETE /api/exams/:id 删除成功与失败路径', async () => {
    const created = await app.inject({
      method: 'POST',
      url: '/api/exams',
      headers: { cookie: authCookie },
      payload: { subject: 'math', paper: '待删', score: 10, totalScore: 100 },
    });
    const id = created.json().id;

    const del = await app.inject({ method: 'DELETE', url: `/api/exams/${id}`, headers: { cookie: authCookie } });
    expect(del.statusCode).toBe(200);
    expect(del.json().ok).toBe(true);

    const again = await app.inject({ method: 'DELETE', url: `/api/exams/${id}`, headers: { cookie: authCookie } });
    expect(again.statusCode).toBe(404);
    expect(again.json().error).toBe('记录不存在');

    const badId = await app.inject({ method: 'DELETE', url: '/api/exams/0', headers: { cookie: authCookie } });
    expect(badId.statusCode).toBe(400);
    expect(badId.json().error).toBe('无效的 id');
  });

  it('跨月与闰年 taken_at 排序保持字符串字典序正确', async () => {
    const fresh = createRealDb(':memory:');
    const freshApp = await buildApp(fresh);
    const insert = fresh.prepare(
      "INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES ((SELECT id FROM users WHERE username = 'examsdeep'), ?, ?, ?, ?, ?, ?)"
    );
    insert.run('math', '闰年2月', 50, 100, 60, '2024-02-29');
    insert.run('math', '跨年', 60, 100, 60, '2023-12-31');
    insert.run('math', '元旦', 70, 100, 60, '2024-01-01');

    const res = await freshApp.inject({ method: 'GET', url: '/api/exams/trend', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.length).toBe(3);
    expect(body[0].takenAt).toBe('2023-12-31');
    expect(body[1].takenAt).toBe('2024-01-01');
    expect(body[2].takenAt).toBe('2024-02-29');

    await freshApp.close();
    fresh.close();
  });

  it('空计划表时 GET 返回空数组而不是报错', async () => {
    const empty = createRealDb(':memory:');
    const emptyApp = await buildApp(empty);

    const list = await emptyApp.inject({ method: 'GET', url: '/api/exams', headers: { cookie: authCookie } });
    expect(list.statusCode).toBe(200);
    expect(list.json()).toEqual([]);

    const trend = await emptyApp.inject({ method: 'GET', url: '/api/exams/trend', headers: { cookie: authCookie } });
    expect(trend.statusCode).toBe(200);
    expect(trend.json()).toEqual([]);

    await emptyApp.close();
    empty.close();
  });
});