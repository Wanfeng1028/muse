import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('words SRS review id formats deep4', () => {
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
  it('拒绝小数 id 并返回 id 无效', async () => {
    const cookie = await registerAndLogin(app, rand('idfrac'));
    await createWord(cookie, 'fracword');
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/1.5/review',
      headers: { cookie },
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'id 无效' });
  });
  it('拒绝零 id 并返回 id 无效', async () => {
    const cookie = await registerAndLogin(app, rand('idzero'));
    await createWord(cookie, 'zeroword');
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/0/review',
      headers: { cookie },
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'id 无效' });
  });
  it('拒绝负数 id 并返回 id 无效', async () => {
    const cookie = await registerAndLogin(app, rand('idneg'));
    await createWord(cookie, 'negword');
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/-3/review',
      headers: { cookie },
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'id 无效' });
  });
  it('拒绝非数字 id 并返回 id 无效', async () => {
    const cookie = await registerAndLogin(app, rand('idnan'));
    await createWord(cookie, 'nanword');
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/abc/review',
      headers: { cookie },
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'id 无效' });
  });
  it('合法正整数但不存在时返回 404 单词不存在', async () => {
    const cookie = await registerAndLogin(app, rand('idmiss'));
    await createWord(cookie, 'missword');
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/999999999/review',
      headers: { cookie },
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(404);
    expect(res.json()).toEqual({ error: '单词不存在' });
  });
});
