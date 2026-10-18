import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerExamsRoutes } from '../src/routes/exams';

function createDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:');
  db.exec(`
CREATE TABLE exam_records (
id INTEGER PRIMARY KEY AUTOINCREMENT,
subject TEXT NOT NULL,
paper TEXT NOT NULL,
score REAL NOT NULL,
total_score REAL NOT NULL,
duration_minutes INTEGER NOT NULL DEFAULT 0,
taken_at TEXT NOT NULL
);
`);
  return db;
}

async function buildApp(db: DatabaseSync): Promise<FastifyInstance> {
  const app = Fastify();
  registerExamsRoutes(app, db);
  await app.ready();
  return app;
}

function insert(
  db: DatabaseSync,
  subject: string,
  paper: string,
  score: number,
  totalScore: number,
  durationMinutes: number,
  takenAt: string,
): void {
  db.prepare(
    'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?,?,?,?,?,?)',
  ).run(subject, paper, score, totalScore, durationMinutes, takenAt);
}

describe('GET /api/exams/summary', () => {
  describe('空库', () => {
    let db: DatabaseSync;
    let app: FastifyInstance;
    beforeAll(async () => {
      db = createDb();
      app = await buildApp(db);
    });
    afterAll(async () => {
      await app.close();
      db.close();
    });

    it('count=0，数字全 0，字符串全空，subject 为 null', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/exams/summary' });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.subject).toBeNull();
      expect(body.count).toBe(0);
      expect(body.avgScore).toBe(0);
      expect(body.avgRate).toBe(0);
      expect(body.bestScore).toBe(0);
      expect(body.bestTakenAt).toBe('');
      expect(body.latestScore).toBe(0);
      expect(body.latestTakenAt).toBe('');
      expect(body.firstScore).toBe(0);
      expect(body.firstTakenAt).toBe('');
      expect(body.improvement).toBe(0);
    });
  });

  describe('非法 subject', () => {
    let db: DatabaseSync;
    let app: FastifyInstance;
    beforeAll(async () => {
      db = createDb();
      app = await buildApp(db);
    });
    afterAll(async () => {
      await app.close();
      db.close();
    });

    it('subject=history 返回 400 与错误信息', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/exams/summary?subject=history' });
      expect(res.statusCode).toBe(400);
      const body = res.json();
      expect(body.error).toBe('无效的 subject 参数');
    });
  });

  describe('3 场数学记录统计', () => {
    let db: DatabaseSync;
    let app: FastifyInstance;
    beforeAll(async () => {
      db = createDb();
      app = await buildApp(db);
      insert(db, 'math', '2024 数学一真题', 90, 150, 180, '2024-12-20');
      insert(db, 'math', '2024 数学二真题', 100, 150, 180, '2024-12-21');
      insert(db, 'math', '2024 数学三真题', 120, 150, 180, '2024-12-22');
    });
    afterAll(async () => {
      await app.close();
      db.close();
    });

    it('count=3，avgScore 与 avgRate 精确值', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/exams/summary?subject=math' });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.subject).toBe('math');
      expect(body.count).toBe(3);
      expect(body.avgScore).toBe(103.3);
      expect(body.avgRate).toBe(0.6889);
      expect(body.bestScore).toBe(120);
      expect(body.bestTakenAt).toBe('2024-12-22');
      expect(body.latestScore).toBe(120);
      expect(body.latestTakenAt).toBe('2024-12-22');
      expect(body.firstScore).toBe(90);
      expect(body.firstTakenAt).toBe('2024-12-20');
      expect(body.improvement).toBe(30);
    });
  });

  describe('bestScore 并列取最早场次', () => {
    let db: DatabaseSync;
    let app: FastifyInstance;
    beforeAll(async () => {
      db = createDb();
      app = await buildApp(db);
      insert(db, 'english', '2024 英语一真题', 80, 100, 180, '2024-12-18');
      insert(db, 'english', '2024 英语二真题', 80, 100, 180, '2024-12-19');
      insert(db, 'english', '2024 英语三真题', 70, 100, 180, '2024-12-20');
    });
    afterAll(async () => {
      await app.close();
      db.close();
    });

    it('bestTakenAt 为并列中最早的日期', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/exams/summary?subject=english' });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.bestScore).toBe(80);
      expect(body.bestTakenAt).toBe('2024-12-18');
    });
  });

  describe('latest 与 first 的并列取 id 规则', () => {
    let db: DatabaseSync;
    let app: FastifyInstance;
    beforeAll(async () => {
      db = createDb();
      app = await buildApp(db);
      insert(db, 'politics', '政治模拟一', 60, 100, 180, '2024-12-10');
      insert(db, 'politics', '政治模拟二', 70, 100, 180, '2024-12-10');
      insert(db, 'politics', '政治模拟三', 65, 100, 180, '2024-12-15');
      insert(db, 'politics', '政治模拟四', 75, 100, 180, '2024-12-15');
    });
    afterAll(async () => {
      await app.close();
      db.close();
    });

    it('latest 取最晚 taken_at 且 id 大者，first 取最早且 id 小者', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/exams/summary?subject=politics' });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.latestScore).toBe(75);
      expect(body.latestTakenAt).toBe('2024-12-15');
      expect(body.firstScore).toBe(60);
      expect(body.firstTakenAt).toBe('2024-12-10');
      expect(body.improvement).toBe(15);
    });
  });

  describe('improvement 精确值与单场归零', () => {
    let db: DatabaseSync;
    let app: FastifyInstance;
    beforeAll(async () => {
      db = createDb();
      app = await buildApp(db);
      insert(db, 'major', '专业课模拟一', 88, 150, 180, '2024-12-01');
      insert(db, 'major', '专业课模拟二', 111, 150, 180, '2024-12-02');
    });
    afterAll(async () => {
      await app.close();
      db.close();
    });

    it('improvement = latestScore - firstScore', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/exams/summary?subject=major' });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.improvement).toBe(23);
    });

    it('单场记录 improvement=0', async () => {
      const db2 = createDb();
      const app2 = await buildApp(db2);
      insert(db2, 'major', '专业课单场', 100, 150, 180, '2024-12-05');
      const res = await app2.inject({ method: 'GET', url: '/api/exams/summary?subject=major' });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.count).toBe(1);
      expect(body.improvement).toBe(0);
      expect(body.latestScore).toBe(100);
      expect(body.firstScore).toBe(100);
      await app2.close();
      db2.close();
    });
  });

  describe('subject 过滤', () => {
    let db: DatabaseSync;
    let app: FastifyInstance;
    beforeAll(async () => {
      db = createDb();
      app = await buildApp(db);
      insert(db, 'math', '数学模拟', 100, 150, 180, '2024-12-20');
      insert(db, 'english', '英语模拟', 80, 100, 180, '2024-12-21');
      insert(db, 'math', '数学模拟二', 110, 150, 180, '2024-12-22');
    });
    afterAll(async () => {
      await app.close();
      db.close();
    });

    it('subject=math 只统计数学，english 不计入', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/exams/summary?subject=math' });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.subject).toBe('math');
      expect(body.count).toBe(2);
      expect(body.avgScore).toBe(105);
      expect(body.avgRate).toBe(0.7);
      expect(body.bestScore).toBe(110);
      expect(body.firstScore).toBe(100);
      expect(body.latestScore).toBe(110);
      expect(body.improvement).toBe(10);
    });
  });

  describe('avgRate 加权分母口径', () => {
    let db: DatabaseSync;
    let app: FastifyInstance;
    beforeAll(async () => {
      db = createDb();
      app = await buildApp(db);
      insert(db, 'math', '不同满分一', 90, 150, 180, '2024-12-01');
      insert(db, 'math', '不同满分二', 60, 100, 180, '2024-12-02');
      insert(db, 'math', '不同满分三', 50, 50, 180, '2024-12-03');
    });
    afterAll(async () => {
      await app.close();
      db.close();
    });

    it('avgRate = 总得分/总满分 保留 4 位小数', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/exams/summary?subject=math' });
      expect(res.statusCode).toBe(200);
      const body = res.json();
      expect(body.count).toBe(3);
      expect(body.avgScore).toBe(66.7);
      expect(body.avgRate).toBe(0.6667);
    });
  });
});
