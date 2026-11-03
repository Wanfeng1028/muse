import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { WebSocketServer, WebSocket } from "ws";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import { makeEnvelope, parseEnvelope } from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb, type Db } from "../src/db.js";
import { routeMessage } from "../src/router.js";

const TEST_TMP_ROOT = join(import.meta.dirname ?? __dirname, "test-tmp");
mkdirSync(TEST_TMP_ROOT, { recursive: true });

interface FrameCollector {
  ws: WebSocket;
  id: string;
  frames: Envelope[];
  seq: number;
  closed: boolean;
}

class TestClient {
  public ws: WebSocket;
  public id: string;
  public frames: Envelope[];
  public seq: number;
  private closed: boolean;

  constructor(ws: WebSocket, id: string) {
    this.ws = ws;
    this.id = id;
    this.frames = [];
    this.seq = 0;
    this.closed = false;
    this.ws.on("message", (data: unknown) => {
      const raw = typeof data === "string" ? data : Buffer.from(data as ArrayBuffer).toString("utf8");
      try {
        this.frames.push(parseEnvelope(raw) as Envelope);
      } catch {
        /* ignore malformed */
      }
    });
  }

  nextSeq(): number {
    this.seq += 1;
    return this.seq;
  }

  sendHello(room: string): void {
    const env = makeEnvelope(
      "hello",
      this.id,
      room,
      this.nextSeq(),
      0,
      { adapter_id: this.id, protocol_version: "1.3", last_seen_seq: 0 },
    );
    this.ws.send(JSON.stringify(env));
  }

  sendMessage(
    room: string,
    payload: MessagePayload,
  ): void {
    const env = makeEnvelope(
      "message",
      this.id,
      room,
      this.nextSeq(),
      0,
      payload,
    );
    this.ws.send(JSON.stringify(env));
  }

  sendCapabilityUpdate(
    room: string,
    version: number,
    intents: ("chat" | "task")[],
  ): void {
    const env = makeEnvelope(
      "capability_update",
      this.id,
      room,
      this.nextSeq(),
      0,
      { version, capabilities: { intents } },
    );
    this.ws.send(JSON.stringify(env));
  }

  async waitFor(
    pred: (env: Envelope) => boolean,
    timeoutMs = 2000,
  ): Promise<Envelope> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const found = this.frames.find(pred);
      if (found) return found;
      await sleep(10);
    }
    throw new Error(`waitFor timeout for client ${this.id}`);
  }

  async close(): Promise<void> {
    if (this.closed) return;
    this.closed = true;
    await new Promise<void>((resolve) => {
      if (this.ws.readyState === WebSocket.CLOSED) {
        resolve();
        return;
      }
      this.ws.once("close", () => resolve());
      this.ws.close();
    });
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitConn(hub: Hub, id: string, timeoutMs = 2000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (hub.getConn(id)) return;
    await sleep(10);
  }
  throw new Error(`waitConn timeout for ${id}`);
}

async function waitCapabilityVersion(
  hub: Hub,
  id: string,
  version: number,
  timeoutMs = 2000,
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const conn = hub.getConn(id);
    if (conn && conn.capabilityVersion === version) return;
    await sleep(10);
  }
  throw new Error(`waitCapabilityVersion timeout for ${id} v=${version}`);
}

describe("router", () => {
  let tmpDir: string;
  let db: Db;
  let hub: Hub;
  let wss: WebSocketServer;
  let port: number;
  const clients: TestClient[] = [];

  beforeEach(async () => {
    tmpDir = mkdtempSync(join(TEST_TMP_ROOT, "router-"));
    db = openDb(tmpDir);
    hub = new Hub(db);
    hub.onMessage = (env) => routeMessage(hub, env, db);
    wss = new WebSocketServer({ port: 0 });
    wss.on("connection", (ws) => hub.handleConnection(ws));
    await new Promise<void>((resolve) => {
      if (wss.address()) {
        resolve();
        return;
      }
      wss.once("listening", () => resolve());
    });
    const addr = wss.address();
    if (typeof addr === "object" && addr) {
      port = addr.port;
    } else {
      throw new Error("no ws address");
    }
  });

  afterEach(async () => {
    for (const c of clients) {
      await c.close();
    }
    clients.length = 0;
    await new Promise<void>((resolve) => wss.close(() => resolve()));
    db.close();
    rmSync(tmpDir, { recursive: true, force: true });
  });

  async function connect(id: string, room: string): Promise<TestClient> {
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    await new Promise<void>((resolve, reject) => {
      ws.once("open", () => resolve());
      ws.once("error", reject);
    });
    const client = new TestClient(ws, id);
    clients.push(client);
    client.sendHello(room);
    await waitConn(hub, id);
    return client;
  }

  it("chat 广播：A 发无 mentions 的 chat → B 收到", async () => {
    const room = "r1";
    const a = await connect("a-id", room);
    const b = await connect("b-id", room);

    a.sendMessage(room, {
      msg_id: "m-1",
      text: "hello room",
      mentions: [],
    });

    const got = await b.waitFor(
      (env) =>
        env.type === "message" &&
        (env.payload as MessagePayload).msg_id === "m-1",
    );
    expect(got.sender).toBe("a-id");
    expect((got.payload as MessagePayload).text).toBe("hello room");
  });

  it("@定向：A 发 mentions=[b-id] → B 收到、A 回显，C 未收到", async () => {
    const room = "r2";
    const a = await connect("a-id", room);
    const b = await connect("b-id", room);

    a.sendMessage(room, {
      msg_id: "m-2",
      text: "hey b",
      mentions: ["b-id"],
    });

    const gotB = await b.waitFor(
      (env) =>
        env.type === "message" &&
        (env.payload as MessagePayload).msg_id === "m-2",
    );
    expect(gotB.sender).toBe("a-id");

    const gotA = await a.waitFor(
      (env) =>
        env.type === "message" &&
        (env.payload as MessagePayload).msg_id === "m-2",
    );
    expect(gotA.sender).toBe("a-id");

    const c = await connect("c-id", room);
    await sleep(150);
    const cGot = c.frames.find(
      (env) =>
        env.type === "message" &&
        (env.payload as MessagePayload).msg_id === "m-2",
    );
    expect(cGot).toBeUndefined();
  });

  it("task 路由：B 登记 task 能力，A 发 task → B 收到", async () => {
    const room = "r3";
    const a = await connect("a-id", room);
    const b = await connect("b-id", room);

    b.sendCapabilityUpdate(room, 1, ["chat", "task"]);
    await waitCapabilityVersion(hub, "b-id", 1);
    const connB = hub.getConn("b-id");
    expect(connB?.capabilities.intents).toContain("task");

    a.sendMessage(room, {
      msg_id: "m-3",
      text: "do task",
      mentions: [],
      intent: "task",
      task_id: "t-1",
    });

    const got = await b.waitFor(
      (env) =>
        env.type === "message" &&
        (env.payload as MessagePayload).task_id === "t-1",
    );
    expect((got.payload as MessagePayload).intent).toBe("task");
  });

  it("task 无可用：只有 A（无 task 能力），A 发 task → 网关回执 unsupported", async () => {
    const room = "r4";
    const a = await connect("a-id", room);

    a.sendMessage(room, {
      msg_id: "m-4",
      text: "task to self",
      mentions: ["a-id"],
      intent: "task",
      task_id: "t-unsup",
    });

    const got = await a.waitFor(
      (env) =>
        env.type === "message" &&
        (env.payload as MessagePayload).task_id === "t-unsup" &&
        (env.payload as MessagePayload).task_status === "unsupported",
    );
    expect(got.sender).toBe("gateway");
    expect((got.payload as MessagePayload).task_status).toBe("unsupported");
    expect((got.payload as MessagePayload).task_id).toBe("t-unsup");
    expect((got.payload as MessagePayload).intent).toBe("task");
  });

  it("capability version 乱序：B 发 v5 再发 v3 → 仍是 5", async () => {
    const room = "r5";
    const b = await connect("b-id", room);

    b.sendCapabilityUpdate(room, 5, ["chat", "task"]);
    await waitCapabilityVersion(hub, "b-id", 5);

    b.sendCapabilityUpdate(room, 3, ["chat"]);
    await sleep(150);

    const conn = hub.getConn("b-id");
    expect(conn?.capabilityVersion).toBe(5);
    expect(conn?.capabilities.intents).toEqual(["chat", "task"]);
  });

  it("task 回执（task_status 已设置）广播而不重路由", async () => {
    const room = "r-receipt";
    const worker = await connect("worker-id", room);
    const watcher = await connect("watcher-id", room);
    // worker 发 task 回执（task_status=done），mentions 为空
    worker.sendMessage(room, {
      msg_id: "r1",
      text: "[x] done",
      mentions: [],
      intent: "task",
      task_id: "t1",
      task_status: "done",
    });
    const got = await watcher.waitFor(
      (env: Envelope) =>
        env.type === "message" &&
        (env.payload as MessagePayload).msg_id === "r1",
    );
    expect(got.sender).toBe("worker-id");
    expect((got.payload as MessagePayload).task_status).toBe("done");
  });
});

// 自查：红线 1-5 逐条通过
