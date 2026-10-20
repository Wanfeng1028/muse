import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('words SRS ease floor via grade1 deep4', () => {
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
  it('24 次 grade=1：每次 ease >= 1.3，末尾 Math.abs(ease-1.3) < 1e-9，repetitions=24，intervalDays=1', async () => {
    const cookie = await registerAndLogin(app, rand('g1a'));
    const id = await createWord(cookie, 'easefloor24');
    let ease = 2.5;
    for (let i = 0; i < 24; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: 1 },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { ease: number; repetitions: number; intervalDays: number } };
      ease = body.state.ease;
      expect(ease).toBeGreaterThanOrEqual(1.3);
    }
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 1 },
    });
    expect(res.statusCode).toBe(200);
    const finalBody = res.json() as { state: { ease: number; repetitions: number; intervalDays: number } };
    expect(finalBody.state.repetitions).toBe(25);
    expect(finalBody.state.intervalDays).toBe(1);
    const list = await app.inject({ method: 'GET', url: '/api/words', headers: { cookie } });
    expect(list.statusCode).toBe(200);
    const rows = list.json() as Array<{ id: number; state: { ease: number; repetitions: number; intervalDays: number } }>;
    const row = rows.find((r) => r.id === id);
    expect(row).toBeDefined();
    expect(Math.abs(row!.state.ease - 1.3)).toBeLessThan(1e-9);
    expect(row!.state.repetitions).toBe(25);
    expect(row!.state.intervalDays).toBe(1);
  });
  it('第 25 次 grade=1 后 ease 精确 === 1.3', async () => {
    const cookie = await registerAndLogin(app, rand('g1b'));
    const id = await createWord(cookie, 'easefloor25');
    for (let i = 0; i < 25; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: 1 },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { ease: number } };
      expect(body.state.ease).toBeGreaterThanOrEqual(1.3);
    }
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 1 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { state: { ease: number } };
    expect(body.state.ease).toBe(1.3);
  });
  it('继续到 30 次：ease 恒 === 1.3，repetitions=30', async () => {
    const cookie = await registerAndLogin(app, rand('g1c'));
    const id = await createWord(cookie, 'easefloor30');
    for (let i = 0; i < 30; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: 1 },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { ease: number } };
      if (i >= 24) {
        expect(body.state.ease).toBe(1.3);
      }
      expect(body.state.ease).toBeGreaterThanOrEqual(1.3);
    }
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade: 1 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { state: { ease: number; repetitions: number } };
    expect(body.state.ease).toBe(1.3);
    expect(body.state.repetitions).toBe(31);
  });
});
