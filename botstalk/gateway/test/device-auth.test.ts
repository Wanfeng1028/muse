import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { WebSocketServer, WebSocket } from "ws";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope, PROTOCOL_VERSION_STR } from "@botstalk/protocol";
import type { HelloPayload, MessagePayload } from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb, getDevice, upsertDevice, revokeDevice } from "../src/db.js";
import type { Db } from "../src/db.js";
import { hashDeviceKey } from "../src/devices.js";

let tmpDir: string;
let db: Db;
let wss: WebSocketServer;
let port: number;
let hub: Hub;

beforeEach(async () => {
  tmpDir = mkdtempSync(join(tmpdir(), "botstalk-device-auth-"));
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

function waitClose(ws: WebSocket, timeoutMs = 3000): Promise<{ code: number }> {
  return new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("timeout waiting close")), timeoutMs);
    ws.once("close", (code: number) => { clearTimeout(t); res({ code }); });
  });
}

async function waitConn(adapterId: string, timeoutMs = 3000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!hub.getConn(adapterId)) {
    if (Date.now() > deadline) throw new Error(`timeout waiting conn ${adapterId}`);
    await new Promise((r) => setTimeout(r, 20));
  }
}

function hello(ws: WebSocket, adapterId: string, extra: Record<string, unknown> = {}): void {
  const env = makeEnvelope<HelloPayload>("hello", adapterId, "room-a", 1, 0, { adapter_id: adapterId, protocol_version: PROTOCOL_VERSION_STR, last_seen_seq: 0, ...extra });
  ws.send(JSON.stringify(env));
}

function seed(deviceId: string, adapterId: string, key: string, room = "room-a", nowMs = 1000): void {
  upsertDevice(db, { deviceId, room, deviceKeyHash: hashDeviceKey(key), adapterId, nowMs });
}

const KEY1 = "0123456789abcdef".repeat(4);
const KEY2 = "fedcba9876543210".repeat(4);

describe("device-auth", () => {
  it("legacy hello without device fields connects", async () => {
    const ws = await connectClient();
    hello(ws, "adapter-1");
    await waitConn("adapter-1");
    expect(hub.getOnlineAdapters("room-a")).toContain("adapter-1");
  });

  it("valid device key connects and refreshes last_seen", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    hello(ws, "adapter-1", { device_id: "phone-1", device_key: KEY1 });
    await waitConn("adapter-1");
    const row = getDevice(db, "phone-1", "room-a");
    expect(row).toBeDefined();
    expect(row!.last_seen_ms).toBeGreaterThanOrEqual(1000);
  });

  it("unknown device is rejected with 4403", async () => {
    const ws = await connectClient();
    const closeP = waitClose(ws);
    hello(ws, "adapter-1", { device_id: "nope", device_key: KEY1 });
    await expect(closeP).resolves.toEqual({ code: 4403 });
    expect(hub.getConn("adapter-1")).toBeUndefined();
  });

  it("wrong key is rejected with 4403", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    const closeP = waitClose(ws);
    hello(ws, "adapter-1", { device_id: "phone-1", device_key: KEY2 });
    await expect(closeP).resolves.toEqual({ code: 4403 });
    expect(hub.getConn("adapter-1")).toBeUndefined();
  });

  it("revoked device is rejected with 4403", async () => {
    seed("phone-1", "adapter-1", KEY1);
    revokeDevice(db, "phone-1", "room-a", 2000);
    const ws = await connectClient();
    const closeP = waitClose(ws);
    hello(ws, "adapter-1", { device_id: "phone-1", device_key: KEY1 });
    await expect(closeP).resolves.toEqual({ code: 4403 });
  });

  it("device_id alone is rejected with 4403", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    const closeP = waitClose(ws);
    hello(ws, "adapter-1", { device_id: "phone-1" });
    await expect(closeP).resolves.toEqual({ code: 4403 });
  });

  it("device_key alone is rejected with 4403", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    const closeP = waitClose(ws);
    hello(ws, "adapter-1", { device_key: KEY1 });
    await expect(closeP).resolves.toEqual({ code: 4403 });
  });

  it("adapter mismatch is rejected with 4403", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    const closeP = waitClose(ws);
    hello(ws, "adapter-2", { device_id: "phone-1", device_key: KEY1 });
    await expect(closeP).resolves.toEqual({ code: 4403 });
  });

  it("failed auth does not replace the existing connection", async () => {
    const ws1 = await connectClient();
    hello(ws1, "adapter-1");
    await waitConn("adapter-1");
    const ws2 = await connectClient();
    const closeP = waitClose(ws2);
    hello(ws2, "adapter-1", { device_id: "nope", device_key: KEY1 });
    await expect(closeP).resolves.toEqual({ code: 4403 });
    expect(hub.getConn("adapter-1")).toBeDefined();
    expect(ws1.readyState).toBe(WebSocket.OPEN);
  });

  it("rotated key replaces the old key", async () => {
    seed("phone-1", "adapter-1", KEY1);
    upsertDevice(db, { deviceId: "phone-1", room: "room-a", deviceKeyHash: hashDeviceKey(KEY2), adapterId: "adapter-1", nowMs: 2000 });
    // 旧 KEY1 已被轮换，应被拒绝（新 socket）
    const wsOld = await connectClient();
    const closeP = waitClose(wsOld);
    hello(wsOld, "adapter-1", { device_id: "phone-1", device_key: KEY1 });
    await expect(closeP).resolves.toEqual({ code: 4403 });
    // 新 KEY2 连接应成功
    const wsNew = await connectClient();
    hello(wsNew, "adapter-1", { device_id: "phone-1", device_key: KEY2 });
    await waitConn("adapter-1");
  });

  it("authenticated connection can send a message frame", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    hello(ws, "adapter-1", { device_id: "phone-1", device_key: KEY1 });
    await waitConn("adapter-1");
    ws.send(JSON.stringify(makeEnvelope<MessagePayload>("message", "adapter-1", "room-a", 2, 0, { msg_id: "m-1", text: "hi", mentions: [] })));
    await new Promise((r) => setTimeout(r, 200));
    expect(ws.readyState).toBe(WebSocket.OPEN);
    expect(hub.getConn("adapter-1")).toBeDefined();
  });

  it("device from another room is rejected with 4403", async () => {
    seed("phone-9", "adapter-9", KEY1, "room-b");
    const ws = await connectClient();
    const closeP = waitClose(ws);
    hello(ws, "adapter-9", { device_id: "phone-9", device_key: KEY1 });
    await expect(closeP).resolves.toEqual({ code: 4403 });
  });
});