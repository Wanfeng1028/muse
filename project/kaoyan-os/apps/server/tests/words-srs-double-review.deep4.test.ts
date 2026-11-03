import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖点：同一单词在同一天内连续多次 review（grade=2 累积、随后 grade=0 重置），验证 review 接口无每日一次限制。
// 不与 words-srs-review*.test.ts 重叠（后者覆盖单次复习/非法入参/越权，无同日多次累积链）。

describe('words SRS double review same day deep4', () => {
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

  it('连续三次 grade=2 同日累积，repetitions 与 intervalDays 逐次推进', async () => {
    const cookie = await registerAndLogin(app, rand('dbl2'));
    const id = await createWord(cookie, 'accumulate');

    const first = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
    expect(first.statusCode).toBe(200);
    const firstBody = first.json() as { state: { repetitions: number; intervalDays: number; ease: number } };
    expect(firstBody.state.repetitions).toBe(1);
    expect(firstBody.state.intervalDays).toBe(1);
    expect(firstBody.state.ease).toBe(2.5);

    const second = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
    expect(second.statusCode).toBe(200);
    const secondBody = second.json() as { state: { repetitions: number; intervalDays: number; ease: number } };
    expect(secondBody.state.repetitions).toBe(2);
    expect(secondBody.state.intervalDays).toBe(3);
    expect(secondBody.state.ease).toBe(2.5);

    const third = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
    expect(third.statusCode).toBe(200);
    const thirdBody = third.json() as { state: { repetitions: number; intervalDays: number; ease: number } };
    expect(thirdBody.state.repetitions).toBe(3);
    expect(thirdBody.state.intervalDays).toBe(8);
    expect(thirdBody.state.ease).toBe(2.5);
  });

  it('多次 grade=2 后紧接一次 grade=0，重置链依旧生效', async () => {
    const cookie = await registerAndLogin(app, rand('dbl0'));
    const id = await createWord(cookie, 'reset');

    await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
    await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
    const third = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
    expect(third.statusCode).toBe(200);
    const thirdBody = third.json() as { state: { repetitions: number; intervalDays: number; ease: number } };
    expect(thirdBody.state.repetitions).toBe(3);
    expect(thirdBody.state.intervalDays).toBe(8);
    expect(thirdBody.state.ease).toBe(2.5);

    const reset = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 0 } });
    expect(reset.statusCode).toBe(200);
    const resetBody = reset.json() as { state: { repetitions: number; intervalDays: number; ease: number } };
    expect(resetBody.state.repetitions).toBe(0);
    expect(resetBody.state.intervalDays).toBe(1);
    expect(resetBody.state.ease).toBe(2.3);
  });
});
