import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerMistakesRoutes } from '../src/routes/mistakes';

function createDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:');
  db.exec(`
    CREATE TABLE mistakes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      content TEXT NOT NULL DEFAULT '',
      analysis TEXT NOT NULL DEFAULT '',
      mastered INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );
  `);
  return db;
}

async function buildApp(db: DatabaseSync): Promise<FastifyInstance> {
  const app = Fastify();
  registerMistakesRoutes(app, db);
  await app.ready();
  return app;
}

describe('mistakes 路由深度测试', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;

  beforeEach(async () => {
    db = createDb();
    app = await buildApp(db);
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  it('创建错题返回 201 并落库，createdAt 为 ISO 字符串', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: {
        subject: 'math',
        title: '  极限的四则运算  ',
        content: '当 x→0 时 sinx/x 的极限',
        analysis: '等价无穷小替换',
      },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body.id).toBeGreaterThan(0);
    expect(body.subject).toBe('math');
    expect(body.title).toBe('极限的四则运算');
    expect(body.mastered).toBe(false);
    expect(typeof body.createdAt).toBe('string');
    expect(Number.isNaN(Date.parse(body.createdAt))).toBe(false);

    const row = db
      .prepare('SELECT * FROM mistakes WHERE id = ?')
      .get(body.id) as { title: string; mastered: number };
    expect(row.title).toBe('极限的四则运算');
    expect(row.mastered).toBe(0);
  });

  it('列表按 id 倒序返回，subject 过滤非法值报 400', async () => {
    for (const title of ['a', 'b', 'c']) {
      await app.inject({
        method: 'POST',
        url: '/api/mistakes',
        payload: { subject: 'english', title, content: '', analysis: '' },
      });
    }
    const ok = await app.inject({ method: 'GET', url: '/api/mistakes' });
    expect(ok.statusCode).toBe(200);
    const list = ok.json() as Array<{ id: number; title: string }>;
    expect(list.length).toBe(3);
    expect(list[0].title).toBe('c');
    expect(list[2].title).toBe('a');

    const bad = await app.inject({
      method: 'GET',
      url: '/api/mistakes?subject=not-a-subject',
    });
    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('无效的 subject');
  });

  it('mastered 只接受 0 或 1，q 关键字同时匹配 title 和 content', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: {
        subject: 'math',
        title: '泰勒展开',
        content: '麦克劳林公式',
        analysis: '',
      },
    });
    await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: {
        subject: 'math',
        title: '夹逼定理',
        content: '泰勒余项估计',
        analysis: '',
      },
    });

    const badMastered = await app.inject({
      method: 'GET',
      url: '/api/mistakes?mastered=2',
    });
    expect(badMastered.statusCode).toBe(400);
    expect(badMastered.json().error).toBe('mastered 必须为 0 或 1');

    const byTitle = await app.inject({
      method: 'GET',
      url: '/api/mistakes?q=%E6%B3%B0%E5%8B%92',
    });
    expect(byTitle.statusCode).toBe(200);
    const titleHits = byTitle.json() as Array<{ title: string }>;
    expect(titleHits.length).toBe(2);

    const byContent = await app.inject({
      method: 'GET',
      url: '/api/mistakes?q=%E5%A4%B9%E9%80%BC',
    });
    expect(byContent.statusCode).toBe(200);
    const contentHits = byContent.json() as Array<{ title: string }>;
    expect(contentHits.length).toBe(1);
    expect(contentHits[0].title).toBe('夹逼定理');
  });

  it('PATCH 逐字段更新，非法 mastered 类型被拒', async () => {
    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: {
        subject: 'math',
        title: '原题',
        content: '原内容',
        analysis: '原解析',
      },
    });
    const id = created.json().id as number;

    const patched = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${id}`,
      payload: { mastered: true, analysis: '新解析' },
    });
    expect(patched.statusCode).toBe(200);
    const after = patched.json();
    expect(after.mastered).toBe(true);
    expect(after.analysis).toBe('新解析');
    expect(after.title).toBe('原题');

    const badType = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${id}`,
      payload: { mastered: 'yes' },
    });
    expect(badType.statusCode).toBe(400);
    expect(badType.json().error).toBe('mastered 非法');
  });

  it('PATCH 空 body 不修改任何字段，返回原记录', async () => {
    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: {
        subject: 'math',
        title: '空体测试',
        content: 'c',
        analysis: 'a',
      },
    });
    const id = created.json().id as number;

    const res = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${id}`,
      payload: {},
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.id).toBe(id);
    expect(body.title).toBe('空体测试');
    expect(body.content).toBe('c');
  });

  it('DELETE 存在记录返回 ok，重复删除返回 404，非法 id 返回 400', async () => {
    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: { subject: 'math', title: '待删', content: '', analysis: '' },
    });
    const id = created.json().id as number;

    const del = await app.inject({
      method: 'DELETE',
      url: `/api/mistakes/${id}`,
    });
    expect(del.statusCode).toBe(200);
    expect(del.json().ok).toBe(true);

    const again = await app.inject({
      method: 'DELETE',
      url: `/api/mistakes/${id}`,
    });
    expect(again.statusCode).toBe(404);
    expect(again.json().error).toBe('错题不存在');

    const badId = await app.inject({
      method: 'DELETE',
      url: '/api/mistakes/abc',
    });
    expect(badId.statusCode).toBe(400);
    expect(badId.json().error).toBe('id 非法');
  });

  it('创建时空 title、非法 subject、非对象 body 均报 400', async () => {
    const emptyTitle = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: { subject: 'math', title: '   ' },
    });
    expect(emptyTitle.statusCode).toBe(400);
    expect(emptyTitle.json().error).toBe('title 不能为空');

    const badSubject = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: { subject: 'physics', title: 'x' },
    });
    expect(badSubject.statusCode).toBe(400);
    expect(badSubject.json().error).toBe('subject 非法');

    const badBody = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: 'not-an-object',
      headers: { 'content-type': 'application/json' },
    });
    expect(badBody.statusCode).toBe(400);
    expect(badBody.json().error).toBe('Bad Request');
  });

  it('PATCH 不存在的 id 返回 404，非法 id 返回 400', async () => {
    const missing = await app.inject({
      method: 'PATCH',
      url: '/api/mistakes/99999',
      payload: { title: 'x' },
    });
    expect(missing.statusCode).toBe(404);
    expect(missing.json().error).toBe('错题不存在');

    const badId = await app.inject({
      method: 'PATCH',
      url: '/api/mistakes/0',
      payload: { title: 'x' },
    });
    expect(badId.statusCode).toBe(400);
    expect(badId.json().error).toBe('id 非法');
  });

  it('列表过滤组合：subject + mastered 同时生效', async () => {
    const a = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: { subject: 'math', title: 'm1', content: '', analysis: '' },
    });
    await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: { subject: 'english', title: 'e1', content: '', analysis: '' },
    });
    await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: { subject: 'math', title: 'm2', content: '', analysis: '' },
    });
    await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${a.json().id}`,
      payload: { mastered: true },
    });

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes?subject=math&mastered=1',
    });
    expect(res.statusCode).toBe(200);
    const list = res.json() as Array<{ title: string; subject: string }>;
    expect(list.length).toBe(1);
    expect(list[0].title).toBe('m1');
    expect(list[0].subject).toBe('math');
  });

  it('PATCH content 与 analysis 均需为字符串，否则 400', async () => {
    const created = await app.inject({
      method: 'POST',
      url: '/api/mistakes',
      payload: { subject: 'math', title: 't', content: 'c', analysis: 'a' },
    });
    const id = created.json().id as number;

    const badContent = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${id}`,
      payload: { content: 123 },
    });
    expect(badContent.statusCode).toBe(400);
    expect(badContent.json().error).toBe('content 非法');

    const badAnalysis = await app.inject({
      method: 'PATCH',
      url: `/api/mistakes/${id}`,
      payload: { analysis: false },
    });
    expect(badAnalysis.statusCode).toBe(400);
    expect(badAnalysis.json().error).toBe('analysis 非法');
  });
});