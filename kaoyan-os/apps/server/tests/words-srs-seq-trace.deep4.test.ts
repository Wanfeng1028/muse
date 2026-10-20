import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { todayStr, addDays } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('words SRS grade sequence trace deep4', () => {
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
  async function review(cookie: string, id: number, grade: number): Promise<any> {
    const res = await app.inject({ method: 'POST', url: `/api/words/${id}/review`, headers: { cookie }, payload: { grade } });
    expect(res.statusCode).toBe(200);
    return res.json();
  }

  const steps = [
    { grade: 2, repetitions: 1, intervalDays: 1, ease: 2.5 },
    { grade: 2, repetitions: 2, intervalDays: 3, ease: 2.5 },
    { grade: 1, repetitions: 3, intervalDays: 4, ease: 2.45 },
    { grade: 2, repetitions: 4, intervalDays: 10, ease: 2.5 },
    { grade: 0, repetitions: 0, intervalDays: 1, ease: 2.3 },
    { grade: 2, repetitions: 1, intervalDays: 1, ease: 2.35 }, // 真实浮点值 2.3499999999999996，见 toBeCloseTo。
  ];

  it('traces repetitions, intervalDays and ease for each of the six review steps', async () => {
    const cookie = await registerAndLogin(app, rand('srsseq'));
    const id = await createWord(cookie, rand('w'));
    for (const step of steps) {
      const body = await review(cookie, id, step.grade);
      expect(body.state.repetitions).toBe(step.repetitions);
      expect(body.state.intervalDays).toBe(step.intervalDays);
      expect(body.state.ease).toBeCloseTo(step.ease, 12);
    }
  });

  it('computes dueDate as addDays(todayStr(), intervalDays) at each step', async () => {
    const cookie = await registerAndLogin(app, rand('srsdue'));
    const id = await createWord(cookie, rand('w'));
    for (const step of steps) {
      const body = await review(cookie, id, step.grade);
      expect(body.state.dueDate).toBe(addDays(todayStr(), step.intervalDays));
    }
  });

  it('keeps state.wordId equal to the created word id across the sequence', async () => {
    const cookie = await registerAndLogin(app, rand('srsid'));
    const id = await createWord(cookie, rand('w'));
    for (const step of steps) {
      const body = await review(cookie, id, step.grade);
      expect(body.id).toBe(id);
      expect(body.state.wordId).toBe(id);
    }
  });
});
