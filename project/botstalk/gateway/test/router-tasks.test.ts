import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import { routeMessage } from "../src/router.js";
import { openDb, getTask } from "../src/db.js";
import type { DatabaseSync } from "node:sqlite";
import type { Hub } from "../src/hub.js";

type Intents = ("chat" | "task")[];

interface ConnSpec {
  id: string;
  intents: Intents;
}

class FakeHub {
  conns: ConnSpec[];
  sent: Array<{ to: string; env: Envelope<MessagePayload> }> = [];
  broadcasted: Array<{ room: string; env: Envelope<MessagePayload> }> = [];
  taskEvents: Array<{ room: string; payload: Record<string, unknown> }> = [];
  private seq = 0;

  constructor(conns: ConnSpec[]) {
    this.conns = conns;
  }

  getOnlineAdapters(): string[] {
    return this.conns.map((c) => c.id);
  }

  getConn(id: string): { capabilities: { intents: Intents } } | undefined {
    const found = this.conns.find((c) => c.id === id);
    if (!found) return undefined;
    return { capabilities: { intents: found.intents } };
  }

  sendTo(adapterId: string, env: Envelope<MessagePayload>): boolean {
    this.sent.push({ to: adapterId, env });
    return true;
  }

  broadcast(room: string, env: Envelope<MessagePayload>, _exclude?: string): void {
    this.broadcasted.push({ room, env });
  }

  broadcastTaskEvent(room: string, payload: Record<string, unknown>): void {
    this.taskEvents.push({ room, payload });
  }

  nextSeq(): number {
    this.seq += 1;
    return this.seq;
  }
}

const TEST_TMP_ROOT = join(import.meta.dirname ?? __dirname, "test-tmp");
mkdirSync(TEST_TMP_ROOT, { recursive: true });
let dir: string;
let db: DatabaseSync;

beforeEach(() => {
  dir = mkdtempSync(join(TEST_TMP_ROOT, "router-tasks-"));
  db = openDb(dir);
});

afterEach(() => {
  db.close();
  rmSync(dir, { recursive: true, force: true });
});

function asHub(h: FakeHub): Hub {
  return h as unknown as Hub;
}

function mkUserEnv(payload: Partial<MessagePayload> & Record<string, unknown>): Envelope<MessagePayload> {
  return makeEnvelope("message", "user", "room1", 1, 0, payload as MessagePayload);
}

function mkEchoEnv(payload: Partial<MessagePayload> & Record<string, unknown>): Envelope<MessagePayload> {
  return makeEnvelope("message", "echo", "room1", 1, 0, payload as MessagePayload);
}

describe("routeMessage task dispatch", () => {
  it("a. dispatches to @echo and writes ledger", () => {
    const hub = new FakeHub([{ id: "echo", intents: ["chat", "task"] }]);
    const env = mkUserEnv({
      msg_id: "m1",
      text: "帮我写个日报",
      mentions: ["echo"],
      intent: "task",
      task_id: "t1",
    });

    routeMessage(asHub(hub), env, db);

    const sentToEcho = hub.sent.find((s) => s.to === "echo");
    expect(sentToEcho).toBeDefined();
    expect(sentToEcho!.env).toBe(env);

    const dispatchEvent = hub.taskEvents.find(
      (e) => e.payload.status === "dispatched" && e.payload.assignee === "echo" && e.payload.task_id === "t1",
    );
    expect(dispatchEvent).toBeDefined();
    expect(dispatchEvent!.room).toBe("room1");

    const row = getTask(db, "t1");
    expect(row).toBeDefined();
    expect(row!.status).toBe("dispatched");
    expect(row!.owner).toBe("user");
    expect(row!.title).toBe("帮我写个日报");
    expect(row!.assignee).toBe("echo");
  });

  it("b. picks lexicographically first adapter when no mentions", () => {
    const hub = new FakeHub([
      { id: "zed", intents: ["chat", "task"] },
      { id: "amy", intents: ["chat", "task"] },
    ]);
    const env = mkUserEnv({
      msg_id: "m2",
      text: "task please",
      mentions: [],
      intent: "task",
      task_id: "t2b",
    });

    routeMessage(asHub(hub), env, db);

    const sentTo = hub.sent.map((s) => s.to);
    expect(sentTo).toContain("amy");
    expect(sentTo).not.toContain("zed");

    const dispatchEvent = hub.taskEvents.find((e) => e.payload.status === "dispatched");
    expect(dispatchEvent).toBeDefined();
    expect(dispatchEvent!.payload.assignee).toBe("amy");
  });

  it("c. mentions limit candidate set", () => {
    const hub = new FakeHub([
      { id: "zed", intents: ["chat", "task"] },
      { id: "amy", intents: ["chat", "task"] },
    ]);
    const env = mkUserEnv({
      msg_id: "m3",
      text: "task please",
      mentions: ["zed"],
      intent: "task",
      task_id: "t2c",
    });

    routeMessage(asHub(hub), env, db);

    const sentTo = hub.sent.map((s) => s.to);
    expect(sentTo).toContain("zed");
    expect(sentTo).not.toContain("amy");

    const dispatchEvent = hub.taskEvents.find((e) => e.payload.status === "dispatched");
    expect(dispatchEvent).toBeDefined();
    expect(dispatchEvent!.payload.assignee).toBe("zed");
  });

  it("d. unsupported when no adapter supports task", () => {
    // user 本人是在线的（否则网关不会回 unsupported 回执）
    const hub = new FakeHub([
      { id: "user", intents: ["chat"] },
      { id: "c", intents: ["chat"] },
    ]);
    const env = mkUserEnv({
      msg_id: "m4",
      text: "task please",
      mentions: [],
      intent: "task",
      task_id: "t4",
    });

    routeMessage(asHub(hub), env, db);

    const sentToAdapters = hub.sent.filter((s) => s.to === "c");
    expect(sentToAdapters).toHaveLength(0);

    const row = getTask(db, "t4");
    expect(row).toBeDefined();
    expect(row!.status).toBe("unsupported");
    expect(row!.assignee).toBeNull();

    const unsupportedEvent = hub.taskEvents.find((e) => e.payload.status === "unsupported");
    expect(unsupportedEvent).toBeDefined();
    expect(typeof unsupportedEvent!.payload.note).toBe("string");
    expect((unsupportedEvent!.payload.note as string).length).toBeGreaterThan(0);

    const receipt = hub.sent.find((s) => s.to === "user");
    expect(receipt).toBeDefined();
    const payload = receipt!.env.payload as MessagePayload & { task_status?: string };
    expect(payload.task_status).toBe("unsupported");
  });

  it("e. receipt running updates ledger and broadcasts", () => {
    const hub = new FakeHub([{ id: "echo", intents: ["chat", "task"] }]);
    const dispatchEnv = mkUserEnv({
      msg_id: "m1e",
      text: "帮我写个日报",
      mentions: ["echo"],
      intent: "task",
      task_id: "t2",
    });
    routeMessage(asHub(hub), dispatchEnv, db);

    const receiptEnv = mkEchoEnv({
      msg_id: "m9",
      text: "[echo] task accepted",
      mentions: [],
      intent: "task",
      task_id: "t2",
      task_status: "running",
    });
    routeMessage(asHub(hub), receiptEnv, db);

    const row = getTask(db, "t2");
    expect(row).toBeDefined();
    expect(row!.status).toBe("running");

    const runningEvent = hub.taskEvents.find(
      (e) => e.payload.status === "running" && e.payload.assignee === "echo",
    );
    expect(runningEvent).toBeDefined();
    expect(runningEvent!.payload.task_id).toBe("t2");

    const broadcasted = hub.broadcasted.find((b) => b.env === receiptEnv);
    expect(broadcasted).toBeDefined();
    expect(broadcasted!.room).toBe("room1");
  });

  it("f. receipt done updates ledger", () => {
    const hub = new FakeHub([{ id: "echo", intents: ["chat", "task"] }]);
    const dispatchEnv = mkUserEnv({
      msg_id: "m1f",
      text: "帮我写个日报",
      mentions: ["echo"],
      intent: "task",
      task_id: "t2f",
    });
    routeMessage(asHub(hub), dispatchEnv, db);

    const runningEnv = mkEchoEnv({
      msg_id: "m9f",
      text: "[echo] task accepted",
      mentions: [],
      intent: "task",
      task_id: "t2f",
      task_status: "running",
    });
    routeMessage(asHub(hub), runningEnv, db);

    const doneEnv = mkEchoEnv({
      msg_id: "m10f",
      text: "[echo] task done",
      mentions: [],
      intent: "task",
      task_id: "t2f",
      task_status: "done",
    });
    routeMessage(asHub(hub), doneEnv, db);

    const row = getTask(db, "t2f");
    expect(row).toBeDefined();
    expect(row!.status).toBe("done");
  });

  it("g. receipt without task_id falls back to msg_id and does not write ledger", () => {
    const hub = new FakeHub([{ id: "echo", intents: ["chat", "task"] }]);
    const env = mkEchoEnv({
      msg_id: "mx",
      text: "x",
      mentions: [],
      intent: "task",
      task_status: "failed",
    });

    expect(() => routeMessage(asHub(hub), env, db)).not.toThrow();

    const failedEvent = hub.taskEvents.find((e) => e.payload.status === "failed");
    expect(failedEvent).toBeDefined();
    expect(failedEvent!.payload.task_id).toBe("mx");

    expect(getTask(db, "mx")).toBeUndefined();
  });

  it("i. title strips leading @mentions", () => {
    const hub = new FakeHub([{ id: "echo", intents: ["chat", "task"] }]);
    const env = mkUserEnv({
      msg_id: "m9",
      text: "@echo @zed 把本周 AI 新闻整理成早报",
      mentions: ["echo"],
      intent: "task",
      task_id: "t9",
    });
    routeMessage(asHub(hub), env, db);
    const row = getTask(db, "t9");
    expect(row).toBeDefined();
    expect(row!.title).toBe("把本周 AI 新闻整理成早报");
    const midMention = mkUserEnv({
      msg_id: "m10",
      text: "请 @echo 帮忙写日报",
      mentions: ["echo"],
      intent: "task",
      task_id: "t10",
    });
    routeMessage(asHub(hub), midMention, db);
    expect(getTask(db, "t10")!.title).toBe("请 @echo 帮忙写日报");
  });

  it("h. long title is truncated to 80 chars plus ellipsis", () => {
    const hub = new FakeHub([{ id: "echo", intents: ["chat", "task"] }]);
    const longText = "a".repeat(100);
    const env = mkUserEnv({
      msg_id: "m8",
      text: longText,
      mentions: ["echo"],
      intent: "task",
      task_id: "t3",
    });

    routeMessage(asHub(hub), env, db);

    const row = getTask(db, "t3");
    expect(row).toBeDefined();
    expect(row!.title.length).toBe(81);
    expect(row!.title.endsWith("…")).toBe(true);
  });
});
