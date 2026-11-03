import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb, todayStr, addDays } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('words SRS multi word independence deep4', () => {
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

  it('三词分别 grade=2/0/1 后各自 state 精确且互不污染', async () => {
    const cookie = await registerAndLogin(app, rand('mwi'));
    const suffix = rand('w');
    const w1 = await createWord(cookie, `w1_${suffix}`);
    const w2 = await createWord(cookie, `w2_${suffix}`);
    const w3 = await createWord(cookie, `w3_${suffix}`);

    const r1 = await app.inject({ method: 'POST', url: `/api/words/${w1}/review`, headers: { cookie }, payload: { grade: 2 } });
    expect(r1.statusCode).toBe(200);
    const b1 = r1.json() as { id: number; state: { wordId: number; ease: number; intervalDays: number; repetitions: number; dueDate: string } };
    expect(b1.id).toBe(w1);
    expect(b1.state.wordId).toBe(w1);
    expect(b1.state.ease).toBe(2.5);
    expect(b1.state.intervalDays).toBe(1);
    expect(b1.state.repetitions).toBe(1);
    expect(b1.state.dueDate).toBe(addDays(todayStr(), 1));

    const r2 = await app.inject({ method: 'POST', url: `/api/words/${w2}/review`, headers: { cookie }, payload: { grade: 0 } });
    expect(r2.statusCode).toBe(200);
    const b2 = r2.json() as { id: number; state: { wordId: number; ease: number; intervalDays: number; repetitions: number; dueDate: string } };
    expect(b2.id).toBe(w2);
    expect(b2.state.wordId).toBe(w2);
    expect(b2.state.ease).toBe(2.3);
    expect(b2.state.intervalDays).toBe(1);
    expect(b2.state.repetitions).toBe(0);
    expect(b2.state.dueDate).toBe(addDays(todayStr(), 1));

    const r3 = await app.inject({ method: 'POST', url: `/api/words/${w3}/review`, headers: { cookie }, payload: { grade: 1 } });
    expect(r3.statusCode).toBe(200);
    const b3 = r3.json() as { id: number; state: { wordId: number; ease: number; intervalDays: number; repetitions: number; dueDate: string } };
    expect(b3.id).toBe(w3);
    expect(b3.state.wordId).toBe(w3);
    expect(b3.state.ease).toBe(2.45);
    expect(b3.state.intervalDays).toBe(1);
    expect(b3.state.repetitions).toBe(1);
    expect(b3.state.dueDate).toBe(addDays(todayStr(), 1));

    const r1b = await app.inject({ method: 'POST', url: `/api/words/${w1}/review`, headers: { cookie }, payload: { grade: 2 } });
    expect(r1b.statusCode).toBe(200);
    const b1b = r1b.json() as { state: { ease: number; intervalDays: number; repetitions: number } };
    expect(b1b.state.repetitions).toBe(2);
    expect(b1b.state.ease).toBe(2.5);
    expect(b1b.state.intervalDays).toBe(3);
  });

  it('GET /api/words 返回 3 条按 word 找到各自条目 state 与单独 review 一致', async () => {
    const cookie = await registerAndLogin(app, rand('mwi'));
    const suffix = rand('w');
    const word1 = `w1_${suffix}`;
    const word2 = `w2_${suffix}`;
    const word3 = `w3_${suffix}`;
    const w1 = await createWord(cookie, word1);
    const w2 = await createWord(cookie, word2);
    const w3 = await createWord(cookie, word3);

    await app.inject({ method: 'POST', url: `/api/words/${w1}/review`, headers: { cookie }, payload: { grade: 2 } });
    await app.inject({ method: 'POST', url: `/api/words/${w2}/review`, headers: { cookie }, payload: { grade: 0 } });
    await app.inject({ method: 'POST', url: `/api/words/${w3}/review`, headers: { cookie }, payload: { grade: 1 } });

    const list = await app.inject({ method: 'GET', url: '/api/words', headers: { cookie } });
    expect(list.statusCode).toBe(200);
    const rows = list.json() as Array<{ id: number; word: string; state: { wordId: number; ease: number; intervalDays: number; repetitions: number; dueDate: string } }>;
    expect(rows.length).toBe(3);

    const byWord = new Map(rows.map((r) => [r.word, r]));
    const e1 = byWord.get(word1);
    const e2 = byWord.get(word2);
    const e3 = byWord.get(word3);
    expect(e1).toBeDefined();
    expect(e2).toBeDefined();
    expect(e3).toBeDefined();

    expect(e1!.id).toBe(w1);
    expect(e1!.state.wordId).toBe(w1);
    expect(e1!.state.ease).toBe(2.5);
    expect(e1!.state.intervalDays).toBe(1);
    expect(e1!.state.repetitions).toBe(1);
    expect(e1!.state.dueDate).toBe(addDays(todayStr(), 1));

    expect(e2!.id).toBe(w2);
    expect(e2!.state.wordId).toBe(w2);
    expect(e2!.state.ease).toBe(2.3);
    expect(e2!.state.intervalDays).toBe(1);
    expect(e2!.state.repetitions).toBe(0);
    expect(e2!.state.dueDate).toBe(addDays(todayStr(), 1));

    expect(e3!.id).toBe(w3);
    expect(e3!.state.wordId).toBe(w3);
    expect(e3!.state.ease).toBe(2.45);
    expect(e3!.state.intervalDays).toBe(1);
    expect(e3!.state.repetitions).toBe(1);
    expect(e3!.state.dueDate).toBe(addDays(todayStr(), 1));
  });
});
