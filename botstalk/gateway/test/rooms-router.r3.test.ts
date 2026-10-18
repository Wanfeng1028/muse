import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import { routeMessage, routeStream } from "../src/router.js";
import type { Hub } from "../src/hub.js";
import { openDb, createRoom, getRoomHistory, updateTaskStatus, getTask } from "../src/db.js";
import type { Db } from "../src/db.js";

class FakeHub {
  conns = new Map<string, { capabilities: { intents: string[] } }>();
  sent = new Map<string, Envelope[]>();
  broadcasted: Envelope[] = [];
  taskEvents: Array<{ room: string; payload: unknown }> = [];
  private seq = 0;
  nextSeq() { return ++this.seq; }
  getConn(id: string) { return this.conns.get(id); }
  getOnlineAdapters() { return [...this.conns.keys()]; }
  sendTo(id: string, env: Envelope) { if (!this.sent.has(id)) this.sent.set(id, []); this.sent.get(id)!.push(env); }
  broadcast(room: string, env: Envelope) { this.broadcasted.push(env); }
  broadcastTaskEvent(room: string, payload: unknown) { this.taskEvents.push({ room, payload }); }
}

function makeMsg(
  sender: string,
  room: string,
  text: string,
  opts: Partial<MessagePayload> = {},
): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", sender, room, 1, 0, {
    msg_id: "m1",
    text,
    mentions: [],
    ...opts,
  });
}

describe("rooms-router.r3 未覆盖分支", () => {
  let dir: string;
  let db: Db;
  let hub: FakeHub;

  const addConn = (id: string, intents: string[] = ["chat", "task"]) => {
    hub.conns.set(id, { capabilities: { intents } });
  };

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "rooms-router-r3-"));
    db = openDb(join(dir, "test.db"));
    createRoom(db, { id: "w1", name: "w1", type: "workroom", owner: "a" });
    hub = new FakeHub();
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("未知 intent 的帧被静默丢弃：不回执、不广播、不落库", () => {
    addConn("a");
    const env = makeMsg("a", "w1", "hello", { intent: "bogus" as unknown as MessagePayload["intent"] });

    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.size).toBe(0);
    expect(hub.broadcasted).toHaveLength(0);
    expect(hub.taskEvents).toHaveLength(0);
    expect(getRoomHistory(db, "w1", 50)).toHaveLength(0);
  });

  it("task 回执对应 task 不存在时仍广播与派发 task_event，不抛错", () => {
    addConn("a");
    const env = makeMsg("a", "w1", "", {
      intent: "task",
      task_id: "t-missing",
      task_status: "done",
    });

    expect(() => routeMessage(hub as unknown as Hub, env, db)).not.toThrow();

    expect(hub.broadcasted).toHaveLength(1);
    expect(hub.taskEvents).toHaveLength(1);
    expect(hub.taskEvents[0].payload).toMatchObject({ task_id: "t-missing" });
    // updateTaskStatus 对不存在的 task 返回 false，但流程继续，不落库新记录
    expect(getRoomHistory(db, "w1", 50)).toHaveLength(0);
  });

  it("在线但无 task 能力的 adapter 被候选过滤，仅派发给有 task 能力者", () => {
    addConn("a", ["chat"]);
    addConn("b", ["chat", "task"]);
    addConn("c", ["chat"]);
    const env = makeMsg("c", "w1", "do it", { intent: "task", msg_id: "m-filter" });

    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.has("a")).toBe(false);
    expect(hub.sent.get("b")).toHaveLength(1);
    expect(hub.sent.get("b")![0]).toBe(env);
  });

  it("定向投递只看 getConn，不校验被@者是否在该 room", () => {
    addConn("a");
    const env = makeMsg("c", "w1", "hi", { mentions: ["a"] });

    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.get("a")).toHaveLength(1);
    expect(hub.sent.get("a")![0]).toBe(env);
  });

  it("routeStream final=true 落库 payload 含 stream_id", () => {
    const env = makeEnvelope("stream", "a", "w1", 7, 0, { stream_id: "s-9", final: true }) as Envelope<any>;

    routeStream(hub as unknown as Hub, env, db);

    const history = getRoomHistory(db, "w1", 50);
    expect(history).toHaveLength(1);
    expect(history[0].type).toBe("stream");
    expect(JSON.parse(history[0].payload).stream_id).toBe("s-9");
  });

  it("新 task 派发时 pick 离线竞态：候选为空走 unsupported 台账并回执 sender", () => {
    addConn("c", ["chat"]);
    const env = makeMsg("c", "w1", "run", {
      intent: "task",
      msg_id: "m-race",
      mentions: ["ghost-id"],
    });

    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.taskEvents).toHaveLength(1);
    expect(hub.taskEvents[0].payload).toMatchObject({
      status: "unsupported",
      note: "no adapter supports task intent",
    });
    const replies = hub.sent.get("c") ?? [];
    expect(replies).toHaveLength(1);
    expect((replies[0].payload as MessagePayload).text).toBe("no adapter supports task intent");
  });

  it("task 回执广播原文透传且 task_event assignee 为 sender", () => {
    addConn("a");
    const env = makeMsg("a", "w1", "done detail", {
      intent: "task",
      task_id: "t1",
      task_status: "done",
    });

    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.broadcasted[0]).toBe(env);
    expect(hub.taskEvents).toHaveLength(1);
    expect((hub.taskEvents[0].payload as { assignee: string }).assignee).toBe("a");
  });

  it("空 text 的新 task 落库标题为空串", () => {
    addConn("b", ["chat", "task"]);
    const env = makeMsg("c", "w1", "", { intent: "task", msg_id: "m-empty" });

    routeMessage(hub as unknown as Hub, env, db);

    const task = getTask(db, "m-empty");
    expect(task).toBeTruthy();
    expect(task!.title).toBe("");
  });
});