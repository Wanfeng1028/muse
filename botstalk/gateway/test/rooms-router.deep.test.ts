// 深测：房间感知路由边界（含重复投递疑似 bug 锁定）
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import type { Hub } from "../src/hub.js";
import { openDb, createRoom } from "../src/db.js";
import type { Db } from "../src/db.js";
import { routeMessage } from "../src/router.js";
import { getTask } from "../src/db.js";

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

function chatEnv(sender: string, room: string, text: string, mentions: string[]): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", sender, room, 1, 0, {
    msg_id: "m1",
    text,
    mentions,
    intent: "chat",
  });
}

function taskEnv(sender: string, room: string, text: string, taskId: string): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", sender, room, 1, 0, {
    msg_id: "m2",
    text,
    mentions: [],
    intent: "task",
    task_id: taskId,
  });
}

function taskReceiptEnv(
  sender: string,
  room: string,
  taskId: string,
  status: string,
): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", sender, room, 1, 0, {
    msg_id: "m3",
    text: "receipt",
    mentions: [],
    intent: "task",
    task_id: taskId,
    task_status: status as never,
  });
}

describe("rooms-router.deep", () => {
  let tmpDir: string;
  let db: Db;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "rooms-router-deep-"));
    db = openDb(tmpDir);
    createRoom(db, { id: "workroom", type: "workroom" });
    createRoom(db, { id: "playroom", type: "playroom" });
  });

  afterEach(() => {
    db.close();
    rmSync(tmpDir, { recursive: true, force: true });
  });

  // 1. workroom @ 了不存在的成员：ghost 未连接 → ghost 收不到，alice（发送者，在线）收到自己那份，无广播。
  it("workroom @ 不存在的成员时仅发送者收到，无广播", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    const env = chatEnv("alice", "workroom", "@ghost hi", ["ghost"]);
    routeMessage(hub as unknown as Hub, env, db);
    expect(hub.sent.get("ghost")).toBeUndefined();
    expect(hub.sent.get("alice")?.length).toBe(1);
    expect(hub.broadcasts.length).toBe(0);
  });

  // 2. workroom @ 多个成员混合在线/离线：bob 在线、ghost 离线、alice 在线 → bob 和 alice 各 1 份，ghost 无记录，无广播。
  it("workroom @ 多成员混合在线离线时只发给在线者与发送者", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    const env = chatEnv("alice", "workroom", "@bob @ghost hi", ["bob", "ghost"]);
    routeMessage(hub as unknown as Hub, env, db);
    expect(hub.sent.get("bob")?.length).toBe(1);
    expect(hub.sent.get("alice")?.length).toBe(1);
    expect(hub.sent.get("ghost")).toBeUndefined();
    expect(hub.broadcasts.length).toBe(0);
  });

  // 3. workroom 发送者自己不在线：alice 离线、bob 在线、mentions=["bob"] → bob 收到 1 份，alice 无记录，不抛错。
  it("workroom 发送者离线时仅被@的在线成员收到", () => {
    const hub = makeFakeHub();
    hub.conns.add("bob");
    const env = chatEnv("alice", "workroom", "@bob hi", ["bob"]);
    expect(() => routeMessage(hub as unknown as Hub, env, db)).not.toThrow();
    expect(hub.sent.get("bob")?.length).toBe(1);
    expect(hub.sent.get("alice")).toBeUndefined();
    expect(hub.broadcasts.length).toBe(0);
  });

  // 4. playroom 新 task 但发送者不在线：无 reply、无广播、无 taskEvents、不抛错。
  it("playroom 新 task 且发送者离线时静默拒绝", () => {
    const hub = makeFakeHub();
    const env = taskEnv("alice", "playroom", "do it", "t-off");
    expect(() => routeMessage(hub as unknown as Hub, env, db)).not.toThrow();
    expect(hub.sent.size).toBe(0);
    expect(hub.broadcasts.length).toBe(0);
    expect(hub.taskEvents.length).toBe(0);
  });

  // 5. playroom 新 task 的拒绝回执内容：intent=task、task_status=unsupported、task_id 一致、text 前缀。
  it("playroom 新 task 的拒绝回执携带正确字段", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    const env = taskEnv("alice", "playroom", "do it", "t-reject");
    routeMessage(hub as unknown as Hub, env, db);
    const replies = hub.sent.get("alice");
    expect(replies?.length).toBe(1);
    const reply = replies![0];
    const payload = reply.payload as MessagePayload;
    expect(payload.intent).toBe("task");
    expect(payload.task_status).toBe("unsupported");
    expect(payload.task_id).toBe("t-reject");
    expect(payload.text.startsWith("ROOM_TYPE_FORBIDDEN")).toBe(true);
  });

  // 6. playroom task 回执 task_status="failed" 放行，且 db 中状态被更新。
  it("playroom task 回执 failed 放行并更新 db 状态", () => {
    const hub = makeFakeHub();
    hub.conns.add("worker1");
    // 先在 workroom 派发一个 task 产生台账
    const dispatchEnv = taskEnv("alice", "workroom", "build", "t-failed");
    routeMessage(hub as unknown as Hub, dispatchEnv, db);
    expect(getTask(db, "t-failed")?.status).toBe("dispatched");

    // 清空记录，便于观察回执路径
    hub.broadcasts.length = 0;
    hub.taskEvents.length = 0;
    hub.sent.clear();

    const receipt = taskReceiptEnv("worker1", "playroom", "t-failed", "failed");
    routeMessage(hub as unknown as Hub, receipt, db);

    expect(hub.broadcasts.length).toBe(1);
    expect(hub.taskEvents.length).toBe(1);
    const evt = hub.taskEvents[0].payload as { status: string };
    expect(evt.status).toBe("failed");
    expect(getTask(db, "t-failed")?.status).toBe("failed");
  });

  // 7. 未注册房间的新 task：ghostroom 默认 workroom → 正常派发。
  it("未注册房间按 workroom 处理并正常派发新 task", () => {
    const hub = makeFakeHub();
    hub.conns.add("worker1");
    const env = taskEnv("alice", "ghostroom", "build", "t-ghost");
    routeMessage(hub as unknown as Hub, env, db);
    expect(hub.taskEvents.length).toBe(1);
    const evt = hub.taskEvents[0].payload as { status: string };
    expect(evt.status).toBe("dispatched");
    // 不应触发 ROOM_TYPE_FORBIDDEN
    for (const [, arr] of hub.sent) {
      for (const e of arr) {
        const p = e.payload as MessagePayload;
        if (typeof p.text === "string") {
          expect(p.text.startsWith("ROOM_TYPE_FORBIDDEN")).toBe(false);
        }
      }
    }
  });

  // 8. workroom chat mentions 为空数组 → 广播 1 次。
  it("workroom chat 空 mention 触发广播", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    const env = chatEnv("alice", "workroom", "hello all", []);
    routeMessage(hub as unknown as Hub, env, db);
    expect(hub.broadcasts.length).toBe(1);
    expect(hub.broadcasts[0].room).toBe("workroom");
  });

  // 9. workroom 定向时 env 原样透传（引用相等）。
  it("workroom 定向时透传同一 env 引用", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    const env = chatEnv("alice", "workroom", "@bob hi", ["bob"]);
    routeMessage(hub as unknown as Hub, env, db);
    const bobRecv = hub.sent.get("bob");
    expect(bobRecv?.length).toBe(1);
    expect(bobRecv![0]).toBe(env);
  });

  // 10. sender 同时是被@成员：按源码如实断言收到 2 份（疑似重复投递 bug，已锁定）。
  it("workroom sender 同时被@时收到两份（疑似重复投递 bug）", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    const env = chatEnv("alice", "workroom", "@alice hi", ["alice"]);
    routeMessage(hub as unknown as Hub, env, db);
    // 现行源码行为：for 循环发一次，sender 分支再发一次，共 2 份。
    // 疑似 bug：被@且是发送者会收到重复投递，已锁定当前行为。
    expect(hub.sent.get("alice")?.length).toBe(2);
    expect(hub.broadcasts.length).toBe(0);
  });

  // 11. workroom 新 task 无候选 adapter 时发送者收到 unsupported 回执。
  it("workroom 新 task 无可用 adapter 时回执 unsupported", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    // 覆盖 getConn：在线连接只支持 chat，不支持 task → 无候选 adapter
    hub.getConn = (id: string) =>
      hub.conns.has(id)
        ? { adapterId: id, capabilities: { intents: ["chat"] as ("chat" | "task")[] } }
        : undefined;
    const env = taskEnv("alice", "workroom", "build", "t-no-worker");
    routeMessage(hub as unknown as Hub, env, db);
    expect(hub.taskEvents.length).toBe(1);
    const evt = hub.taskEvents[0].payload as { status: string };
    expect(evt.status).toBe("unsupported");
    const replies = hub.sent.get("alice");
    expect(replies?.length).toBe(1);
    const p = replies![0].payload as MessagePayload;
    expect(p.task_status).toBe("unsupported");
  });

  // 12. workroom 新 task 候选多个在线 adapter 时按字典序选第一个。
  it("workroom 新 task 多候选按字典序选首个", () => {
    const hub = makeFakeHub();
    hub.conns.add("zeta");
    hub.conns.add("alpha");
    const env = taskEnv("alice", "workroom", "build", "t-sort");
    routeMessage(hub as unknown as Hub, env, db);
    expect(hub.sent.get("alpha")?.length).toBe(1);
    expect(hub.sent.get("zeta")).toBeUndefined();
    expect(getTask(db, "t-sort")?.assignee).toBe("alpha");
  });

  // 13. workroom 新 task 带 mentions 时只从被@者中挑选候选。
  it("workroom 新 task 带 mention 时仅从被@者中挑候选", () => {
    const hub = makeFakeHub();
    hub.conns.add("alpha");
    hub.conns.add("bob");
    const env = makeEnvelope<MessagePayload>("message", "alice", "workroom", 1, 0, {
      msg_id: "m-mention-task",
      text: "@bob build",
      mentions: ["bob"],
      intent: "task",
      task_id: "t-mention",
    });
    routeMessage(hub as unknown as Hub, env, db);
    expect(hub.sent.get("bob")?.length).toBe(1);
    expect(hub.sent.get("alpha")).toBeUndefined();
    expect(getTask(db, "t-mention")?.assignee).toBe("bob");
  });

  // 14. workroom 新 task title 超过 80 字符时被截断加省略号。
  it("workroom 新 task 标题超长被截断", () => {
    const hub = makeFakeHub();
    hub.conns.add("worker1");
    const long = "x".repeat(120);
    const env = taskEnv("alice", "workroom", long, "t-long");
    routeMessage(hub as unknown as Hub, env, db);
    const evt = hub.taskEvents[0].payload as { title: string };
    expect(evt.title.length).toBe(81);
    expect(evt.title.endsWith("…")).toBe(true);
  });

  // 15. workroom 新 task 文本以 @前缀 开头时 title 去除 mention。
  it("workroom 新 task 标题去除前缀 mention", () => {
    const hub = makeFakeHub();
    hub.conns.add("worker1");
    const env = makeEnvelope<MessagePayload>("message", "alice", "workroom", 1, 0, {
      msg_id: "m-strip",
      text: "@worker1 do the thing",
      mentions: ["worker1"],
      intent: "task",
      task_id: "t-strip",
    });
    routeMessage(hub as unknown as Hub, env, db);
    const evt = hub.taskEvents[0].payload as { title: string };
    expect(evt.title).toBe("do the thing");
  });

  // 16. playroom 回执放行时 sender 也收到广播（任务完成上报可穿越房间限制）。
  it("playroom 回执时 taskEvents 记录 assignee 为发送者", () => {
    const hub = makeFakeHub();
    hub.conns.add("worker1");
    routeMessage(hub as unknown as Hub, taskEnv("alice", "workroom", "build", "t-ack"), db);
    hub.taskEvents.length = 0;
    hub.broadcasts.length = 0;
    routeMessage(hub as unknown as Hub, taskReceiptEnv("worker1", "playroom", "t-ack", "done"), db);
    expect(hub.taskEvents.length).toBe(1);
    const evt = hub.taskEvents[0].payload as { assignee: string; status: string };
    expect(evt.assignee).toBe("worker1");
    expect(evt.status).toBe("done");
    expect(hub.broadcasts.length).toBe(1);
  });

  // 17. playroom 带 @ 的 chat 广播，且被@的在线成员也仅通过广播收到。
  it("playroom 带 @ 的 chat 仅广播不直发", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    hub.conns.add("bob");
    const env = chatEnv("alice", "playroom", "@bob lol", ["bob"]);
    routeMessage(hub as unknown as Hub, env, db);
    expect(hub.broadcasts.length).toBe(1);
    expect(hub.sent.get("bob")).toBeUndefined();
  });

  // 18. workroom 新 task 无在线 adapter 时发送者离线也不抛错且无回执。
  it("workroom 新 task 无候选且发送者离线时静默不抛错", () => {
    const hub = makeFakeHub();
    const env = taskEnv("alice", "workroom", "build", "t-silent");
    expect(() => routeMessage(hub as unknown as Hub, env, db)).not.toThrow();
    expect(hub.sent.size).toBe(0);
    expect(hub.taskEvents.length).toBe(1);
    const evt = hub.taskEvents[0].payload as { status: string };
    expect(evt.status).toBe("unsupported");
  });

  // 19. playroom 回执 task_status=done 时 db 状态被更新为 done。
  it("playroom 回执 done 时 db 状态更新", () => {
    const hub = makeFakeHub();
    hub.conns.add("worker1");
    routeMessage(hub as unknown as Hub, taskEnv("alice", "workroom", "build", "t-done-db"), db);
    expect(getTask(db, "t-done-db")?.status).toBe("dispatched");
    routeMessage(hub as unknown as Hub, taskReceiptEnv("worker1", "playroom", "t-done-db", "done"), db);
    expect(getTask(db, "t-done-db")?.status).toBe("done");
  });

  // 20. workroom 新 task task_id 缺省时使用 msg_id 作为 task_id。
  it("workroom 新 task 缺省 task_id 时回退到 msg_id", () => {
    const hub = makeFakeHub();
    hub.conns.add("worker1");
    const env = makeEnvelope<MessagePayload>("message", "alice", "workroom", 1, 0, {
      msg_id: "m-fallback",
      text: "build",
      mentions: [],
      intent: "task",
    });
    routeMessage(hub as unknown as Hub, env, db);
    expect(getTask(db, "m-fallback")?.status).toBe("dispatched");
  });
});
