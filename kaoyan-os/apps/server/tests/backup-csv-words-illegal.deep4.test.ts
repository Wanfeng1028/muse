import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('backup csv words illegal rows deep4', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  const rand = (p: string) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  async function newUser(prefix: string): Promise<{ cookie: string; userId: number }> {
    const name = rand(prefix);
    const cookie = await registerAndLogin(app, name);
    const row = db.prepare('SELECT id FROM users WHERE username = ?').get(name) as { id: number };
    return { cookie, userId: row.id };
  }
  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify({ logger: false });
    registerBackupRoutes(app, db);
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    await app.ready();
  });
  afterEach(async () => { await app.close(); });

  const csvText =
    '\uFEFF' +
    'word,meaning,phonetic\n' +
    'apple,苹果,\n' +
    ',无词\n' +
    'banana,,\n' +
    'apple,苹果2,\n' +
    '"quo""te",引号词,\n' +
    '\n' +
    'cherry,樱桃,\n';

  it('csv 非法行矩阵统计 imported/skippedEmpty/skippedExisting/errorRows', async () => {
    const { cookie } = await newUser('csv_matrix');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/words',
      headers: { cookie },
      payload: { csv: csvText },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      imported: number;
      skippedEmpty: number;
      skippedExisting: number;
      errors: { row: number; message: string }[];
      errorRows: number;
    };
    expect(body.imported).toBe(3);
    expect(body.skippedEmpty).toBe(1);
    expect(body.skippedExisting).toBe(1);
    expect(body.errorRows).toBe(1);
  });

  it('errors 精确指向第 4 行 meaning 不能为空', async () => {
    const { cookie } = await newUser('csv_errors');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/words',
      headers: { cookie },
      payload: { csv: csvText },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      errors: { row: number; message: string }[];
    };
    expect(body.errors.length).toBe(1);
    expect(body.errors[0].row).toBe(4);
    expect(body.errors[0].message).toBe('meaning 不能为空');
  });

  it('引号转义落库为 quo"te 且 apple 仅一行', async () => {
    const { cookie, userId } = await newUser('csv_quote');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/words',
      headers: { cookie },
      payload: { csv: csvText },
    });
    expect(res.statusCode).toBe(200);
    const quoted = db
      .prepare('SELECT word, meaning FROM words WHERE user_id = ? AND word = ?')
      .get(userId, 'quo"te') as { word: string; meaning: string } | undefined;
    expect(quoted).toBeTruthy();
    expect(quoted!.word).toBe('quo"te');
    expect(quoted!.meaning).toBe('引号词');
    const appleCount = db
      .prepare('SELECT COUNT(*) AS n FROM words WHERE user_id = ? AND word = ?')
      .get(userId, 'apple') as { n: number };
    expect(appleCount.n).toBe(1);
  });
});
