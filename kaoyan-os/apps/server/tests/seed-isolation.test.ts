import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerPlansRoutes } from '../src/routes/plans';
import { seedIfEmpty } from '../src/seed';
import { createSeededUser, registerAndLogin, authHeaders } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerPlansRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  seedIfEmpty(db);
});

afterEach(async () => {
  await app.close();
});

function countByUser(table: string, userId: number): number {
  const row = db
    .prepare(`SELECT COUNT(*) AS c FROM ${table} WHERE user_id = ?`)
    .get(userId) as { c: number };
  return row.c;
}

describe('seedIfEmpty 只种给 local 用户', () => {
  it('种子写入 local 用户，其他用户不会被污染', () => {
    const local = db
      .prepare("SELECT id FROM users WHERE username = 'local'")
      .get() as { id: number } | undefined;
    expect(local).toBeTruthy();
    const localId = local!.id;

    // local 下有种子
    expect(countByUser('settings', localId)).toBeGreaterThan(0);
    expect(countByUser('words', localId)).toBe(24);
    expect(countByUser('plans', localId)).toBe(6);
    expect(countByUser('mistakes', localId)).toBe(3);
    expect(countByUser('exam_records', localId)).toBe(2);
    expect(countByUser('focus_sessions', localId)).toBe(8); // 种子：过去6天各1条+今天2条=8

    // 不存在 user_id=0 的孤儿行（防御性断言）
    expect(countByUser('settings', 0)).toBe(0);
    expect(countByUser('words', 0)).toBe(0);
    expect(countByUser('plans', 0)).toBe(0);
    expect(countByUser('mistakes', 0)).toBe(0);
    expect(countByUser('exam_records', 0)).toBe(0);
    expect(countByUser('focus_sessions', 0)).toBe(0);
  });

  it('没有 local 用户时抛错，而不是静默写到 user_id=0', () => {
    const fresh = new DatabaseSync(':memory:');
    // 复制 schema：直接复用当前 db 的建表 SQL 会更好，但为最小化耦合，
    // 这里只创建 seed 必需的表中最关键的一张来触发提前报错。
    fresh.exec(`
      CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE);
      CREATE TABLE settings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL);
    `);
    expect(() => seedIfEmpty(fresh)).toThrow(/local user not found/);
    fresh.close();
  });
});

describe('新注册用户没有默认种子数据', () => {
  it('注册后仅凭 cookie 访问业务接口，返回空集合', async () => {
    const cookie = await registerAndLogin(app, 'fresh_user_a');

    const userRow = db
      .prepare("SELECT id FROM users WHERE username = 'fresh_user_a'")
      .get() as { id: number };
    const uid = userRow.id;

    // 直接查库：新用户各表为空
    expect(countByUser('settings', uid)).toBe(0);
    expect(countByUser('words', uid)).toBe(0);
    expect(countByUser('plans', uid)).toBe(0);
    expect(countByUser('mistakes', uid)).toBe(0);
    expect(countByUser('exam_records', uid)).toBe(0);
    expect(countByUser('focus_sessions', uid)).toBe(0);

    // 通过 HTTP 再确认：新用户看不到 local 的种子
    const plansRes = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: authHeaders(cookie),
    });
    expect(plansRes.statusCode).toBe(200);
    const plansBody = plansRes.json() as unknown;
    const plansArr = Array.isArray(plansBody)
      ? plansBody
      : (plansBody as { items?: unknown[] }).items ?? [];
    expect(plansArr.length).toBe(0);
  });

  it('createSeededUser 复制的数据只落在新用户名下，local 的计数不变', async () => {
    const local = db
      .prepare("SELECT id FROM users WHERE username = 'local'")
      .get() as { id: number };
    const localId = local.id;
    const before = {
      plans: countByUser('plans', localId),
      words: countByUser('words', localId),
      focus: countByUser('focus_sessions', localId),
      mistakes: countByUser('mistakes', localId),
      exams: countByUser('exam_records', localId),
      settings: countByUser('settings', localId),
    };

    const { userId } = await createSeededUser(db, app, 'seeded_user_a');

    // 新用户名下应有对应数量的副本
    expect(countByUser('plans', userId)).toBe(before.plans);
    expect(countByUser('words', userId)).toBe(before.words);
    expect(countByUser('focus_sessions', userId)).toBe(before.focus);
    expect(countByUser('mistakes', userId)).toBe(before.mistakes);
    expect(countByUser('exam_records', userId)).toBe(before.exams);
    expect(countByUser('settings', userId)).toBe(before.settings);

    // local 数据未被修改
    expect(countByUser('plans', localId)).toBe(before.plans);
    expect(countByUser('words', localId)).toBe(before.words);
    expect(countByUser('focus_sessions', localId)).toBe(before.focus);
    expect(countByUser('mistakes', localId)).toBe(before.mistakes);
    expect(countByUser('exam_records', localId)).toBe(before.exams);
    expect(countByUser('settings', localId)).toBe(before.settings);
  });
});
