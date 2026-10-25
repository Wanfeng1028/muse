import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerExamsRoutes } from '../src/routes/exams';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

function insert(
  db: DatabaseSync,
  subject: string,
  paper: string,
  score: number,
  totalScore: number,
  durationMinutes: number,
  takenAt: string
) {
  db.prepare(
    "INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES ((SELECT id FROM users WHERE username = 'examsbysubject'), ?,?,?,?,?,?)"
  ).run(subject, paper, score, totalScore, durationMinutes, takenAt);
}

function insert2(
  db: DatabaseSync,
  subject: string,
  paper: string,
  score: number,
  totalScore: number,
  durationMinutes: number,
  takenAt: string
) {
  db.prepare(
    "INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES ((SELECT id FROM users WHERE username = 'examsbysubject2'), ?,?,?,?,?,?)"
  ).run(subject, paper, score, totalScore, durationMinutes, takenAt);
}

describe('GET /api/exams/summary/by-subject – empty db', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let cookie: string;

  beforeAll(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerExamsRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'examsbysubject', 'pass1234');
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  it('returns { subjects: [] } when no records', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ subjects: [] });
  });
});

describe('GET /api/exams/summary/by-subject – precise values & order', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let cookie: string;

  beforeAll(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerExamsRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'examsbysubject', 'pass1234');

    // Insert out of SUBJECTS order: english, major, math
    insert(db, 'english', 'en-paper1', 80, 100, 45, '2026-10-02T10:00:00Z');
    insert(db, 'major', 'mj-paper1', 60, 100, 50, '2026-10-04T10:00:00Z');
    insert(db, 'math', 'mt-paper1', 100, 150, 120, '2026-10-01T10:00:00Z');
    insert(db, 'math', 'mt-paper2', 120, 150, 130, '2026-10-03T10:00:00Z');
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  it('returns subjects in SUBJECTS order, omitting zero-record subjects', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.subjects).toHaveLength(3);

    // math
    const math = body.subjects[0];
    expect(math.subject).toBe('math');
    expect(math.count).toBe(2);
    expect(math.avgScore).toBe(110);
    expect(math.avgRate).toBe(0.7333);
    expect(math.bestScore).toBe(120);
    expect(math.bestTakenAt).toBe('2026-10-03T10:00:00Z');
    expect(math.latestScore).toBe(120);
    expect(math.latestTakenAt).toBe('2026-10-03T10:00:00Z');
    expect(math.firstScore).toBe(100);
    expect(math.firstTakenAt).toBe('2026-10-01T10:00:00Z');
    expect(math.improvement).toBe(20);

    // english
    const english = body.subjects[1];
    expect(english.subject).toBe('english');
    expect(english.count).toBe(1);
    expect(english.avgScore).toBe(80);
    expect(english.avgRate).toBe(0.8);
    expect(english.bestScore).toBe(80);
    expect(english.bestTakenAt).toBe('2026-10-02T10:00:00Z');
    expect(english.latestScore).toBe(80);
    expect(english.latestTakenAt).toBe('2026-10-02T10:00:00Z');
    expect(english.firstScore).toBe(80);
    expect(english.firstTakenAt).toBe('2026-10-02T10:00:00Z');
    expect(english.improvement).toBe(0);

    // major
    const major = body.subjects[2];
    expect(major.subject).toBe('major');
    expect(major.count).toBe(1);
    expect(major.avgScore).toBe(60);
    expect(major.avgRate).toBe(0.6);
    expect(major.bestScore).toBe(60);
    expect(major.bestTakenAt).toBe('2026-10-04T10:00:00Z');
    expect(major.latestScore).toBe(60);
    expect(major.latestTakenAt).toBe('2026-10-04T10:00:00Z');
    expect(major.firstScore).toBe(60);
    expect(major.firstTakenAt).toBe('2026-10-04T10:00:00Z');
    expect(major.improvement).toBe(0);
  });
});

describe('GET /api/exams/summary/by-subject – user isolation', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let cookie1: string;
  let cookie2: string;

  beforeAll(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerExamsRoutes(app, db);
    await app.ready();
    cookie1 = await registerAndLogin(app, 'examsbysubject', 'pass1234');
    cookie2 = await registerAndLogin(app, 'examsbysubject2', 'pass5678');

    insert(db, 'math', 'mt-paper1', 100, 150, 120, '2026-10-01T10:00:00Z');
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  it('second user sees empty subjects', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject',
      headers: { cookie: cookie2 },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ subjects: [] });
  });

  it('first user data is unaffected', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject',
      headers: { cookie: cookie1 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.subjects).toHaveLength(1);
    expect(body.subjects[0].subject).toBe('math');
    expect(body.subjects[0].count).toBe(1);
    expect(body.subjects[0].avgScore).toBe(100);
    expect(body.subjects[0].avgRate).toBeCloseTo(0.6667, 4);
    expect(body.subjects[0].bestScore).toBe(100);
    expect(body.subjects[0].bestTakenAt).toBe('2026-10-01T10:00:00Z');
    expect(body.subjects[0].latestScore).toBe(100);
    expect(body.subjects[0].latestTakenAt).toBe('2026-10-01T10:00:00Z');
    expect(body.subjects[0].firstScore).toBe(100);
    expect(body.subjects[0].firstTakenAt).toBe('2026-10-01T10:00:00Z');
    expect(body.subjects[0].improvement).toBe(0);
  });
});

describe('GET /api/exams/summary/by-subject – unauthenticated', () => {
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

  it('returns 401 without session cookie', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/summary/by-subject',
    });
    expect(res.statusCode).toBe(401);
  });
});
