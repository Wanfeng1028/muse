import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerExamsRoutes } from '../src/routes/exams';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

const TEST_USER = 'examssummarydeep';

type SummaryResponse = {
  subject: string | null;
  count: number;
  avgScore: number;
  avgRate: number;
  bestScore: number | null;
  bestTakenAt: string | null;
  latestScore: number | null;
  latestTakenAt: string | null;
  firstScore: number | null;
  firstTakenAt: string | null;
  improvement: number;
};

let app: FastifyInstance;
let db: DatabaseSync;

let authCookie = '';

async function setupApp(): Promise<void> {
  db = createRealDb(':memory:');
  app = Fastify();
  registerExamsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  authCookie = await registerAndLogin(app, TEST_USER);
}

function insert(
  subject: string,
  paper: string,
  score: number,
  totalScore: number,
  durationMinutes: number | null,
  takenAt: string,
): void {
  db.prepare(
    "INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES ((SELECT id FROM users WHERE username = 'examssummarydeep'), ?, ?, ?, ?, ?, ?)",
  ).run(subject, paper, score, totalScore, durationMinutes, takenAt);
}

async function fetchSummary(query: string): Promise<SummaryResponse> {
  const res = await app.inject({ method: 'GET', url: `/api/exams/summary${query}`, headers: { cookie: authCookie } });
  expect(res.statusCode).toBe(200);
  return res.json() as SummaryResponse;
}

beforeEach(async () => {
  await setupApp();
});

afterAll(async () => {
  if (app) {
    await app.close();
  }
  if (db) {
    db.close();
  }
});

describe('GET /api/exams/summary deep edge cases', () => {
  it('total_score 全为 0 时 avgRate=0 且 avgScore 正常', async () => {
    insert('math', 'p1', 50, 0, 60, '2024-01-01T09:00:00Z');
    insert('math', 'p2', 70, 0, 60, '2024-01-02T09:00:00Z');
    const body = await fetchSummary('?subject=math');
    expect(body.subject).toBe('math');
    expect(body.count).toBe(2);
    expect(body.avgScore).toBe(60);
    expect(body.avgRate).toBe(0);
  });

  it('退步场景 78→85→70 时 improvement=-8', async () => {
    insert('math', 'p1', 78, 100, 60, '2024-02-01T09:00:00Z');
    insert('math', 'p2', 85, 100, 60, '2024-02-02T09:00:00Z');
    insert('math', 'p3', 70, 100, 60, '2024-02-03T09:00:00Z');
    const body = await fetchSummary('?subject=math');
    expect(body.count).toBe(3);
    expect(body.firstScore).toBe(78);
    expect(body.latestScore).toBe(70);
    expect(body.improvement).toBe(-8);
  });

  it('bestScore 三场并列 90 时 bestTakenAt 取最早', async () => {
    insert('math', 'p1', 90, 100, 60, '2024-03-05T09:00:00Z');
    insert('math', 'p2', 90, 100, 60, '2024-03-01T09:00:00Z');
    insert('math', 'p3', 90, 100, 60, '2024-03-03T09:00:00Z');
    const body = await fetchSummary('?subject=math');
    expect(body.bestScore).toBe(90);
    expect(body.bestTakenAt).toBe('2024-03-01T09:00:00Z');
  });

  it('同 taken_at 时 latest 取 id 大者 first 取 id 小者', async () => {
    const sameTime = '2024-04-01T09:00:00Z';
    insert('math', 'p1', 60, 100, 60, sameTime);
    insert('math', 'p2', 75, 100, 60, sameTime);
    insert('math', 'p3', 88, 100, 60, sameTime);
    const body = await fetchSummary('?subject=math');
    expect(body.firstScore).toBe(60);
    expect(body.latestScore).toBe(88);
    expect(body.improvement).toBe(28);
  });

  it('不传 subject 时 subject=null 且统计全部科目', async () => {
    insert('math', 'p1', 60, 100, 60, '2024-05-01T09:00:00Z');
    insert('english', 'p2', 90, 100, 60, '2024-05-02T09:00:00Z');
    const body = await fetchSummary('');
    expect(body.subject).toBeNull();
    expect(body.count).toBe(2);
    expect(body.avgScore).toBe(75);
    expect(body.avgRate).toBe(0.75);
  });

  it('avgScore 四舍五入到 1 位：60/70/70 → 66.7', async () => {
    insert('math', 'p1', 60, 100, 60, '2024-06-01T09:00:00Z');
    insert('math', 'p2', 70, 100, 60, '2024-06-02T09:00:00Z');
    insert('math', 'p3', 70, 100, 60, '2024-06-03T09:00:00Z');
    const body = await fetchSummary('?subject=math');
    expect(body.avgScore).toBe(66.7);
  });

  it('单场时 improvement=0 且 best/latest/first 均为该场', async () => {
    insert('math', 'p1', 82, 100, 60, '2024-07-01T09:00:00Z');
    const body = await fetchSummary('?subject=math');
    expect(body.count).toBe(1);
    expect(body.improvement).toBe(0);
    expect(body.bestScore).toBe(82);
    expect(body.bestTakenAt).toBe('2024-07-01T09:00:00Z');
    expect(body.latestScore).toBe(82);
    expect(body.latestTakenAt).toBe('2024-07-01T09:00:00Z');
    expect(body.firstScore).toBe(82);
    expect(body.firstTakenAt).toBe('2024-07-01T09:00:00Z');
  });

  it('subject= 空字符串时返回 400 与错误信息', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/exams/summary?subject=', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(400);
    const body = res.json() as { error: string };
    expect(body.error).toBe('无效的 subject 参数');
  });
});
