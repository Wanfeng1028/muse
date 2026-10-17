import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerBackupRoutes } from '../src/routes/backup';

let app: FastifyInstance;
let db: ReturnType<typeof createDb>;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerBackupRoutes(app, db);
  await app.ready();
});

afterEach(async () => {
  await app.close();
  db.close();
});

describe('POST /api/import/mistakes 边界', () => {
  it('body 为数组时返回 400 请求体无效', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: [] as unknown as Record<string, unknown>,
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '请求体无效' });
  });

  it('body 为字符串时返回 415 不支持的内容类型', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: 'subject,title\nmath,foo' as unknown as Record<string, unknown>,
    });
    expect(res.statusCode).toBe(415);
  });

  it('body 为 JSON 数组 [1,2,3] 时返回 400 请求体无效', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: [1, 2, 3] as unknown as Record<string, unknown>,
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '请求体无效' });
  });

  it('csv 为空字符串返回 400 csv 不能为空', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv: '' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'csv 不能为空' });
  });

  it('csv 为纯空白返回 400 csv 不能为空', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv: '   \n\t  ' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'csv 不能为空' });
  });

  it('缺少 csv 字段返回 400 csv 不能为空', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: {} as Record<string, unknown>,
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'csv 不能为空' });
  });

  it('csv 为纯换行符返回 400 csv 不能为空', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv: '\n\n' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'csv 不能为空' });
  });

  it('csv 为带引号的空字段时返回 400 缺少必需列', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv: '""' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '缺少必需列：subject / title' });
  });

  it('表头只有 title 列时返回 400 缺少必需列', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv: 'title\nfoo' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '缺少必需列：subject / title' });
  });

  it('表头前有 2 个空行时正常识别表头并导入', async () => {
    const csv = '\n\nsubject,title\nmath,题目A';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ imported: 1, errors: [], errorRows: 0 });
    const rows = db.prepare('SELECT subject, title FROM mistakes').all() as {
      subject: string;
      title: string;
    }[];
    expect(rows).toEqual([{ subject: 'math', title: '题目A' }]);
  });

  it('subject 非法时报错行号为 3', async () => {
    const csv = 'subject,title\nmath,题目A\nphysics,题目B';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      imported: number;
      errors: { row: number; message: string }[];
      errorRows: number;
    };
    expect(body.imported).toBe(1);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toEqual([{ row: 3, message: '无效的 subject' }]);
  });

  it('title 为空时报错且不入库', async () => {
    const csv = 'subject,title\nmath,';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      imported: number;
      errors: { row: number; message: string }[];
      errorRows: number;
    };
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toEqual([{ row: 2, message: 'title 不能为空' }]);
    const count = db.prepare('SELECT COUNT(*) AS c FROM mistakes').get() as { c: number };
    expect(count.c).toBe(0);
  });

  it('60 个坏行时 errorRows=60 但 errors 截断为 50', async () => {
    const lines: string[] = ['subject,title'];
    for (let i = 0; i < 60; i += 1) {
      lines.push(`physics,题目${i}`);
    }
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv: lines.join('\n') },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      imported: number;
      errors: { row: number; message: string }[];
      errorRows: number;
    };
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(60);
    expect(body.errors).toHaveLength(50);
    expect(body.errors[0]).toEqual({ row: 2, message: '无效的 subject' });
    expect(body.errors[49]).toEqual({ row: 51, message: '无效的 subject' });
  });

  it('content 用双引号包裹逗号时完整保留', async () => {
    const csv = 'subject,title,content\nmath,题目A,"a,b,c"';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ imported: 1, errors: [], errorRows: 0 });
    const row = db
      .prepare('SELECT content FROM mistakes WHERE title = ?')
      .get('题目A') as { content: string };
    expect(row.content).toBe('a,b,c');
  });

  it('无 content/analysis 列时导入成功且 content 为空字符串', async () => {
    const csv = 'subject,title\nmath,题目A';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ imported: 1, errors: [], errorRows: 0 });
    const row = db
      .prepare('SELECT content, analysis FROM mistakes WHERE title = ?')
      .get('题目A') as { content: string; analysis: string };
    expect(row.content).toBe('');
    expect(row.analysis).toBe('');
  });

  it('成功导入的错题 mastered=0', async () => {
    const csv = 'subject,title\nmath,题目A';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const row = db
      .prepare('SELECT mastered FROM mistakes WHERE title = ?')
      .get('题目A') as { mastered: number };
    expect(row.mastered).toBe(0);
  });
});