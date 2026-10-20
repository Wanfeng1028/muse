import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 覆盖点：七步复习序列 [2,2,2,0,1,2,2] 的 SRS 状态精确推演，含中段 grade=1 与重置点验证。
// 不与 words-srs-reset-chain-deep2 短重置链文件重叠（本文件为七步长链且含 grade=1 中段）。
describe('words SRS long reset chain deep4', () => {
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

  async function review(cookie: string, id: number, grade: number) {
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      headers: { cookie },
      payload: { grade },
    });
    expect(res.statusCode).toBe(200);
    return res.json() as {
      id: number;
      state: { repetitions: number; intervalDays: number; ease: number; dueDate: string };
    };
  }

  it('七步序列 [2,2,2,0,1,2,2] 每一步 repetitions/intervalDays/ease 精确', async () => {
    const cookie = await registerAndLogin(app, rand('srs_chain7'));
    const id = await createWord(cookie, rand('w_chain7'));

    const s1 = await review(cookie, id, 2);
    expect(s1.state.repetitions).toBe(1);
    expect(s1.state.intervalDays).toBe(1);
    expect(s1.state.ease).toBe(2.5);

    const s2 = await review(cookie, id, 2);
    expect(s2.state.repetitions).toBe(2);
    expect(s2.state.intervalDays).toBe(3);
    expect(s2.state.ease).toBe(2.5);

    const s3 = await review(cookie, id, 2);
    expect(s3.state.repetitions).toBe(3);
    expect(s3.state.intervalDays).toBe(8);
    expect(s3.state.ease).toBe(2.5);

    const s4 = await review(cookie, id, 0);
    expect(s4.state.repetitions).toBe(0);
    expect(s4.state.intervalDays).toBe(1);
    expect(s4.state.ease).toBe(2.3);

    const s5 = await review(cookie, id, 1);
    expect(s5.state.repetitions).toBe(1);
    expect(s5.state.intervalDays).toBe(1);
    expect(s5.state.ease).toBe(2.25);

    const s6 = await review(cookie, id, 2);
    expect(s6.state.repetitions).toBe(2);
    expect(s6.state.intervalDays).toBe(3);
    expect(s6.state.ease).toBe(2.3);

    const s7 = await review(cookie, id, 2);
    expect(s7.state.repetitions).toBe(3);
    expect(s7.state.intervalDays).toBe(7);
    // 真实浮点值 2.3499999999999996，见 toBeCloseTo。
    expect(s7.state.ease).toBeCloseTo(2.35, 12);
  });

  it('重置点：grade=0 后 repetitions=0 且 intervalDays=1；随后 grade=1 仍 intervalDays=1', async () => {
    const cookie = await registerAndLogin(app, rand('srs_reset7'));
    const id = await createWord(cookie, rand('w_reset7'));

    const a = await review(cookie, id, 2);
    expect(a.state.repetitions).toBe(1);
    expect(a.state.intervalDays).toBe(1);
    expect(a.state.ease).toBe(2.5);

    const b = await review(cookie, id, 2);
    expect(b.state.repetitions).toBe(2);
    expect(b.state.intervalDays).toBe(3);
    expect(b.state.ease).toBe(2.5);

    const c = await review(cookie, id, 2);
    expect(c.state.repetitions).toBe(3);
    expect(c.state.intervalDays).toBe(8);
    expect(c.state.ease).toBe(2.5);

    const d = await review(cookie, id, 0);
    expect(d.state.repetitions).toBe(0);
    expect(d.state.intervalDays).toBe(1);
    expect(d.state.ease).toBe(2.3);

    const e = await review(cookie, id, 1);
    expect(e.state.repetitions).toBe(1);
    expect(e.state.intervalDays).toBe(1);
    expect(e.state.ease).toBe(2.25);
  });
});
