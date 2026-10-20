import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖 POST /api/import/mistakes 的非法行矩阵（subject 非法 / title 空）与缺列 400；
// 与 mistakes-csv-import-boundary.test.ts 分工：本文件只做 5 行矩阵的精确行号断言与缺列 400，不覆盖正常导入统计与去重。

describe('backup csv mistakes illegal rows deep4', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  async function newUser(prefix: string): Promise<{ cookie: string; userId: number }> {
    const name = rand(prefix);
    const cookie = await registerAndLogin(app, name);
    const row = db.prepare('SELECT id FROM users WHERE username = ?').get(name) as { id: number };
    return { cookie, userId: row.id };
  }
  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerBackupRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });

  it('非法行矩阵：imported=2、errorRows=2、errors.length=2', async () => {
    const { cookie } = await newUser('mim');
    const csv = [
      'subject,title,content',
      'math,错题1,内容1',
      'nope,错题2,x',
      'english,,x',
      'politics,错题3,',
    ].join('\n');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie },
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      imported: number;
      errorRows: number;
      errors: { row: number; message: string }[];
    };
    expect(body.imported).toBe(2);
    expect(body.errorRows).toBe(2);
    expect(body.errors.length).toBe(2);
  });

  it('非法行矩阵：errors 行号与文案精确匹配', async () => {
    const { cookie } = await newUser('mir');
    const csv = [
      'subject,title,content',
      'math,错题1,内容1',
      'nope,错题2,x',
      'english,,x',
      'politics,错题3,',
    ].join('\n');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie },
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      imported: number;
      errorRows: number;
      errors: { row: number; message: string }[];
    };
    expect(body.errors[0]).toEqual({ row: 3, message: '无效的 subject' });
    expect(body.errors[1]).toEqual({ row: 4, message: 'title 不能为空' });
  });

  it('缺少 subject / title 列：400 且库中 mistakes 为 0 行', async () => {
    const { cookie, userId } = await newUser('mim2');
    const csv = ['foo,bar', 'x,y'].join('\n');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie },
      payload: { csv },
    });
    expect(res.statusCode).toBe(400);
    const body = res.json() as { error: string };
    expect(body.error).toBe('缺少必需列：subject / title');
    const count = db
      .prepare('SELECT COUNT(*) AS c FROM mistakes WHERE user_id = ?')
      .get(userId) as { c: number };
    expect(count.c).toBe(0);
  });
});
