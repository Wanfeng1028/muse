import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerWordsRoutes } from '../src/routes/words';
import { registerAndLogin, authHeaders } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;
let cookieA: string;
let cookieB: string;
let userAId: number;
let userBId: number;

beforeAll(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerWordsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();

  cookieA = await registerAndLogin(app, 'words_user_a');
  cookieB = await registerAndLogin(app, 'words_user_b');

  const a = db.prepare('SELECT id FROM users WHERE username = ?').get('words_user_a') as { id: number };
  const b = db.prepare('SELECT id FROM users WHERE username = ?').get('words_user_b') as { id: number };
  userAId = a.id;
  userBId = b.id;
});

afterAll(async () => {
  await app.close();
});

describe('多用户 words / srs 隔离', () => {
  it('用户 A 创建的单词不应出现在用户 B 的 GET /api/words', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: authHeaders(cookieA),
      payload: { word: 'alpha-only-a', meaning: '仅 A' },
    });
    expect(create.statusCode).toBe(201);

    const listB = await app.inject({
      method: 'GET',
      url: '/api/words',
      headers: authHeaders(cookieB),
    });
    expect(listB.statusCode).toBe(200);
    const wordsB = listB.json() as Array<{ word: string }>;
    expect(wordsB.find((w) => w.word === 'alpha-only-a')).toBeUndefined();

    const listA = await app.inject({
      method: 'GET',
      url: '/api/words',
      headers: authHeaders(cookieA),
    });
    const wordsA = listA.json() as Array<{ word: string }>;
    expect(wordsA.find((w) => w.word === 'alpha-only-a')).toBeDefined();
  });

  it('用户 B 不能通过 id 复核用户 A 的单词', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: authHeaders(cookieA),
      payload: { word: 'review-target-a', meaning: '仅 A' },
    });
    const created = create.json() as { id: number };

    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${created.id}/review`,
      headers: authHeaders(cookieB),
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(404);
  });

  it('用户 B 不能删除用户 A 的单词', async () => {
    const create = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: authHeaders(cookieA),
      payload: { word: 'delete-target-a', meaning: '仅 A' },
    });
    const created = create.json() as { id: number };

    const res = await app.inject({
      method: 'DELETE',
      url: `/api/words/${created.id}`,
      headers: authHeaders(cookieB),
    });
    expect(res.statusCode).toBe(404);

    const stillThere = db
      .prepare('SELECT id FROM words WHERE id = ? AND user_id = ?')
      .get(created.id, userAId) as { id: number } | undefined;
    expect(stillThere).toBeDefined();
  });

  it('seed-vocab 对同一用户幂等：第二次调用全部 skippedExisting，不新增', async () => {
    const first = await app.inject({
      method: 'POST',
      url: '/api/words/seed-vocab',
      headers: authHeaders(cookieA),
    });
    expect(first.statusCode).toBe(200);
    const r1 = first.json() as { imported: number; skippedExisting: number };
    expect(r1.imported).toBeGreaterThan(0);

    const second = await app.inject({
      method: 'POST',
      url: '/api/words/seed-vocab',
      headers: authHeaders(cookieA),
    });
    expect(second.statusCode).toBe(200);
    const r2 = second.json() as { imported: number; skippedExisting: number };
    expect(r2.imported).toBe(0);
    // 第二次全部跳过：skippedExisting == 首次 imported + 首次 skippedExisting（文件内去重也计入跳过）
    expect(r2.skippedExisting).toBe(r1.imported + r1.skippedExisting);
  });

  it('seed-vocab 按用户隔离：A 播种不影响 B 的 vocab-status', async () => {
    const beforeB = await app.inject({
      method: 'GET',
      url: '/api/words/vocab-status',
      headers: authHeaders(cookieB),
    });
    expect(beforeB.statusCode).toBe(200);
    const beforeBody = beforeB.json() as { total: number };

    // A 已经在前一个用例中播种过
    const aCount = db
      .prepare("SELECT COUNT(*) AS c FROM words WHERE user_id = ? AND source = 'core500'")
      .get(userAId) as { c: number };
    expect(aCount.c).toBeGreaterThan(0);

    const bCount = db
      .prepare("SELECT COUNT(*) AS c FROM words WHERE user_id = ? AND source = 'core500'")
      .get(userBId) as { c: number };
    expect(bCount.c).toBe(beforeBody.total);
  });

  it('用户 A 对单词 review 后，用户 B 的对应单词 SRS 不受影响（同名词独立）', async () => {
    const createA = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: authHeaders(cookieA),
      payload: { word: 'shared-word', meaning: 'A 的' },
    });
    const createB = await app.inject({
      method: 'POST',
      url: '/api/words',
      headers: authHeaders(cookieB),
      payload: { word: 'shared-word', meaning: 'B 的' },
    });
    expect(createA.statusCode).toBe(201);
    expect(createB.statusCode).toBe(201);
    const idA = (createA.json() as { id: number }).id;
    const idB = (createB.json() as { id: number }).id;
    expect(idA).not.toBe(idB);

    const reviewA = await app.inject({
      method: 'POST',
      url: `/api/words/${idA}/review`,
      headers: authHeaders(cookieA),
      payload: { grade: 2 },
    });
    expect(reviewA.statusCode).toBe(200);
    const reviewed = reviewA.json() as { state: { repetitions: number; dueDate: string } };
    expect(reviewed.state.repetitions).toBe(1);

    const listB = await app.inject({
      method: 'GET',
      url: '/api/words',
      headers: authHeaders(cookieB),
    });
    const wordsB = listB.json() as Array<{ id: number; word: string; state: { repetitions: number } }>;
    const bWord = wordsB.find((w) => w.id === idB);
    expect(bWord).toBeDefined();
    expect(bWord!.state.repetitions).toBe(0);
  });

  it('用户 A 导入的单词不进入 B 的 import 去重（B 可再次导入同名）', async () => {
    const payload = {
      words: [{ word: 'import-dup-test', meanings_zh: ['导入测试'] }],
      source: 'manual' as const,
    };
    const r1 = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      headers: authHeaders(cookieA),
      payload,
    });
    expect(r1.statusCode).toBe(200);
    expect((r1.json() as { imported: number }).imported).toBe(1);

    const r2 = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      headers: authHeaders(cookieB),
      payload,
    });
    expect(r2.statusCode).toBe(200);
    expect((r2.json() as { imported: number }).imported).toBe(1);
    expect((r2.json() as { skippedExisting: number }).skippedExisting).toBe(0);
  });
});
