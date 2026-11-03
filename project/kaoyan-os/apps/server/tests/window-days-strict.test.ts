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

async function newUser(prefix: string) {
  const uname = prefix + '_' + Math.random().toString(36).slice(2, 10);
  const cookie = await registerAndLogin(app, uname);
  const row = db.prepare('SELECT id FROM users WHERE username = ?').get(uname) as { id: number };
  return { cookie, userId: row.id };
}

function insertMistake(userId: number, subject: string, title: string, createdAt: string) {
  const info = db.prepare('INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)').run(userId, subject, title, 'c-' + title, 'a-' + title, 0, createdAt);
  return Number(info.lastInsertRowid);
}

function insertExam(userId: number, subject: string, paper: string, takenAt: string) {
  const info = db.prepare('INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)').run(userId, subject, paper, 100, 150, 180, takenAt);
  return Number(info.lastInsertRowid);
}

function findArray(value: unknown, keys: string[]): unknown[] | undefined {
  if (Array.isArray(value)) return value;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of keys) {
      const child = record[key];
      if (Array.isArray(child)) return child;
    }
    for (const child of Object.values(record)) {
      const found = findArray(child, keys);
      if (found) return found;
    }
  }
  return undefined;
}

function getList(body: unknown, keys: string[]): unknown[] {
  const list = findArray(body, keys);
  if (!list) throw new Error('expected an array in response body');
  return list;
}

const invalidValues = ['1.0', '0x2', '+7', '%207', '7%20', '', '1.5', 'abc', '91', '-1'];

describe('source-exams 严格校验', () => {
  it('非法 windowDays 返回 400 与错误体', async () => {
    const { cookie, userId } = await newUser('src_invalid');
    const mistakeId = insertMistake(userId, 'math', 'm-src-invalid', '2026-10-19T08:00:00.000Z');

    for (const value of invalidValues) {
      const res = await app.inject({
        method: 'GET',
        url: `/api/mistakes/${mistakeId}/source-exams?windowDays=${value}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'windowDays 非法' });
    }
  });

  it('合法 windowDays 返回 200', async () => {
    const { cookie, userId } = await newUser('src_valid');
    const mistakeId = insertMistake(userId, 'math', 'm-src-valid', '2026-10-19T08:00:00.000Z');
    insertExam(userId, 'math', 'paper-src-valid', '2026-10-19');

    const cases = [
      { url: `/api/mistakes/${mistakeId}/source-exams`, expectCount: undefined },
      { url: `/api/mistakes/${mistakeId}/source-exams?windowDays=07`, expectCount: undefined },
      { url: `/api/mistakes/${mistakeId}/source-exams?windowDays=0`, expectCount: 1 },
      { url: `/api/mistakes/${mistakeId}/source-exams?windowDays=90`, expectCount: 1 },
    ];

    for (const testCase of cases) {
      const res = await app.inject({
        method: 'GET',
        url: testCase.url,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(200);
      if (testCase.expectCount !== undefined) {
        expect(getList(res.json(), ['exams', 'sourceExams', 'records', 'items', 'list'])).toHaveLength(testCase.expectCount);
      }
    }
  });
});

describe('related-mistakes 严格校验', () => {
  it('非法 windowDays 返回 400 与错误体', async () => {
    const { cookie, userId } = await newUser('rel_invalid');
    const examId = insertExam(userId, 'math', 'paper-rel-invalid', '2026-10-19');

    for (const value of invalidValues) {
      const res = await app.inject({
        method: 'GET',
        url: `/api/exams/${examId}/related-mistakes?windowDays=${value}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'windowDays 非法' });
    }
  });

  it('合法 windowDays 返回 200', async () => {
    const { cookie, userId } = await newUser('rel_valid');
    const examId = insertExam(userId, 'math', 'paper-rel-valid', '2026-10-19');
    insertMistake(userId, 'math', 'm-rel-valid', '2026-10-19T08:00:00.000Z');

    const cases = [
      { url: `/api/exams/${examId}/related-mistakes`, expectCount: undefined },
      { url: `/api/exams/${examId}/related-mistakes?windowDays=07`, expectCount: undefined },
      { url: `/api/exams/${examId}/related-mistakes?windowDays=0`, expectCount: 1 },
      { url: `/api/exams/${examId}/related-mistakes?windowDays=90`, expectCount: 1 },
    ];

    for (const testCase of cases) {
      const res = await app.inject({
        method: 'GET',
        url: testCase.url,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(200);
      if (testCase.expectCount !== undefined) {
        expect(getList(res.json(), ['mistakes', 'relatedMistakes', 'records', 'items', 'list'])).toHaveLength(testCase.expectCount);
      }
    }
  });
});