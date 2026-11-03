import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerWordsRoutes } from '../src/routes/words';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: DatabaseSync;
let app: FastifyInstance;
let authCookie: string;

function userId(username: string): number {
  const row = db.prepare('SELECT id FROM users WHERE username = ?').get(username) as { id: number };
  return row.id;
}

function insertWord(username: string, word: string, source: string): number {
  const info = db
    .prepare('INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES (?, ?, ?, ?, ?, ?, ?)')
    .run(userId(username), word, '', '', '', source, '');
  return Number(info.lastInsertRowid);
}

function insertSrs(wordId: number, dueDate: string): void {
  db.prepare('INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, 2.5, 0, 0, ?)')
    .run(wordId, dueDate);
}

describe('GET /api/words/summary/by-source', () => {
  beforeEach(async () => {
    db = createRealDb(':memory:');
    app = Fastify();
    registerWordsRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'wordsbysource');
  });

  afterAll(async () => {
    if (app) await app.close();
  });

  it('空库返回 sources 为空数组', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/words/summary/by-source',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ sources: [] });
  });

  it('分来源统计总数/到期/未开始，按 WORD_SOURCES 顺序排列，零词来源省略', async () => {
    const today = new Date();
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    const yesterday = iso(new Date(today.getTime() - 86400000));
    const tomorrow = iso(new Date(today.getTime() + 86400000));
    const todayStr = iso(today);

    const w1 = insertWord('wordsbysource', 'w-manual-due', 'manual');
    insertSrs(w1, yesterday);
    const w2 = insertWord('wordsbysource', 'w-manual-today', 'manual');
    insertSrs(w2, todayStr);
    const w3 = insertWord('wordsbysource', 'w-manual-future', 'manual');
    insertSrs(w3, tomorrow);
    insertWord('wordsbysource', 'w-manual-new', 'manual');
    const w5 = insertWord('wordsbysource', 'w-core-due', 'core500');
    insertSrs(w5, yesterday);

    const res = await app.inject({
      method: 'GET',
      url: '/api/words/summary/by-source',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({
      sources: [
        { source: 'core500', total: 1, due: 1, notStarted: 0 },
        { source: 'manual', total: 4, due: 2, notStarted: 1 },
      ],
    });
  });

  it('只统计当前用户，他人单词不计入', async () => {
    await registerAndLogin(app, 'wordsbysourceother');
    insertWord('wordsbysourceother', 'w-other', 'manual');
    const res = await app.inject({
      method: 'GET',
      url: '/api/words/summary/by-source',
      headers: { cookie: authCookie },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ sources: [] });
  });

  it('未登录返回 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/words/summary/by-source' });
    expect(res.statusCode).toBe(401);
  });
});
