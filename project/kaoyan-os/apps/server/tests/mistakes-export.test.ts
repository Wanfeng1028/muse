import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('GET /api/mistakes/export', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let authCookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    registerMistakesRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'mistakesexport');
  });

  afterAll(async () => {
    await app.close();
  });

  it('空库导出：返回 200、带 BOM、text/csv，首行为表头', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/mistakes/export', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    expect(res.body.charCodeAt(0)).toBe(0xFEFF);
    expect(res.headers['content-type']).toContain('text/csv');
    const firstLine = res.body.slice(1).trim().split(/\r?\n/)[0];
    expect(firstLine).toBe('id,subject,subject_name,title,content,analysis,mastered,created_at');
  });

  it('两条记录按 created_at 升序导出，subject_name 为数学，mastered 列为 1 与 0', async () => {
    db.exec(`INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
      VALUES ((SELECT id FROM users WHERE username = 'mistakesexport'), 'math', '后创建的题', '解方程步骤', '先移项再合并', 0, '2024-06-02 09:00:00')`);
    db.exec(`INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
      VALUES ((SELECT id FROM users WHERE username = 'mistakesexport'), 'math', '先创建的题', '解方程步骤', '先移项再合并', 1, '2024-06-01 08:00:00')`);

    const res = await app.inject({ method: 'GET', url: '/api/mistakes/export', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const lines = res.body.slice(1).trim().split(/\r?\n/);
    expect(lines).toHaveLength(3);
    expect(lines[1]).toContain('数学');
    expect(lines[2]).toContain('数学');
    expect(lines[1]).toContain('先创建的题');
    expect(lines[2]).toContain('后创建的题');
    expect(lines[1].split(',')[6]).toBe('1');
    expect(lines[2].split(',')[6]).toBe('0');
  });

  it('标题含逗号与双引号时按 RFC4180 转义', async () => {
    db.exec(`INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
      VALUES ((SELECT id FROM users WHERE username = 'mistakesexport'), 'math', 'a,b"c', '内容', '分析', 1, '2024-06-01 08:00:00')`);

    const res = await app.inject({ method: 'GET', url: '/api/mistakes/export', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const lines = res.body.slice(1).trim().split(/\r?\n/);
    expect(lines).toHaveLength(2);
    expect(lines[1]).toContain('"a,b""c"');
    expect(res.body).not.toContain('a,b"c');
  });

  it('subject 过滤导出，非法 subject 返回 400', async () => {
    db.exec(`INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
      VALUES ((SELECT id FROM users WHERE username = 'mistakesexport'), 'math', '数学题m', '内容', '分析', 1, '2024-06-01 08:00:00')`);
    db.exec(`INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
      VALUES ((SELECT id FROM users WHERE username = 'mistakesexport'), 'english', '英语题e', '内容', '分析', 0, '2024-06-02 09:00:00')`);

    const resMath = await app.inject({ method: 'GET', url: '/api/mistakes/export?subject=math', headers: { cookie: authCookie } });
    expect(resMath.statusCode).toBe(200);
    const mathLines = resMath.body.slice(1).trim().split(/\r?\n/);
    expect(mathLines).toHaveLength(2);
    expect(mathLines[1]).toContain('数学题m');
    expect(mathLines[1]).toContain('数学');
    expect(resMath.body).not.toContain('英语题e');

    const resEnglish = await app.inject({ method: 'GET', url: '/api/mistakes/export?subject=english', headers: { cookie: authCookie } });
    expect(resEnglish.statusCode).toBe(200);
    expect(resEnglish.body).toContain('英语题e');
    expect(resEnglish.body).not.toContain('数学题m');
    expect(resEnglish.body).not.toContain('数学');

    const resBogus = await app.inject({ method: 'GET', url: '/api/mistakes/export?subject=bogus', headers: { cookie: authCookie } });
    expect(resBogus.statusCode).toBe(400);
  });

  it('用户隔离：第一用户导出不含第二用户的错题', async () => {
    const otherCookie = await registerAndLogin(app, 'mistakesexport2');
    db.exec(`INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
      VALUES ((SELECT id FROM users WHERE username = 'mistakesexport2'), 'math', '第二用户独有的隔离标题', '内容', '分析', 0, '2024-06-03 10:00:00')`);

    const res = await app.inject({ method: 'GET', url: '/api/mistakes/export', headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    expect(res.body).not.toContain('第二用户独有的隔离标题');

    const resOther = await app.inject({ method: 'GET', url: '/api/mistakes/export', headers: { cookie: otherCookie } });
    expect(resOther.statusCode).toBe(200);
    expect(resOther.body).toContain('第二用户独有的隔离标题');
  });

  it('未登录导出返回 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/mistakes/export' });
    expect(res.statusCode).toBe(401);
  });
});