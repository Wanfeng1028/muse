import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('backup csv header edge deep4', () => {
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

  it('表头前有 2 个空行时仍能定位表头并导入', async () => {
    const { cookie, userId } = await newUser('csvhdrblank');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/words',
      headers: { cookie },
      payload: { csv: '\n\nword,meaning\napple,苹果\n' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1);
    const rows = db.prepare('SELECT word, meaning FROM words WHERE user_id = ?').all(userId) as {
      word: string;
      meaning: string;
    }[];
    expect(rows.length).toBe(1);
    expect(rows[0].word).toBe('apple');
    expect(rows[0].meaning).toBe('苹果');
  });

  it('表头大小写混写 Word,MEANING 归一化后命中必需列', async () => {
    const { cookie, userId } = await newUser('csvhdrcase');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/words',
      headers: { cookie },
      payload: { csv: 'Word,MEANING\napple,苹果\n' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1);
    const rows = db.prepare('SELECT word, meaning FROM words WHERE user_id = ?').all(userId) as {
      word: string;
      meaning: string;
    }[];
    expect(rows.length).toBe(1);
    expect(rows[0].word).toBe('apple');
    expect(rows[0].meaning).toBe('苹果');
  });

  it('重复表头 word,word,meaning 取第一列作为 word', async () => {
    const { cookie, userId } = await newUser('csvhdrdup');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/words',
      headers: { cookie },
      payload: { csv: 'word,word,meaning\nfirst,second,义\n' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1);
    const rows = db.prepare('SELECT word, meaning FROM words WHERE user_id = ?').all(userId) as {
      word: string;
      meaning: string;
    }[];
    expect(rows.length).toBe(1);
    expect(rows[0].word).toBe('first');
    expect(rows[0].meaning).toBe('义');
  });

  it('存在多余列 extra 时被忽略且 meaning 正确导入', async () => {
    const { cookie, userId } = await newUser('csvhdrextra');
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/words',
      headers: { cookie },
      payload: { csv: 'word,meaning,extra\napple,苹果,忽略我\n' },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1);
    const rows = db.prepare('SELECT word, meaning FROM words WHERE user_id = ?').all(userId) as {
      word: string;
      meaning: string;
    }[];
    expect(rows.length).toBe(1);
    expect(rows[0].word).toBe('apple');
    expect(rows[0].meaning).toBe('苹果');
  });
});
