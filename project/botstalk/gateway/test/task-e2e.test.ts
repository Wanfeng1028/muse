import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload, ApprovalRequestPayload, ApprovalDecisionPayload } from "@botstalk/protocol";
import type { Hub } from "../src/hub.js";
import { routeMessage, routeApprovalDecision, setTaskApprovalMode, setTaskTimeoutMs, sweepTaskTimeouts } from "../src/router.js";
import { openDb, getTask, getTaskProgress } from "../src/db.js";

class FakeHub {
  conns: Array<{ id: string; intents: Array<"chat" | "task"> }>;
  sent: Array<{ to: string; env: Envelope }>;
  broadcasted: Array<{ room: string; env: Envelope }>;
  taskEvents: Array<{ room: string; payload: Record<string, unknown> }>;
  private seq: number;

  constructor(conns: Array<{ id: string; intents: Array<"chat" | "task"> }>) {
    this.conns = conns;
    this.sent = [];
    this.broadcasted = [];
    this.taskEvents = [];
    this.seq = 0;
  }

  getOnlineAdapters(): string[] {
    return this.conns.map(c => c.id);
  }

  getConn(id: string) {
    const f = this.conns.find(c => c.id === id);
    return f ? { capabilities: { intents: f.intents } } : undefined;
  }

  sendTo(to: string, env: Envelope): boolean {
    this.sent.push({ to, env });
    return true;
  }

  broadcast(room: string, env: Envelope): void {
    this.broadcasted.push({ room, env });
  }

  broadcastTaskEvent(room: string, payload: Record<string, unknown>): void {
    this.taskEvents.push({ room, payload });
  }

  nextSeq(): number {
    return ++this.seq;
  }
}

let dir: string;
let db: ReturnType<typeof openDb>;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "botstalk-test-"));
  db = openDb(dir);
});

afterEach(() => {
  db.close();
  rmSync(dir, { recursive: true, force: true });
  setTaskTimeoutMs(300000);
  setTaskApprovalMode("off");
});

function mkHub(): FakeHub {
  return new FakeHub([
    { id: "boss", intents: ["chat"] },
    { id: "bot-a", intents: ["chat", "task"] }
  ]);
}

function dispatchEnv(taskId: string, text: string): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", "boss", "room1", 1, 0, { msg_id: "m1", text, mentions: ["bot-a"], intent: "task", task_id: taskId });
}

function progressEnv(taskId: string, message: string, data?: Record<string, unknown>): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", "bot-a", "room1", 2, 0, { msg_id: "m2", text: "", mentions: [], intent: "task", task_progress: { task_id: taskId, message, ...(data !== undefined ? { data } : {}) } });
}

function doneEnv(taskId: string): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", "bot-a", "room1", 3, 0, { msg_id: "m3", text: "done", mentions: [], intent: "task", task_id: taskId, task_status: "done" });
}

function lastTextTo(hub: FakeHub, to: string): string {
  const records = hub.sent.filter(s => s.to === to);
  const last = records[records.length - 1];
  return (last.env.payload as MessagePayload).text!;
}

describe("task e2e", () => {
  it("派发", () => {
    const hub = mkHub();
    routeMessage(hub as unknown as Hub, dispatchEnv("task-1", "do task 1"), db);
    expect(hub.sent.some(s => s.to === "bot-a")).toBe(true);
    expect(hub.taskEvents.some(e => e.payload.status === "dispatched")).toBe(true);
    const task = getTask(db, "task-1")!
    expect(task.assignee).toBe("bot-a");
    expect(task.deadline_ms).toBeGreaterThan(Date.now());
  });

  it("进度两轮", () => {
    const hub = mkHub();
    routeMessage(hub as unknown as Hub, dispatchEnv("task-t2", "do task t2"), db);
    routeMessage(hub as unknown as Hub, progressEnv("task-t2", "搜集中"), db);
    routeMessage(hub as unknown as Hub, progressEnv("task-t2", "整理中"), db);
    const progressEvents = hub.taskEvents.filter(e => e.payload.status === "progress");
    expect(progressEvents.map(e => e.payload.progress_count)).toEqual([1, 2]);
    const prog = getTaskProgress(db, "task-t2");
    expect(prog).toHaveLength(2);
    expect(prog.map(p => p.message)).toEqual(["搜集中", "整理中"]);
    expect(getTask(db, "task-t2")!.status).toBe("running");
  });

  it("完成", () => {
    const hub = mkHub();
    routeMessage(hub as unknown as Hub, dispatchEnv("task-t3", "do task t3"), db);
    routeMessage(hub as unknown as Hub, doneEnv("task-t3"), db);
    expect(getTask(db, "task-t3")!.status).toBe("done");
    expect(hub.taskEvents.some(e => e.payload.status === "done")).toBe(true);
  });

  it("超时全链路", () => {
    setTaskTimeoutMs(1000);
    const hub = mkHub();
    routeMessage(hub as unknown as Hub, dispatchEnv("task-2", "do task 2"), db);
    sweepTaskTimeouts(hub as unknown as Hub, db, Date.now() + 2000);
    const task = getTask(db, "task-2")!
    expect(task.status).toBe("timed_out");
    expect(task.error).toBe("Task timed out");
    expect(hub.taskEvents.some(e => e.payload.status === "timed_out")).toBe(true);
    expect(hub.sent.filter(s => s.to === "boss" && (s.env.payload as MessagePayload).text?.includes("TASK_TIMEOUT")).length).toBeGreaterThan(0);
    expect(hub.sent.filter(s => s.to === "bot-a" && (s.env.payload as MessagePayload).text?.includes("TASK_TIMEOUT")).length).toBeGreaterThan(0);
  });

  it("超时任务详情", () => {
    setTaskTimeoutMs(1000);
    const hub = mkHub();
    routeMessage(hub as unknown as Hub, dispatchEnv("task-5", "do task 5"), db);
    sweepTaskTimeouts(hub as unknown as Hub, db, Date.now() + 2000);
    expect(getTaskProgress(db, "task-5")).toEqual([]);
    const task = getTask(db, "task-5")!
    expect(task.progress_count).toBe(0);
  });

  it("审批门下 deadline 从放行起算", () => {
    setTaskApprovalMode("all");
    const hub = mkHub();
    routeMessage(hub as unknown as Hub, dispatchEnv("task-3", "do task 3"), db);
    const task = getTask(db, "task-3")!
    expect(task.status).toBe("pending_approval");
    expect(task.deadline_ms).toBeNull();
    const approvalBroadcast = hub.broadcasted.find(b => b.env.type === "approval_request");
    const approval_id = (approvalBroadcast!.env.payload as ApprovalRequestPayload).approval_id;
    routeApprovalDecision(hub as unknown as Hub, makeEnvelope<ApprovalDecisionPayload>("approval_decision", "boss", "room1", 9, 0, { approval_id, decision: "approve" }), db);
    const updatedTask = getTask(db, "task-3")!
    expect(updatedTask.status).toBe("dispatched");
    expect(updatedTask.deadline_ms).not.toBeNull();
  });
});