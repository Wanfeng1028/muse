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
import { routeMessage } from "../src/router.js";
import { getTask } from "../src/db.js";

let tmpDir: string; let db: Db; let wss: WebSocketServer; let port: number; let hub: Hub;
beforeEach(async () => {
  tmpDir = mkdtempSync(join(tmpdir(), "botstalk-hub-"));
  db = openDb(tmpDir);
  wss = new WebSocketServer({ port: 0 });
  await new Promise<void>((res) => wss.once("listening", () => res()));
  const addr = wss.address();
  port = typeof addr === "object" && addr ? addr.port : 0;
  hub = new Hub(db);
  hub.onMessage = (env: Envelope<MessagePayload>) => { routeMessage(hub, env, db); };
  wss.on("connection", (ws) => hub.handleConnection(ws));
});
const clients: WebSocket[] = [];
afterEach(async () => {
  for (const c of clients.splice(0)) { try { c.terminate(); } catch { /* ignore */ } }
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
interface FrameLog { frames: Envelope[]; }
/** 常驻收集器：建连后立刻挂载，避免广播帧在 waitForFrame 挂载前到达而错过。 */
function collectFrames(ws: WebSocket): FrameLog {
  const log: FrameLog = { frames: [] };
  ws.on("message", (d: unknown) => {
    try { log.frames.push(JSON.parse(String(d)) as Envelope); } catch { /* ignore */ }
  });
  return log;
}
async function waitForFrame(log: FrameLog, pred: (e: Envelope) => boolean, timeoutMs = 3000): Promise<Envelope> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const found = log.frames.find(pred);
    if (found) return found;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error("timeout waiting frame");
}
async function hello(ws: WebSocket, adapterId: string, room: string): Promise<void> {
  const env = makeEnvelope<HelloPayload>("hello", adapterId, room, 1, 0,
    { adapter_id: adapterId, protocol_version: PROTOCOL_VERSION_STR, last_seen_seq: 0 });
  ws.send(JSON.stringify(env));
}
async function waitConn(adapterId: string): Promise<void> {
  const deadline = Date.now() + 2000;
  while (!hub.getConn(adapterId)) {
    if (Date.now() > deadline) throw new Error("timeout waiting conn " + adapterId);
    await new Promise((r) => setTimeout(r, 20));
  }
}

describe("task lifecycle e2e", () => {
  it("dispatch → running → done 全链路", async () => {
    const user = await connectClient();
    const echo = await connectClient();
    const userLog = collectFrames(user);
    const echoLog = collectFrames(echo);
    await hello(user, "user", "lobby");
    await hello(echo, "echo", "lobby");
    await waitConn("user");
    await waitConn("echo");

    const capEnv = makeEnvelope("capability_update", "echo", "lobby", 2, 0,
      { version: 1, capabilities: { intents: ["chat", "task"] } });
    echo.send(JSON.stringify(capEnv));
    await new Promise((r) => setTimeout(r, 100));

    const dispatchEnv = makeEnvelope("message", "user", "lobby", 2, 0,
      { msg_id: "m1", text: "做个总结", mentions: ["echo"], intent: "task", task_id: "t-e2e" });
    user.send(JSON.stringify(dispatchEnv));

    const dispatchFrame = await waitForFrame(echoLog, (e) =>
      e.type === "message" &&
      (e.payload as MessagePayload).intent === "task" &&
      (e.payload as MessagePayload).task_id === "t-e2e" &&
      (e.payload as MessagePayload).task_status === undefined
    );
    expect(dispatchFrame.type).toBe("message");

    const dispatchedFrame = await waitForFrame(userLog, (e) =>
      e.type === "task_event" &&
      (e.payload as { task_id?: string }).task_id === "t-e2e" &&
      (e.payload as { status?: string }).status === "dispatched"
    );
    expect((dispatchedFrame.payload as { assignee?: string }).assignee).toBe("echo");
    expect(getTask(db, "t-e2e")?.status).toBe("dispatched");

    const runningEnv = makeEnvelope("message", "echo", "lobby", 3, 0,
      { msg_id: "m2", text: "[echo] running", mentions: [], intent: "task", task_id: "t-e2e", task_status: "running" });
    echo.send(JSON.stringify(runningEnv));

    const runningFrame = await waitForFrame(userLog, (e) =>
      e.type === "task_event" &&
      (e.payload as { task_id?: string }).task_id === "t-e2e" &&
      (e.payload as { status?: string }).status === "running"
    );
    expect(runningFrame.type).toBe("task_event");

    const doneEnv = makeEnvelope("message", "echo", "lobby", 4, 0,
      { msg_id: "m3", text: "[echo] done", mentions: [], intent: "task", task_id: "t-e2e", task_status: "done" });
    echo.send(JSON.stringify(doneEnv));

    const doneFrame = await waitForFrame(userLog, (e) =>
      e.type === "task_event" &&
      (e.payload as { task_id?: string }).task_id === "t-e2e" &&
      (e.payload as { status?: string }).status === "done"
    );
    expect(doneFrame.type).toBe("task_event");

    const task = getTask(db, "t-e2e");
    expect(task?.status).toBe("done");
    expect(task?.owner).toBe("user");
    expect(task?.title).toBe("做个总结");

    const echoReceipt = await waitForFrame(userLog, (e) =>
      e.type === "message" &&
      (e.payload as MessagePayload).task_id === "t-e2e" &&
      (e.payload as MessagePayload).task_status === "done"
    );
    expect(echoReceipt.type).toBe("message");
  });

  it("无可用 adapter → unsupported 全链路", async () => {
    const user2 = await connectClient();
    const plain = await connectClient();
    const user2Log = collectFrames(user2);
    await hello(user2, "user2", "lobby2");
    await hello(plain, "plain", "lobby2");
    await waitConn("user2");
    await waitConn("plain");

    const dispatchEnv = makeEnvelope("message", "user2", "lobby2", 2, 0,
      { msg_id: "m-unsup", text: "帮我查", mentions: [], intent: "task", task_id: "t-unsup" });
    user2.send(JSON.stringify(dispatchEnv));

    const unsupFrame = await waitForFrame(user2Log, (e) =>
      e.type === "task_event" &&
      (e.payload as { task_id?: string }).task_id === "t-unsup" &&
      (e.payload as { status?: string }).status === "unsupported"
    );
    expect(unsupFrame.type).toBe("task_event");

    const task = getTask(db, "t-unsup");
    expect(task?.status).toBe("unsupported");
    expect(task?.assignee ?? null).toBe(null);

    const gwReceipt = await waitForFrame(user2Log, (e) =>
      e.type === "message" &&
      (e.payload as MessagePayload).task_id === "t-unsup" &&
      (e.payload as MessagePayload).task_status === "unsupported" &&
      e.sender === "gateway"
    );
    expect(gwReceipt.type).toBe("message");
  });
});
