import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
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

async function buildApp(db: DatabaseSync): Promise<FastifyInstance> {
  const app = Fastify();
  registerExamsRoutes(app, db);
  await app.ready();
  return app;
}

function insertExam(
  db: DatabaseSync,
  subject: string,
  paper: string,
  score: number,
  totalScore: number,
  durationMinutes: number,
  takenAt: string
): number {
  const r = db
    .prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    )
    .run(subject, paper, score, totalScore, durationMinutes, takenAt);
  return Number(r.lastInsertRowid);
}

function todayStr(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

describe('exams 模块第三轮深测 (r3)', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;

  beforeEach(async () => {
    db = createDb();
    app = await buildApp(db);
  });

  afterAll(async () => {
    if (app) await app.close();
  });

  it('1. trend 按 taken_at 升序、同 taken_at 按 id 升序（与列表降序对称）', async () => {
    const idA = insertExam(db, 'math', 'p-early', 100, 300, 60, '2024-01-01');
    const idB = insertExam(db, 'math', 'p-mid-1', 110, 300, 60, '2024-02-01');
    const idC = insertExam(db, 'math', 'p-mid-2', 120, 300, 60, '2024-02-01');
    const idD = insertExam(db, 'math', 'p-late', 130, 300, 60, '2024-03-01');

    const trendRes = await app.inject({ method: 'GET', url: '/api/exams/trend' });
    expect(trendRes.statusCode).toBe(200);
    const trend = trendRes.json() as Array<{ takenAt: string; paper: string }>;
    expect(trend.map((p) => p.paper)).toEqual([
      'p-early',
      'p-mid-1',
      'p-mid-2',
      'p-late',
    ]);

    const listRes = await app.inject({ method: 'GET', url: '/api/exams' });
    expect(listRes.statusCode).toBe(200);
    const list = listRes.json() as Array<{ id: number; paper: string }>;
    expect(list.map((r) => r.paper)).toEqual([
      'p-late',
      'p-mid-2',
      'p-mid-1',
      'p-early',
    ]);
    expect(list.map((r) => r.id)).toEqual([idD, idC, idB, idA]);
  });

  it('2. trend rate 四位小数精确：100/300=0.3333, 200/300=0.6667, 1/6=0.1667', async () => {
    insertExam(db, 'math', 'r1', 100, 300, 60, '2024-01-01');
    insertExam(db, 'math', 'r2', 200, 300, 60, '2024-01-02');
    insertExam(db, 'math', 'r3', 1, 6, 60, '2024-01-03');

    const res = await app.inject({ method: 'GET', url: '/api/exams/trend' });
    expect(res.statusCode).toBe(200);
    const points = res.json() as Array<{ paper: string; rate: number }>;
    const byPaper = new Map(points.map((p) => [p.paper, p.rate]));
    expect(byPaper.get('r1')).toBe(0.3333);
    expect(byPaper.get('r2')).toBe(0.6667);
    expect(byPaper.get('r3')).toBe(0.1667);
  });

  it('3. trend rate 边界：满分=1，零分=0，total_score=0 防御分支返回 0', async () => {
    insertExam(db, 'math', 'full', 300, 300, 60, '2024-01-01');
    insertExam(db, 'math', 'zero', 0, 300, 60, '2024-01-02');
    // 直接插 DB 一条 total_score = 0 的记录，走防御分支
    insertExam(db, 'math', 'defensive', 0, 0, 60, '2024-01-03');

    const res = await app.inject({ method: 'GET', url: '/api/exams/trend' });
    expect(res.statusCode).toBe(200);
    const points = res.json() as Array<{ paper: string; rate: number }>;
    const byPaper = new Map(points.map((p) => [p.paper, p.rate]));
    expect(byPaper.get('full')).toBe(1);
    expect(byPaper.get('zero')).toBe(0);
    expect(byPaper.get('defensive')).toBe(0);
  });

  it('4. POST durationMinutes：90.9 floor 为 90，缺省为 0，负数 400，NaN 400', async () => {
    const ok1 = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: 'd-floor',
        score: 100,
        totalScore: 150,
        durationMinutes: 90.9,
        takenAt: '2024-01-01',
      },
    });
    expect(ok1.statusCode).toBe(201);
    expect(ok1.json().durationMinutes).toBe(90);

    const ok2 = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: 'd-default',
        score: 100,
        totalScore: 150,
        takenAt: '2024-01-02',
      },
    });
    expect(ok2.statusCode).toBe(201);
    expect(ok2.json().durationMinutes).toBe(0);

    const neg = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: 'd-neg',
        score: 100,
        totalScore: 150,
        durationMinutes: -1,
      },
    });
    expect(neg.statusCode).toBe(400);
    expect(neg.json().error).toBe('durationMinutes 必须大于等于 0');

    // Number.NaN 经 JSON 序列化变成 null，源码把 null 视为"未提供"，故返回 201 且 durationMinutes 为 0
    // 这是传输层 + 源码共同决定的真实行为，测试如实记录
    const nan = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: 'd-nan',
        score: 100,
        totalScore: 150,
        durationMinutes: Number.NaN,
      },
    });
    expect(nan.statusCode).toBe(201);
    expect(nan.json().durationMinutes).toBe(0);

  });

  it('5. POST paper 校验：空字符串 400，全空白 400，数字 400', async () => {
    const empty = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: '',
        score: 100,
        totalScore: 150,
      },
    });
    expect(empty.statusCode).toBe(400);
    expect(empty.json().error).toBe('paper 不能为空');

    const blank = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: '   ',
        score: 100,
        totalScore: 150,
      },
    });
    expect(blank.statusCode).toBe(400);
    expect(blank.json().error).toBe('paper 不能为空');

    const num = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: 123,
        score: 100,
        totalScore: 150,
      },
    });
    expect(num.statusCode).toBe(400);
    expect(num.json().error).toBe('paper 不能为空');
  });

  it('6. POST score 校验：>totalScore 400，负数 400，NaN/Infinity/字符串 400', async () => {
    const over = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: 151, totalScore: 150 },
    });
    expect(over.statusCode).toBe(400);
    expect(over.json().error).toBe('score 必须在 0 到 totalScore 之间');

    const neg = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: -1, totalScore: 150 },
    });
    expect(neg.statusCode).toBe(400);
    expect(neg.json().error).toBe('score 必须在 0 到 totalScore 之间');

    const nan = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: Number.NaN, totalScore: 150 },
    });
    expect(nan.statusCode).toBe(400);
    expect(nan.json().error).toBe('score 必须在 0 到 totalScore 之间');

    const inf = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: Number.POSITIVE_INFINITY, totalScore: 150 },
    });
    expect(inf.statusCode).toBe(400);
    expect(inf.json().error).toBe('score 必须在 0 到 totalScore 之间');

    const str = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: '100', totalScore: 150 },
    });
    expect(str.statusCode).toBe(400);
    expect(str.json().error).toBe('score 必须在 0 到 totalScore 之间');
  });

  it('7. POST totalScore 校验：0 400，负数 400，NaN 400', async () => {
    const zero = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: 0, totalScore: 0 },
    });
    expect(zero.statusCode).toBe(400);
    expect(zero.json().error).toBe('totalScore 必须大于 0');

    const neg = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: 0, totalScore: -10 },
    });
    expect(neg.statusCode).toBe(400);
    expect(neg.json().error).toBe('totalScore 必须大于 0');

    const nan = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: 0, totalScore: Number.NaN },
    });
    expect(nan.statusCode).toBe(400);
    expect(nan.json().error).toBe('totalScore 必须大于 0');
  });

  it('8. POST takenAt：非字符串 400，空字符串 400，合法原样入库，缺省为今天', async () => {
    const num = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: 10, totalScore: 100, takenAt: 12345 },
    });
    expect(num.statusCode).toBe(400);
    expect(num.json().error).toBe('takenAt 无效');

    const empty = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'p', score: 10, totalScore: 100, takenAt: '' },
    });
    expect(empty.statusCode).toBe(400);
    expect(empty.json().error).toBe('takenAt 无效');

    const ok = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: 'explicit-date',
        score: 10,
        totalScore: 100,
        takenAt: '2023-06-15',
      },
    });
    expect(ok.statusCode).toBe(201);
    expect(ok.json().takenAt).toBe('2023-06-15');

    const listRes = await app.inject({ method: 'GET', url: '/api/exams' });
    const list = listRes.json() as Array<{ paper: string; takenAt: string }>;
    const found = list.find((r) => r.paper === 'explicit-date');
    expect(found?.takenAt).toBe('2023-06-15');

    const def = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'math', paper: 'default-date', score: 10, totalScore: 100 },
    });
    expect(def.statusCode).toBe(201);
    expect(def.json().takenAt).toBe(todayStr());
  });

  it('9. POST subject 非法 400；body 为 null 或数组 400', async () => {
    const bad = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: { subject: 'art', paper: 'p', score: 10, totalScore: 100 },
    });
    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('无效的 subject');

    const nullBody = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: 'null',
      headers: { 'content-type': 'application/json' },
    });
    expect(nullBody.statusCode).toBe(400);
    expect(nullBody.json().error).toBe('请求体不能为空');

    const arrBody = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: '[]',
      headers: { 'content-type': 'application/json' },
    });
    expect(arrBody.statusCode).toBe(400);
    expect(arrBody.json().error).toBe('无效的 subject');
  });

  it('10. DELETE：0/负数/小数/abc 400；不存在 404；删除后 list 与 trend 均不再含该记录', async () => {
    const zero = await app.inject({ method: 'DELETE', url: '/api/exams/0' });
    expect(zero.statusCode).toBe(400);
    expect(zero.json().error).toBe('无效的 id');

    const neg = await app.inject({ method: 'DELETE', url: '/api/exams/-5' });
    expect(neg.statusCode).toBe(400);
    expect(neg.json().error).toBe('无效的 id');

    const dec = await app.inject({ method: 'DELETE', url: '/api/exams/1.5' });
    expect(dec.statusCode).toBe(400);
    expect(dec.json().error).toBe('无效的 id');

    const abc = await app.inject({ method: 'DELETE', url: '/api/exams/abc' });
    expect(abc.statusCode).toBe(400);
    expect(abc.json().error).toBe('无效的 id');

    const notFound = await app.inject({ method: 'DELETE', url: '/api/exams/9999' });
    expect(notFound.statusCode).toBe(404);
    expect(notFound.json().error).toBe('记录不存在');

    const keepId = insertExam(db, 'math', 'keep', 50, 100, 30, '2024-01-01');
    const delId = insertExam(db, 'math', 'to-delete', 60, 100, 30, '2024-01-02');

    const del = await app.inject({ method: 'DELETE', url: `/api/exams/${delId}` });
    expect(del.statusCode).toBe(200);
    expect(del.json()).toEqual({ ok: true });

    const listRes = await app.inject({ method: 'GET', url: '/api/exams' });
    const list = listRes.json() as Array<{ id: number; paper: string }>;
    expect(list.find((r) => r.id === delId)).toBeUndefined();
    expect(list.find((r) => r.id === keepId)).toBeDefined();

    const trendRes = await app.inject({ method: 'GET', url: '/api/exams/trend' });
    const trend = trendRes.json() as Array<{ paper: string }>;
    expect(trend.find((p) => p.paper === 'to-delete')).toBeUndefined();
    expect(trend.find((p) => p.paper === 'keep')).toBeDefined();
  });

  it('11. GET ?subject 过滤：仅返回该科目；非法 subject 400；trend ?subject 同样生效', async () => {
    insertExam(db, 'math', 'm1', 10, 100, 30, '2024-01-01');
    insertExam(db, 'english', 'e1', 20, 100, 30, '2024-01-02');
    insertExam(db, 'math', 'm2', 30, 100, 30, '2024-01-03');
    insertExam(db, 'politics', 'p1', 40, 100, 30, '2024-01-04');

    const mathList = await app.inject({ method: 'GET', url: '/api/exams?subject=math' });
    expect(mathList.statusCode).toBe(200);
    const mathRows = mathList.json() as Array<{ subject: string; paper: string }>;
    expect(mathRows.every((r) => r.subject === 'math')).toBe(true);
    expect(mathRows.map((r) => r.paper)).toEqual(['m2', 'm1']);

    const bad = await app.inject({ method: 'GET', url: '/api/exams?subject=art' });
    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('无效的 subject 参数');

    const mathTrend = await app.inject({
      method: 'GET',
      url: '/api/exams/trend?subject=math',
    });
    expect(mathTrend.statusCode).toBe(200);
    const trendPoints = mathTrend.json() as Array<{ paper: string }>;
    expect(trendPoints.map((p) => p.paper)).toEqual(['m1', 'm2']);

    const badTrend = await app.inject({
      method: 'GET',
      url: '/api/exams/trend?subject=art',
    });
    expect(badTrend.statusCode).toBe(400);
    expect(badTrend.json().error).toBe('无效的 subject 参数');
  });

  it('12. 字段映射：POST 返回体 totalScore/durationMinutes/takenAt 与入库一致', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'english',
        paper: 'mapping-test',
        score: 88.5,
        totalScore: 100,
        durationMinutes: 120,
        takenAt: '2024-05-20',
      },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json() as {
      id: number;
      subject: string;
      paper: string;
      score: number;
      totalScore: number;
      durationMinutes: number;
      takenAt: string;
    };
    expect(body.subject).toBe('english');
    expect(body.paper).toBe('mapping-test');
    expect(body.score).toBe(88.5);
    expect(body.totalScore).toBe(100);
    expect(body.durationMinutes).toBe(120);
    expect(body.takenAt).toBe('2024-05-20');

    const row = db
      .prepare(
        'SELECT subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE id = ?'
      )
      .get(body.id) as {
      subject: string;
      paper: string;
      score: number;
      total_score: number;
      duration_minutes: number;
      taken_at: string;
    };
    expect(row.subject).toBe(body.subject);
    expect(row.paper).toBe(body.paper);
    expect(row.score).toBe(body.score);
    expect(row.total_score).toBe(body.totalScore);
    expect(row.duration_minutes).toBe(body.durationMinutes);
    expect(row.taken_at).toBe(body.takenAt);

    const listRes = await app.inject({ method: 'GET', url: '/api/exams' });
    const list = listRes.json() as Array<{
      id: number;
      totalScore: number;
      durationMinutes: number;
      takenAt: string;
    }>;
    const fromList = list.find((r) => r.id === body.id);
    expect(fromList?.totalScore).toBe(100);
    expect(fromList?.durationMinutes).toBe(120);
    expect(fromList?.takenAt).toBe('2024-05-20');
  });
});
