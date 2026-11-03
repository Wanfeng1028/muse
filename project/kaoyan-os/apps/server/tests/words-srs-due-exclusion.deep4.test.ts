import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb, todayStr, addDays } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('words SRS due exclusion deep4', () => {
  let app: FastifyInstance;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerWordsRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });
  async function createWord(cookie: string, word: string): Promise<number> {
    const res = await app.inject({ method: 'POST', url: '/api/words', headers: { cookie }, payload: { word, meaning: '义' } });
    expect(res.statusCode).toBe(201);
    return (res.json() as { id: number }).id;
  }

  it('新词 A 在 due 列表中，3 次 grade=2 后退出 due 列表', async () => {
    const cookie = await registerAndLogin(app, rand('due_a'));
    const aId = await createWord(cookie, rand('wordA'));

    const dueBefore = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie } });
    expect(dueBefore.statusCode).toBe(200);
    const beforeList = dueBefore.json() as Array<{ id: number }>;
    expect(beforeList.map((w) => w.id)).toContain(aId);

    for (let i = 0; i < 3; i += 1) {
      const review = await app.inject({
        method: 'POST',
        url: `/api/words/${aId}/review`,
        headers: { cookie },
        payload: { grade: 2 },
      });
      expect(review.statusCode).toBe(200);
      expect((review.json() as { state: { intervalDays: number } }).state.intervalDays).toBe(i === 0 ? 1 : i === 1 ? 3 : 8);
    }

    const dueAfter = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie } });
    expect(dueAfter.statusCode).toBe(200);
    const afterList = dueAfter.json() as Array<{ id: number }>;
    expect(afterList.map((w) => w.id)).not.toContain(aId);
  });

  it('未复习的新词 B 始终在 due 列表中', async () => {
    const cookie = await registerAndLogin(app, rand('due_b'));
    const aId = await createWord(cookie, rand('wordA'));
    const bId = await createWord(cookie, rand('wordB'));

    for (let i = 0; i < 3; i += 1) {
      const review = await app.inject({
        method: 'POST',
        url: `/api/words/${aId}/review`,
        headers: { cookie },
        payload: { grade: 2 },
      });
      expect(review.statusCode).toBe(200);
    }

    const dueRes = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie } });
    expect(dueRes.statusCode).toBe(200);
    const ids = (dueRes.json() as Array<{ id: number }>).map((w) => w.id);
    expect(ids).toContain(bId);
    expect(ids).not.toContain(aId);
  });

  it('A 复习 3 次 grade=2 后 state.dueDate 等于 addDays(todayStr(), 8)', async () => {
    const cookie = await registerAndLogin(app, rand('due_c'));
    const aId = await createWord(cookie, rand('wordA'));

    let last: { state: { intervalDays: number; dueDate: string } } | null = null;
    for (let i = 0; i < 3; i += 1) {
      const review = await app.inject({
        method: 'POST',
        url: `/api/words/${aId}/review`,
        headers: { cookie },
        payload: { grade: 2 },
      });
      expect(review.statusCode).toBe(200);
      last = review.json() as { state: { intervalDays: number; dueDate: string } };
    }
    expect(last!.state.intervalDays).toBe(8);
    expect(last!.state.dueDate).toBe(addDays(todayStr(), 8));

    const allRes = await app.inject({ method: 'GET', url: '/api/words', headers: { cookie } });
    expect(allRes.statusCode).toBe(200);
    const found = (allRes.json() as Array<{ id: number; state: { dueDate: string } }>).find((w) => w.id === aId);
    expect(found).toBeDefined();
    expect(found!.state.dueDate).toBe(addDays(todayStr(), 8));
  });
});
