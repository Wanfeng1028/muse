import { describe, it, expect, beforeAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerBackupRoutes } from '../src/routes/backup';
import { registerAndLogin, authHeaders } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

beforeAll(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerBackupRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

async function seedUser(userId: number, tag: string) {
  db.prepare(
    `INSERT INTO words (user_id, word, phonetic, meaning, example, source)
     VALUES (?, ?, '', ?, '', 'manual')`
  ).run(userId, `w-${tag}`, `m-${tag}`);
  const wordId = Number(
    (db.prepare('SELECT id FROM words WHERE user_id = ? AND word = ?').get(userId, `w-${tag}`) as { id: number }).id
  );
  db.prepare(
    `INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date)
     VALUES (?, 2.5, 0, 0, '2026-01-01')`
  ).run(wordId);
  db.prepare(
    `INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at)
     VALUES (?, '2026-01-01', 'math', ?, 60, 0, '2026-01-01T00:00:00.000Z')`
  ).run(userId, `plan-${tag}`);
  db.prepare(
    `INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
     VALUES (?, 'math', ?, '', '', 0, '2026-01-01T00:00:00.000Z')`
  ).run(userId, `mistake-${tag}`);
  db.prepare(
    `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note)
     VALUES (?, 'math', 30, '2026-01-01T10:00:00.000Z', NULL)`
  ).run(userId);
  db.prepare(
    `INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at)
     VALUES (?, 'math', ?, 100, 150, 180, '2026-01-01T09:00:00.000Z')`
  ).run(userId, `paper-${tag}`);
  db.prepare(
    `INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)`
  ).run(userId, `k-${tag}`, `v-${tag}`);
}

async function getUserId(username: string): Promise<number> {
  const row = db.prepare('SELECT id FROM users WHERE username = ?').get(username) as { id: number } | undefined;
  if (!row) throw new Error(`user not found: ${username}`);
  return row.id;
}

describe('backup per-user isolation', () => {
  it('export 只包含当前用户数据', async () => {
    const aCookie = await registerAndLogin(app, 'iso_a');
    const bCookie = await registerAndLogin(app, 'iso_b');
    const aId = await getUserId('iso_a');
    const bId = await getUserId('iso_b');

    await seedUser(aId, 'a');
    await seedUser(bId, 'b');

    const res = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: authHeaders(aCookie),
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      format: string;
      version: number;
      tables: Record<string, Array<Record<string, unknown>>>;
    };
    expect(body.format).toBe('kaoyan-backup');
    expect(body.version).toBe(1);

    const words = body.tables.words;
    expect(words).toHaveLength(1);
    expect(words[0].word).toBe('w-a');
    expect(words[0].user_id).toBeUndefined();

    const plans = body.tables.plans;
    expect(plans).toHaveLength(1);
    expect(plans[0].title).toBe('plan-a');

    // B 用户数据不出现在 A 的导出
    for (const key of ['plans', 'focus_sessions', 'mistakes', 'words', 'exam_records', 'settings'] as const) {
      const arr = body.tables[key] ?? [];
      for (const row of arr) {
        expect(row.user_id).toBeUndefined();
        expect(JSON.stringify(row)).not.toContain('-b');
      }
    }

    // b 用户仍能看到自己的导出
    const resB = await app.inject({
      method: 'GET',
      url: '/api/backup/export',
      headers: authHeaders(bCookie),
    });
    expect(resB.statusCode).toBe(200);
    const bodyB = resB.json() as { tables: Record<string, Array<Record<string, unknown>>> };
    expect(bodyB.tables.words).toHaveLength(1);
    expect(bodyB.tables.words[0].word).toBe('w-b');
  });

  it('import replace 只清空并写入当前用户数据，不影响他人', async () => {
    const aCookie = await registerAndLogin(app, 'imp_a');
    const bCookie = await registerAndLogin(app, 'imp_b');
    const aId = await getUserId('imp_a');
    const bId = await getUserId('imp_b');

    await seedUser(aId, 'a');
    await seedUser(bId, 'b');

    // 构造 A 的导入负载：word 携带 user_id 试图越权（应被忽略），
    // srs_state 引用 B 的 word_id（应被丢弃）
    const bWordId = Number(
      (db.prepare('SELECT id FROM words WHERE user_id = ? AND word = ?').get(bId, 'w-b') as { id: number }).id
    );

    const payload = {
      mode: 'replace',
      data: {
        format: 'kaoyan-backup',
        version: 1,
        exportedAt: '2026-01-01T00:00:00.000Z',
        tables: {
          plans: [
            {
              id: 999,
              user_id: bId,
              date: '2026-02-01',
              subject: 'english',
              title: 'new-plan',
              planned_minutes: 30,
              done: 0,
              created_at: '2026-02-01T00:00:00.000Z',
            },
          ],
          focus_sessions: [],
          mistakes: [],
          words: [
            {
              id: 999,
              user_id: bId,
              word: 'new-word',
              phonetic: '',
              meaning: 'new-meaning',
              example: '',
              source: 'manual',
            },
          ],
          srs_state: [
            { word_id: bWordId, ease: 2.0, interval_days: 1, repetitions: 1, due_date: '2026-03-01' },
          ],
          exam_records: [],
          settings: [{ key: 'new-key', value: 'new-value' }],
        },
      },
    };

    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: authHeaders(aCookie),
      payload,
    });
    expect(res.statusCode).toBe(200);

    // A 的旧数据被清空，新数据写入
    const aPlans = db
      .prepare('SELECT title, user_id FROM plans WHERE user_id = ?')
      .all(aId) as Array<{ title: string; user_id: number }>;
    expect(aPlans).toHaveLength(1);
    expect(aPlans[0].title).toBe('new-plan');
    expect(aPlans[0].user_id).toBe(aId);

    const aWords = db
      .prepare('SELECT word, user_id FROM words WHERE user_id = ?')
      .all(aId) as Array<{ word: string; user_id: number }>;
    expect(aWords).toHaveLength(1);
    expect(aWords[0].word).toBe('new-word');
    expect(aWords[0].user_id).toBe(aId);

    // B 的数据完全没被触碰
    const bWords = db
      .prepare('SELECT word FROM words WHERE user_id = ?')
      .all(bId) as Array<{ word: string }>;
    expect(bWords.map((w) => w.word)).toEqual(['w-b']);
    const bPlans = db
      .prepare('SELECT title FROM plans WHERE user_id = ?')
      .all(bId) as Array<{ title: string }>;
    expect(bPlans.map((p) => p.title)).toEqual(['plan-b']);
    const bSrs = db
      .prepare('SELECT COUNT(*) as c FROM srs_state s JOIN words w ON w.id = s.word_id WHERE w.user_id = ?')
      .get(bId) as { c: number };
    expect(bSrs.c).toBe(1);

    // A 的 srs_state 引用 B 的 word_id 被丢弃
    const aSrs = db
      .prepare('SELECT COUNT(*) as c FROM srs_state s JOIN words w ON w.id = s.word_id WHERE w.user_id = ?')
      .get(aId) as { c: number };
    expect(aSrs.c).toBe(0);
  });

  it('import merge 不覆盖他人数据，且相同 word 跳过', async () => {
    const aCookie = await registerAndLogin(app, 'mrg_a');
    const bCookie = await registerAndLogin(app, 'mrg_b');
    const aId = await getUserId('mrg_a');
    const bId = await getUserId('mrg_b');

    await seedUser(aId, 'a');
    await seedUser(bId, 'b');

    const payload = {
      mode: 'merge',
      data: {
        format: 'kaoyan-backup',
        version: 1,
        exportedAt: '2026-01-01T00:00:00.000Z',
        tables: {
          plans: [],
          focus_sessions: [],
          mistakes: [],
          words: [
            { word: 'w-a', phonetic: '', meaning: 'dup', example: '', source: 'manual' },
            { word: 'mrg-new', phonetic: '', meaning: 'new', example: '', source: 'manual' },
          ],
          srs_state: [],
          exam_records: [],
          settings: [{ key: 'k-a', value: 'changed' }],
        },
      },
    };

    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: authHeaders(aCookie),
      payload,
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      mode: string;
      imported: Record<string, number>;
      skipped: Record<string, number>;
    };
    expect(body.mode).toBe('merge');
    expect(body.skipped.words).toBe(1);
    expect(body.imported.words).toBe(1);
    expect(body.imported.settings).toBe(1);

    // A 的 w-a 只有一个，且未产生重复
    const aWords = db
      .prepare('SELECT word FROM words WHERE user_id = ? ORDER BY word')
      .all(aId) as Array<{ word: string }>;
    expect(aWords.map((w) => w.word)).toEqual(['mrg-new', 'w-a']);

    // B 数据未变
    const bWords = db
      .prepare('SELECT word FROM words WHERE user_id = ?')
      .all(bId) as Array<{ word: string }>;
    expect(bWords.map((w) => w.word)).toEqual(['w-b']);

    // A 的 k-a 被更新为 changed，且没影响 B
    const aSetting = db
      .prepare('SELECT value FROM settings WHERE user_id = ? AND key = ?')
      .get(aId, 'k-a') as { value: string };
    expect(aSetting.value).toBe('changed');
    const bSetting = db
      .prepare('SELECT value FROM settings WHERE user_id = ? AND key = ?')
      .get(bId, 'k-b') as { value: string };
    expect(bSetting.value).toBe('v-b');
  });

  it('CSV words 导入时 source=csv，且 user_id 归属当前用户', async () => {
    const csvCookie = await registerAndLogin(app, 'csv_user');
    const csvId = await getUserId('csv_user');

    const csv = 'word,meaning,phonetic,example\ncsvw1,mean1,,,';
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/words',
      headers: authHeaders(csvCookie),
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { imported: number };
    expect(body.imported).toBe(1);

    const row = db
      .prepare('SELECT user_id, source FROM words WHERE word = ?')
      .get('csvw1') as { user_id: number; source: string };
    expect(row.user_id).toBe(csvId);
    expect(row.source).toBe('csv');
  });

  it('kaoyan-backup version 校验', async () => {
    const cookie = await registerAndLogin(app, 'ver_user');
    const res = await app.inject({
      method: 'POST',
      url: '/api/backup/import',
      headers: authHeaders(cookie),
      payload: {
        mode: 'replace',
        data: {
          format: 'kaoyan-backup',
          version: 2,
          exportedAt: '2026-01-01T00:00:00.000Z',
          tables: {
            plans: [],
            focus_sessions: [],
            mistakes: [],
            words: [],
            srs_state: [],
            exam_records: [],
            settings: [],
          },
        },
      },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('version 无效');
  });
});
