import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';
import { registerPlansRoutes } from '../src/routes/plans';

const EXPORT_HEADER = 'id,date,subject,subject_name,title,planned_minutes,done,created_at';

describe('GET /api/plans/export', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let authCookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    registerPlansRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'plansexport');
  });

  afterAll(async () => {
    await app.close();
  });

  function insertPlan(opts: { user: string; date: string; subject: string; title: string; done?: number }): void {
    db.prepare(
      "INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?, 30, ?, '2024-05-01 08:00:00')"
    ).run(opts.user, opts.date, opts.subject, opts.title, opts.done ?? 0);
  }

  function csvLines(body: string): string[] {
    return body
      .replace(/^\uFEFF/, '')
      .split(/\r?\n/)
      .filter((line) => line.length > 0);
  }

  it('空库导出返回 200,响应带 BOM 的 text/csv,首行为表头', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/export',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    expect(res.headers['content-type']).toContain('text/csv');
    expect(res.body.startsWith('\uFEFF')).toBe(true);
    expect(csvLines(res.body)[0]).toBe(EXPORT_HEADER);
  });

  it('导出两条计划,按 date 升序,subject_name 与 done 列正确', async () => {
    insertPlan({ user: 'plansexport', date: '2024-05-01', subject: 'math', title: '加减法练习', done: 1 });
    insertPlan({ user: 'plansexport', date: '2024-05-02', subject: 'math', title: '乘法口诀', done: 0 });

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/export',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    const lines = csvLines(res.body);
    expect(lines).toHaveLength(3);
    const rows = lines.slice(1).map((line) => line.split(','));
    expect(rows[0][1]).toBe('2024-05-01');
    expect(rows[1][1]).toBe('2024-05-02');
    expect(rows[0][3]).toBe('数学');
    expect(rows[1][3]).toBe('数学');
    expect(rows[0][6]).toBe('1');
    expect(rows[1][6]).toBe('0');
  });

  it('标题含逗号与双引号时按 RFC4180 转义', async () => {
    insertPlan({ user: 'plansexport', date: '2024-05-01', subject: 'math', title: 'a,b"c' });

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/export',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    const lines = csvLines(res.body);
    expect(lines).toHaveLength(2);
    expect(lines[1]).toContain('"a,b""c"');
  });

  it('subject=math 只导出数学计划,非法 subject 返回 400', async () => {
    insertPlan({ user: 'plansexport', date: '2024-05-01', subject: 'math', title: '数学计划' });
    insertPlan({ user: 'plansexport', date: '2024-05-02', subject: 'english', title: '英语计划' });

    const ok = await app.inject({
      method: 'GET',
      url: '/api/plans/export?subject=math',
      headers: { cookie: authCookie },
    });
    expect(ok.statusCode).toBe(200);
    const lines = csvLines(ok.body);
    expect(lines).toHaveLength(2);
    expect(lines[1]).toContain('数学计划');
    expect(lines[1]).not.toContain('英语计划');

    const bad = await app.inject({
      method: 'GET',
      url: '/api/plans/export?subject=bogus',
      headers: { cookie: authCookie },
    });
    expect(bad.statusCode).toBe(400);
  });

  it('用户隔离:只导出当前登录用户的计划', async () => {
    await registerAndLogin(app, 'plansexport2');
    insertPlan({ user: 'plansexport2', date: '2024-05-03', subject: 'math', title: '第二用户的独享计划' });
    insertPlan({ user: 'plansexport', date: '2024-05-01', subject: 'math', title: '我的计划' });

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/export',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    expect(res.body).toContain('我的计划');
    expect(res.body).not.toContain('第二用户的独享计划');
  });

  it('未登录返回 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/plans/export' });
    expect(res.statusCode).toBe(401);
  });
});
