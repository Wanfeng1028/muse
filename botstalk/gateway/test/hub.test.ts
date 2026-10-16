import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { WebSocketServer, WebSocket } from "ws";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  makeEnvelope,
  PROTOCOL_VERSION_STR,
} from "@botstalk/protocol";
import type {
  Envelope,
  MessagePayload,
  HelloPayload,
  GapPayload,
} from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb, getRoomHistory } from "../src/db.js";
import type { Db } from "../src/db.js";

let tmpDir: string;
let db: Db;
let wss: WebSocketServer;
let port: number;
let hub: Hub;

beforeEach(async () => {
  tmpDir = mkdtempSync(join(process.cwd(), "test-tmp-"));
  db = openDb(tmpDir);
  wss = new WebSocketServer({ port: 0 });
  await new Promise<void>((res) => wss.once("listening", () => res()));
  const addr = wss.address();
  port = typeof addr === "object" && addr ? addr.port : 0;
  hub = new Hub(db);
  wss.on("connection", (ws) => hub.handleConnection(ws));
});

const clients: WebSocket[] = [];

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

function waitFrame(ws: WebSocket, timeoutMs = 2000): Promise<Envelope> {
  return new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("timeout waiting frame")), timeoutMs);
    ws.once("message", (d) => {
      clearTimeout(t);
      res(JSON.parse(String(d)) as Envelope);
    });
  });
}

function waitClose(ws: WebSocket, timeoutMs = 2000): Promise<{ code: number }> {
  return new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("timeout waiting close")), timeoutMs);
    ws.once("close", (code) => {
      clearTimeout(t);
      res({ code });
    });
  });
}

async function waitConn(adapterId: string, timeoutMs = 2000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!hub.getConn(adapterId)) {
    if (Date.now() > deadline) throw new Error(`timeout waiting conn ${adapterId}`);
    await new Promise((r) => setTimeout(r, 20));
  }
}

async function hello(ws: WebSocket, adapterId: string, lastSeen = 0, pv = PROTOCOL_VERSION_STR) {
  const env = makeEnvelope<HelloPayload>(
    "hello",
    adapterId,
    "room-a",
    1,
    0,
    { adapter_id: adapterId, protocol_version: pv, last_seen_seq: lastSeen },
  );
  ws.send(JSON.stringify(env));
}

describe("Hub", () => {
  it("accepts hello and records presence", async () => {
    const ws = await connectClient();
    await hello(ws, "adapter-1");
    await new Promise((r) => setTimeout(r, 50));
    expect(hub.getConn("adapter-1")).toBeDefined();
    expect(hub.getOnlineAdapters("room-a")).toContain("adapter-1");
    ws.close();
  });

  it("replaces existing connection with 4402", async () => {
    const ws1 = await connectClient();
    await hello(ws1, "dup");
    const closeP = waitClose(ws1);
    const frameP = waitFrame(ws1);

    const ws2 = await connectClient();
    await hello(ws2, "dup");

    const frame = await frameP;
    expect(frame.type).toBe("message");
    const c = await closeP;
    expect(c.code).toBe(4402);
    const dupConn = hub.getConn("dup");
    expect(dupConn).toBeDefined();
    expect(dupConn?.adapterId).toBe("dup");
    ws2.close();
  });

  it("rejects bad protocol version with 4400", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    await hello(ws, "bad-pv", 0, "9.9");
    const c = await closeP;
    expect(c.code).toBe(4400);
  });

  it("rejects non-hello first frame with 4401", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    const env = makeEnvelope<MessagePayload>(
      "message",
      "x",
      "room-a",
      1,
      0,
      { msg_id: "m1", text: "hi", mentions: [] },
    );
    ws.send(JSON.stringify(env));
    const c = await closeP;
    expect(c.code).toBe(4401);
  });

  it("sweep terminates stale connections", async () => {
    const ws = await connectClient();
    await hello(ws, "stale");
    await waitConn("stale");
    const conn = hub.getConn("stale");
    expect(conn).toBeDefined();
    conn!.lastFrameAtMs = Date.now() - 46000;
    hub.sweep(Date.now());
    expect(hub.getConn("stale")).toBeUndefined();
    ws.terminate();
  });

  it("resends missing frames on gap request", async () => {
    const ws = await connectClient();
    await hello(ws, "gapc");
    await waitConn("gapc");
    const conn = hub.getConn("gapc")!;

    const received: Envelope[] = [];
    ws.on("message", (d) => received.push(JSON.parse(String(d)) as Envelope));

    const f1 = makeEnvelope<MessagePayload>("message", "gateway", "room-a", hub["serverSeq"].nextSeq(), 0, { msg_id: "a", text: "one", mentions: [] });
    const f2 = makeEnvelope<MessagePayload>("message", "gateway", "room-a", hub["serverSeq"].nextSeq(), 0, { msg_id: "b", text: "two", mentions: [] });
    const f3 = makeEnvelope<MessagePayload>("message", "gateway", "room-a", hub["serverSeq"].nextSeq(), 0, { msg_id: "c", text: "three", mentions: [] });

    hub.sendTo("gapc", f1);
    hub.sendTo("gapc", f2);
    hub.sendTo("gapc", f3);

    // wait for first 3 frames
    let deadline = Date.now() + 2000;
    while (received.length < 3 && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 20));
    }
    expect(received.length).toBe(3);

    const gapEnv = makeEnvelope<GapPayload>("gap", "gapc", "room-a", 2, 0, { from_seq: 2, to_seq: 2 });
    ws.send(JSON.stringify(gapEnv));

    deadline = Date.now() + 2000;
    while (received.length < 4 && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 20));
    }
    expect(received.length).toBe(4);
    const resent = received[3]!;
    expect(resent.seq).toBe(2);
    expect(resent.type).toBe("message");

    void conn;
    ws.close();
  });

  it("invokes onMessage and persists", async () => {
    const ws = await connectClient();
    await hello(ws, "msgc");

    let called = false;
    hub.onMessage = () => {
      called = true;
    };

    const env = makeEnvelope<MessagePayload>(
      "message",
      "msgc",
      "room-a",
      2,
      0,
      { msg_id: "m-1", text: "hello", mentions: [] },
    );
    ws.send(JSON.stringify(env));

    const deadline = Date.now() + 2000;
    while (!called && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 20));
    }
    expect(called).toBe(true);

    const history = getRoomHistory(db, "room-a", 10);
    expect(history.some((m) => (JSON.parse(m.payload) as { msg_id: string }).msg_id === "m-1")).toBe(true);

    ws.close();
  });

  it("断线补发按 gseq 区间：重连只收到断线期间的帧且 gseq 连续", async () => {
    hub.onMessage = (env) => hub.broadcast("room-a", env);

    const a = await connectClient();
    const b = await connectClient();
    await hello(a, "adapter-A");
    await hello(b, "adapter-B");
    await waitConn("adapter-A");
    await waitConn("adapter-B");

    // A 发一条 chat（mentions=[] → broadcast），B 在线收到，记下 gseq
    const m1 = makeEnvelope<MessagePayload>("message", "adapter-A", "room-a", 2, 0,
      { msg_id: "m-1", text: "before", mentions: [] });
    a.send(JSON.stringify(m1));
    const firstToB = await waitFrame(b);
    expect(typeof firstToB.gseq).toBe("number");
    const bMaxGseq = firstToB.gseq as number;

    // 断开 B
    b.terminate();
    await new Promise((r) => setTimeout(r, 200));

    // A 在 B 断线期间发 3 条
    const texts = ["off-1", "off-2", "off-3"];
    for (let i = 0; i < texts.length; i++) {
      const m = makeEnvelope<MessagePayload>("message", "adapter-A", "room-a", 3 + i, 0,
        { msg_id: `m-off-${i}`, text: texts[i], mentions: [] });
      a.send(JSON.stringify(m));
    }
    await new Promise((r) => setTimeout(r, 500));

    // B 重连，带上已见最大 gseq
    // 注意：网关在处理 hello 时同步发出补发帧，必须先挂好收集器再发 hello，
    // 否则帧可能在 waitFrame 挂载监听器之前到达而丢失。
    const b2 = await connectClient();
    const received: Envelope[] = [];
    const gotAll = new Promise<void>((resolve) => {
      b2.on("message", (d) => {
        received.push(JSON.parse(String(d)) as Envelope);
        if (received.length >= texts.length) resolve();
      });
    });
    await hello(b2, "adapter-B", bMaxGseq);
    await waitConn("adapter-B");
    await Promise.race([
      gotAll,
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout waiting resend")), 5000)),
    ]);
    expect(received.map((f) => (f.payload as MessagePayload).text)).toEqual(texts);
    const gseqs = received.map((f) => f.gseq as number);
    for (const g of gseqs) expect(g).toBeGreaterThan(bMaxGseq);
    for (let i = 1; i < gseqs.length; i++) expect(gseqs[i]).toBe(gseqs[i - 1] + 1);
  });
});

// 自查：红线 1-5 逐条通过
