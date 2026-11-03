import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('isolation words due deep4', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  beforeEach(async () => {
    db = createDb(':memory:');
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

  it('B 的 due 列表只含 B1（A1 不可见），A 的 due 列表只含 A1（B1 不可见）', async () => {
    const cookieA = await registerAndLogin(app, rand('dueiso_a'));
    const cookieB = await registerAndLogin(app, rand('dueiso_b'));

    const idA1 = await createWord(cookieA, 'alpha_due_a1');
    const idB1 = await createWord(cookieB, 'beta_due_b1');

    const resB = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie: cookieB } });
    expect(resB.statusCode).toBe(200);
    const dueB = resB.json() as Array<{ id: number; word: string }>;
    expect(dueB.map((w) => w.id)).toEqual([idB1]);
    expect(dueB.some((w) => w.id === idA1)).toBe(false);

    const resA = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie: cookieA } });
    expect(resA.statusCode).toBe(200);
    const dueA = resA.json() as Array<{ id: number; word: string }>;
    expect(dueA.map((w) => w.id)).toEqual([idA1]);
    expect(dueA.some((w) => w.id === idB1)).toBe(false);
  });

  it('把 A1 的 due_date 改为 2999-01-01 后：A due 为空数组，B due 仍含 B1', async () => {
    const cookieA = await registerAndLogin(app, rand('dueiso2_a'));
    const cookieB = await registerAndLogin(app, rand('dueiso2_b'));

    const idA1 = await createWord(cookieA, 'alpha_due2_a1');
    const idB1 = await createWord(cookieB, 'beta_due2_b1');

    db.prepare("UPDATE srs_state SET due_date = '2999-01-01' WHERE word_id = ?").run(idA1);

    const resA = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie: cookieA } });
    expect(resA.statusCode).toBe(200);
    expect(resA.json()).toEqual([]);

    const resB = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie: cookieB } });
    expect(resB.statusCode).toBe(200);
    const dueB = resB.json() as Array<{ id: number }>;
    expect(dueB.map((w) => w.id)).toEqual([idB1]);
  });

  it('A1 改 due_date 后 A GET /api/words 仍能看到 A1（只是不在 due 里）', async () => {
    const cookieA = await registerAndLogin(app, rand('dueiso3_a'));
    const cookieB = await registerAndLogin(app, rand('dueiso3_b'));

    const idA1 = await createWord(cookieA, 'alpha_due3_a1');
    await createWord(cookieB, 'beta_due3_b1');

    db.prepare("UPDATE srs_state SET due_date = '2999-01-01' WHERE word_id = ?").run(idA1);

    const listA = await app.inject({ method: 'GET', url: '/api/words', headers: { cookie: cookieA } });
    expect(listA.statusCode).toBe(200);
    const wordsA = listA.json() as Array<{ id: number }>;
    expect(wordsA.map((w) => w.id)).toEqual([idA1]);

    const dueA = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie: cookieA } });
    expect(dueA.statusCode).toBe(200);
    expect(dueA.json()).toEqual([]);
  });
});
