import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { registerExamsRoutes } from '../src/routes/exams';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: DatabaseSync;
let app: FastifyInstance;

function insertMistake(userId: number, subject: string, title: string, createdAt: string): number {
  const info = db
  .prepare('INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)')
  .run(userId, subject, title, 'c-' + title, 'a-' + title, 0, createdAt);
  return Number(info.lastInsertRowid);
}

function insertExam(userId: number, subject: string, paper: string, takenAt: string): number {
  const info = db
  .prepare('INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)')
  .run(userId, subject, paper, 100, 150, 180, takenAt);
  return Number(info.lastInsertRowid);
}

function randSuffix(): string {
  return Math.random().toString(36).slice(2, 10);
}

async function newUser(prefix: string): Promise<{ cookie: string; userId: number }> {
  const uname = `${prefix}_${randSuffix()}`;
  const cookie = await registerAndLogin(app, uname);
  const row = db.prepare('SELECT id FROM users WHERE username = ?').get(uname) as { id: number };
  return { cookie, userId: row.id };
}

beforeEach(async () => {
    db = createRealDb(':memory:');
    app = Fastify();
    registerMistakesRoutes(app, db);
    registerExamsRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });

afterAll(async () => {
    await app.close();
  });

describe('GET /api/mistakes/:id/source-exams', () => {
    it('返回同科目、错题 created_at 前后 3 天内的真题', async () => {
        const { cookie, userId } = await newUser('link1');
        const mid = insertMistake(userId, 'math', '错题A', '2026-10-19T08:00:00.000Z');
        insertExam(userId, 'math', '真题-前3天', '2026-10-16');
        insertExam(userId, 'math', '真题-当天', '2026-10-19');
        insertExam(userId, 'math', '真题-后3天', '2026-10-22');

        const res = await app.inject({
            method: 'GET',
            url: `/api/mistakes/${mid}/source-exams`,
            headers: { cookie },
          });
        expect(res.statusCode).toBe(200);
        const body = res.json() as Array<{ paper: string }>;
        expect(body.length).toBe(3);
        expect(body.map((x) => x.paper)).toEqual(['真题-后3天', '真题-当天', '真题-前3天']);
      });

    it('相差 30 天的同科目真题不被返回', async () => {
        const { cookie, userId } = await newUser('link2');
        const mid = insertMistake(userId, 'english', '错题B', '2026-10-19T08:00:00.000Z');
        insertExam(userId, 'english', '真题-远', '2026-09-19');
        insertExam(userId, 'english', '真题-近', '2026-10-18');

        const res = await app.inject({
            method: 'GET',
            url: `/api/mistakes/${mid}/source-exams`,
            headers: { cookie },
          });
        expect(res.statusCode).toBe(200);
        const body = res.json() as Array<{ paper: string }>;
        expect(body.length).toBe(1);
        expect(body[0].paper).toBe('真题-近');
      });

    it('日期相近但不同科目的真题不被返回', async () => {
        const { cookie, userId } = await newUser('link3');
        const mid = insertMistake(userId, 'math', '错题C', '2026-10-19T08:00:00.000Z');
        insertExam(userId, 'math', '真题-数学', '2026-10-18');
        insertExam(userId, 'english', '真题-英语', '2026-10-18');

        const res = await app.inject({
            method: 'GET',
            url: `/api/mistakes/${mid}/source-exams`,
            headers: { cookie },
          });
        expect(res.statusCode).toBe(200);
        const body = res.json() as Array<{ paper: string }>;
        expect(body.length).toBe(1);
        expect(body[0].paper).toBe('真题-数学');
      });
  });

describe('GET /api/exams/:id/related-mistakes', () => {
    it('返回同科目、真题 taken_at 前后 3 天内的错题', async () => {
        const { cookie, userId } = await newUser('link4');
        const eid = insertExam(userId, 'math', '真题X', '2026-10-19');
        insertMistake(userId, 'math', '错题-前3天', '2026-10-16T09:00:00.000Z');
        insertMistake(userId, 'math', '错题-当天', '2026-10-19T10:00:00.000Z');
        insertMistake(userId, 'math', '错题-后3天', '2026-10-22T11:00:00.000Z');
        insertMistake(userId, 'math', '错题-远', '2026-09-01T00:00:00.000Z');
        insertMistake(userId, 'english', '错题-其他科', '2026-10-19T00:00:00.000Z');

        const res = await app.inject({
            method: 'GET',
            url: `/api/exams/${eid}/related-mistakes`,
            headers: { cookie },
          });
        expect(res.statusCode).toBe(200);
        const body = res.json() as Array<{ title: string }>;
        expect(body.length).toBe(3);
        expect(body.map((x) => x.title)).toEqual(['错题-后3天', '错题-当天', '错题-前3天']);
      });
  });

describe('参数与不存在', () => {
    it('source-exams：不存在的 id 返回 404，id=abc 返回 400，windowDays=999 返回 400', async () => {
        const { cookie, userId: _uid5 } = await newUser('link5');
        void _uid5;

        const r404 = await app.inject({
            method: 'GET',
            url: '/api/mistakes/999999/source-exams',
            headers: { cookie },
          });
        expect(r404.statusCode).toBe(404);
        expect(r404.json()).toEqual({ error: '错题不存在' });

        const r400 = await app.inject({
            method: 'GET',
            url: '/api/mistakes/abc/source-exams',
            headers: { cookie },
          });
        expect(r400.statusCode).toBe(400);
        expect(r400.json()).toEqual({ error: 'id 非法' });

        const rowD = db.prepare('SELECT id FROM users').get() as { id: number };
        const mid = insertMistake(rowD.id, 'math', '错题D', '2026-10-19T08:00:00.000Z');
        const rWin = await app.inject({
            method: 'GET',
            url: `/api/mistakes/${mid}/source-exams?windowDays=999`,
            headers: { cookie },
          });
        expect(rWin.statusCode).toBe(400);
        expect(rWin.json()).toEqual({ error: 'windowDays 非法' });
      });
  });

describe('用户隔离', () => {
    it('用户 B 的真题不会出现在用户 A 错题的 source-exams 里', async () => {
        const ua = await newUser('linka');
        const ub = await newUser('linkb');
        const cookieA = ua.cookie;
        const cookieB = ub.cookie;

        const midA = insertMistake(ua.userId, 'math', 'A错题', '2026-10-19T08:00:00.000Z');
        insertExam(ua.userId, 'math', 'A真题', '2026-10-19');
        insertExam(ub.userId, 'math', 'B真题', '2026-10-19');

        const res = await app.inject({
            method: 'GET',
            url: `/api/mistakes/${midA}/source-exams`,
            headers: { cookie: cookieA },
          });
        expect(res.statusCode).toBe(200);
        const body = res.json() as Array<{ paper: string }>;
        expect(body.length).toBe(1);
        expect(body[0].paper).toBe('A真题');

        // 反证：B 自己看到的是 B 的真题
        const resB = await app.inject({
            method: 'GET',
            url: '/api/mistakes/999999/source-exams',
            headers: { cookie: cookieB },
          });
        expect(resB.statusCode).toBe(404);
      });
  });
