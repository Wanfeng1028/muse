import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { WebSocketServer, WebSocket } from "ws";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope, PROTOCOL_VERSION_STR } from "@botstalk/protocol";
import type { Envelope, MessagePayload, HelloPayload } from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb, getRoomHistory } from "../src/db.js";
import type { Db } from "../src/db.js";
import { routeMessage } from "../src/router.js";

let tmpDir: string;
let db: Db;
let wss: WebSocketServer;
let port: number;
let hub: Hub;
const clients: WebSocket[] = [];

beforeEach(async () => {
  tmpDir = mkdtempSync(join(tmpdir(), "botstalk-thread-"));
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

async function hello(ws: WebSocket, adapterId: string) {
  ws.send(JSON.stringify(makeEnvelope<HelloPayload>("hello", adapterId, "room-a", 1, 0, {
    adapter_id: adapterId, protocol_version: PROTOCOL_VERSION_STR, last_seen_seq: 0,
  })));
  await new Promise((r) => setTimeout(r, 50));
}

function sendMsg(ws: WebSocket, sender: string, seq: number, payload: MessagePayload) {
  ws.send(JSON.stringify(makeEnvelope<MessagePayload>("message", sender, "room-a", seq, 0, payload)));
}

describe("thread hub", () => {
  it("derives thread_id on reply and flattens reply-to-reply to root", async () => {
    const a = await connectClient();
    const b = await connectClient();
    await hello(a, "a");
    await hello(b, "b");
    sendMsg(a, "a", 2, { msg_id: "root1", text: "root", mentions: [] });
    await waitFrameWhere(b, (e) => (e.payload as MessagePayload).msg_id === "root1");
    sendMsg(b, "b", 2, { msg_id: "rep1", text: "reply", mentions: [], reply_to: "root1" });
    const rep = await waitFrameWhere(a, (e) => (e.payload as MessagePayload).msg_id === "rep1");
    expect((rep.payload as MessagePayload).thread_id).toBe("root1");
    sendMsg(a, "a", 3, { msg_id: "rep2", text: "reply to reply", mentions: [], reply_to: "rep1" });
    const rep2 = await waitFrameWhere(b, (e) => (e.payload as MessagePayload).msg_id === "rep2");
    expect((rep2.payload as MessagePayload).thread_id).toBe("root1");
    const rows = getRoomHistory(db, "room-a", 100);
    expect(rows.length).toBeGreaterThanOrEqual(3);
  });

  it("rejects reply to missing target without saving", async () => {
    const a = await connectClient();
    await hello(a, "a");
    const before = getRoomHistory(db, "room-a", 100).length;
    sendMsg(a, "a", 2, { msg_id: "bad1", text: "orphan", mentions: [], reply_to: "missing" });
    const err = await waitFrameWhere(a, (e) => {
      const p = e.payload as MessagePayload;
      return typeof p.text === "string" && p.text.includes("REPLY_TARGET_NOT_FOUND");
    });
    expect(err.sender).toBe("gateway");
    expect(getRoomHistory(db, "room-a", 100).length).toBe(before);
  });
});
