import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖 words 路由 SRS ease 下钳 1.3 后经 grade=2 回升至 2.5 上钳的精确浮点路径；不与 words-srs-ease-ceiling deep2 的 20 轮上钳与低位回升重叠
describe('words SRS ease ceiling recovery deep4', () => {
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

  it('连续 6 次 grade=0 时 ease 精确落到 1.3，repetitions 恒 0、intervalDays 恒 1', async () => {
    const cookie = await registerAndLogin(app, rand('ease_zero'));
    const id = await createWord(cookie, rand('w0'));
    const expectedEase = [2.3, 2.1, 1.9, 1.7, 1.5, 1.3];
    for (let i = 0; i < 6; i += 1) {
      const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 0 } });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { ease: number; intervalDays: number; repetitions: number } };
      // 浮点链：2.3-0.2=2.0999999999999996，用近似断言。
      expect(body.state.ease).toBeCloseTo(expectedEase[i], 12);
      expect(body.state.repetitions).toBe(0);
      expect(body.state.intervalDays).toBe(1);
    }
  });

  it('从 1.3 起连续 24 次 grade=2 时 ease 恒不超过 2.5，且第 24 次后逼近 2.5', async () => {
    const cookie = await registerAndLogin(app, rand('ease_up'));
    const id = await createWord(cookie, rand('w1'));
    for (let i = 0; i < 6; i += 1) {
      const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 0 } });
      expect(res.statusCode).toBe(200);
    }
    let lastEase = 0;
    for (let i = 0; i < 24; i += 1) {
      const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { ease: number } };
      expect(body.state.ease).toBeLessThanOrEqual(2.5);
      lastEase = body.state.ease;
    }
    expect(Math.abs(lastEase - 2.5)).toBeLessThan(1e-9);
  });

  it('第 25 次 grade=2 后 ease 精确等于 2.5，续到 30 次仍恒为 2.5', async () => {
    const cookie = await registerAndLogin(app, rand('ease_clamp'));
    const id = await createWord(cookie, rand('w2'));
    for (let i = 0; i < 6; i += 1) {
      const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 0 } });
      expect(res.statusCode).toBe(200);
    }
    for (let i = 0; i < 24; i += 1) {
      const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
      expect(res.statusCode).toBe(200);
    }
    const res25 = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
    expect(res25.statusCode).toBe(200);
    const body25 = res25.json() as { state: { ease: number } };
    expect(body25.state.ease).toBe(2.5);
    for (let i = 26; i <= 30; i += 1) {
      const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 2 } });
      expect(res.statusCode).toBe(200);
      const body = res.json() as { state: { ease: number } };
      expect(body.state.ease).toBe(2.5);
    }
  });
});
