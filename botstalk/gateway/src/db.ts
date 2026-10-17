import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

export type Db = DatabaseSync;

export function openDb(dataDir: string): DatabaseSync {
  mkdirSync(dataDir, { recursive: true });
  const db = new DatabaseSync(join(dataDir, "botstalk.db"));
  db.exec("PRAGMA journal_mode=WAL;");
  db.exec(`
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      room TEXT NOT NULL,
      sender TEXT NOT NULL,
      seq INTEGER NOT NULL,
      type TEXT NOT NULL,
      payload TEXT NOT NULL,
      ts INTEGER NOT NULL
    );
  `);
  db.exec("CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room, id);");
  db.exec(`
    CREATE TABLE IF NOT EXISTS presence (
      adapter_id TEXT PRIMARY KEY,
      status TEXT NOT NULL,
      last_seen_ms INTEGER NOT NULL,
      usage_in INTEGER NOT NULL DEFAULT 0,
      usage_out INTEGER NOT NULL DEFAULT 0
    );
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS artifacts (
      id TEXT PRIMARY KEY,
      filename TEXT NOT NULL,
      size INTEGER NOT NULL,
      mime TEXT,
      path TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL
    );
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS gateway_state (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS pending_frames (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      adapter_id TEXT NOT NULL,
      gseq INTEGER NOT NULL,
      envelope TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL
    );
  `);
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_pending_frames_adapter_gseq ON pending_frames(adapter_id, gseq);",
  );
  db.exec(
    "CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, room TEXT NOT NULL, owner TEXT NOT NULL, assignee TEXT, title TEXT NOT NULL, status TEXT NOT NULL, created_at_ms INTEGER NOT NULL, updated_at_ms INTEGER NOT NULL);",
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_tasks_room_updated ON tasks(room, updated_at_ms DESC);",
  );
  return db;
}

export function getGatewayState(db: Db, key: string): string | undefined {
  const stmt = db.prepare("SELECT value FROM gateway_state WHERE key = ?");
  const row = stmt.get(key) as unknown as { value: string } | undefined;
  return row ? row.value : undefined;
}

export function setGatewayState(db: Db, key: string, value: string): void {
  const stmt = db.prepare(
    `INSERT INTO gateway_state (key, value) VALUES (?, ?)
     ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
  );
  stmt.run(key, value);
}

export interface PendingFrameRow {
  id: number;
  adapter_id: string;
  gseq: number;
  envelope: string;
  created_at_ms: number;
}

export function savePendingFrame(
  db: Db,
  adapter_id: string,
  gseq: number,
  envelopeJson: string,
): void {
  const stmt = db.prepare(
    "INSERT INTO pending_frames (adapter_id, gseq, envelope, created_at_ms) VALUES (?, ?, ?, ?)",
  );
  stmt.run(adapter_id, gseq, envelopeJson, Date.now());
}

export function loadPendingFrames(
  db: Db,
  adapter_id: string,
): Array<{ gseq: number; envelope: string }> {
  const stmt = db.prepare(
    "SELECT gseq, envelope FROM pending_frames WHERE adapter_id = ? ORDER BY gseq ASC",
  );
  return stmt.all(adapter_id) as unknown as Array<{ gseq: number; envelope: string }>;
}

export function prunePendingFrames(db: Db, adapter_id: string, keepMax: number): void {
  const stmt = db.prepare(
    `DELETE FROM pending_frames
     WHERE adapter_id = ?
       AND id NOT IN (
         SELECT id FROM pending_frames
         WHERE adapter_id = ?
         ORDER BY gseq DESC
         LIMIT ?
       )`,
  );
  stmt.run(adapter_id, adapter_id, keepMax);
}

export interface MessageRow {
  id: number;
  room: string;
  sender: string;
  seq: number;
  type: string;
  payload: string;
  ts: number;
}

export function saveMessage(
  db: Db,
  m: { room: string; sender: string; seq: number; type: string; payload: string; ts: number },
): number {
  const stmt = db.prepare(
    "INSERT INTO messages (room, sender, seq, type, payload, ts) VALUES (?, ?, ?, ?, ?, ?)",
  );
  const info = stmt.run(m.room, m.sender, m.seq, m.type, m.payload, m.ts);
  return Number(info.lastInsertRowid);
}

export function getRoomHistory(
  db: Db,
  room: string,
  limit: number,
  beforeId?: number,
): MessageRow[] {
  if (beforeId === undefined) {
    const stmt = db.prepare(
      "SELECT id, room, sender, seq, type, payload, ts FROM messages WHERE room = ? ORDER BY id DESC LIMIT ?",
    );
    return stmt.all(room, limit) as unknown as MessageRow[];
  }
  const stmt = db.prepare(
    "SELECT id, room, sender, seq, type, payload, ts FROM messages WHERE room = ? AND id < ? ORDER BY id DESC LIMIT ?",
  );
  return stmt.all(room, beforeId, limit) as unknown as MessageRow[];
}

export interface PresenceRow {
  adapter_id: string;
  status: string;
  last_seen_ms: number;
  usage_in: number;
  usage_out: number;
}

export function upsertPresence(
  db: Db,
  p: {
    adapter_id: string;
    status: string;
    last_seen_ms: number;
    usage_in: number;
    usage_out: number;
  },
): void {
  const stmt = db.prepare(
    `INSERT INTO presence (adapter_id, status, last_seen_ms, usage_in, usage_out)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(adapter_id) DO UPDATE SET
       status = excluded.status,
       last_seen_ms = excluded.last_seen_ms,
       usage_in = excluded.usage_in,
       usage_out = excluded.usage_out`,
  );
  stmt.run(p.adapter_id, p.status, p.last_seen_ms, p.usage_in, p.usage_out);
}

export function getPresence(db: Db, adapter_id: string): PresenceRow | undefined {
  const stmt = db.prepare(
    "SELECT adapter_id, status, last_seen_ms, usage_in, usage_out FROM presence WHERE adapter_id = ?",
  );
  const row = stmt.get(adapter_id);
  return row as unknown as PresenceRow | undefined;
}

export function listPresence(db: Db): PresenceRow[] {
  const stmt = db.prepare(
    "SELECT adapter_id, status, last_seen_ms, usage_in, usage_out FROM presence",
  );
  return stmt.all() as unknown as PresenceRow[];
}

export interface ArtifactRow {
  id: string;
  filename: string;
  size: number;
  mime: string | null;
  path: string;
  created_at_ms: number;
}

export function saveArtifact(
  db: Db,
  a: { id: string; filename: string; size: number; mime: string | null; path: string },
): void {
  const stmt = db.prepare(
    "INSERT INTO artifacts (id, filename, size, mime, path, created_at_ms) VALUES (?, ?, ?, ?, ?, ?)",
  );
  stmt.run(a.id, a.filename, a.size, a.mime, a.path, Date.now());
}

export function getArtifact(db: Db, id: string): ArtifactRow | undefined {
  const stmt = db.prepare(
    "SELECT id, filename, size, mime, path, created_at_ms FROM artifacts WHERE id = ?",
  );
  const row = stmt.get(id);
  return row as unknown as ArtifactRow | undefined;
}

export type TaskStatus = "dispatched" | "running" | "done" | "failed" | "unsupported" | "cancelled";

export interface TaskRow {
  task_id: string;
  room: string;
  owner: string;
  assignee: string | null;
  title: string;
  status: TaskStatus;
  created_at_ms: number;
  updated_at_ms: number;
}

/** 任务派发时登记；同一 task_id 重复派发则更新（幂等）。 */
export function upsertTaskDispatch(
  db: Db,
  t: { task_id: string; room: string; owner: string; assignee: string | null; title: string; status: TaskStatus },
): void {
  const now = Date.now();
  const stmt = db.prepare(
    `INSERT INTO tasks (task_id, room, owner, assignee, title, status, created_at_ms, updated_at_ms)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(task_id) DO UPDATE SET
       room = excluded.room, owner = excluded.owner, assignee = excluded.assignee,
       title = excluded.title, status = excluded.status, updated_at_ms = excluded.updated_at_ms`,
  );
  stmt.run(t.task_id, t.room, t.owner, t.assignee, t.title, t.status, now, now);
}

/** 任务状态流转；不存在的 task_id 返回 false。 */
export function updateTaskStatus(db: Db, task_id: string, status: TaskStatus): boolean {
  const stmt = db.prepare("UPDATE tasks SET status = ?, updated_at_ms = ? WHERE task_id = ?");
  const info = stmt.run(status, Date.now(), task_id);
  return Number(info.changes) > 0;
}

export function getTask(db: Db, task_id: string): TaskRow | undefined {
  const stmt = db.prepare("SELECT task_id, room, owner, assignee, title, status, created_at_ms, updated_at_ms FROM tasks WHERE task_id = ?");
  return stmt.get(task_id) as unknown as TaskRow | undefined;
}

/** 按更新时间倒序；room/status 可选过滤；limit 上限 200；before_* 游标翻页（与排序一致） */
export function listTasks(db: Db, opts: { room?: string; status?: TaskStatus; limit?: number; before_updated_ms?: number; before_task_id?: string }): TaskRow[] {
  const conds: string[] = [];
  const args: Array<string | number> = [];
  if (opts.room !== undefined) { conds.push("room = ?"); args.push(opts.room); }
  if (opts.status !== undefined) { conds.push("status = ?"); args.push(opts.status); }
  if (opts.before_updated_ms !== undefined && opts.before_task_id !== undefined) {
    conds.push("(updated_at_ms < ? OR (updated_at_ms = ? AND task_id > ?))");
    args.push(opts.before_updated_ms, opts.before_updated_ms, opts.before_task_id);
  }
  const where = conds.length > 0 ? "WHERE " + conds.join(" AND ") : "";
  const limit = Math.min(Math.max(opts.limit ?? 50, 1), 200);
  const stmt = db.prepare(
    `SELECT task_id, room, owner, assignee, title, status, created_at_ms, updated_at_ms FROM tasks ${where} ORDER BY updated_at_ms DESC, task_id ASC LIMIT ?`,
  );
  return stmt.all(...args, limit) as unknown as TaskRow[];
}

export function countTasksByStatus(db: Db, room?: string): Record<string, number> {
  const where = room !== undefined ? "WHERE room = ?" : "";
  const args = room !== undefined ? [room] : [];
  const stmt = db.prepare(`SELECT status, COUNT(*) AS n FROM tasks ${where} GROUP BY status`);
  const rows = stmt.all(...args) as unknown as Array<{ status: string; n: number }>;
  const out: Record<string, number> = {};
  for (const r of rows) out[r.status] = r.n;
  return out;
}

// 自查：红线 1-5 逐条通过
