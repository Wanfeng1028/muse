import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, getTask } from "../src/db.js";
import { createScheduledTask } from "../src/workflows.js";
import { sweepScheduledTasks, buildScheduledTaskEnvelope } from "../src/scheduler.js";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import type { Db } from "../src/db.js";
import type { Hub } from "../src/hub.js";

class FakeHub {
  sent: Array<{ to: string; env: Envelope<MessagePayload> }> = [];
  taskEvents: Array<{ room: string; payload: Record<string, unknown> }> = [];
  private seq = 0;
  constructor(private adapters: string[]) {}
  getOnlineAdapters(): string[] { return [...this.adapters]; }
  getConn(id: string): { capabilities: { intents: string[] } } | undefined {
    return this.adapters.includes(id) ? { capabilities: { intents: ["task", "chat"] } } : undefined;
  }
  sendTo(to: string, env: Envelope<MessagePayload>): boolean { this.sent.push({ to, env }); return true; }
  broadcast(_room: string, _env: Envelope<MessagePayload>): void {}
  broadcastTaskEvent(room: string, payload: Record<string, unknown>): void { this.taskEvents.push({ room, payload }); }
  nextSeq(): number { return ++this.seq; }
}

let dir: string;
let db: Db;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "wf-")); db = openDb(dir); });
afterEach(() => { db.close(); rmSync(dir, { recursive: true, force: true }); });

function makeDueTask(room: string, extra: Record<string, unknown> = {}) {
  const t = createScheduledTask(db, { room, name: "t", interval_sec: 3600, prompt: "做早报", owner: "u", ...(extra as { agent_id?: string }) });
  db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(Date.now() - 1000, t.id);
  return t;
}

describe("sweepScheduledTasks", () => {
  it("到期任务派发给指定执行者", () => {
    makeDueTask("r1", { agent_id: "agent1" });
    const hub = new FakeHub(["agent1"]);
    const n = sweepScheduledTasks(hub as unknown as Hub, db, Date.now());
    expect(n).toBe(1);
    expect(hub.sent).toHaveLength(1);
    expect(hub.sent[0].to).toBe("agent1");
    expect(hub.sent[0].env.sender).toBe("scheduler");
    expect(hub.sent[0].env.payload.intent).toBe("task");
    const taskId = hub.sent[0].env.payload.task_id as string;
    expect(getTask(db, taskId)?.status).toBe("dispatched");
    expect(getTask(db, taskId)?.owner).toBe("scheduler");
  });
  it("未到期不派发", () => {
    createScheduledTask(db, { room: "r1", name: "t", interval_sec: 3600, prompt: "p", owner: "u" });
    const hub = new FakeHub(["agent1"]);
    expect(sweepScheduledTasks(hub as unknown as Hub, db, Date.now())).toBe(0);
    expect(hub.sent).toHaveLength(0);
  });
  it("无执行者时记 unsupported", () => {
    makeDueTask("r1", { agent_id: "ghost" });
    const hub = new FakeHub([]);
    const n = sweepScheduledTasks(hub as unknown as Hub, db, Date.now());
    expect(n).toBe(1);
    expect(hub.sent).toHaveLength(0);
    const taskId = hub.taskEvents[0].payload["task_id"] as string;
    expect(getTask(db, taskId)?.status).toBe("unsupported");
  });
  it("不指定执行者时自动挑在线 adapter", () => {
    makeDueTask("r1");
    const hub = new FakeHub(["b", "a"]);
    sweepScheduledTasks(hub as unknown as Hub, db, Date.now());
    expect(hub.sent[0].to).toBe("a");
  });
});

describe("buildScheduledTaskEnvelope", () => {
  it("帧字段正确", () => {
    const hub = new FakeHub([]);
    const t = createScheduledTask(db, { room: "r9", name: "t", interval_sec: 60, prompt: "p", owner: "u", agent_id: "ag" });
    const env = buildScheduledTaskEnvelope(hub as unknown as Hub, t);
    expect(env.sender).toBe("scheduler");
    expect(env.room).toBe("r9");
    expect(env.payload.intent).toBe("task");
    expect(env.payload.mentions).toEqual(["ag"]);
    expect(env.payload.task_id).toBeTruthy();
  });
});