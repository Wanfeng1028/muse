import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerExamsRoutes } from '../src/routes/exams';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

type SummarySubject = {
  subject: string;
  count: number;
  avgScore: number;
  avgRate: number;
  bestScore: number;
  bestTakenAt: string;
  latestScore: number;
  latestTakenAt: string;
  firstScore: number;
  firstTakenAt: string;
  improvement: number;
};

const dateStr = (daysAgo: number) => {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const takenAtDaysAgo = (daysAgo: number) => `${dateStr(daysAgo)}T10:00:00Z`;

const getSubjects = (res: { json: () => unknown }) =>
  (res.json() as { subjects: SummarySubject[] }).subjects;

describe('GET /api/exams/summary/by-subject days', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let cookie: string;

  const insertExamRecord = (
    subject: string,
    paper: string,
    score: number,
    totalScore: number,
    durationMinutes: number,
    daysAgo: number,
  ) => {
    db
      .prepare(
        "INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES ((SELECT id FROM users WHERE username = 'examsbysubjectdays'), ?,?,?,?,?,?)",
      )
      .run(subject, paper, score, totalScore, durationMinutes, takenAtDaysAgo(daysAgo));
  };

  beforeAll(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerExamsRoutes(app, db);
    await app.ready();

    cookie = await registerAndLogin(app, 'examsbysubjectdays', 'pass1234');

    insertExamRecord('math', 'mt-today1', 100, 150, 120, 0);
    insertExamRecord('math', 'mt-today2', 120, 150, 130, 0);
    insertExamRecord('math', 'mt-6d', 90, 150, 110, 6);
    insertExamRecord('english', 'en-today', 80, 100, 45, 0);
    insertExamRecord('english', 'en-7d', 70, 100, 40, 7);
    insertExamRecord('math', 'mt-40d', 50, 150, 100, 40);
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  it('days=7 时只统计最近 7 天', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject?days=7',
      headers: { cookie },
    });

    expect(res.statusCode).toBe(200);
    expect(getSubjects(res)).toEqual([
      {
        subject: 'math',
        count: 3,
        avgScore: 103.3,
        avgRate: 0.6889,
        bestScore: 120,
        bestTakenAt: takenAtDaysAgo(0),
        latestScore: 120,
        latestTakenAt: takenAtDaysAgo(0),
        firstScore: 90,
        firstTakenAt: takenAtDaysAgo(6),
        improvement: 30,
      },
      {
        subject: 'english',
        count: 1,
        avgScore: 80,
        avgRate: 0.8,
        bestScore: 80,
        bestTakenAt: takenAtDaysAgo(0),
        latestScore: 80,
        latestTakenAt: takenAtDaysAgo(0),
        firstScore: 80,
        firstTakenAt: takenAtDaysAgo(0),
        improvement: 0,
      },
    ]);
  });

  it('days=1 时只统计今天', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject?days=1',
      headers: { cookie },
    });

    expect(res.statusCode).toBe(200);
    expect(getSubjects(res)).toEqual([
      {
        subject: 'math',
        count: 2,
        avgScore: 110,
        avgRate: 0.7333,
        bestScore: 120,
        bestTakenAt: takenAtDaysAgo(0),
        latestScore: 120,
        latestTakenAt: takenAtDaysAgo(0),
        firstScore: 100,
        firstTakenAt: takenAtDaysAgo(0),
        improvement: 20,
      },
      {
        subject: 'english',
        count: 1,
        avgScore: 80,
        avgRate: 0.8,
        bestScore: 80,
        bestTakenAt: takenAtDaysAgo(0),
        latestScore: 80,
        latestTakenAt: takenAtDaysAgo(0),
        firstScore: 80,
        firstTakenAt: takenAtDaysAgo(0),
        improvement: 0,
      },
    ]);
  });

  it('days 越界（0、-1、32、100）返回 400，days=31 仍返回 200', async () => {
    for (const d of [0, -1, 32, 100]) {
      const res = await app.inject({
        method: 'GET',
        url: `/api/exams/summary/by-subject?days=${d}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json().error).toBe('days 参数无效');
    }

    const res31 = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject?days=31',
      headers: { cookie },
    });

    expect(res31.statusCode).toBe(200);

    const subjects31 = getSubjects(res31);
    expect(subjects31).toEqual([
      {
        subject: 'math',
        count: 3,
        avgScore: 103.3,
        avgRate: 0.6889,
        bestScore: 120,
        bestTakenAt: takenAtDaysAgo(0),
        latestScore: 120,
        latestTakenAt: takenAtDaysAgo(0),
        firstScore: 90,
        firstTakenAt: takenAtDaysAgo(6),
        improvement: 30,
      },
      {
        subject: 'english',
        count: 2,
        avgScore: 75,
        avgRate: 0.75,
        bestScore: 80,
        bestTakenAt: takenAtDaysAgo(0),
        latestScore: 80,
        latestTakenAt: takenAtDaysAgo(0),
        firstScore: 70,
        firstTakenAt: takenAtDaysAgo(7),
        improvement: 10,
      },
    ]);
  });

  it('days 非法（abc、1.5、1x、空串）时返回 400', async () => {
    for (const q of ['abc', '1.5', '1x', '']) {
      const res = await app.inject({
        method: 'GET',
        url: `/api/exams/summary/by-subject?days=${q}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect((res.json() as { error: string }).error).toBe('days 参数无效');
    }
  });

  it('days 不传时统计全部历史', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject',
      headers: { cookie },
    });

    expect(res.statusCode).toBe(200);
    expect(getSubjects(res)).toEqual([
      {
        subject: 'math',
        count: 4,
        avgScore: 90,
        avgRate: 0.6,
        bestScore: 120,
        bestTakenAt: takenAtDaysAgo(0),
        latestScore: 120,
        latestTakenAt: takenAtDaysAgo(0),
        firstScore: 50,
        firstTakenAt: takenAtDaysAgo(40),
        improvement: 70,
      },
      {
        subject: 'english',
        count: 2,
        avgScore: 75,
        avgRate: 0.75,
        bestScore: 80,
        bestTakenAt: takenAtDaysAgo(0),
        latestScore: 80,
        latestTakenAt: takenAtDaysAgo(0),
        firstScore: 70,
        firstTakenAt: takenAtDaysAgo(7),
        improvement: 10,
      },
    ]);
  });
});

describe('GET /api/exams/summary/by-subject days unauthenticated', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;

  beforeAll(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerExamsRoutes(app, db);
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  it('未登录请求 days=7 返回 401', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject?days=7',
    });

    expect(res.statusCode).toBe(401);
  });
});
