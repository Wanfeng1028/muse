import { randomUUID } from "node:crypto";
import type { Db } from "./db.js";

export interface ScheduledTask {
  id: string;
  room: string;
  name: string;
  enabled: 0 | 1;
  interval_sec: number;
  agent_id: string | null;
  task_title: string;
  prompt: string;
  owner: string;
  next_run_ms: number;
  last_run_ms: number | null;
  created_at_ms: number;
  updated_at_ms: number;
}

export interface NewScheduledTask {
  room: string;
  name: string;
  interval_sec: number;
  agent_id?: string | null;
  task_title?: string;
  prompt: string;
  owner: string;
}

export interface ScheduledTaskPatch {
  name?: string;
  enabled?: boolean;
  interval_sec?: number;
  agent_id?: string | null;
  task_title?: string;
  prompt?: string;
}

/**
 * 创建定时任务表和索引。
 */
export function ensureScheduledTaskTable(db: Db): void {
  db.prepare(
    `
    CREATE TABLE IF NOT EXISTS scheduled_tasks (
      id TEXT PRIMARY KEY,
      room TEXT NOT NULL,
      name TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      interval_sec INTEGER NOT NULL,
      agent_id TEXT,
      task_title TEXT NOT NULL,
      prompt TEXT NOT NULL,
      owner TEXT NOT NULL,
      next_run_ms INTEGER NOT NULL,
      last_run_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    )
  `,
  ).run();

  db.prepare(
    "CREATE INDEX IF NOT EXISTS idx_sched_room_next ON scheduled_tasks(room, next_run_ms)",
  ).run();
}

/**
 * 创建新定时任务。
 */
export function createScheduledTask(db: Db, input: NewScheduledTask): ScheduledTask {
  const id = randomUUID();
  const now = Date.now();
  const title =
    input.task_title ?? input.prompt.trim().slice(0, 40).trimEnd();

  const stmt = db.prepare(
    `
    INSERT INTO scheduled_tasks (
      id, room, name, enabled, interval_sec, agent_id,
      task_title, prompt, owner, next_run_ms, last_run_ms,
      created_at_ms, updated_at_ms
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
  );

  // 默认 enabled = 1
  stmt.run(
    id,
    input.room,
    input.name,
    1, // enabled
    input.interval_sec,
    input.agent_id ?? null,
    title,
    input.prompt,
    input.owner,
    now + input.interval_sec * 1000, // next_run_ms
    null, // last_run_ms
    now, // created_at_ms
    now, // updated_at_ms
  );

  // 返回完整的 ScheduledTask 对象
  return {
    id,
    room: input.room,
    name: input.name,
    enabled: 1,
    interval_sec: input.interval_sec,
    agent_id: input.agent_id ?? null,
    task_title: title,
    prompt: input.prompt,
    owner: input.owner,
    next_run_ms: now + input.interval_sec * 1000,
    last_run_ms: null,
    created_at_ms: now,
    updated_at_ms: now,
  };
}

/**
 * 列出指定 room 的所有定时任务，按创建时间升序。
 */
export function listScheduledTasks(db: Db, room: string): ScheduledTask[] {
  const stmt = db.prepare(
    "SELECT id, room, name, enabled, interval_sec, agent_id, task_title, prompt, owner, next_run_ms, last_run_ms, created_at_ms, updated_at_ms FROM scheduled_tasks WHERE room = ? ORDER BY created_at_ms ASC",
  );
  return stmt.all(room) as unknown as ScheduledTask[];
}

/**
 * 根据 ID 获取单个定时任务。
 */
export function getScheduledTask(db: Db, id: string): ScheduledTask | undefined {
  const stmt = db.prepare(
    "SELECT id, room, name, enabled, interval_sec, agent_id, task_title, prompt, owner, next_run_ms, last_run_ms, created_at_ms, updated_at_ms FROM scheduled_tasks WHERE id = ?",
  );
  return stmt.get(id) as unknown as ScheduledTask | undefined;
}

/**
 * 更新定时任务，应用补丁。
 */
export function updateScheduledTask(
  db: Db,
  id: string,
  patch: ScheduledTaskPatch,
): ScheduledTask | undefined {
  const existing = getScheduledTask(db, id);
  if (!existing) return undefined;

  const updates: string[] = [];
  const params: (string | number | null)[] = [];

  if (patch.name !== undefined) {
    updates.push("name = ?");
    params.push(patch.name);
  }
  if (patch.enabled !== undefined) {
    updates.push("enabled = ?");
    params.push(patch.enabled ? 1 : 0);
  }
  if (patch.interval_sec !== undefined) {
    updates.push("interval_sec = ?");
    params.push(patch.interval_sec);
    // 当 interval_sec 变更时，更新 next_run_ms
    updates.push("next_run_ms = ?");
    params.push(Date.now() + patch.interval_sec * 1000);
  }
  if (patch.agent_id !== undefined) {
    updates.push("agent_id = ?");
    params.push(patch.agent_id);
  }
  if (patch.task_title !== undefined) {
    updates.push("task_title = ?");
    params.push(patch.task_title);
  }
  if (patch.prompt !== undefined) {
    updates.push("prompt = ?");
    params.push(patch.prompt);
  }

  if (updates.length === 0) return existing;

  updates.push("updated_at_ms = ?");
  params.push(Date.now());

  const setClause = updates.join(", ");
  params.push(id);

  const stmt = db.prepare(
    `UPDATE scheduled_tasks SET ${setClause} WHERE id = ?`,
  );
  const info = stmt.run(...params);

  if (info.changes > 0) {
    // 返回更新后的完整对象
    const updatedAt = Date.now();
    const nextRunMs =
      patch.interval_sec !== undefined
        ? updatedAt + patch.interval_sec * 1000
        : existing.next_run_ms;
    const lastRunMs = existing.last_run_ms; // 保持原 last_run_ms，除非有专门的字段
    return {
      ...existing,
      ...(patch.name !== undefined && { name: patch.name }),
      ...(patch.enabled !== undefined && {
        enabled: patch.enabled ? (1 as const) : (0 as const),
      }),
      ...(patch.interval_sec !== undefined && {
        interval_sec: patch.interval_sec,
        next_run_ms: nextRunMs,
      }),
      ...(patch.agent_id !== undefined && { agent_id: patch.agent_id }),
      ...(patch.task_title !== undefined && { task_title: patch.task_title }),
      ...(patch.prompt !== undefined && { prompt: patch.prompt }),
      updated_at_ms: updatedAt,
    };
  }
  return existing;
}

/**
 * 删除定时任务，返回是否成功。
 */
export function deleteScheduledTask(db: Db, id: string): boolean {
  const stmt = db.prepare("DELETE FROM scheduled_tasks WHERE id = ?");
  const info = stmt.run(id);
  return Number(info.changes) > 0;
}

/**
 * 获取所有到期的任务，并更新 next_run_ms，last_run_ms。
 */
export function claimDueScheduledTasks(db: Db, nowMs: number): ScheduledTask[] {
  // 1) SELECT 启用且已到期的任务，按 next_run_ms 升序
  const selectStmt = db.prepare(
    "SELECT id, room, name, enabled, interval_sec, agent_id, task_title, prompt, owner, next_run_ms, last_run_ms, created_at_ms, updated_at_ms FROM scheduled_tasks WHERE enabled = 1 AND next_run_ms <= ? ORDER BY next_run_ms ASC",
  );
  const dueList = selectStmt.all(nowMs) as unknown as ScheduledTask[];

  const claimed: ScheduledTask[] = [];

  for (const task of dueList) {
    const newNext = nowMs + task.interval_sec * 1000;
    const updateStmt = db.prepare(
      "UPDATE scheduled_tasks SET next_run_ms = ?, last_run_ms = ?, updated_at_ms = ? WHERE id = ? AND next_run_ms <= ? AND enabled = 1",
    );
    const info = updateStmt.run(newNext, nowMs, Date.now(), task.id, task.next_run_ms);

    if (info.changes > 0) {
      claimed.push({
        ...task,
        next_run_ms: newNext,
        last_run_ms: nowMs,
        updated_at_ms: Date.now(),
      });
    }
  }

  return claimed;
}

/**
 * 验证新建/更新定时任务的输入字段。
 */
export function validateScheduledTaskInput(input: {
  name?: unknown;
  interval_sec?: unknown;
  prompt?: unknown;
}): string | null {
  // 验证 name
  const nameRaw = input.name;
  if (typeof nameRaw !== "string" || !nameRaw.trim()) {
    return "名称不能为空";
  }

  // 验证 interval_sec
  const intervalRaw = input.interval_sec;
  const intervalNum = typeof intervalRaw === "number"
    ? intervalRaw
    : Number(intervalRaw);
  if (!Number.isInteger(intervalNum) || intervalNum < 60 || intervalNum > 2592000) {
    return "间隔秒数须为 60~2592000 的整数";
  }

  // 验证 prompt
  const promptRaw = input.prompt;
  if (typeof promptRaw !== "string" || !promptRaw.trim()) {
    return "任务内容不能为空";
  }

  return null;
}

export interface TriggerRule {
  id: string;
  room: string;
  name: string;
  enabled: 0 | 1;
  match_type: "keyword" | "sender" | "event";
  pattern: string;
  agent_id: string | null;
  task_title: string;
  prompt: string;
  owner: string;
  cooldown_sec: number;
  last_fired_ms: number | null;
  created_at_ms: number;
  updated_at_ms: number;
}

export interface NewTriggerRule {
  room: string;
  name: string;
  match_type: "keyword" | "sender" | "event";
  pattern: string;
  agent_id?: string | null;
  task_title?: string;
  prompt: string;
  owner: string;
  cooldown_sec?: number;
}

export interface TriggerRulePatch {
  name?: string;
  enabled?: boolean;
  match_type?: "keyword" | "sender" | "event";
  pattern?: string;
  agent_id?: string | null;
  task_title?: string;
  prompt?: string;
  cooldown_sec?: number;
}

export function ensureTriggerRuleTable(db: Db): void {
  // 创建表及索引
  db.prepare(
    `
    CREATE TABLE IF NOT EXISTS trigger_rules(
      id TEXT PRIMARY KEY,
      room TEXT NOT NULL,
      name TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      match_type TEXT NOT NULL,
      pattern TEXT NOT NULL,
      agent_id TEXT,
      task_title TEXT NOT NULL,
      prompt TEXT NOT NULL,
      owner TEXT NOT NULL,
      cooldown_sec INTEGER NOT NULL DEFAULT 300,
      last_fired_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    )
    `
  ).run();
  // 房间索引，提升按房间查询性能
  db.prepare(`CREATE INDEX IF NOT EXISTS idx_trig_room ON trigger_rules(room)`).run();
}

export function createTriggerRule(db: Db, input: NewTriggerRule): TriggerRule {
  const id = randomUUID();
  const now = Date.now();
  // 默认冷却时间
  const cooldown_sec = input.cooldown_sec ?? 300;
  // 若未提供 task_title，则用 prompt 截取前 40 个字符
  const task_title = input.task_title ?? input.prompt.replace(/\s+/g, "").slice(0, 40);
  const enabled = 1 as const;

  db.prepare(
    `
    INSERT INTO trigger_rules(
      id, room, name, enabled, match_type, pattern,
      agent_id, task_title, prompt, owner, cooldown_sec,
      last_fired_ms, created_at_ms, updated_at_ms
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `
  ).run(
    id,
    input.room,
    input.name,
    enabled,
    input.match_type,
    input.pattern,
    input.agent_id ?? null,
    task_title,
    input.prompt,
    input.owner,
    cooldown_sec,
    null,
    now,
    now
  );

  // 构建返回值对象
  return {
    id,
    room: input.room,
    name: input.name,
    enabled,
    match_type: input.match_type,
    pattern: input.pattern,
    agent_id: input.agent_id ?? null,
    task_title,
    prompt: input.prompt,
    owner: input.owner,
    cooldown_sec,
    last_fired_ms: null,
    created_at_ms: now,
    updated_at_ms: now,
  } as unknown as TriggerRule;
}

export function listTriggerRules(db: Db, room: string): TriggerRule[] {
  // 按创建时间升序获取房间内所有规则
  return db.prepare(`SELECT * FROM trigger_rules WHERE room = ? ORDER BY created_at_ms ASC`).all(room) as unknown as TriggerRule[];
}

export function getTriggerRule(db: Db, id: string): TriggerRule | undefined {
  return db.prepare(`SELECT * FROM trigger_rules WHERE id = ?`).get(id) as unknown as TriggerRule | undefined;
}

export function updateTriggerRule(db: Db, id: string, patch: TriggerRulePatch): TriggerRule | undefined {
  const existing = getTriggerRule(db, id);
  if (!existing) return undefined;
  const now = Date.now();
  const updates: string[] = [];
  const params: Array<string | number | null> = [];

  if (patch.name !== undefined) {
    updates.push("name = ?");
    params.push(patch.name);
  }
  if (patch.enabled !== undefined) {
    updates.push("enabled = ?");
    params.push(patch.enabled ? 1 : 0);
  }
  if (patch.match_type !== undefined) {
    updates.push("match_type = ?");
    params.push(patch.match_type);
  }
  if (patch.pattern !== undefined) {
    updates.push("pattern = ?");
    params.push(patch.pattern);
  }
  if (patch.agent_id !== undefined) {
    updates.push("agent_id = ?");
    params.push(patch.agent_id ?? null);
  }
  if (patch.task_title !== undefined) {
    updates.push("task_title = ?");
    params.push(patch.task_title);
  }
  if (patch.prompt !== undefined) {
    updates.push("prompt = ?");
    params.push(patch.prompt);
  }
  if (patch.cooldown_sec !== undefined) {
    updates.push("cooldown_sec = ?");
    params.push(patch.cooldown_sec);
  }
  if (updates.length === 0) return existing;

  updates.push("updated_at_ms = ?");
  params.push(now);
  params.push(id);

  const sql = `UPDATE trigger_rules SET ${updates.join(", ")} WHERE id = ?`;
  const result = db.prepare(sql).run(...params);
  if (result.changes === 0) return undefined;

  // 查询最新行返回
  return db.prepare(`SELECT * FROM trigger_rules WHERE id = ?`).get(id) as unknown as TriggerRule;
}

export function deleteTriggerRule(db: Db, id: string): boolean {
  const result = db.prepare(`DELETE FROM trigger_rules WHERE id = ?`).run(id);
  return result.changes > 0;
}

export function validateTriggerRuleInput(input: { name?: unknown; match_type?: unknown; pattern?: unknown; prompt?: unknown; cooldown_sec?: unknown }): string | null {
  if (!input.name || typeof input.name !== "string" || input.name.trim() === "") {
    return "名称不能为空";
  }
  if (!["keyword", "sender", "event"].includes(input.match_type as string)) {
    return "匹配类型须为 keyword/sender/event";
  }
  if (!input.pattern || typeof input.pattern !== "string" || input.pattern.trim() === "") {
    return "匹配模式不能为空";
  }
  if (input.match_type === "keyword") {
    const words = (input.pattern as string).split(",").map((w) => w.trim()).filter(Boolean);
    if (words.length === 0) {
      return "关键词不能为空";
    }
  }
  if (!input.prompt || typeof input.prompt !== "string" || input.prompt.trim() === "") {
    return "任务内容不能为空";
  }
  if (input.cooldown_sec !== undefined) {
    const n = Number(input.cooldown_sec);
    if (!Number.isInteger(n) || n < 0) {
      return "冷却秒数须为非负整数";
    }
  }
  return null;
}

export function renderTemplate(tpl: string, vars: { text: string; sender: string; room: string }): string {
  let result = tpl;
  result = result.replace(/{text}/g, vars.text);
  result = result.replace(/{sender}/g, vars.sender);
  result = result.replace(/{room}/g, vars.room);
  return result;
}

export function ruleMatches(rule: TriggerRule, env: { sender: string; payload: { intent?: string; text?: string; task_status?: string } }): boolean {
  if (env.payload.intent === "chat") {
    if (rule.match_type === "keyword") {
      const words = rule.pattern.split(",").map((w) => w.trim().toLowerCase()).filter(Boolean);
      const text = env.payload.text ?? "";
      return words.some((w) => text.toLowerCase().includes(w));
    }
    if (rule.match_type === "sender") {
      return env.sender === rule.pattern;
    }
  } else if (env.payload.intent === "task") {
    if (rule.match_type === "event") {
      return env.payload.task_status !== undefined && env.payload.task_status === rule.pattern;
    }
  }
  return false;
}

export function claimTriggerFire(db: Db, id: string, nowMs: number): TriggerRule | undefined {
  const rule = getTriggerRule(db, id);
  if (!rule || rule.enabled !== 1) return undefined;
  const oldLastFired = rule.last_fired_ms;
  if (oldLastFired !== null && nowMs - oldLastFired < rule.cooldown_sec * 1000) {
    return undefined;
  }
  // 使用乐观锁更新 last_fired_ms
  const sql = `
    UPDATE trigger_rules
    SET last_fired_ms = ?, updated_at_ms = ?
    WHERE id = ? AND ((last_fired_ms IS NULL AND ? IS NULL) OR last_fired_ms = ?)
  `;
  const params = [nowMs, nowMs, id, oldLastFired, oldLastFired];
  const result = db.prepare(sql).run(...params);
  if (result.changes === 0) return undefined;
  // 返回更新后的规则对象
  return db.prepare(`SELECT * FROM trigger_rules WHERE id = ?`).get(id) as unknown as TriggerRule;
}