import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('words SRS ease pingpong deep4', () => {
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

  it('ease 在 [1,2,1,2] 四步中精确为 2.45, 2.5, 2.45, 2.5', async () => {
    const cookie = await registerAndLogin(app, rand('easeping'));
    const id = await createWord(cookie, rand('word'));
    const grades = [1, 2, 1, 2] as const;
    const expectedEase = [2.45, 2.5, 2.45, 2.5];
    for (let i = 0; i < grades.length; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: grades[i] },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { ease: number } };
      expect(body.state.ease === expectedEase[i]).toBe(true);
    }
  });

  it('repetitions 与 intervalDays 在 [1,2,1,2] 四步中精确为 (1,1),(2,3),(3,4),(4,10)', async () => {
    const cookie = await registerAndLogin(app, rand('repping'));
    const id = await createWord(cookie, rand('word'));
    const grades = [1, 2, 1, 2] as const;
    const expectedReps = [1, 2, 3, 4];
    const expectedInterval = [1, 3, 4, 10];
    for (let i = 0; i < grades.length; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        headers: { cookie },
        payload: { grade: grades[i] },
      });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { repetitions: number; intervalDays: number } };
      expect(body.state.repetitions).toBe(expectedReps[i]);
      expect(body.state.intervalDays).toBe(expectedInterval[i]);
    }
  });
});
