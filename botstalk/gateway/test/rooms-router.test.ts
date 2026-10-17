import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import { routeMessage } from "../src/router.js";
import { openDb, createRoom, type Db } from "../src/db.js";
import type { Hub } from "../src/hub.js";

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

function chatEnv(sender: string, room: string, text: string, mentions: string[] = []): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", sender, room, 1, 0, {
    msg_id: "m1", text, mentions, intent: "chat",
  });
}
function taskEnv(sender: string, room: string, text: string, taskId = "t1"): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", sender, room, 1, 0, {
    msg_id: "m2", text, mentions: [], intent: "task", task_id: taskId,
  });
}

let tmpDir: string;
let db: Db;

beforeEach(() => {
  tmpDir = mkdtempSync(join(process.cwd(), "rooms-router-"));
  mkdirSync(join(tmpDir, "data"), { recursive: true });
  db = openDb(join(tmpDir, "data"));
  createRoom(db, { id: "workroom", type: "workroom" });
  createRoom(db, { id: "playroom", type: "playroom" });
});

afterEach(() => {
  try { (db as unknown as { close?: () => void }).close?.(); } catch { /* noop */ }
  rmSync(tmpDir, { recursive: true, force: true });
});

describe("rooms router", () => {
  it("playroom new task: sender gets ROOM_TYPE_FORBIDDEN, no broadcast, no dispatch", () => {
    const hub = makeFakeHub();
    hub.conns.add("alice");
    const env = taskEnv("alice", "playroom", "please do it");
    routeMessage(hub as unknown as Hub, env, db);

    const sent = hub.sent.get("alice") ?? [];
    expect(sent).toHaveLength(1);
    const payload = sent[0].payload as MessagePayload;
    expect(payload.text.startsWith("ROOM_TYPE_FORBIDDEN")).toBe(true);
    expect(hub.broadcasts).toHaveLength(0);
    expect(hub.taskEvents).toHaveLength(0);
  });

  it("playroom task status done: not intercepted, broadcast normally", () => {
    const hub = makeFakeHub();
    const base = taskEnv("alice", "playroom", "done", "t-done");
    const env: Envelope<MessagePayload> = {
      ...base,
      payload: { ...base.payload, task_status: "done" } as MessagePayload,
    };
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0].room).toBe("playroom");
  });

  it("workroom new task: dispatched via taskEvents and sent to online adapter", () => {
    const hub = makeFakeHub();
    hub.conns.add("adapter-1");
    const env = taskEnv("alice", "workroom", "please do it");
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.taskEvents.length).toBeGreaterThanOrEqual(1);
    const dispatched = hub.taskEvents.find((e) => {
      const p = e.payload as { status?: string };
      return p?.status === "dispatched";
    });
    expect(dispatched).toBeDefined();
    expect(dispatched!.room).toBe("workroom");
    const toAdapter = hub.sent.get("adapter-1") ?? [];
    expect(toAdapter.length).toBeGreaterThanOrEqual(1);
  });

  it("workroom chat with mentions: mentioned and sender receive, no broadcast", () => {
    const hub = makeFakeHub();
    hub.conns.add("bob");
    hub.conns.add("alice");
    const env = chatEnv("alice", "workroom", "hey @bob", ["bob"]);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.get("bob")?.length).toBeGreaterThanOrEqual(1);
    expect(hub.sent.get("alice")?.length).toBeGreaterThanOrEqual(1);
    expect(hub.broadcasts).toHaveLength(0);
  });

  it("playroom chat with mentions: broadcast, no direct sends", () => {
    const hub = makeFakeHub();
    hub.conns.add("bob");
    const env = chatEnv("alice", "playroom", "hey @bob", ["bob"]);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.broadcasts).toHaveLength(1);
    expect(hub.broadcasts[0].room).toBe("playroom");
    expect(hub.sent.size).toBe(0);
  });

  it("chat without mentions: broadcast in both workroom and playroom", () => {
    const hubA = makeFakeHub();
    routeMessage(hubA as unknown as Hub, chatEnv("alice", "workroom", "hello"), db);
    expect(hubA.broadcasts).toHaveLength(1);
    expect(hubA.broadcasts[0].room).toBe("workroom");

    const hubB = makeFakeHub();
    routeMessage(hubB as unknown as Hub, chatEnv("alice", "playroom", "hello"), db);
    expect(hubB.broadcasts).toHaveLength(1);
    expect(hubB.broadcasts[0].room).toBe("playroom");
  });

  it("unregistered room: treated as workroom (mentions routed directly)", () => {
    const hub = makeFakeHub();
    hub.conns.add("bob");
    hub.conns.add("alice");
    const env = chatEnv("alice", "ghostroom", "hey @bob", ["bob"]);
    routeMessage(hub as unknown as Hub, env, db);

    expect(hub.sent.get("bob")?.length).toBeGreaterThanOrEqual(1);
    expect(hub.sent.get("alice")?.length).toBeGreaterThanOrEqual(1);
    expect(hub.broadcasts).toHaveLength(0);
  });
});
