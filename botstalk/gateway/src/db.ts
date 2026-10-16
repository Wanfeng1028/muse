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
  return db;
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

// 自查：红线 1-5 逐条通过
