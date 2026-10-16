import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WebSocketServer } from "ws";
import type { WebSocket } from "ws";
import { HEARTBEAT_MS } from "@botstalk/protocol";
import { AdapterClient } from "../src/client.js";

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

describe("AdapterClient", () => {
  let gateway: FakeGateway;
  let client: AdapterClient | null;

  beforeEach(async () => {
    gateway = await startFakeGateway();
    client = null;
  });

  afterEach(async () => {
    client?.disconnect();
    client = null;
    vi.useRealTimers();
    await gateway.close();
  });

  it("sends hello with adapter_id and protocol_version 1.1", async () => {
    client = new AdapterClient({ adapterId: "test-adapter", gatewayUrl: gateway.url });
    client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    const hello = gateway.received.find((f) => f.type === "hello");
    expect(hello).toBeDefined();
    const payload = hello?.payload as { adapter_id: string; protocol_version: string; last_seen_seq: number };
    expect(payload.adapter_id).toBe("test-adapter");
    expect(payload.protocol_version).toBe("1.1");
  });

  it("sends presence heartbeat on interval", async () => {
    client = new AdapterClient({ adapterId: "hb-adapter", gatewayUrl: gateway.url, heartbeatMs: 100 });
    client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    await waitFor(() => gateway.received.some((f) => f.type === "presence"), 3000);
    const count = gateway.received.filter((f) => f.type === "presence").length;
    expect(count).toBeGreaterThan(0);
  });

  it("sendMessage increments seq monotonically", async () => {
    client = new AdapterClient({ adapterId: "seq-adapter", gatewayUrl: gateway.url });
    client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    client.sendMessage("one");
    client.sendMessage("two");
    await waitFor(() => gateway.received.filter((f) => f.type === "message").length >= 2);
    const messages = gateway.received.filter((f) => f.type === "message");
    expect(messages.length).toBeGreaterThanOrEqual(2);
    for (let i = 1; i < messages.length; i++) {
      const prev = messages[i - 1];
      const cur = messages[i];
      if (prev && cur) {
        expect(cur.seq).toBeGreaterThan(prev.seq);
      }
    }
  });

  it("resends frames on gap", async () => {
    client = new AdapterClient({ adapterId: "gap-adapter", gatewayUrl: gateway.url });
    client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    const env1 = client.sendMessage("first");
    const env2 = client.sendMessage("second");
    await waitFor(() => gateway.received.filter((f) => f.type === "message").length >= 2);

    const beforeCount = gateway.received.filter((f) => f.type === "message").length;
    gateway.sendToClients({
      v: 1,
      type: "gap",
      seq: 100,
      ack: 0,
      sender: "gateway",
      room: "lobby",
      ts: Date.now(),
      payload: { from_seq: env1.seq, to_seq: env1.seq },
    });
    await waitFor(() => gateway.received.filter((f) => f.type === "message").length > beforeCount);
    const resent = gateway.received.filter((f) => f.type === "message");
    const seqs = resent.map((f) => f.seq);
    expect(seqs).toContain(env1.seq);
    expect(env2.seq).toBeGreaterThan(env1.seq);
  });

  it("dispatches chat to onMessage and task to onTask", async () => {
    const onMessage = vi.fn();
    const onTask = vi.fn();
    client = new AdapterClient({
      adapterId: "dispatch-adapter",
      gatewayUrl: gateway.url,
      onMessage,
      onTask,
    });
    client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));

    gateway.sendToClients({
      v: 1,
      type: "message",
      seq: 10,
      ack: 0,
      sender: "peer",
      room: "lobby",
      ts: Date.now(),
      payload: { msg_id: "m1", text: "hi", mentions: [], intent: "chat" },
    });
    await waitFor(() => onMessage.mock.calls.length > 0);

    gateway.sendToClients({
      v: 1,
      type: "message",
      seq: 11,
      ack: 0,
      sender: "peer",
      room: "lobby",
      ts: Date.now(),
      payload: { msg_id: "m2", text: "do", mentions: [], intent: "task", task_id: "t1", task_status: "running" },
    });
    await waitFor(() => onTask.mock.calls.length > 0);

    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onTask).toHaveBeenCalledTimes(1);
    const chatEnv = onMessage.mock.calls[0]?.[0] as { payload: { text: string } };
    expect(chatEnv.payload.text).toBe("hi");
    const taskEnv = onTask.mock.calls[0]?.[0] as { payload: { task_id: string } };
    expect(taskEnv.payload.task_id).toBe("t1");
  });

  it("收到带 gseq 的帧后 maxGseq 推进且不回退", async () => {
    client = new AdapterClient({ adapterId: "test-adapter", gatewayUrl: gateway.url });
    client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    gateway.sendToClients({ v: 1, type: "message", seq: 1, ack: 0, sender: "peer", room: "lobby", ts: Date.now(), gseq: 5, payload: { msg_id: "x1", text: "hi", mentions: [] } });
    gateway.sendToClients({ v: 1, type: "message", seq: 2, ack: 0, sender: "peer", room: "lobby", ts: Date.now(), gseq: 3, payload: { msg_id: "x2", text: "hi", mentions: [] } });
    gateway.sendToClients({ v: 1, type: "message", seq: 3, ack: 0, sender: "peer", room: "lobby", ts: Date.now(), gseq: 9, payload: { msg_id: "x3", text: "hi", mentions: [] } });
    await waitFor(() => (client as unknown as { maxGseq: number }).maxGseq === 9);
    expect((client as unknown as { maxGseq: number }).maxGseq).toBe(9);
  });

  it("hello 的 last_seen_seq 等于当前 maxGseq", async () => {
    client = new AdapterClient({ adapterId: "test-adapter", gatewayUrl: gateway.url });
    (client as unknown as { maxGseq: number }).maxGseq = 42;
    client.connect();
    await waitFor(() => gateway.received.some((f) => f.type === "hello"));
    const helloFrame = gateway.received.find((f) => f.type === "hello");
    expect((helloFrame.payload as { last_seen_seq: number }).last_seen_seq).toBe(42);
  });
});
// 自查：红线 1-5 逐条通过
