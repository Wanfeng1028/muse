import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';
import { registerWordsRoutes } from '../src/routes/words';

const EXPORT_HEADER =
  'id,word,phonetic,meaning,example,source,source_name,memory_tip,repetitions,due_date';

describe('GET /api/words/export', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let authCookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    registerWordsRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'wordsexport');
  });

  afterAll(async () => {
    await app.close();
  });

  function insertWord(opts: { user: string; word: string; source: string; meaning?: string }): number {
    const result = db
      .prepare(
        "INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?, ?, ?, ?)"
      )
      .run(opts.user, opts.word, '/w3:d/', opts.meaning ?? '释义', `This is ${opts.word}.`, opts.source, '联想记忆');
    return Number(result.lastInsertRowid);
  }

  function insertSrs(wordId: number, repetitions: number, dueDate: string): void {
    db.prepare(
      'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, 2.5, 3, ?, ?)'
    ).run(wordId, repetitions, dueDate);
  }

  function csvLines(body: string): string[] {
    return body
      .replace(/^\uFEFF/, '')
      .split(/\r?\n/)
      .filter((line) => line.length > 0);
  }

  it('空库导出返回 200,响应带 BOM 的 text/csv,首行为表头', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/words/export',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    expect(res.headers['content-type']).toContain('text/csv');
    expect(res.body.startsWith('\uFEFF')).toBe(true);
    expect(csvLines(res.body)[0]).toBe(EXPORT_HEADER);
  });

  it('导出两条单词,按 id 升序,source_name 与 SRS 列正确', async () => {
    const manualId = insertWord({ user: 'wordsexport', word: 'apple', source: 'manual' });
    insertSrs(manualId, 3, '2024-06-10');
    insertWord({ user: 'wordsexport', word: 'banana', source: 'core500' });

    const res = await app.inject({
      method: 'GET',
      url: '/api/words/export',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    const lines = csvLines(res.body);
    expect(lines).toHaveLength(3);
    const rows = lines.slice(1).map((line) => line.split(','));
    expect(rows[0][1]).toBe('apple');
    expect(rows[1][1]).toBe('banana');
    expect(rows[0][6]).toBe('手动录入');
    expect(rows[1][6]).toBe('核心500词库');
    expect(rows[0][8]).toBe('3');
    expect(rows[0][9]).toBe('2024-06-10');
    expect(rows[1][8]).toBe('');
    expect(rows[1][9]).toBe('');
  });

  it('释义含逗号与双引号时按 RFC4180 转义', async () => {
    insertWord({ user: 'wordsexport', word: 'quoteword', source: 'manual', meaning: 'a,b"c' });

    const res = await app.inject({
      method: 'GET',
      url: '/api/words/export',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    const lines = csvLines(res.body);
    expect(lines).toHaveLength(2);
    expect(lines[1]).toContain('"a,b""c"');
  });

  it('source=manual 只导出手动词,非法 source 返回 400', async () => {
    insertWord({ user: 'wordsexport', word: 'manualword', source: 'manual' });
    insertWord({ user: 'wordsexport', word: 'coreword', source: 'core500' });

    const ok = await app.inject({
      method: 'GET',
      url: '/api/words/export?source=manual',
      headers: { cookie: authCookie },
    });
    expect(ok.statusCode).toBe(200);
    const lines = csvLines(ok.body);
    expect(lines).toHaveLength(2);
    expect(lines[1]).toContain('manualword');
    expect(lines[1]).not.toContain('coreword');

    const bad = await app.inject({
      method: 'GET',
      url: '/api/words/export?source=bogus',
      headers: { cookie: authCookie },
    });
    expect(bad.statusCode).toBe(400);
  });

  it('用户隔离:只导出当前登录用户的单词', async () => {
    await registerAndLogin(app, 'wordsexport2');
    insertWord({ user: 'wordsexport2', word: 'ghostword', source: 'manual' });
    insertWord({ user: 'wordsexport', word: 'myword', source: 'manual' });

    const res = await app.inject({
      method: 'GET',
      url: '/api/words/export',
      headers: { cookie: authCookie },
    });

    expect(res.statusCode).toBe(200);
    expect(res.body).toContain('myword');
    expect(res.body).not.toContain('ghostword');
  });

  it('未登录返回 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/words/export' });
    expect(res.statusCode).toBe(401);
  });
});
