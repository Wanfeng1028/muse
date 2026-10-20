import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { registerExamsRoutes } from '../src/routes/exams';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: DatabaseSync;
let app: FastifyInstance;

function insertMistake(userId: number, subject: string, title: string, createdAt: string): number {
const info = db
.prepare('INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at) VALUES (?,?,?,?,?,?,?)')
.run(userId, subject, title, 'c-' + title, 'a-' + title, 0, createdAt);
return Number(info.lastInsertRowid);
}

function insertMistakeWithMastered(userId: number, subject: string, title: string, createdAt: string, mastered: number): number {
const info = db
.prepare('INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at) VALUES (?,?,?,?,?,?,?)')
.run(userId, subject, title, 'c-' + title, 'a-' + title, mastered, createdAt);
return Number(info.lastInsertRowid);
}

beforeEach(async () => {
db = createRealDb(':memory:');
app = Fastify();
registerMistakesRoutes(app, db);
registerExamsRoutes(app, db);
applyAuthHook(app, db);
registerAuthRoutes(app, db);
await app.ready();
});

afterAll(async () => {
await app.close();
});

describe('POST /api/mistakes/quiz/generate 深测', () => {
it('空题库组卷返回 200 且题目数组为空', async () => {
const cookie = await registerAndLogin(app, 'u1');
const res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: {}
});
expect(res.statusCode).toBe(200);
const body = res.json();
expect(body.data.items).toEqual([]);
});

it('limit 大于题量时返回全部（不报错）', async () => {
const cookie = await registerAndLogin(app, 'u1');
insertMistake(1, 'math', 't1', '2024-01-01');
insertMistake(1, 'math', 't2', '2024-01-02');
const res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { limit: 100 }
});
expect(res.statusCode).toBe(200);
const body = res.json();
expect(body.data.items.length).toBe(2);
});

it('unmasteredOnly 默认 true：插 2 未掌握 + 1 已掌握，返回 2 条且全未掌握', async () => {
const cookie = await registerAndLogin(app, 'u1');
insertMistake(1, 'math', 't1', '2024-01-01');
insertMistake(1, 'math', 't2', '2024-01-02');
insertMistakeWithMastered(1, 'math', 't3', '2024-01-03', 1);
const res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: {}
});
expect(res.statusCode).toBe(200);
const body = res.json();
expect(body.data.items.length).toBe(2);
for (const item of body.data.items) {
expect(item.mastered).toBe(0);
}
});

it('unmasteredOnly=false 时返回 3 条', async () => {
const cookie = await registerAndLogin(app, 'u1');
insertMistake(1, 'math', 't1', '2024-01-01');
insertMistake(1, 'math', 't2', '2024-01-02');
insertMistakeWithMastered(1, 'math', 't3', '2024-01-03', 1);
const res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { unmasteredOnly: false }
});
expect(res.statusCode).toBe(200);
const body = res.json();
expect(body.data.items.length).toBe(3);
});

it('subject 过滤：math/english 各插 1 条，subject=math 只返回 math', async () => {
const cookie = await registerAndLogin(app, 'u1');
insertMistake(1, 'math', 't1', '2024-01-01');
insertMistake(1, 'english', 't2', '2024-01-02');
const res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { subject: 'math' }
});
expect(res.statusCode).toBe(200);
const body = res.json();
expect(body.data.items.length).toBe(1);
expect(body.data.items[0].subject).toBe('math');
});

it('from/to 日期过滤：from 晚于所有 created_at 返回空', async () => {
const cookie = await registerAndLogin(app, 'u1');
insertMistake(1, 'math', 't1', '2024-01-01');
insertMistake(1, 'math', 't2', '2024-01-02');
const res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { from: '2025-01-01' }
});
expect(res.statusCode).toBe(200);
const body = res.json();
expect(body.data.items.length).toBe(0);
});

it('非法入参均返回 400', async () => {
const cookie = await registerAndLogin(app, 'u1');
let res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { limit: 0 }
});
expect(res.statusCode).toBe(400);
res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { limit: 101 }
});
expect(res.statusCode).toBe(400);
res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { limit: 1.5 }
});
expect(res.statusCode).toBe(400);
res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { subject: 'xxx' }
});
expect(res.statusCode).toBe(400);
res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { from: '2024-13-40' }
});
expect(res.statusCode).toBe(400);
res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { from: '2024-02-01', to: '2024-01-01' }
});
expect(res.statusCode).toBe(400);
res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie }
});
expect(res.statusCode).toBe(400);
});

it('未掌握优先排序：mastered=0 排在 mastered=1 前面', async () => {
const cookie = await registerAndLogin(app, 'u1');
insertMistakeWithMastered(1, 'math', 'old-mastered', '2024-01-01', 1);
insertMistakeWithMastered(1, 'math', 'new-unmastered', '2024-01-02', 0);
const res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie },
payload: { unmasteredOnly: false }
});
expect(res.statusCode).toBe(200);
const body = res.json();
expect(body.data.items.length).toBe(2);
expect(body.data.items[0].mastered).toBe(0);
expect(body.data.items[1].mastered).toBe(1);
});

it('用户隔离：用户 B 看不到用户 A 的错题', async () => {
await registerAndLogin(app, 'userA');
insertMistake(1, 'math', 't1', '2024-01-01');
insertMistake(1, 'math', 't2', '2024-01-02');
const cookieB = await registerAndLogin(app, 'userB');
const res = await app.inject({
method: 'POST',
url: '/api/mistakes/quiz/generate',
headers: { cookie: cookieB },
payload: {}
});
expect(res.statusCode).toBe(200);
const body = res.json();
expect(body.data.items.length).toBe(0);
});
});
