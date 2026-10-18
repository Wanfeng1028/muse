
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload, StreamPayload } from "@botstalk/protocol";
import { routeMessage, routeStream } from "../src/router.js";
import type { Hub } from "../src/hub.js";
import { openDb, createRoom, getRoomHistory } from "../src/db.js";
import type { Db } from "../src/db.js";

interface FakeHub {
  conns: Set<string>;
  sent: Map<string, Envelope[]>;
  broadcasts: { room: string; env: Envelope }[];
  taskEvents: { room: string; payload: unknown }[];
  seq: number;
  getConn(id: string): unknown;
  sendTo(id: string, env: Envelope): boolean;
  broadcast(room: string, env: Envelope): void;
  broadcastTaskEvent(room: string, payload: unknown): void;
  nextSeq(): number;
  getOnlineAdapters(): string[];
}

function makeFakeHub(): FakeHub {
  const hub: FakeHub = {
    conns: new Set<string>(),
    sent: new Map<string, Envelope[]>(),
    broadcasts: [],
    taskEvents: [],
    seq: 0,
    getConn(id: string) {
      return this.conns.has(id)
        ? { adapterId: id, capabilities: { intents: ["chat", "task"] } }
        : undefined;
    },
    getOnlineAdapters() { return [...this.conns]; },
    sendTo(id: string, env: Envelope) {
      const arr = this.sent.get(id) ?? [];
      arr.push(env);
      this.sent.set(id, arr);
      return true;
    },
    broadcast(room: string, env: Envelope) { this.broadcasts.push({ room, env }); },
    broadcastTaskEvent(room: string, payload: unknown) { this.taskEvents.push({ room, payload }); },
    nextSeq() { this.seq += 1; return this.seq; },
  };
  return hub;
}

let db: Db;
let tmpDir: string;

beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), "rooms-router-r2-"));
  db = openDb(tmpDir);
  createRoom(db, { id: "workroom", type: "workroom" });
  createRoom(db, { id: "playroom", type: "playroom" });
});

afterEach(() => {
  (db as unknown as { close(): void }).close();
  rmSync(tmpDir, { recursive: true, force: true });
});

function chatEnv(
  sender: string,
  room: string,
  text: string,
  mentions: string[],
  overrides?: { intent?: "chat" | "task"; task_status?: string; task_id?: string; msg_id?: string },
): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>(
    "message",
    sender,
    room,
    1,
    0,
    {
      msg_id: overrides?.msg_id ?? `m-${sender}-${room}`,
      text,
      mentions,
      intent: overrides?.intent ?? "chat",
      task_status: overrides?.task_status as MessagePayload["task_status"],
      task_id: overrides?.task_id,
    },
  );
}

describe("rooms-router.r2", () => {
  it("r2-01 未注册房间回落到 workroom：有 mentions 时走定向分支", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    const env = chatEnv("alice", "ghost-room", "hello @bob", ["bob"]);
    routeMessage(hub as unknown as Hub, env, db);

    // workroom 定向：bob 收到 1 份，alice 收到自己 1 份副本
    expect(hub.sent.get("bob")).toEqual([env]);
    expect(hub.sent.get("alice")).toEqual([env]);
    // 无广播（定向分支不广播）
    expect(hub.broadcasts).toEqual([]);
  });

  it("r2-02 playroom 广播：sender 自己也收到广播（broadcast 不排除 sender）", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    const env = chatEnv("alice", "playroom", "lol", []);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0]).toEqual({ room: "playroom", env });
    // 定向路径未触发
    expect(hub.sent.size).toBe(0);
  });

  it("r2-03 playroom 即使带 mentions 也走广播，不做定向", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    hub.conns.add("carol");
    const env = chatEnv("alice", "playroom", "hi @bob @carol", ["bob", "carol"]);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0]).toEqual({ room: "playroom", env });
    expect(hub.sent.size).toBe(0);
  });

  it("r2-04 workroom 定向：被@者离线、sender 在线 → sender 仍收到自己 1 份", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice"); // sender 在线
    // bob 不在线
    const env = chatEnv("alice", "workroom", "ping @bob", ["bob"]);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.get("bob")).toBeUndefined();
    expect(hub.sent.get("alice")).toEqual([env]);
    expect(hub.broadcasts).toEqual([]);
  });

  it("r2-05 workroom 定向：sender 离线、被@者在线 → 被@者 1 份，sender 无投递", () => {
    const hub = makeFakeHub();
    // alice 不在线
    hub.conns.add("bob");
    const env = chatEnv("alice", "workroom", "ping @bob", ["bob"]);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.get("bob")).toEqual([env]);
    expect(hub.sent.get("alice")).toBeUndefined();
    expect(hub.broadcasts).toEqual([]);
  });

  it("r2-06 mentions 含空字符串：getConn 返回 undefined，跳过不崩", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    const env = chatEnv("alice", "workroom", "hi", ["", "bob"]);
    routeMessage(hub as unknown as Hub, env, db);

    // 空字符串 getConn 返回 undefined，被跳过；bob 收到；alice 收到自己副本
    expect(hub.sent.get("")).toBeUndefined();
    expect(hub.sent.get("bob")).toEqual([env]);
    expect(hub.sent.get("alice")).toEqual([env]);
    expect(hub.broadcasts).toEqual([]);
  });

  it("r2-07 大量 mentions（8 个不同在线 id）：每人恰好 1 份，无广播", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    const targets = ["u1", "u2", "u3", "u4", "u5", "u6", "u7", "u8"];
    for (const t of targets) hub.conns.add(t);
    const env = chatEnv("alice", "workroom", "all hands", targets);
    routeMessage(hub as unknown as Hub, env, db);

    for (const t of targets) {
      expect(hub.sent.get(t)).toEqual([env]);
    }
    expect(hub.sent.get("alice")).toEqual([env]);
    // 总共 9 个 key（8 targets + alice）
    expect(hub.sent.size).toBe(9);
    expect(hub.broadcasts).toEqual([]);
  });

  it("r2-08 workroom task 回执：写台账 + task_event 1 次 + 广播 1 次，不重路由", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("worker");
    const env = chatEnv("worker", "workroom", "done", [], {
      intent: "task",
      task_status: "done",
      task_id: "t-100",
      msg_id: "m-receipt-1",
    });
    routeMessage(hub as unknown as Hub, env, db);

    // 回执分支：不派发（sendTo 未被调用）
    expect(hub.sent.size).toBe(0);
    // 广播 task_event 恰好 1 次
    expect(hub.taskEvents).toHaveLength(1);
    expect(hub.taskEvents[0].room).toBe("workroom");
    expect(hub.taskEvents[0].payload).toMatchObject({
      task_id: "t-100",
      status: "done",
      assignee: "worker",
    });
    // 消息广播恰好 1 次
    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0]).toEqual({ room: "workroom", env });
  });

  it("r2-09 routeStream：直接广播 1 次；final=true 落库", () => {
    const hub = makeFakeHub();
    const env = makeEnvelope<StreamPayload>("stream", "alice", "workroom", 7, 0, {
      stream_id: "s-1",
      chunk_index: 0,
      delta: "abc",
      final: true,
    });
    routeStream(hub as unknown as Hub, env, db);

    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0]).toEqual({ room: "workroom", env });

    const history = getRoomHistory(db, "workroom", 10);
    expect(history).toHaveLength(1);
    expect(history[0].type).toBe("stream");
    expect(history[0].seq).toBe(7);
    expect(history[0].sender).toBe("alice");
  });

  it("r2-10 intent 省略（undefined）按 chat 处理：workroom 有 mentions 时走定向", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    const env = makeEnvelope<MessagePayload>("message", "alice", "workroom", 1, 0, {
      msg_id: "m-omit-intent",
      text: "hi @bob",
      mentions: ["bob"],
      // intent 省略
    });
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.get("bob")).toEqual([env]);
    expect(hub.sent.get("alice")).toEqual([env]);
    expect(hub.broadcasts).toEqual([]);
  });

  it("r2-11 workroom 定向：mentions 同时含 sender 与自己，sender 只收 1 份副本", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    // mentions 同时包含 sender(alice) 与 bob，以及重复的 bob
    const env = chatEnv("alice", "workroom", "self ping", ["alice", "bob", "bob"]);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.get("alice")).toEqual([env]);
    expect(hub.sent.get("bob")).toEqual([env]);
    expect(hub.broadcasts).toEqual([]);
  });

  it("r2-12 workroom 定向：mentions 全部离线且 sender 也离线 → 无任何投递", () => {
    const hub = makeFakeHub();
    // 无任何连接
    const env = chatEnv("ghost", "workroom", "anyone?", ["u1", "u2"]);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.size).toBe(0);
    expect(hub.broadcasts).toEqual([]);
  });

  it("r2-13 workroom 无 mentions：走广播（非定向）", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    const env = chatEnv("alice", "workroom", "team sync", []);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0]).toEqual({ room: "workroom", env });
    expect(hub.sent.size).toBe(0);
  });

  it("r2-14 routeStream final=false 时不落库", () => {
    const hub = makeFakeHub();
    const env = makeEnvelope<StreamPayload>("stream", "alice", "workroom", 3, 0, {
      stream_id: "s-2",
      chunk_index: 0,
      delta: "partial",
      final: false,
    });
    routeStream(hub as unknown as Hub, env, db);

    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0]).toEqual({ room: "workroom", env });
    const history = getRoomHistory(db, "workroom", 10);
    expect(history).toEqual([]);
  });

  it("r2-15 workroom task 回执 task_id 缺失：以 msg_id 作为 task_id 记账与广播", () => {
    const hub = makeFakeHub();
    hub.conns.add("worker");
    const env = chatEnv("worker", "workroom", "ok", [], {
      intent: "task",
      task_status: "done",
      msg_id: "m-fallback-id",
    });
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.size).toBe(0);
    expect(hub.taskEvents).toHaveLength(1);
    expect(hub.taskEvents[0].payload).toMatchObject({
      task_id: "m-fallback-id",
      status: "done",
      assignee: "worker",
    });
    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0]).toEqual({ room: "workroom", env });
  });
});
