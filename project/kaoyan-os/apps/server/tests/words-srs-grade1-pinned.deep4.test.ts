import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖点：grade=1 连续五次复习时 (repetitions, intervalDays, ease) 全程钉死为 intervalDays=1 的精确演化。
// 不与 words-srs-grade1-interval-pinned.deep2.test.ts 重叠（该文件仅覆盖前两次）。

describe('words SRS grade1 interval pinned deep4', () => {
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

  it('五次 grade=1 每一步 (repetitions, intervalDays, ease) 精确断言，intervalDays 全程为 1', async () => {
    const cookie = await registerAndLogin(app, rand('g1deep4a'));
    const id = await createWord(cookie, 'pinned_a');

    const expected = [
      { repetitions: 1, intervalDays: 1, ease: 2.45 },
      { repetitions: 2, intervalDays: 1, ease: 2.4 },
      { repetitions: 3, intervalDays: 1, ease: 2.35 },
      { repetitions: 4, intervalDays: 1, ease: 2.3 },
      { repetitions: 5, intervalDays: 1, ease: 2.25 },
    ];

    for (const step of expected) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: 1 },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as {
        state: { repetitions: number; intervalDays: number; ease: number };
      };
      expect(body.state.repetitions).toBe(step.repetitions);
      expect(body.state.intervalDays).toBe(step.intervalDays);
      expect(body.state.ease).toBeCloseTo(step.ease, 10);
    }

    const listRes = await app.inject({ method: 'GET', url: '/api/words', headers: { cookie } });
    expect(listRes.statusCode).toBe(200);
    const list = listRes.json() as Array<{
      id: number;
      state: { repetitions: number; intervalDays: number; ease: number };
    }>;
    const target = list.find((w) => w.id === id);
    expect(target).toBeDefined();
    expect(target!.state.repetitions).toBe(5);
    expect(target!.state.intervalDays).toBe(1);
    expect(target!.state.ease).toBeCloseTo(2.25, 10);
  });

  it('ease 精确序列 2.45, 2.4, 2.35, 2.3, 2.25（每次 -0.05，无钳制介入）', async () => {
    const cookie = await registerAndLogin(app, rand('g1deep4b'));
    const id = await createWord(cookie, 'pinned_b');

    const easeSequence = [2.45, 2.4, 2.35, 2.3, 2.25];
    const seen: number[] = [];

    for (let i = 0; i < easeSequence.length; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: 1 },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { ease: number } };
      seen.push(body.state.ease);
    }

    expect(seen.length).toBe(5);
    for (let i = 0; i < easeSequence.length; i += 1) {
      expect(seen[i]).toBeCloseTo(easeSequence[i], 10);
    }
    expect(seen[0]).toBeCloseTo(2.45, 10);
    expect(seen[1]).toBeCloseTo(2.4, 10);
    expect(seen[2]).toBeCloseTo(2.35, 10);
    expect(seen[3]).toBeCloseTo(2.3, 10);
    expect(seen[4]).toBeCloseTo(2.25, 10);
  });
});
