import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WebSocketServer } from "ws";
import type { WebSocket } from "ws";
import { AdapterClient } from "../src/client.js";
import type { ThreadHistoryMessage } from "../src/thread-context.js";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import * as fs from "node:fs";
import * as os from "node:os";

interface ReceivedFrame {
  v: number;
  type: string;
  seq: number;
  ack: number;
  sender: string;
  room: string;
  ts: number;
  payload: unknown;
}

interface FakeGateway {
  url: string;
  received: ReceivedFrame[];
  sockets: WebSocket[];
  sendToClients: (frame: unknown) => void;
  close: () => Promise<void>;
}

async function startFakeGateway(): Promise<FakeGateway> {
  const wss = new WebSocketServer({ port: 0 });
  await new Promise<void>((resolve) => wss.once("listening", () => resolve()));
  const addr = wss.address();
  if (typeof addr === "string" || addr === null) {
    throw new Error("no address");
  }
  const url = `ws://127.0.0.1:${addr.port}`;
  const received: ReceivedFrame[] = [];
  const sockets: WebSocket[] = [];

  wss.on("connection", (socket) => {
    sockets.push(socket);
    socket.on("message", (data) => {
      const text = typeof data === "string" ? data : String(data);
      const frame = JSON.parse(text) as ReceivedFrame;
      received.push(frame);
      if (frame.type === "hello") {
        socket.send(
          JSON.stringify({
            v: 1,
            type: "presence",
            seq: 1,
            ack: frame.seq,
            sender: "gateway",
            room: "lobby",
            ts: Date.now(),
            payload: { status: "online" },
          }),
        );
      }
    });
  });

  return {
    url,
    received,
    sockets,
    sendToClients: (frame: unknown) => {
      const text = JSON.stringify(frame);
      for (const s of sockets) {
        if (s.readyState === s.OPEN) s.send(text);
      }
    },
    close: async () => {
      for (const s of sockets) {
        try {
          s.close();
        } catch {
          // ignore
        }
      }
      await new Promise<void>((resolve) => wss.close(() => resolve()));
    },
  };
}

function waitFor(predicate: () => boolean, timeoutMs = 2000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => {
      if (predicate()) {
        resolve();
        return;
      }
      if (Date.now() - start > timeoutMs) {
        reject(new Error("timeout waiting for predicate"));
        return;
      }
      setTimeout(tick, 10);
    };
    tick();
  });
}


function makeMessageFrame(
  seq: number,
  sender: string,
  payload: Record<string, unknown>,
  ts?: number,
  room?: string,
) {
  return {
    v: 1,
    type: "message",
    seq,
    ack: 0,
    sender,
    room: room ?? "lobby",
    ts: ts ?? Date.now(),
    payload,
  };
}

describe("AdapterClient threadContext", () => {
  let gateway: FakeGateway;
  let client: AdapterClient | null;
  let tmpDir: string;

  beforeEach(async () => {
    gateway = await startFakeGateway();
    client = null;
    tmpDir = fs.mkdtempSync(os.tmpdir() + "/tc-test-");
  });

  afterEach(async () => {
    if (client) {
      await client.disconnect();
      client = null;
    }
    await gateway.close();
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it("disabled by default", async () => {
    const received: Envelope[] = [];

    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      onMessage: (envelope) => {
        received.push(envelope);
      },
    });

    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));

    const payload = { msg_id: "m1", text: "hello world", mentions: [] };
    gateway.sendToClients(makeMessageFrame(1, "alice", payload));

    await waitFor(() => received.length > 0);

    const env0 = received[0];
    if (env0 === undefined) throw new Error("no message received");
    const p = env0.payload as Record<string, unknown>;
    expect(p.thread_context).toBeUndefined();
    expect(p.text).toBe("hello world");
  });

  it("enabled + injected history", async () => {
    const received: Envelope[] = [];
    const fetchHistory = vi.fn(async (): Promise<ThreadHistoryMessage[]> => [
      { sender: "alice", text: "first point about the budget", ts: 1000, msgId: "h1", frameType: "message" },
      { sender: "bob", text: "second point about the timeline", ts: 2000, msgId: "h2", frameType: "message" },
      { sender: "carol", text: "status text that must not appear", ts: 3000, msgId: "h3", frameType: "message", taskStatus: "done" },
    ]);

    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: {
        enabled: true,
        fetchHistory,
      },
      onMessage: (envelope) => {
        received.push(envelope);
      },
    });

    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));

    const payload = { msg_id: "trig1", text: "current question", mentions: [] };
    gateway.sendToClients(makeMessageFrame(1, "alice", payload, 4000));

    await waitFor(() => received.length > 0);

    const env0 = received[0];
    if (env0 === undefined) throw new Error("no message received");
    const p = env0.payload as Record<string, unknown>;
    const block = p.thread_context as string;
    const texts = block
      .split("\n")
      .filter((l) => l.startsWith("{"))
      .map((l) => (JSON.parse(l) as { text: string }).text);
    const idxFirst = texts.indexOf("first point about the budget");
    const idxSecond = texts.indexOf("second point about the timeline");
    expect(idxFirst).toBeGreaterThan(-1);
    expect(idxSecond).toBeGreaterThan(-1);
    expect(idxFirst).toBeLessThan(idxSecond);
    expect(texts.includes("status text that must not appear")).toBe(false);
    expect(p.text).toBe("current question");
    expect(fetchHistory).toHaveBeenCalledTimes(1);
    expect(fetchHistory).toHaveBeenCalledWith("lobby", { msgId: "trig1", ts: 4000 });
  });

  it("trigger self-exclusion", async () => {
    const received: Envelope[] = [];
    const fetchHistory = vi.fn(async (): Promise<ThreadHistoryMessage[]> => [
      { sender: "alice", text: "earlier message", ts: 1000, msgId: "h1", frameType: "message" },
      { sender: "alice", text: "trigger text that should be excluded", ts: 2000, msgId: "trig2", frameType: "message" },
      { sender: "bob", text: "later message", ts: 3000, msgId: "h3", frameType: "message" },
    ]);

    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: {
        enabled: true,
        fetchHistory,
      },
      onMessage: (envelope) => {
        received.push(envelope);
      },
    });

    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));

    const payload = { msg_id: "trig2", text: "trigger text that should be excluded", mentions: [] };
    gateway.sendToClients(makeMessageFrame(1, "alice", payload, 2000));

    await waitFor(() => received.length > 0);

    const env0 = received[0];
    if (env0 === undefined) throw new Error("no message received");
    const p = env0.payload as Record<string, unknown>;
    const block = p.thread_context as string;
    const texts = block
      .split("\n")
      .filter((l) => l.startsWith("{"))
      .map((l) => (JSON.parse(l) as { text: string }).text);
    expect(texts.includes("trigger text that should be excluded")).toBe(false);
    expect(texts.includes("earlier message")).toBe(true);
    expect(texts.includes("later message")).toBe(false);
  });

  it("self-sender skip", async () => {
    const received: Envelope[] = [];
    const fetchHistory = vi.fn(async (): Promise<ThreadHistoryMessage[]> => []);

    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: {
        enabled: true,
        fetchHistory,
      },
      onMessage: (envelope) => {
        received.push(envelope);
      },
    });

    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));

    const payload = { msg_id: "self1", text: "from self", mentions: [] };
    gateway.sendToClients(makeMessageFrame(1, "tc-adapter", payload));

    await waitFor(() => received.length > 0);

    expect(fetchHistory).toHaveBeenCalledTimes(0);
    const env0 = received[0];
    if (env0 === undefined) throw new Error("no message received");
    const p = env0.payload as Record<string, unknown>;
    expect(p.text).toBe("from self");
  });

  it("status-frame skip", async () => {
    const received: Envelope[] = [];
    const fetchHistory = vi.fn(async (): Promise<ThreadHistoryMessage[]> => []);

    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: {
        enabled: true,
        fetchHistory,
      },
      onMessage: (envelope) => {
        received.push(envelope);
      },
      onTask: (envelope) => {
        received.push(envelope);
      },
    });

    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));

    const payload = { msg_id: "status1", text: "status update", mentions: [], task_id: "task1", task_status: "done" };
    gateway.sendToClients(makeMessageFrame(1, "alice", payload));

    await waitFor(() => received.length > 0);

    expect(fetchHistory).toHaveBeenCalledTimes(0);
  });


  it("task_progress-frame skip", async () => {
    const received: Envelope[] = [];
    const fetchHistory = vi.fn(async () => []);
    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: { enabled: true, fetchHistory },
      onMessage: (env) => { received.push(env); },
      onTask: (env) => { received.push(env); },
    });
    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    gateway.sendToClients(
      makeMessageFrame(1, "alice", {
        msg_id: "p1",
        text: "progress note",
        mentions: [],
        intent: "task",
        task_id: "task1",
        task_progress: { task_id: "task1", message: "progress note" },
      })
    );
    await waitFor(() => received.length > 0);

    expect(fetchHistory).toHaveBeenCalledTimes(0);
    expect(received.length).toBeGreaterThan(0);
  });

  it("fetch rejection degrades", async () => {
    const received: Envelope[] = [];
    const fetchHistory = vi.fn(async () => { throw new Error("boom"); });
    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: { enabled: true, fetchHistory },
      onMessage: (env) => { received.push(env); },
      onTask: (env) => { received.push(env); },
    });
    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    gateway.sendToClients(
      makeMessageFrame(1, "alice", { msg_id: "m9", text: "original text", mentions: [] })
    );
    await waitFor(() => received.length > 0);

    const env0 = received[0];
    if (env0 === undefined) throw new Error("no message received");
    const p = env0.payload as Record<string, unknown>;
    expect(p.thread_context).toBeUndefined();
    expect(p.text).toBe("original text");
  });

  it("empty history degrades", async () => {
    const received: Envelope[] = [];
    const fetchHistory = vi.fn(async () => []);
    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: { enabled: true, fetchHistory },
      onMessage: (env) => { received.push(env); },
      onTask: (env) => { received.push(env); },
    });
    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    gateway.sendToClients(
      makeMessageFrame(1, "alice", { msg_id: "m10", text: "hello", mentions: [] })
    );
    await waitFor(() => received.length > 0);

    const env0 = received[0];
    if (env0 === undefined) throw new Error("no message received");
    const p = env0.payload as Record<string, unknown>;
    expect(p.thread_context).toBeUndefined();
  });

  it("task intent path", async () => {
    const receivedMsg: Envelope[] = [];
    const receivedTask: Envelope[] = [];
    const fetchHistory = vi.fn(async () => [
      { sender: "alice", text: "prior decision", ts: 1000, msgId: "h1", frameType: "message" },
    ]);
    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: { enabled: true, fetchHistory },
      onMessage: (env) => { receivedMsg.push(env); },
      onTask: (env) => { receivedTask.push(env); },
    });
    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    gateway.sendToClients(
      makeMessageFrame(1, "alice", { msg_id: "t9", text: "do the task", mentions: [], intent: "task", task_id: "task9" }, 2000)
    );
    await waitFor(() => receivedTask.length > 0);

    expect(receivedMsg.length).toBe(0);
    const env0 = receivedTask[0];
    if (env0 === undefined) throw new Error("no task received");
    const p = env0.payload as Record<string, unknown>;
    const tc = p.thread_context as string;
    const lines = tc.split("\n").filter((l: string) => l.startsWith("{"));
    const texts = lines.map((l: string) => (JSON.parse(l) as Record<string, unknown>).text);
    expect(texts).toContain("prior decision");
  });

  it("dm-room skip", async () => {
    const received: Envelope[] = [];
    const fetchHistory = vi.fn(async () => []);
    client = new AdapterClient({
      adapterId: "tc-adapter",
      gatewayUrl: gateway.url,
      heartbeatMs: 60000,
      stateDir: tmpDir,
      threadContext: { enabled: true, fetchHistory },
      onMessage: (env) => { received.push(env); },
      onTask: (env) => { received.push(env); },
    });
    await client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    gateway.sendToClients(
      makeMessageFrame(1, "alice", { msg_id: "dm1", text: "dm hello", mentions: [] }, undefined, "dm:alice")
    );
    await waitFor(() => received.length > 0);

    expect(fetchHistory).toHaveBeenCalledTimes(0);
    expect(received.length).toBeGreaterThan(0);
  });
});
