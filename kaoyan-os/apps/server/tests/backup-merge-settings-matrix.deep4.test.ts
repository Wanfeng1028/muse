import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerBackupRoutes } from '../src/routes/backup';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('backup merge settings matrix deep4', () => {
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

  it('merge settings 三态：同值 skipped、异值 update、新 key insert，计数 imported=2 skipped=1', async () => {
    const { cookie, userId } = await newUser('bms');
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)').run(userId, 'theme', 'light');
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)').run(userId, 'lang', 'zh');

    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: {
        mode: 'merge',
        data: {
          format: 'kaoyan-backup',
          version: 1,
          exportedAt: '2024-01-01T00:00:00.000Z',
          tables: {
            plans: [],
            focus_sessions: [],
            mistakes: [],
            words: [],
            srs_state: [],
            exam_records: [],
            settings: [
              { key: 'theme', value: 'light' },
              { key: 'lang', value: 'en' },
              { key: 'notify', value: 'on' },
            ],
          },
        },
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      mode: string;
      imported: Record<string, number>;
      skipped: Record<string, number>;
    };
    expect(body.mode).toBe('merge');
    expect(body.imported.settings).toBe(2);
    expect(body.skipped.settings).toBe(1);
  });

  it('merge settings 最终库值：theme 保持 light、lang 更新为 en、notify 新增 on', async () => {
    const { cookie, userId } = await newUser('bms');
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)').run(userId, 'theme', 'light');
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)').run(userId, 'lang', 'zh');

    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: { cookie },
      payload: {
        mode: 'merge',
        data: {
          format: 'kaoyan-backup',
          version: 1,
          exportedAt: '2024-01-01T00:00:00.000Z',
          tables: {
            plans: [],
            focus_sessions: [],
            mistakes: [],
            words: [],
            srs_state: [],
            exam_records: [],
            settings: [
              { key: 'theme', value: 'light' },
              { key: 'lang', value: 'en' },
              { key: 'notify', value: 'on' },
            ],
          },
        },
      },
    });

    expect(res.statusCode).toBe(200);

    const theme = db.prepare('SELECT value FROM settings WHERE user_id = ? AND key = ?').get(userId, 'theme') as { value: string };
    const lang = db.prepare('SELECT value FROM settings WHERE user_id = ? AND key = ?').get(userId, 'lang') as { value: string };
    const notify = db.prepare('SELECT value FROM settings WHERE user_id = ? AND key = ?').get(userId, 'notify') as { value: string };

    expect(theme.value).toBe('light');
    expect(lang.value).toBe('en');
    expect(notify.value).toBe('on');

    const count = db.prepare('SELECT COUNT(*) AS c FROM settings WHERE user_id = ?').get(userId) as { c: number };
    expect(count.c).toBe(3);
  });
});
