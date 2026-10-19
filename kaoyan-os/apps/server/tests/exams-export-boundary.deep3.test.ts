import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { registerExamsRoutes } from '../src/routes/exams';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

interface SeedExam {
  subject: string;
  paper: string;
  score: number;
  totalScore: number;
  durationMinutes: number;
  takenAt: string;
}

function seedExam(db: DatabaseSync, userId: number, e: SeedExam): void {
  db.prepare(
    'INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
  ).run(userId, e.subject, e.paper, e.score, e.totalScore, e.durationMinutes, e.takenAt);
}

function getUserId(db: DatabaseSync, username: string): number {
  const row = db
    .prepare('SELECT id FROM users WHERE username = ?')
    .get(username) as { id: number } | undefined;
  if (!row) throw new Error(`user ${username} not found`);
  return row.id;
}

const HEADER =
  'id,subject,subject_name,paper,score,total_score,rate,duration_minutes,taken_at';

function dataLines(body: string): string[] {
  // 去掉 BOM，按 \n 切分，去掉末尾空行
  const withoutBom = body.charCodeAt(0) === 0xfeff ? body.slice(1) : body;
  const lines = withoutBom.split('\n');
  if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
  return lines;
}

describe('exams export boundary', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let cookie: string;
  let userId: number;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerExamsRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'expuser');
    userId = getUserId(db, 'expuser');
  });

  afterEach(async () => {
    await app.close();
  });

  it('导出响应体以 BOM 开头', async () => {
    seedExam(db, userId, {
      subject: 'math',
      paper: '真题',
      score: 10,
      totalScore: 20,
      durationMinutes: 60,
      takenAt: '2024-10-20',
    });
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.body.charCodeAt(0)).toBe(0xfeff);
  });

  it('paper 含逗号时该字段被双引号整体包裹', async () => {
    seedExam(db, userId, {
      subject: 'math',
      paper: '张宇,30讲',
      score: 10,
      totalScore: 20,
      durationMinutes: 60,
      takenAt: '2024-10-20',
    });
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const lines = dataLines(res.body);
    expect(lines.length).toBe(2);
    expect(lines[1]).toContain('"张宇,30讲"');
    // 逗号在引号内，不能成为裸分隔符
    // 逗号在引号内，不能成为裸分隔符：前后逗号证明它是独立字段
    expect(lines[1]).toContain(',"张宇,30讲",');
  });

  it('paper 含双引号时翻倍并整体加双引号', async () => {
    seedExam(db, userId, {
      subject: 'math',
      paper: '李林"6套卷"',
      score: 10,
      totalScore: 20,
      durationMinutes: 60,
      takenAt: '2024-10-20',
    });
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const lines = dataLines(res.body);
    expect(lines.length).toBe(2);
    expect(lines[1]).toContain('"李林""6套卷"""');
  });

  it('paper 含换行时被双引号包裹（引号内含换行）', async () => {
    seedExam(db, userId, {
      subject: 'math',
      paper: '第一行\n第二行',
      score: 10,
      totalScore: 20,
      durationMinutes: 60,
      takenAt: '2024-10-20',
    });
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.body).toContain('"第一行\n第二行"');
  });

  it('rate 精度：score=2, totalScore=3 → 0.6667', async () => {
    seedExam(db, userId, {
      subject: 'math',
      paper: 'p',
      score: 2,
      totalScore: 3,
      durationMinutes: 60,
      takenAt: '2024-10-20',
    });
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const lines = dataLines(res.body);
    expect(lines.length).toBe(2);
    const cols = lines[1].split(',');
    // id,subject,subject_name,paper,score,total_score,rate,...
    expect(cols[6]).toBe('0.6667');
  });

  it('score=0 → rate 列为 0', async () => {
    seedExam(db, userId, {
      subject: 'math',
      paper: 'p',
      score: 0,
      totalScore: 20,
      durationMinutes: 60,
      takenAt: '2024-10-20',
    });
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const lines = dataLines(res.body);
    expect(lines.length).toBe(2);
    const cols = lines[1].split(',');
    expect(cols[6]).toBe('0');
  });

  it('数据行按 taken_at 升序，同 taken_at 按 id 升序', async () => {
    seedExam(db, userId, {
      subject: 'math',
      paper: 'late',
      score: 1,
      totalScore: 10,
      durationMinutes: 60,
      takenAt: '2024-10-22',
    });
    seedExam(db, userId, {
      subject: 'math',
      paper: 'early',
      score: 1,
      totalScore: 10,
      durationMinutes: 60,
      takenAt: '2024-10-20',
    });
    seedExam(db, userId, {
      subject: 'math',
      paper: 'sameA',
      score: 1,
      totalScore: 10,
      durationMinutes: 60,
      takenAt: '2024-10-21',
    });
    seedExam(db, userId, {
      subject: 'math',
      paper: 'sameB',
      score: 1,
      totalScore: 10,
      durationMinutes: 60,
      takenAt: '2024-10-21',
    });
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const lines = dataLines(res.body);
    expect(lines.length).toBe(5);
    const papers = lines.slice(1).map((l) => l.split(',')[3]);
    expect(papers).toEqual(['early', 'sameA', 'sameB', 'late']);
  });

  it('subject_name 列：math 行第三列为 数学', async () => {
    seedExam(db, userId, {
      subject: 'math',
      paper: 'p',
      score: 1,
      totalScore: 10,
      durationMinutes: 60,
      takenAt: '2024-10-20',
    });
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const lines = dataLines(res.body);
    expect(lines.length).toBe(2);
    const cols = lines[1].split(',');
    expect(cols[1]).toBe('math');
    expect(cols[2]).toBe('数学');
  });

  it('空库导出只有表头', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.body).toBe('\ufeff' + HEADER + '\n');
  });

  it('?subject=bad → 400 无效的 subject 参数', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export?subject=bad',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject 参数' });
  });

  it('Content-Disposition 依据 subject 生成文件名', async () => {
    const resAll = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(resAll.statusCode).toBe(200);
    expect(resAll.headers['content-disposition']).toBe(
      'attachment; filename="kaoyan-exams.csv"'
    );
    expect(resAll.headers['content-type']).toBe('text/csv; charset=utf-8');

    const resMath = await app.inject({
      method: 'GET',
      url: '/api/exams/export?subject=math',
      headers: { cookie },
    });
    expect(resMath.statusCode).toBe(200);
    expect(resMath.headers['content-disposition']).toBe(
      'attachment; filename="kaoyan-exams-math.csv"'
    );
  });

  it('大数据量：200 条记录导出非空行数为 201 且每行至少 9 列', async () => {
    for (let i = 0; i < 200; i += 1) {
      seedExam(db, userId, {
        subject: 'math',
        paper: `paper-${i}`,
        score: i % 10,
        totalScore: 10,
        durationMinutes: 60,
        takenAt: '2024-10-20',
      });
    }
    const res = await app.inject({
      method: 'GET',
      url: '/api/exams/export',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    const lines = dataLines(res.body);
    expect(lines.length).toBe(201);
    for (const line of lines) {
      expect(line.split(',').length).toBeGreaterThanOrEqual(9);
    }
  });
});