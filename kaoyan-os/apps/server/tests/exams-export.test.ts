import { describe, it, expect, beforeEach, afterAll } from 'vitest';
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

describe('GET /api/exams/export', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;

  beforeEach(async () => {
    db = createDb();
    app = Fastify();
    registerExamsRoutes(app, db);
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  it('empty database: header row + BOM + text/csv content-type', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/exams/export' });
    expect(res.statusCode).toBe(200);
    expect(res.body.charCodeAt(0)).toBe(0xFEFF);
    expect(res.headers['content-type']).toContain('text/csv');
    const lines = res.body.split('\n');
    expect(lines[0].replace(/^\uFEFF/, '').trim()).toBe(
      'id,subject,subject_name,paper,score,total_score,rate,duration_minutes,taken_at'
    );
  });

  it('two records: 3 lines total, ordered by taken_at ASC, subject_name = 数学', async () => {
    db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run('math', 'later', 90, 150, 180, '2024-12-25');
    db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run('math', 'earlier', 80, 150, 170, '2024-12-20');

    const res = await app.inject({ method: 'GET', url: '/api/exams/export' });
    const lines = res.body.split('\n').filter((l) => l.length > 0);
    expect(lines.length).toBe(3);
    expect(lines[1]).toContain('数学');
    expect(lines[1]).toContain('earlier');
    expect(lines[2]).toContain('later');
    expect(lines[1].indexOf('earlier')).toBeGreaterThanOrEqual(0);
    expect(lines[1].split(',')[8]).toBe('2024-12-20');
    expect(lines[2].split(',')[8]).toBe('2024-12-25');
  });

  it('paper with comma and double quotes is RFC4180 escaped', async () => {
    db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run('math', '张宇8套卷,第"1"套', 90, 150, 180, '2024-12-20');

    const res = await app.inject({ method: 'GET', url: '/api/exams/export' });
    const lines = res.body.split('\n').filter((l) => l.length > 0);
    expect(lines[1]).toContain('"张宇8套卷,第""1""套"');
  });

  it('rate keeps 4 decimals (90/150=0.6) and total_score=0 -> rate=0', async () => {
    db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run('math', 'p1', 90, 150, 180, '2024-12-20');
    db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run('math', 'p2', 0, 0, 0, '2024-12-21');

    const res = await app.inject({ method: 'GET', url: '/api/exams/export' });
    const lines = res.body.split('\n').filter((l) => l.length > 0);
    const row1 = lines[1].split(',');
    const row2 = lines[2].split(',');
    expect(row1[6]).toBe('0.6');
    expect(row2[6]).toBe('0');
  });

  it('?subject=math only exports math rows', async () => {
    db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run('math', 'p_math', 90, 150, 180, '2024-12-20');
    db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run('english', 'p_eng', 70, 100, 120, '2024-12-21');

    const res = await app.inject({ method: 'GET', url: '/api/exams/export?subject=math' });
    expect(res.statusCode).toBe(200);
    expect(res.body).toContain('p_math');
    expect(res.body).not.toContain('p_eng');
    expect(res.body).toContain('数学');
  });

  it('invalid subject returns 400', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/exams/export?subject=invalid_subject' });
    expect(res.statusCode).toBe(400);
  });

  it('content-disposition contains kaoyan-exams.csv', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/exams/export' });
    expect(res.headers['content-disposition']).toContain('kaoyan-exams.csv');
  });

  it('duration_minutes and taken_at match inserted values', async () => {
    db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run('math', 'p1', 90, 150, 180, '2024-12-20');

    const res = await app.inject({ method: 'GET', url: '/api/exams/export' });
    const lines = res.body.split('\n').filter((l) => l.length > 0);
    const cols = lines[1].split(',');
    expect(cols[7]).toBe('180');
    expect(cols[8]).toBe('2024-12-20');
  });
});
