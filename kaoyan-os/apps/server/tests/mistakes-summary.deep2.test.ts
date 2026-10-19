import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

function insertMistakeFor(
  db: DatabaseSync,
  username: string,
  subject: string,
  mastered: number,
): void {
  db.prepare(
    "INSERT INTO mistakes (user_id, subject, title, mastered) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
  ).run(username, subject, `t-${subject}-${mastered}-${Math.random()}`, mastered);
}

describe('GET /api/mistakes/summary 深度边界', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let authCookie: string;

  beforeEach(async () => {
    db = createRealDb(':memory:');
    app = Fastify();
    registerMistakesRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'summarydeep');
  });

  afterAll(async () => {
    if (app) {
      await app.close();
    }
  });

  it('全部掌握时 masteredRate 正好是 1', async () => {
    insertMistakeFor(db, 'summarydeep', 'math', 1);
    insertMistakeFor(db, 'summarydeep', 'english', 1);
    insertMistakeFor(db, 'summarydeep', 'politics', 1);
    insertMistakeFor(db, 'summarydeep', 'major', 1);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subject: null,
      total: 4,
      mastered: 4,
      unmastered: 0,
      masteredRate: 1,
    });
  });

  it('全部没掌握时 masteredRate 是 0', async () => {
    insertMistakeFor(db, 'summarydeep', 'math', 0);
    insertMistakeFor(db, 'summarydeep', 'english', 0);
    insertMistakeFor(db, 'summarydeep', 'politics', 0);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      subject: null,
      total: 3,
      mastered: 0,
      unmastered: 3,
      masteredRate: 0,
    });
  });

  it('1/6 四舍五入到 0.1667', async () => {
    insertMistakeFor(db, 'summarydeep', 'math', 1);
    insertMistakeFor(db, 'summarydeep', 'math', 0);
    insertMistakeFor(db, 'summarydeep', 'math', 0);
    insertMistakeFor(db, 'summarydeep', 'math', 0);
    insertMistakeFor(db, 'summarydeep', 'math', 0);
    insertMistakeFor(db, 'summarydeep', 'math', 0);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { total: number; mastered: number; unmastered: number; masteredRate: number };
    expect(body.total).toBe(6);
    expect(body.mastered).toBe(1);
    expect(body.unmastered).toBe(5);
    expect(body.masteredRate).toBe(0.1667);
  });

  it('2/3 四舍五入到 0.6667', async () => {
    insertMistakeFor(db, 'summarydeep', 'math', 1);
    insertMistakeFor(db, 'summarydeep', 'math', 1);
    insertMistakeFor(db, 'summarydeep', 'math', 0);

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { total: number; mastered: number; unmastered: number; masteredRate: number };
    expect(body.total).toBe(3);
    expect(body.mastered).toBe(2);
    expect(body.unmastered).toBe(1);
    expect(body.masteredRate).toBe(0.6667);
  });

  it('1/32 的 312.5 半数向上进位到 0.0313', async () => {
    for (let i = 0; i < 32; i += 1) {
      insertMistakeFor(db, 'summarydeep', 'english', i === 0 ? 1 : 0);
    }

    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { total: number; mastered: number; unmastered: number; masteredRate: number };
    expect(body.total).toBe(32);
    expect(body.mastered).toBe(1);
    expect(body.unmastered).toBe(31);
    expect(body.masteredRate).toBe(0.0313);
  });

  it('subject 传空字符串返回 400 且错误文案精确匹配', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary?subject=',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '无效的 subject 参数' });
  });

  it('四个科目分别过滤后 total/mastered 之和等于不过滤的总量，且 subject 回显正确', async () => {
    insertMistakeFor(db, 'summarydeep', 'math', 1);
    insertMistakeFor(db, 'summarydeep', 'math', 0);
    insertMistakeFor(db, 'summarydeep', 'english', 1);
    insertMistakeFor(db, 'summarydeep', 'english', 1);
    insertMistakeFor(db, 'summarydeep', 'english', 0);
    insertMistakeFor(db, 'summarydeep', 'politics', 0);
    insertMistakeFor(db, 'summarydeep', 'major', 1);
    insertMistakeFor(db, 'summarydeep', 'major', 1);
    insertMistakeFor(db, 'summarydeep', 'major', 1);
    insertMistakeFor(db, 'summarydeep', 'major', 0);

    const allRes = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(allRes.statusCode).toBe(200);
    const allBody = allRes.json() as { total: number; mastered: number };

    const subjects = ['math', 'english', 'politics', 'major'] as const;
    let sumTotal = 0;
    let sumMastered = 0;
    for (const subject of subjects) {
      const res = await app.inject({
        method: 'GET',
        url: `/api/mistakes/summary?subject=${subject}`,
        headers: { cookie: authCookie },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as {
        subject: string | null;
        total: number;
        mastered: number;
        unmastered: number;
        masteredRate: number;
      };
      expect(body.subject).toBe(subject);
      sumTotal += body.total;
      sumMastered += body.mastered;
    }
    expect(sumTotal).toBe(allBody.total);
    expect(sumMastered).toBe(allBody.mastered);
  });

  it('一个用户的错题不会影响另一个用户的 summary', async () => {
    insertMistakeFor(db, 'summarydeep', 'math', 1);
    insertMistakeFor(db, 'summarydeep', 'math', 0);
    insertMistakeFor(db, 'summarydeep', 'english', 0);

    const cookieB = await registerAndLogin(app, 'summarydeepb');
    insertMistakeFor(db, 'summarydeepb', 'math', 1);
    insertMistakeFor(db, 'summarydeepb', 'math', 1);

    const resA = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: authCookie },
    });
    expect(resA.statusCode).toBe(200);
    expect(resA.json()).toEqual({
      subject: null,
      total: 3,
      mastered: 1,
      unmastered: 2,
      masteredRate: 0.3333,
    });

    const resB = await app.inject({
      method: 'GET',
      url: '/api/mistakes/summary',
      headers: { cookie: cookieB },
    });
    expect(resB.statusCode).toBe(200);
    expect(resB.json()).toEqual({
      subject: null,
      total: 2,
      mastered: 2,
      unmastered: 0,
      masteredRate: 1,
    });
  });
});
