import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb, todayStr, addDays } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('words SRS deep5', () => {
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
  async function reviewOk(cookie: string, id: number, grade: number): Promise<any> {
    const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade } });
    expect(res.statusCode).toBe(200);
    return res.json();
  }

  it('grade=3 越界整数返回 400 且文案为 grade 必须为 0|1|2', async () => {
    const cookie = await registerAndLogin(app, rand('d5g3'));
    const id = await createWord(cookie, rand('w'));
    const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 3 } });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'grade 必须为 0|1|2' });
  });

  it('grade=-1 负数返回 400', async () => {
    const cookie = await registerAndLogin(app, rand('d5gneg'));
    const id = await createWord(cookie, rand('w'));
    const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: -1 } });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'grade 必须为 0|1|2' });
  });

  it("grade='2' 字符串返回 400", async () => {
    const cookie = await registerAndLogin(app, rand('d5gstr'));
    const id = await createWord(cookie, rand('w'));
    const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: '2' } });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'grade 必须为 0|1|2' });
  });

  it('grade=1.5 小数返回 400', async () => {
    const cookie = await registerAndLogin(app, rand('d5gfrac'));
    const id = await createWord(cookie, rand('w'));
    const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade: 1.5 } });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'grade 必须为 0|1|2' });
  });

  it('grade=2 八步长链 interval 序列精确为 1,3,8,20,50,125,313,783', async () => {
    const cookie = await registerAndLogin(app, rand('d5chain'));
    const id = await createWord(cookie, rand('w'));
    const expected = [1, 3, 8, 20, 50, 125, 313, 783];
    let lastBody: any;
    for (let i = 0; i < 8; i++) {
      lastBody = await reviewOk(cookie, id, 2);
      expect(lastBody.state.repetitions).toBe(i + 1);
      expect(lastBody.state.intervalDays).toBe(expected[i]);
      expect(lastBody.state.ease).toBe(2.5);
      expect(lastBody.state.dueDate).toBe(addDays(todayStr(), expected[i]));
    }
    expect(lastBody.state.dueDate).toBe(addDays(todayStr(), 783));
  });

  it('混合序列 [2,2,2,1,1,0] 每一步精确追踪', async () => {
    const cookie = await registerAndLogin(app, rand('d5mix'));
    const id = await createWord(cookie, rand('w'));
    const expected = [
      { repetitions: 1, intervalDays: 1, ease: 2.5 },
      { repetitions: 2, intervalDays: 3, ease: 2.5 },
      { repetitions: 3, intervalDays: 8, ease: 2.5 },
      { repetitions: 4, intervalDays: 10, ease: 2.45 },
      { repetitions: 5, intervalDays: 12, ease: 2.4 },
      { repetitions: 0, intervalDays: 1, ease: 2.2 },
    ];
    const grades = [2, 2, 2, 1, 1, 0];
    for (let i = 0; i < grades.length; i++) {
      const body = await reviewOk(cookie, id, grades[i]);
      expect(body.state.repetitions).toBe(expected[i].repetitions);
      expect(body.state.intervalDays).toBe(expected[i].intervalDays);
      expect(body.state.ease).toBeCloseTo(expected[i].ease, 12);
    }
  });

  it('ease 下限组合：6 次 grade0 钉住 1.3、grade2 反弹、grade0 再钉回', async () => {
    const cookie = await registerAndLogin(app, rand('d5floor'));
    const id = await createWord(cookie, rand('w'));
    const zeroEase = [2.3, 2.1, 1.9, 1.7, 1.5, 1.3];
    for (let i = 0; i < 6; i++) {
      const body = await reviewOk(cookie, id, 0);
      expect(body.state.ease).toBeCloseTo(zeroEase[i], 12);
      expect(body.state.repetitions).toBe(0);
      expect(body.state.intervalDays).toBe(1);
    }
    const body7 = await reviewOk(cookie, id, 2);
    expect(body7.state.ease).toBeCloseTo(1.35, 12);
    expect(body7.state.repetitions).toBe(1);
    expect(body7.state.intervalDays).toBe(1);
    const body8 = await reviewOk(cookie, id, 0);
    expect(body8.state.ease).toBe(1.3);
    expect(body8.state.repetitions).toBe(0);
    expect(body8.state.intervalDays).toBe(1);
  });

  it('同天到期多词 due 列表按 id 升序', async () => {
    const cookie = await registerAndLogin(app, rand('d5due'));
    const id1 = await createWord(cookie, rand('w'));
    const id2 = await createWord(cookie, rand('w'));
    const id3 = await createWord(cookie, rand('w'));
    const res = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie } });
    expect(res.statusCode).toBe(200);
    const ids = (res.json() as Array<{ id: number }>).map((w) => w.id);
    expect(ids).toEqual([id1, id2, id3]);
  });

  it('混合队列：A 三次 grade2 退出队列，B 一次 grade0 明天回来，C 未复习留在队列', async () => {
    const cookie = await registerAndLogin(app, rand('d5queue'));
    const idA = await createWord(cookie, rand('w'));
    const idB = await createWord(cookie, rand('w'));
    const idC = await createWord(cookie, rand('w'));
    let bodyA: any;
    for (let i = 0; i < 3; i++) {
      bodyA = await reviewOk(cookie, idA, 2);
    }
    expect(bodyA.state.intervalDays).toBe(8);
    const bodyB = await reviewOk(cookie, idB, 0);
    expect(bodyB.state.dueDate).toBe(addDays(todayStr(), 1));
    const dueRes = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie } });
    expect(dueRes.statusCode).toBe(200);
    const dueIds = (dueRes.json() as Array<{ id: number }>).map((w) => w.id);
    expect(dueIds).toEqual([idC]);
    const listRes = await app.inject({ method: 'GET', url: '/api/words', headers: { cookie } });
    expect(listRes.statusCode).toBe(200);
    const words = listRes.json() as Array<{ id: number; state: { dueDate: string } }>;
    const a = words.find((w) => w.id === idA);
    const b = words.find((w) => w.id === idB);
    const c = words.find((w) => w.id === idC);
    expect(a?.state.dueDate).toBe(addDays(todayStr(), 8));
    expect(b?.state.dueDate).toBe(addDays(todayStr(), 1));
    expect(c?.state.dueDate).toBe(todayStr());
  });

  it('due 条目 state 字段完整且与 /api/words 一致', async () => {
    const cookie = await registerAndLogin(app, rand('d5state'));
    const id = await createWord(cookie, rand('w'));
    const dueRes = await app.inject({ method: 'GET', url: '/api/words/due', headers: { cookie } });
    expect(dueRes.statusCode).toBe(200);
    const dueEntry = (dueRes.json() as Array<{ id: number; state: any }>)[0];
    expect(dueEntry.state.wordId).toBe(id);
    expect(dueEntry.state.ease).toBe(2.5);
    expect(dueEntry.state.intervalDays).toBe(0);
    expect(dueEntry.state.repetitions).toBe(0);
    expect(dueEntry.state.dueDate).toBe(todayStr());
    const listRes = await app.inject({ method: 'GET', url: '/api/words', headers: { cookie } });
    expect(listRes.statusCode).toBe(200);
    const listEntry = (listRes.json() as Array<{ id: number; state: any }>).find((w) => w.id === id);
    expect(listEntry?.state).toEqual(dueEntry.state);
  });
});