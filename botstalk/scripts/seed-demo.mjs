#!/usr/bin/env node
import { DatabaseSync } from 'node:sqlite';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const dataDir = process.argv[2]
  ? resolve(process.argv[2])
  : resolve(__dirname, '..', 'data');
const dbPath = join(dataDir, 'botstalk.db');

if (!existsSync(dbPath)) {
  console.error(`未找到数据库：${dbPath}`);
  console.error('先启动一次网关建库');
  process.exit(1);
}

const db = new DatabaseSync(dbPath);

db.exec("DELETE FROM tasks WHERE task_id LIKE 'demo-%'");
db.exec("DELETE FROM messages WHERE payload LIKE '%demo-%'");

const now = Date.now();

const tasks = [
  { task_id: 'demo-t1', room: 'lobby', owner: '老板', assignee: 'echo',     title: '把本周 AI 新闻整理成早报',     status: 'done',        created_at_ms: now - 60 * 60 * 1000, updated_at_ms: now - 50 * 60 * 1000 },
  { task_id: 'demo-t2', room: 'lobby', owner: '老板', assignee: 'echo',     title: '调研三个 RSS 阅读器的去重方案', status: 'running',     created_at_ms: now - 50 * 60 * 1000, updated_at_ms: now - 40 * 60 * 1000 },
  { task_id: 'demo-t3', room: 'lobby', owner: '老板', assignee: 'deepseek', title: '写一份短剧分镜模板',           status: 'dispatched',  created_at_ms: now - 40 * 60 * 1000, updated_at_ms: now - 30 * 60 * 1000 },
  { task_id: 'demo-t4', room: 'lobby', owner: '老板', assignee: 'echo',     title: '生成产品海报',                 status: 'failed',      created_at_ms: now - 30 * 60 * 1000, updated_at_ms: now - 20 * 60 * 1000 },
  { task_id: 'demo-t5', room: 'lobby', owner: '老板', assignee: null,       title: '@一个不存在的成员',            status: 'unsupported', created_at_ms: now - 20 * 60 * 1000, updated_at_ms: now - 15 * 60 * 1000 },
  { task_id: 'demo-t6', room: 'lobby', owner: '老板', assignee: 'echo',     title: '导出全部聊天记录',             status: 'cancelled',   created_at_ms: now - 15 * 60 * 1000, updated_at_ms: now - 10 * 60 * 1000 },
];

const insertTask = db.prepare(
  'INSERT INTO tasks (task_id, room, owner, assignee, title, status, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
);

for (const t of tasks) {
  insertTask.run(
    t.task_id,
    t.room,
    t.owner,
    t.assignee,
    t.title,
    t.status,
    t.created_at_ms,
    t.updated_at_ms
  );
}

const baseTs = now - 5 * 60 * 1000;

const messages = [
  {
    room: 'lobby',
    sender: '老板',
    seq: 1,
    type: 'message',
    payload: JSON.stringify({ msg_id: 'demo-c1', text: '早会开始，同步下手头的活儿', mentions: [] }),
    ts: baseTs,
  },
  {
    room: 'lobby',
    sender: 'echo',
    seq: 2,
    type: 'message',
    payload: JSON.stringify({ msg_id: 'demo-m1', text: '[echo] task done', mentions: [], intent: 'task', task_id: 'demo-t1', task_status: 'done' }),
    ts: baseTs + 1000,
  },
  {
    room: 'lobby',
    sender: 'echo',
    seq: 3,
    type: 'message',
    payload: JSON.stringify({ msg_id: 'demo-m2', text: '[echo] task running', mentions: [], intent: 'task', task_id: 'demo-t2', task_status: 'running' }),
    ts: baseTs + 2000,
  },
  {
    room: 'lobby',
    sender: '老板',
    seq: 4,
    type: 'message',
    payload: JSON.stringify({ msg_id: 'demo-c2', text: '@echo demo-t3 的分镜模板今天能出吗', mentions: ['echo'] }),
    ts: baseTs + 3000,
  },
];

const insertMessage = db.prepare(
  'INSERT INTO messages (room, sender, seq, type, payload, ts) VALUES (?, ?, ?, ?, ?, ?)'
);

for (const m of messages) {
  insertMessage.run(m.room, m.sender, m.seq, m.type, m.payload, m.ts);
}

console.log(`tasks inserted: ${tasks.length}`);
console.log(`messages inserted: ${messages.length}`);

db.close();
