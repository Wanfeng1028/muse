import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { WebSocketServer, WebSocket } from "ws";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope, PROTOCOL_VERSION_STR } from "@botstalk/protocol";
import type { Envelope, MessagePayload, HelloPayload } from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb, getRoomHistory, setPermRole, getPermRole } from "../src/db.js";
import type { Db } from "../src/db.js";
import { routeMessage } from "../src/router.js";

let tmpDir: string;
let db: Db;
let wss: WebSocketServer;
let port: number;
let hub: Hub;
const clients: WebSocket[] = [];

beforeEach(async () => {
  tmpDir = mkdtempSync(join(tmpdir(), "botstalk-vis-"));
  db = openDb(tmpDir);
  wss = new WebSocketServer({ port: 0 });
  await new Promise<void>((res) => wss.once("listening", () => res()));
  const addr = wss.address();
  port = typeof addr === "object" && addr ? addr.port : 0;
  hub = new Hub(db);
  hub.onMessage = (env) => routeMessage(hub, env, db);
  wss.on("connection", (ws) => hub.handleConnection(ws));
});

afterEach(async () => {
  for (const c of clients.splice(0)) {
    try { c.terminate(); } catch { /* ignore */ }
  }
  await new Promise<void>((res) => wss.close(() => res()));
  rmSync(tmpDir, { recursive: true, force: true });
});

function connectClient(): Promise<WebSocket> {
  return new Promise((res, rej) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    ws.once("open", () => { clients.push(ws); res(ws); });
    ws.once("error", rej);
  });
}

function waitFrameWhere(ws: WebSocket, pred: (e: Envelope) => boolean, timeoutMs = 5000): Promise<Envelope> {
  return new Promise((res, rej) => {
    const t = setTimeout(() => { ws.off("message", onMsg); rej(new Error("timeout waiting frame")); }, timeoutMs);
    const onMsg = (d: unknown) => {
      let env: Envelope;
      try { env = JSON.parse(String(d)) as Envelope; } catch { return; }
      if (pred(env)) { clearTimeout(t); ws.off("message", onMsg); res(env); }
    };
    ws.on("message", onMsg);
  });
}

function expectNoFrame(ws: WebSocket, pred: (e: Envelope) => boolean, waitMs = 300): Promise<boolean> {
  return new Promise((res) => {
    let seen = false;
    const onMsg = (d: unknown) => {
      try {
        const env = JSON.parse(String(d)) as Envelope;
        if (pred(env)) seen = true;
      } catch { /* ignore */ }
    };
    ws.on("message", onMsg);
    setTimeout(() => { ws.off("message", onMsg); res(!seen); }, waitMs);
  });
}

async function hello(ws: WebSocket, adapterId: string) {
  ws.send(JSON.stringify(makeEnvelope<HelloPayload>("hello", adapterId, "room-a", 1, 0, {
    adapter_id: adapterId, protocol_version: PROTOCOL_VERSION_STR, last_seen_seq: 0,
  })));
  await new Promise((r) => setTimeout(r, 50));
}

function sendMsg(ws: WebSocket, sender: string, seq: number, payload: MessagePayload, extra?: { visibility?: "direct" | "restricted"; visible_to?: string[] }) {
  ws.send(JSON.stringify(makeEnvelope<MessagePayload>("message", sender, "room-a", seq, 0, payload, undefined, extra)));
}

describe("visibility hub", () => {
  it("direct reaches only sender + target, and is not saved to history", async () => {
    const a = await connectClient();
    const b = await connectClient();
    const c = await connectClient();
    await hello(a, "a");
    await hello(b, "b");
    await hello(c, "c");
    const before = getRoomHistory(db, "room-a", 100).length;
    sendMsg(a, "a", 2, { msg_id: "whisper1", text: "secret", mentions: [] }, { visibility: "direct", visible_to: ["b"] });
    const got = await waitFrameWhere(b, (e) => (e.payload as MessagePayload).msg_id === "whisper1");
    expect(got.visibility).toBe("direct");
    expect(await expectNoFrame(c, (e) => (e.payload as MessagePayload).msg_id === "whisper1")).toBe(true);
    expect(getRoomHistory(db, "room-a", 100).length).toBe(before);
  });

  it("restricted reaches only listed recipients", async () => {
    const a = await connectClient();
    const b = await connectClient();
    const c = await connectClient();
    await hello(a, "a");
    await hello(b, "b");
    await hello(c, "c");
    sendMsg(a, "a", 2, { msg_id: "note1", text: "for b only", mentions: [] }, { visibility: "restricted", visible_to: ["b"] });
    await waitFrameWhere(b, (e) => (e.payload as MessagePayload).msg_id === "note1");
    expect(await expectNoFrame(c, (e) => (e.payload as MessagePayload).msg_id === "note1")).toBe(true);
  });

  it("guest cannot send task intent; chat still works", async () => {
    const g = await connectClient();
    const a = await connectClient();
    await hello(g, "guest1");
    await hello(a, "a");
    setPermRole(db, "room-a", "guest1", "guest");
    expect(getPermRole(db, "room-a", "guest1")).toBe("guest");
    sendMsg(g, "guest1", 2, { msg_id: "t1", text: "do work", mentions: [], intent: "task", task_id: "task-1" });
    const err = await waitFrameWhere(g, (e) => {
      const p = e.payload as MessagePayload;
      return typeof p.text === "string" && p.text.includes("PERMISSION_DENIED");
    });
    expect((err.payload as MessagePayload).task_status).toBe("unsupported");
    sendMsg(g, "guest1", 3, { msg_id: "chat1", text: "hello", mentions: [] });
    await waitFrameWhere(a, (e) => (e.payload as MessagePayload).msg_id === "chat1");
  });
});

describe("perm role db", () => {
  it("set/get, default member, illegal value falls back to member, non-member undefined", () => {
    expect(getPermRole(db, "room-a", "nobody")).toBeUndefined();
    setPermRole(db, "room-a", "m1", "admin");
    expect(getPermRole(db, "room-a", "m1")).toBe("admin");
    setPermRole(db, "room-a", "m1", "guest");
    expect(getPermRole(db, "room-a", "m1")).toBe("guest");
    db.prepare("UPDATE room_members SET perm_role = 'bogus' WHERE room_id = ? AND adapter_id = ?").run("room-a", "m1");
    expect(getPermRole(db, "room-a", "m1")).toBe("member");
  });
});
