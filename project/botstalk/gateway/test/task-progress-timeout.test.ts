import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import { handleTaskProgress, sweepTaskTimeouts, setTaskTimeoutMs } from "../src/router.js";
import { openDb, upsertTaskDispatch, getTask, getTaskProgress } from "../src/db.js";
import type { Hub } from "../src/hub.js";

class FakeHub {
  conns: Array<{ id: string; intents: Array<"chat" | "task"> }>;
  sent: Array<{ to: string; env: Envelope }> = [];
  taskEvents: Array<{ room: string; payload: Record<string, unknown> }> = [];
  private seq = 0;
  constructor(conns: Array<{ id: string; intents: Array<"chat" | "task"> }>) {
    this.conns = conns;
  }
  getOnlineAdapters(): string[] {
    return this.conns.map((c) => c.id);
  }
  getConn(id: string) {
    const f = this.conns.find((c) => c.id === id);
    return f ? { capabilities: { intents: f.intents } } : undefined;
  }
  sendTo(adapterId: string, env: Envelope): boolean {
    this.sent.push({ to: adapterId, env });
    return true;
  }
  broadcast(room: string, env: Envelope): void {}
  broadcastTaskEvent(room: string, payload: Record<string, unknown>): void {
    this.taskEvents.push({ room, payload });
  }
  nextSeq(): number {
    this.seq += 1;
    return this.seq;
  }
}

let db: ReturnType<typeof openDb>;
let dir: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "botstalk-test-"));
  db = openDb(join(dir, "test.db"));
});

afterEach(() => {
  db.close();
  rmSync(dir, { recursive: true, force: true });
});

const makeProgressEnv = (
  sender: string,
  taskId: string,
  message: string,
  data?: Record<string, unknown>
) =>
  makeEnvelope<MessagePayload>("message", sender, "room1", 1, 0, {
    msg_id: "m1",
    text: "report",
    mentions: [],
    intent: "task",
    task_id: taskId,
    task_progress: {
      task_id: taskId,
      message,
      ...(data !== undefined ? { data } : {}),
    },
  });

describe("task-progress-timeout", () => {
  describe("A. 行为对照", () => {
    it("上报成功", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() + 60000 });
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("bot-a", "t1", "50% done", { pct: 50 }), db);
      const task = getTask(db, "t1");
      expect(task!.progress_count).toBe(1);
      expect(hub.taskEvents).toHaveLength(1);
      expect(hub.taskEvents[0].payload.status).toBe("progress");
      expect((hub.taskEvents[0].payload as any).progress.message).toBe("50% done");
      expect(hub.taskEvents[0].payload.progress_count).toBe(1);
      const reply = hub.sent.find((s) => s.to === "bot-a");
      expect((reply?.env.payload as MessagePayload).text).toContain("TASK_PROGRESS_OK");
    });

    it("首次上报把 dispatched 转 running", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() + 60000 });
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("bot-a", "t1", "50% done"), db);
      expect(getTask(db, "t1")!.status).toBe("running");
    });

    it("多次上报 seq 递增", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() + 60000 });
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("bot-a", "t1", "10%"), db);
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("bot-a", "t1", "20%"), db);
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("bot-a", "t1", "30%"), db);
      const progs = getTaskProgress(db, "t1");
      expect(progs).toHaveLength(3);
      expect(progs.map((p: any) => p.message)).toEqual(["10%", "20%", "30%"]);
    });

    it("data 可选", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() + 60000 });
      handleTaskProgress(hub as unknown as Hub, makeEnvelope<MessagePayload>("message", "bot-a", "room1", 1, 0, { msg_id: "m1", text: "report", mentions: [], intent: "task", task_progress: { task_id: "t1", message: "no data" } }), db);
      const progs = getTaskProgress(db, "t1");
      expect(progs).toHaveLength(1);
      expect((progs[0] as any).data_json).toBeNull();
      const reply = hub.sent.find((s) => s.to === "bot-a");
      expect((reply?.env.payload as MessagePayload).text).toContain("TASK_PROGRESS_OK");
    });

    it("上报者非 assignee 被拒", () => {
      const hub = new FakeHub([{ id: "boss", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() + 60000 });
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("boss", "t1", "50% done"), db);
      const reply = hub.sent.find((s) => s.to === "boss");
      expect((reply?.env.payload as MessagePayload).text).toContain("TASK_PROGRESS_UNAUTHORIZED");
      expect(getTask(db, "t1")!.progress_count).toBe(0);
    });

    it("任务不存在", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("bot-a", "nope", "50% done"), db);
      const reply = hub.sent.find((s) => s.to === "bot-a");
      expect((reply?.env.payload as MessagePayload).text).toContain("TASK_PROGRESS_NOT_FOUND");
    });

    it("帧顶层 task_id 与 task_progress.task_id 不一致被拒", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() + 60000 });
      const env = makeEnvelope<MessagePayload>("message", "bot-a", "room1", 1, 0, { msg_id: "m1", text: "report", mentions: [], intent: "task", task_id: "other", task_progress: { task_id: "t1", message: "hi" } });
      handleTaskProgress(hub as unknown as Hub, env, db);
      const reply = hub.sent.find((s) => s.to === "bot-a");
      expect((reply?.env.payload as MessagePayload).text).toContain("TASK_PROGRESS_REJECTED");
      expect(getTask(db, "t1")!.progress_count).toBe(0);
    });

    it("终端态任务拒绝上报", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "done", deadline_ms: Date.now() + 60000 });
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("bot-a", "t1", "50% done"), db);
      const reply = hub.sent.find((s) => s.to === "bot-a");
      expect((reply?.env.payload as MessagePayload).text).toContain("TASK_PROGRESS_REJECTED");
    });
  });

  describe("B. 超时清扫", () => {
    it("过期任务被标 timed_out", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }, { id: "boss", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() - 1000 });
      sweepTaskTimeouts(hub as unknown as Hub, db, Date.now());
      const task = getTask(db, "t1");
      expect(task!.status).toBe("timed_out");
      expect(task!.error).toBe("Task timed out");
    });

    it("双通知", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }, { id: "boss", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() - 1000 });
      sweepTaskTimeouts(hub as unknown as Hub, db, Date.now());
      expect(hub.taskEvents.some((e) => e.payload.status === "timed_out")).toBe(true);
      expect(hub.sent.some((s) => s.to === "boss" && (s.env.payload as MessagePayload).text.includes("TASK_TIMEOUT"))).toBe(true);
      expect(hub.sent.some((s) => s.to === "bot-a" && (s.env.payload as MessagePayload).text.includes("TASK_TIMEOUT"))).toBe(true);
    });

    it("未过期不扫", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() + 60000 });
      sweepTaskTimeouts(hub as unknown as Hub, db, Date.now());
      expect(getTask(db, "t1")!.status).toBe("dispatched");
    });

    it("done 的过期任务不扫", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "done", deadline_ms: Date.now() - 1000 });
      sweepTaskTimeouts(hub as unknown as Hub, db, Date.now());
      expect(getTask(db, "t1")!.status).toBe("done");
    });

    it("严格边界", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      const deadline = Date.now();
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: deadline });
      sweepTaskTimeouts(hub as unknown as Hub, db, deadline);
      expect(getTask(db, "t1")!.status).toBe("dispatched");
    });
  });

  describe("C. 失败注入", () => {
    it("assignee 掉线仍能超时标记", () => {
      const hub = new FakeHub([{ id: "boss", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() - 1000 });
      sweepTaskTimeouts(hub as unknown as Hub, db, Date.now());
      expect(getTask(db, "t1")!.status).toBe("timed_out");
      expect(hub.sent.some((s) => s.to === "boss" && (s.env.payload as MessagePayload).text.includes("TASK_TIMEOUT"))).toBe(true);
      expect(hub.taskEvents.some((e) => e.payload.status === "timed_out")).toBe(true);
    });

    it("重复 sweep 幂等", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }, { id: "boss", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() - 1000 });
      sweepTaskTimeouts(hub as unknown as Hub, db, Date.now());
      const count = hub.taskEvents.length;
      sweepTaskTimeouts(hub as unknown as Hub, db, Date.now());
      expect(hub.taskEvents.length).toBe(count);
    });

    it("上报空 message 被拒", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() + 60000 });
      handleTaskProgress(hub as unknown as Hub, makeEnvelope<MessagePayload>("message", "bot-a", "room1", 1, 0, { msg_id: "m1", text: "report", mentions: [], intent: "task", task_progress: { task_id: "t1", message: "" } }), db);
      const reply = hub.sent.find((s) => s.to === "bot-a");
      expect((reply?.env.payload as MessagePayload).text).toContain("TASK_PROGRESS_REJECTED");
    });

    it("超时后上报被拒", () => {
      const hub = new FakeHub([{ id: "bot-a", intents: ["task"] }, { id: "boss", intents: ["task"] }]);
      upsertTaskDispatch(db, { task_id: "t1", room: "room1", owner: "boss", assignee: "bot-a", title: "do thing", status: "dispatched", deadline_ms: Date.now() - 1000 });
      sweepTaskTimeouts(hub as unknown as Hub, db, Date.now());
      handleTaskProgress(hub as unknown as Hub, makeProgressEnv("bot-a", "t1", "50% done"), db);
      const toBot = hub.sent.filter((s) => s.to === "bot-a");
      const reply = toBot[toBot.length - 1];
      expect((reply?.env.payload as MessagePayload).text).toContain("TASK_PROGRESS_REJECTED");
    });
  });
});
