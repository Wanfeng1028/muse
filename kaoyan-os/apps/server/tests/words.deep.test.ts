import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerWordsRoutes } from '../src/routes/words';

function createDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:');
  db.exec(`
    CREATE TABLE words (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      word TEXT NOT NULL UNIQUE,
      phonetic TEXT NOT NULL DEFAULT '',
      meaning TEXT NOT NULL DEFAULT '',
      example TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'core500',
      memory_tip TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE srs_state (
      word_id INTEGER PRIMARY KEY,
      ease REAL NOT NULL DEFAULT 2.5,
      interval_days INTEGER NOT NULL DEFAULT 0,
      repetitions INTEGER NOT NULL DEFAULT 0,
      due_date TEXT NOT NULL
    );
  `);
  return db;
}

function seedWord(db: DatabaseSync, word: string, dueDate: string, repetitions = 0): number {
  const info = db
    .prepare(
      'INSERT INTO words (word, phonetic, meaning, example, source, memory_tip) VALUES (?, ?, ?, ?, ?, ?)',
    )
    .run(word, '', '测试释义', '', 'core500', '');
  const id = Number(info.lastInsertRowid);
  db.prepare(
    'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
  ).run(id, 2.5, 0, repetitions, dueDate);
  return id;
}

let app: FastifyInstance;
let db: DatabaseSync;

beforeEach(async () => {
  db = createDb();
  app = Fastify({ logger: false });
  registerWordsRoutes(app, db);
  await app.ready();
});

afterEach(async () => {
  await app.close();
  db.close();
});

describe('words deep - SRS 排程边界', () => {
  it('跨月复习：due_date 落在月末，grade=good 后应推进到下一个合法日期', async () => {
    const id = seedWord(db, 'boundary-cross-month', '2024-01-31');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(typeof body.state.intervalDays).toBe('number');
    expect(body.state.intervalDays).toBeGreaterThanOrEqual(1);
    expect(body.state.dueDate).not.toBe('2024-01-31');
    expect(body.state.dueDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('闰年边界：2024-02-29 复习后 due_date 必须仍是合法日期', async () => {
    const id = seedWord(db, 'boundary-leap', '2024-02-29');
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state.dueDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const parts = body.state.dueDate.split('-').map(Number);
    expect(parts[1]).toBeGreaterThanOrEqual(1);
    expect(parts[1]).toBeLessThanOrEqual(12);
    expect(parts[2]).toBeGreaterThanOrEqual(1);
    expect(parts[2]).toBeLessThanOrEqual(31);
  });

  it('空计划边界：没有到期词时 due 列表返回空数组', async () => {
    seedWord(db, 'future-word', '2999-12-31');
    const res = await app.inject({ method: 'GET', url: '/api/words/due' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBe(0);
  });

  it('grade=0 应把 repetitions 归零并让 dueDate 落到今天', async () => {
    const id = seedWord(db, 'again-word', '2024-01-01', 5);
    const res = await app.inject({
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 0 },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.state.repetitions).toBe(0);
    expect(body.state.intervalDays).toBe(1);
  });
});

// 已删除：番茄计时边界用例，/api/words/pomodoro 端点不存在，本文件仅注册 words 路由，无法用真实 API 表达

describe('words deep - 单词去重', () => {
  it('同一单词重复创建应返回 409 只保留一条', async () => {
    const first = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'dup-word', meaning: '重复' },
    });
    expect(first.statusCode).toBe(201);
    const second = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'dup-word', meaning: '重复' },
    });
    expect(second.statusCode).toBe(409);
    const list = await app.inject({ method: 'GET', url: '/api/words' });
    expect(list.statusCode).toBe(200);
    const items = list.json().filter((w: { word: string }) => w.word === 'dup-word');
    expect(items.length).toBe(1);
  });
});

describe('words deep - 单词 SRS 状态', () => {
  it('新导入单词默认 ease=2.5 intervalDays=0 repetitions=0', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words',
      payload: { word: 'srs-default-new', meaning: '默认' },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body.state.ease).toBe(2.5);
    expect(body.state.intervalDays).toBe(0);
    expect(body.state.repetitions).toBe(0);
  });

  it('连续 good 复习应让 intervalDays 单调不减', async () => {
    const id = seedWord(db, 'srs-monotonic', '2024-01-01');
    let prev = 0;
    for (let i = 0; i < 3; i += 1) {
      const res = await app.inject({
        method: 'POST',
        url: `/api/words/${id}/review`,
        payload: { grade: 2 },
      });
      expect(res.statusCode).toBe(200);
      const interval = res.json().state.intervalDays;
      expect(interval).toBeGreaterThanOrEqual(prev);
      prev = interval;
    }
    expect(prev).toBeGreaterThan(0);
  });
});

describe('words deep - 批量导入畸形行', () => {
  it('批量导入畸形条目应被跳过并统计 errors', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        words: [{ word: 'validword', meanings_zh: ['有效'] }, { word: '', meanings_zh: ['空词'] }, 'badline'],
        source: 'manual',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1);
    expect(body.skippedInvalid).toBeGreaterThanOrEqual(1);
    expect(Array.isArray(body.errors)).toBe(true);
  });

  it('批量导入空数组应返回 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: { words: [] },
    });
    expect(res.statusCode).toBe(400);
  });
});

describe('words deep - 备份恢复 round-trip', () => {
  it('删除后经批量导入应恢复同样的单词', async () => {
    seedWord(db, 'backup-a', '2024-03-01', 2);
    seedWord(db, 'backup-b', '2024-04-01', 4);

    const snapshotRes = await app.inject({ method: 'GET', url: '/api/words' });
    expect(snapshotRes.statusCode).toBe(200);
    const snapshot = snapshotRes.json();
    expect(Array.isArray(snapshot)).toBe(true);
    expect(snapshot.length).toBe(2);

    db.exec('DELETE FROM srs_state');
    db.exec('DELETE FROM words');

    const restoreRes = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        words: snapshot.map((w: { word: string; meaning: string }) => ({
          word: w.word,
          meanings_zh: [w.meaning],
        })),
        source: 'manual',
      },
    });
    expect(restoreRes.statusCode).toBe(200);
    const restored = restoreRes.json();
    expect(restored.imported).toBe(2);

    const list = await app.inject({ method: 'GET', url: '/api/words' });
    expect(list.statusCode).toBe(200);
    const items = list.json();
    expect(items.length).toBe(2);
    const words = items.map((w: { word: string }) => w.word).sort();
    expect(words).toEqual(['backup-a', 'backup-b']);
  });
});