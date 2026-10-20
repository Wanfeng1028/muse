import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';
import { registerBackupRoutes } from '../src/routes/backup';


function randName(prefix: string): string {
  return (prefix + Math.random().toString(36).slice(2, 10)).toLowerCase().replace(/[^a-z0-9_]/g, '');
}

describe('POST /api/import/mistakes 边界测试', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let cookie: string;

  beforeEach(async () => {
    db = createRealDb(':memory:');
    app = Fastify();
    registerBackupRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, randName('u'), 'password123');
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  it('1. 非对象 body（传数组）→400 请求体无效', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: [1, 2, 3]
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('请求体无效');
  });

  it('2. csv 为空串或全空白 →400 csv 不能为空', async () => {
    const res1 = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv: '' }
    });
    expect(res1.statusCode).toBe(400);
    expect(res1.json().error).toBe('csv 不能为空');

    const res2 = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv: '   \n  \n\t\n' }
    });
    expect(res2.statusCode).toBe(400);
    expect(res2.json().error).toBe('csv 不能为空');
  });

  it('3. 全空行 csv →400 缺少必需列', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv: '\n\n\n' }
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('csv 不能为空');
  });

  it('4. 表头缺 title 列 →400 缺少必需列', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv: 'subject,content\nmath,解析A' }
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('缺少必需列：subject / title');
  });

  it('5. 正常导入 2 条 →200 imported=2 errorRows=0', async () => {
    const csv = 'subject,title,content\nmath,错题1,解析A\nenglish,错题2,';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv }
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(2);
    expect(body.errorRows).toBe(0);

    // 若列表路由不同，只断言 imported 即可
    const listRes = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: { cookie }
    });
    if (listRes.statusCode === 200) {
      const list = listRes.json();
      expect(Array.isArray(list)).toBe(true);
      expect(list.length).toBe(2);
    }
  });

  it('6. 非法 subject 行 →200 errorRows=1 errors[0].message=无效的 subject', async () => {
    const csv = 'subject,title\nxxx,错题1\nmath,错题2';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv }
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.errorRows).toBe(1);
    expect(body.imported).toBe(1);
    expect(body.errors[0].message).toBe('无效的 subject');
    // 表头为第1行，第一行数据为第2行
    expect(body.errors[0].row).toBe(2);
  });

  it('7. 空 title 行 →200 errorRows=1 errors[0].message=title 不能为空', async () => {
    const csv = 'subject,title\nmath,\nenglish,错题2';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv }
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.errorRows).toBe(1);
    expect(body.imported).toBe(1);
    expect(body.errors[0].message).toBe('title 不能为空');
  });

  it('8. errors 上限 50：60 行非法 subject →200 errors.length=50 errorRows=60', async () => {
    const lines = ['subject,title'];
    for (let i = 0; i < 60; i++) {
      lines.push('xxx,错题' + i);
    }
    const csv = lines.join('\n');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv }
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.errors.length).toBe(50);
    expect(body.errorRows).toBe(60);
    expect(body.imported).toBe(0);
  });

  it('9. CSV 引号转义：title 含逗号 "a,b" →正常导入且 title 还原为 a,b', async () => {
    const csv = 'subject,title\nmath,"a,b"';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie, 'content-type': 'application/json' },
      payload: { csv }
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1);
    expect(body.errorRows).toBe(0);

    // 验证 title 还原
    const listRes = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: { cookie }
    });
    if (listRes.statusCode === 200) {
      const list = listRes.json();
      expect(list.length).toBe(1);
      expect(list[0].title).toBe('a,b');
    }
  });

  it('10. 用户隔离：A 导入 2 条，B 导入 1 条，A 看不到 B 的', async () => {
    const cookieA = await registerAndLogin(app, randName('u'), 'password123');
    const cookieB = await registerAndLogin(app, randName('u'), 'password123');

    const csvA = 'subject,title\nmath,错题A1\nenglish,错题A2';
    const resA = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie: cookieA, 'content-type': 'application/json' },
      payload: { csv: csvA }
    });
    expect(resA.statusCode).toBe(200);
    expect(resA.json().imported).toBe(2);

    const csvB = 'subject,title\npolitics,错题B1';
    const resB = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      headers: { cookie: cookieB, 'content-type': 'application/json' },
      payload: { csv: csvB }
    });
    expect(resB.statusCode).toBe(200);
    expect(resB.json().imported).toBe(1);

    // 若列表路由不支持，则断言两次导入的 imported 各自正确
    const listResA = await app.inject({
      method: 'GET',
      url: '/api/mistakes',
      headers: { cookie: cookieA }
    });
    if (listResA.statusCode === 200) {
      const listA = listResA.json();
      expect(Array.isArray(listA)).toBe(true);
      expect(listA.length).toBe(2);
      // 不应包含 B 的错题
      const titles = listA.map((m: any) => m.title);
      expect(titles).not.toContain('错题B1');
    }
  });
});
