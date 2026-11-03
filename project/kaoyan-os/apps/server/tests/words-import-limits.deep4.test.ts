import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

// 本文件覆盖 POST /api/words/import 的 2000 精确上限与 errors.length<50 截断行为；
// 不与 words-import.test.ts 重叠（后者覆盖 2001→400、批次内重复、非法项计数）。

describe('words import limits deep4', () => {
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

  it('接受 2000 个合法词并全部导入', async () => {
    const cookie = await registerAndLogin(app, rand('lim2000'));
    const words = [];
    for (let i = 0; i < 2000; i += 1) {
      words.push({ word: `lim${i}`, meanings_zh: ['义'] });
    }
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      headers: { cookie },
      payload: { words },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      imported: number;
      skippedExisting: number;
      skippedInvalid: number;
      errors: Array<{ index: number; message: string }>;
    };
    expect(body.imported).toBe(2000);
    expect(body.skippedExisting).toBe(0);
    expect(body.skippedInvalid).toBe(0);
    expect(body.errors.length).toBe(0);
  });

  it('60 个空 word 非法项截断 errors 到 50 条', async () => {
    const cookie = await registerAndLogin(app, rand('lim60bad'));
    const words = [];
    for (let i = 0; i < 60; i += 1) {
      words.push({ word: '', meanings_zh: ['义'] });
    }
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      headers: { cookie },
      payload: { words },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      imported: number;
      skippedExisting: number;
      skippedInvalid: number;
      errors: Array<{ index: number; message: string }>;
    };
    expect(body.imported).toBe(0);
    expect(body.skippedInvalid).toBe(60);
    expect(body.errors.length).toBe(50);
    expect(body.errors[0].message).toBe('word 不能为空');
    expect(body.errors[0].index).toBe(0);
  });
});
