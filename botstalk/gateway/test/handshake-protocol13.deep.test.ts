import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { WebSocketServer, WebSocket } from "ws";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope, PROTOCOL_VERSION_STR } from "@botstalk/protocol";
import type { Envelope, MessagePayload, HelloPayload } from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb } from "../src/db.js";
import type { Db } from "../src/db.js";
import { randomUUID } from "node:crypto";

let tmpDir: string;
let db: Db;
let wss: WebSocketServer;
let port: number;
let hub: Hub;

beforeEach(async () => {
  tmpDir = mkdtempSync(join(tmpdir(), "botstalk-handshake-"));
  db = openDb(tmpDir);
  wss = new WebSocketServer({ port: 0 });
  await new Promise<void>((res) => wss.once("listening", () => res()));
  const addr = wss.address();
  port = typeof addr === "object" && addr ? addr.port : 0;
  hub = new Hub(db);
  // 模拟真实 server 的 routeMessage 广播语义：chat 消息广播给房间成员
  hub.onMessage = (env: Envelope<MessagePayload>) => {
    hub.broadcast(env.room, env);
  };
  wss.on("connection", (ws) => hub.handleConnection(ws));
});

const clients: WebSocket[] = [];

afterEach(async () => {
  for (const c of clients.splice(0)) {
    try {
      c.terminate();
    } catch {
      /* ignore */
    }
  }
  await new Promise<void>((res) => wss.close(() => res()));
  rmSync(tmpDir, { recursive: true, force: true });
});

function connectClient(): Promise<WebSocket> {
  return new Promise((res, rej) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    ws.once("open", () => {
      clients.push(ws);
      res(ws);
    });
    ws.once("error", rej);
  });
}

function waitClose(ws: WebSocket, timeoutMs = 3000): Promise<number> {
  return new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("timeout waiting close")), timeoutMs);
    ws.once("close", (code) => {
      clearTimeout(t);
      res(code);
    });
  });
}

function waitFrame(ws: WebSocket, timeoutMs = 3000): Promise<Envelope> {
  return new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("timeout waiting frame")), timeoutMs);
    ws.once("message", (d) => {
      clearTimeout(t);
      res(JSON.parse(String(d)) as Envelope);
    });
  });
}

async function waitFor<T>(
  fn: () => T | undefined | Promise<T | undefined>,
  timeoutMs = 3000,
  intervalMs = 20,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const v = await fn();
    if (v !== undefined) return v;
    if (Date.now() > deadline) throw new Error("waitFor timeout");
    await new Promise<void>((res) => setTimeout(res, intervalMs));
  }
}

function sendHello(
  ws: WebSocket,
  adapterId: string,
  protocolVersion: unknown,
  lastSeenSeq = -1,
  room = "r1",
): void {
  const env = makeEnvelope<HelloPayload>(
    "hello",
    adapterId,
    room,
    1,
    0,
    {
      adapter_id: adapterId,
      protocol_version: protocolVersion as string,
      last_seen_seq: lastSeenSeq,
    },
  );
  ws.send(JSON.stringify(env));
}

describe("handshake protocol 1.3 deep", () => {
  it("accepts hello with protocol_version 1.3 and registers connection", async () => {
    const ws = await connectClient();
    sendHello(ws, "a-13", PROTOCOL_VERSION_STR);
    const conn = await waitFor(() => hub.getConn("a-13"));
    expect(conn).toBeDefined();
    expect(conn.adapterId).toBe("a-13");
    ws.close();
  });

  it("rejects protocol_version 1.2 with close code 4400", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    sendHello(ws, "a-12", "1.2");
    const code = await closeP;
    expect(code).toBe(4400);
  });

  it("rejects protocol_version 1.1 with close code 4400", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    sendHello(ws, "a-11", "1.1");
    const code = await closeP;
    expect(code).toBe(4400);
  });

  it("rejects protocol_version 2.0 with close code 4400", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    sendHello(ws, "a-20", "2.0");
    const code = await closeP;
    expect(code).toBe(4400);
  });

  it("rejects empty protocol_version string with close code 4401", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    sendHello(ws, "a-empty", "");
    const code = await closeP;
    // 空字符串通不过 validateHelloPayload 的非空校验，走 4401 而非 4400
    expect(code).toBe(4401);
  });

  it("rejects numeric protocol_version with close code 4401", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    sendHello(ws, "a-num", 1.3);
    const code = await closeP;
    // 非字符串通不过 validateHelloPayload 的非空字符串校验，走 4401 而非 4400
    expect(code).toBe(4401);
  });

  it("rejects first frame of type message with close code 4401", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    const env = makeEnvelope<MessagePayload>(
      "message",
      "a-msg",
      "r1",
      1,
      0,
      { msg_id: randomUUID(), text: "hi", mentions: [] },
    );
    ws.send(JSON.stringify(env));
    const code = await closeP;
    expect(code).toBe(4401);
  });

  it("rejects malformed JSON first frame with close code 4401", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    ws.send("not-json{{{");
    const code = await closeP;
    expect(code).toBe(4401);
  });

  it("rejects hello missing adapter_id with close code 4401", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    const env = makeEnvelope<HelloPayload>(
      "hello",
      "a-missing",
      "r1",
      1,
      0,
      { protocol_version: PROTOCOL_VERSION_STR, last_seen_seq: -1 } as HelloPayload,
    );
    ws.send(JSON.stringify(env));
    const code = await closeP;
    expect(code).toBe(4401);
  });

  it("resends missed frames on reconnect when last_seen_seq is set to a known gseq", async () => {
    // A connects with last_seen_seq=-1
    const wsA = await connectClient();
    sendHello(wsA, "a-resend", PROTOCOL_VERSION_STR, -1, "r-resend");
    await waitFor(() => hub.getConn("a-resend"));

    // B connects
    const wsB = await connectClient();
    sendHello(wsB, "b-resend", PROTOCOL_VERSION_STR, -1, "r-resend");
    await waitFor(() => hub.getConn("b-resend"));

    // B sends M1, A receives it and records gseq=G1
    const m1 = makeEnvelope<MessagePayload>(
      "message",
      "b-resend",
      "r-resend",
      2,
      0,
      { msg_id: randomUUID(), text: "M1", mentions: [] },
    );
    wsB.send(JSON.stringify(m1));
    const frameAtA = await waitFrame(wsA);
    expect(frameAtA.type).toBe("message");
    expect(frameAtA.gseq).toBeTypeOf("number");
    const g1 = frameAtA.gseq as number;

    // A disconnects
    const aClosed = waitClose(wsA);
    wsA.close();
    await aClosed;
    await waitFor(() => (hub.getConn("a-resend") === undefined ? true : undefined));

    // B sends M2 while A offline (queued for resend)
    const m2 = makeEnvelope<MessagePayload>(
      "message",
      "b-resend",
      "r-resend",
      3,
      0,
      { msg_id: randomUUID(), text: "M2", mentions: [] },
    );
    wsB.send(JSON.stringify(m2));
    await new Promise<void>((res) => setTimeout(res, 100));

    // A reconnects with last_seen_seq=-1: no resend of M2, all gseq > previous max
    const wsA2 = await connectClient();
    sendHello(wsA2, "a-resend", PROTOCOL_VERSION_STR, -1, "r-resend");
    await waitFor(() => hub.getConn("a-resend"));

    const seenAtA2: Envelope[] = [];
    const onMsg = (d: unknown) => seenAtA2.push(JSON.parse(String(d)) as Envelope);
    wsA2.on("message", onMsg);
    await new Promise<void>((res) => setTimeout(res, 250));
    wsA2.off("message", onMsg);
    for (const f of seenAtA2) {
      expect(typeof f.gseq === "number" ? f.gseq : 0).toBeGreaterThan(g1);
    }
    expect(seenAtA2.find((f) => (f.payload as MessagePayload | undefined)?.text === "M2")).toBeUndefined();

    // A disconnects again
    const a2Closed = waitClose(wsA2);
    wsA2.close();
    await a2Closed;
    await waitFor(() => (hub.getConn("a-resend") === undefined ? true : undefined));

    // B sends M3 while A offline
    const m3 = makeEnvelope<MessagePayload>(
      "message",
      "b-resend",
      "r-resend",
      4,
      0,
      { msg_id: randomUUID(), text: "M3", mentions: [] },
    );
    wsB.send(JSON.stringify(m3));
    await new Promise<void>((res) => setTimeout(res, 100));

    // A reconnects with last_seen_seq=G1: should receive M2 and M3 resends with gseq > G1
    const wsA3 = await connectClient();
    // 监听器必须在 sendHello 之前挂载：服务端在 hello 处理流程内同步补发，挂晚了帧会丢
    const collected: Envelope[] = [];
    const onMsg3 = (d: unknown) => collected.push(JSON.parse(String(d)) as Envelope);
    wsA3.on("message", onMsg3);
    sendHello(wsA3, "a-resend", PROTOCOL_VERSION_STR, g1, "r-resend");
    await waitFor(() => hub.getConn("a-resend"));

    const gotM2 = await waitFor(() =>
      collected.find(
        (f) =>
          f.type === "message" &&
          (f.payload as MessagePayload | undefined)?.text === "M2" &&
          typeof f.gseq === "number" &&
          (f.gseq as number) > g1,
      ),
    );
    const gotM3 = await waitFor(() =>
      collected.find(
        (f) =>
          f.type === "message" &&
          (f.payload as MessagePayload | undefined)?.text === "M3" &&
          typeof f.gseq === "number" &&
          (f.gseq as number) > g1,
      ),
    );
    expect(gotM2).toBeDefined();
    expect(gotM3).toBeDefined();
    wsA3.off("message", onMsg3);
  });
});
