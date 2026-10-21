import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { DEFAULT_ROOM_TYPE, type RoomType } from "@botstalk/protocol";



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
      usage_out INTEGER NOT NULL DEFAULT 0,
      room TEXT
    );
  `);
  {
    const cols = db.prepare("PRAGMA table_info(presence)").all() as unknown as Array<{ name: string }>;
    if (!cols.some((c) => c.name === "room")) {
      db.exec("ALTER TABLE presence ADD COLUMN room TEXT");
    }
  }
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
  db.exec(`
      CREATE TABLE IF NOT EXISTS rooms (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL DEFAULT 'workroom',
        name TEXT,
        topic TEXT,
        owner TEXT,
        created_at_ms INTEGER NOT NULL
      );
    `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS room_members (
      room_id TEXT NOT NULL,
      adapter_id TEXT NOT NULL,
      persona_role TEXT,
      joined_at_ms INTEGER NOT NULL,
      PRIMARY KEY (room_id, adapter_id)
    );
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS game_sessions (
      id TEXT PRIMARY KEY,
      room_id TEXT NOT NULL,
      game TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT '{}',
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );
  `);
  db.exec("CREATE INDEX IF NOT EXISTS idx_game_sessions_room ON game_sessions(room_id);");
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
  room: string | null;
}

export function upsertPresence(
  db: Db,
  p: {
    adapter_id: string;
    status: string;
    last_seen_ms: number;
    usage_in: number;
    usage_out: number;
    room?: string | null;
  },
): void {
  const stmt = db.prepare(
    `INSERT INTO presence (adapter_id, status, last_seen_ms, usage_in, usage_out, room)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(adapter_id) DO UPDATE SET
       status = excluded.status,
       last_seen_ms = excluded.last_seen_ms,
       usage_in = excluded.usage_in,
       usage_out = excluded.usage_out,
       room = COALESCE(excluded.room, presence.room)`,
  );
  stmt.run(p.adapter_id, p.status, p.last_seen_ms, p.usage_in, p.usage_out, p.room ?? null);
}

export function getPresence(db: Db, adapter_id: string): PresenceRow | undefined {
  const stmt = db.prepare(
    "SELECT adapter_id, status, last_seen_ms, usage_in, usage_out, room FROM presence WHERE adapter_id = ?",
  );
  const row = stmt.get(adapter_id);
  return row as unknown as PresenceRow | undefined;
}

/**
 * 网关全局全量 presence。端点不再使用（改为 listPresenceForRoom 按 room 过滤）；
 * 保留导出供网关级用途及老调用方使用。
 */
export function listPresence(db: Db): PresenceRow[] {
  const stmt = db.prepare(
    "SELECT adapter_id, status, last_seen_ms, usage_in, usage_out, room FROM presence",
  );
  return stmt.all() as unknown as PresenceRow[];
}

/** 只返回指定房间的 presence。端点按 room 过滤用。 */
export function listPresenceForRoom(db: Db, room: string): PresenceRow[] {
  const stmt = db.prepare(
    "SELECT adapter_id, status, last_seen_ms, usage_in, usage_out, room FROM presence WHERE room = ?",
  );
  return stmt.all(room) as unknown as PresenceRow[];
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

export type TaskStatus = "dispatched" | "running" | "done" | "failed" | "unsupported" | "cancelled" | "pending_approval";

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

export interface RoomRow {
  id: string;
  type: RoomType;
  name: string | null;
  topic: string | null;
  owner: string | null;
  created_at_ms: number;
}

/** 建房间；type 缺省 'workroom'；id 冲突时让 SQLite 抛错（调用方保证唯一）；返回写入的行。 */
export function createRoom(
  db: Db,
  r: { id: string; type?: RoomType; name?: string; topic?: string; owner?: string },
): RoomRow {
  const now = Date.now();
  const stmt = db.prepare(
    "INSERT INTO rooms (id, type, name, topic, owner, created_at_ms) VALUES (?, ?, ?, ?, ?, ?)",
  );
  stmt.run(r.id, r.type ?? DEFAULT_ROOM_TYPE, r.name ?? null, r.topic ?? null, r.owner ?? null, now);
  const row = getRoom(db, r.id);
  if (!row) throw new Error("createRoom: row missing after insert");
  return row;
}

export function getRoom(db: Db, id: string): RoomRow | undefined {
  const stmt = db.prepare(
    "SELECT id, type, name, topic, owner, created_at_ms FROM rooms WHERE id = ?",
  );
  return stmt.get(id) as unknown as RoomRow | undefined;
}

export function listRooms(db: Db): RoomRow[] {
  const stmt = db.prepare(
    "SELECT id, type, name, topic, owner, created_at_ms FROM rooms ORDER BY created_at_ms ASC",
  );
  return stmt.all() as unknown as RoomRow[];
}

/** 改房间类型；房间不存在返回 false。 */
export function setRoomType(db: Db, id: string, type: RoomType): boolean {
  const stmt = db.prepare("UPDATE rooms SET type = ? WHERE id = ?");
  return Number(stmt.run(type, id).changes) > 0;
}

/** 改名/话题；只更新传入的字段；房间不存在返回 false。 */
export function updateRoom(db: Db, id: string, patch: { name?: string; topic?: string }): boolean {
  const sets: string[] = [];
  const args: Array<string | null> = [];
  if (patch.name !== undefined) { sets.push("name = ?"); args.push(patch.name); }
  if (patch.topic !== undefined) { sets.push("topic = ?"); args.push(patch.topic); }
  if (sets.length === 0) return getRoom(db, id) !== undefined;
  const stmt = db.prepare(`UPDATE rooms SET ${sets.join(", ")} WHERE id = ?`);
  return Number(stmt.run(...args, id).changes) > 0;
}

/**
 * 取房间类型。房间不存在（老数据/未注册）→ DEFAULT_ROOM_TYPE；
 * type 字段非法 → DEFAULT_ROOM_TYPE。保证总返回合法值。
 */
export function getRoomType(db: Db, id: string): RoomType {
  const row = getRoom(db, id);
  const t = row?.type;
  return t === "workroom" || t === "playroom" ? t : DEFAULT_ROOM_TYPE;
}

export interface RoomMemberRow {
  room_id: string;
  adapter_id: string;
  persona_role: string | null;
  joined_at_ms: number;
}

/** 加成员；已存在则更新 persona_role（upsert）。 */
export function addRoomMember(
  db: Db,
  room_id: string,
  adapter_id: string,
  persona_role?: string | null,
): void {
  const stmt = db.prepare(
    `INSERT INTO room_members (room_id, adapter_id, persona_role, joined_at_ms)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(room_id, adapter_id) DO UPDATE SET persona_role = excluded.persona_role`,
  );
  stmt.run(room_id, adapter_id, persona_role ?? null, Date.now());
}

/** 移除成员；不存在返回 false。 */
export function removeRoomMember(db: Db, room_id: string, adapter_id: string): boolean {
  const stmt = db.prepare("DELETE FROM room_members WHERE room_id = ? AND adapter_id = ?");
  return Number(stmt.run(room_id, adapter_id).changes) > 0;
}

export function listRoomMembers(db: Db, room_id: string): RoomMemberRow[] {
  const stmt = db.prepare(
    "SELECT room_id, adapter_id, persona_role, joined_at_ms FROM room_members WHERE room_id = ? ORDER BY joined_at_ms ASC",
  );
  return stmt.all(room_id) as unknown as RoomMemberRow[];
}

/** 设人设角色；成员不存在则先添加（upsert 语义）。 */
export function setPersonaRole(
  db: Db,
  room_id: string,
  adapter_id: string,
  role: string | null,
): void {
  addRoomMember(db, room_id, adapter_id, role);
}

/** 取人设角色；非成员返回 undefined。 */
export function getPersonaRole(
  db: Db,
  room_id: string,
  adapter_id: string,
): string | null | undefined {
  const stmt = db.prepare(
    "SELECT persona_role FROM room_members WHERE room_id = ? AND adapter_id = ?",
  );
  const row = stmt.get(room_id, adapter_id) as unknown as { persona_role: string | null } | undefined;
  return row === undefined ? undefined : row.persona_role;
}

export function countRoomMembers(db: Db, room_id: string): number {
  const stmt = db.prepare("SELECT COUNT(*) AS n FROM room_members WHERE room_id = ?");
  const row = stmt.get(room_id) as unknown as { n: number };
  return row.n;
}

export interface GameSessionRow {
  id: string;
  room_id: string;
  game: string;
  state: string;
  created_at_ms: number;
  updated_at_ms: number;
}

/** 开一局游戏；state 缺省 '{}'；id 冲突让 SQLite 抛错；返回写入的行。 */
export function createGameSession(
  db: Db,
  s: { id: string; room_id: string; game: string; state?: string },
): GameSessionRow {
  const now = Date.now();
  const stmt = db.prepare(
    "INSERT INTO game_sessions (id, room_id, game, state, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?)",
  );
  stmt.run(s.id, s.room_id, s.game, s.state ?? "{}", now, now);
  const row = getGameSession(db, s.id);
  if (!row) throw new Error("createGameSession: row missing after insert");
  return row;
}

export function getGameSession(db: Db, id: string): GameSessionRow | undefined {
  const stmt = db.prepare(
    "SELECT id, room_id, game, state, created_at_ms, updated_at_ms FROM game_sessions WHERE id = ?",
  );
  return stmt.get(id) as unknown as GameSessionRow | undefined;
}

export function listGameSessions(db: Db, room_id: string): GameSessionRow[] {
  const stmt = db.prepare(
    "SELECT id, room_id, game, state, created_at_ms, updated_at_ms FROM game_sessions WHERE room_id = ? ORDER BY created_at_ms DESC",
  );
  return stmt.all(room_id) as unknown as GameSessionRow[];
}

/** 更新游戏状态 JSON；同时刷新 updated_at_ms；不存在返回 false。 */
export function updateGameSessionState(db: Db, id: string, state: string): boolean {
  const stmt = db.prepare("UPDATE game_sessions SET state = ?, updated_at_ms = ? WHERE id = ?");
  return Number(stmt.run(state, Date.now(), id).changes) > 0;
}

/** 结束一局（删除）；不存在返回 false。 */
export function endGameSession(db: Db, id: string): boolean {
  const stmt = db.prepare("DELETE FROM game_sessions WHERE id = ?");
  return Number(stmt.run(id).changes) > 0;
}

export function countGameSessions(db: Db, room_id: string): number {
  const stmt = db.prepare("SELECT COUNT(*) AS n FROM game_sessions WHERE room_id = ?");
  const row = stmt.get(room_id) as unknown as { n: number };
  return row.n;
}

// 自查：红线 1-5 逐条通过
