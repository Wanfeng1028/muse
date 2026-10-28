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
import { startServer } from "../src/server.js";

const KEY1 = "0123456789abcdef".repeat(4);
const KEY2 = "fedcba9876543210".repeat(4);

describe("device-revoke-kick", () => {
  let tmpDir: string;
  let db: Db;
  let wss: WebSocketServer;
  let hub: Hub;
  let port: number;
  let clients: WebSocket[];

  beforeEach(async () => {
    tmpDir = mkdtempSync(join(tmpdir(), "botstalk-device-revoke-kick-"));
    db = openDb(tmpDir);
    clients = [];
    wss = new WebSocketServer({ port: 0 });
    await new Promise<void>((resolve) => {
      wss.on("listening", () => resolve());
    });
    const address = wss.address();
    if (address === null || typeof address === "string") {
      throw new Error("WebSocketServer did not bind to a TCP port");
    }
    port = address.port;
    hub = new Hub(db);
    wss.on("connection", (ws) => hub.handleConnection(ws));
  });

  afterEach(async () => {
    for (const client of clients) {
      client.terminate();
    }
    clients = [];
    await new Promise<void>((resolve) => {
      wss.close(() => resolve());
    });
    rmSync(tmpDir, { recursive: true, force: true });
  });

  function connectClient(): Promise<WebSocket> {
    return new Promise<WebSocket>((resolve, reject) => {
      const ws = new WebSocket(`ws://127.0.0.1:${port}`);
      ws.once("open", () => {
        clients.push(ws);
        resolve(ws);
      });
      ws.once("error", reject);
    });
  }

  function waitClose(ws: WebSocket, timeoutMs = 3000): Promise<{ code: number }> {
    return new Promise<{ code: number }>((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`close event not received within ${timeoutMs}ms`));
      }, timeoutMs);
      ws.once("close", (code: number) => {
        clearTimeout(timer);
        resolve({ code });
      });
    });
  }

  function waitConn(adapterId: string, timeoutMs = 3000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    return new Promise<void>((resolve, reject) => {
      const poll = (): void => {
        if (hub.getConn(adapterId) !== undefined) {
          resolve();
          return;
        }
        if (Date.now() > deadline) {
          reject(new Error(`conn ${adapterId} not registered within ${timeoutMs}ms`));
          return;
        }
        setTimeout(poll, 10);
      };
      poll();
    });
  }

  function hello(
    ws: WebSocket,
    adapterId: string,
    extra: Record<string, unknown> = {},
    room = "room-a",
  ): void {
    const env = makeEnvelope<HelloPayload>("hello", adapterId, room, 1, 0, {
      adapter_id: adapterId,
      protocol_version: PROTOCOL_VERSION_STR,
      last_seen_seq: 0,
      ...extra,
    });
    ws.send(JSON.stringify(env));
  }

  function seed(
    deviceId: string,
    adapterId: string,
    key: string,
    room = "room-a",
    nowMs = 1000,
  ): void {
    upsertDevice(db, {
      deviceId,
      room,
      deviceKeyHash: hashDeviceKey(key),
      adapterId,
      nowMs,
    });
  }

  it("kicks a device-authenticated connection matching room and deviceId", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    hello(ws, "adapter-1", { device_id: "phone-1", device_key: KEY1 });
    await waitConn("adapter-1");
    expect(hub.getConn("adapter-1")?.deviceId).toBe("phone-1");

    const closed = waitClose(ws);
    expect(hub.kickDeviceConnections("room-a", "phone-1")).toBe(1);
    expect((await closed).code).toBe(4403);

    const deadline = Date.now() + 3000;
    while (hub.getConn("adapter-1") !== undefined) {
      if (Date.now() > deadline) {
        throw new Error("conn adapter-1 was not cleaned up within 3000ms");
      }
      await new Promise<void>((r) => setTimeout(r, 10));
    }

    expect(hub.getConn("adapter-1")).toBeUndefined();
    expect(hub.getOnlineAdapters("room-a")).not.toContain("adapter-1");
  });

  it("does not kick legacy connections whose deviceId is undefined", async () => {
    const ws = await connectClient();
    hello(ws, "adapter-1");
    await waitConn("adapter-1");
    expect(hub.getConn("adapter-1")?.deviceId).toBeUndefined();

    expect(hub.kickDeviceConnections("room-a", "phone-1")).toBe(0);
    expect(ws.readyState).toBe(WebSocket.OPEN);
    expect(hub.getConn("adapter-1")).toBeDefined();
  });

  it("does not kick a same-named device that lives in another room", async () => {
    seed("phone-1", "adapter-1", KEY1, "room-a");
    seed("phone-1", "adapter-9", KEY1, "room-b");
    const wsA = await connectClient();
    const wsB = await connectClient();
    hello(wsA, "adapter-1", { device_id: "phone-1", device_key: KEY1 }, "room-a");
    hello(wsB, "adapter-9", { device_id: "phone-1", device_key: KEY1 }, "room-b");
    await waitConn("adapter-1");
    await waitConn("adapter-9");

    const closedA = waitClose(wsA);
    expect(hub.kickDeviceConnections("room-a", "phone-1")).toBe(1);
    expect((await closedA).code).toBe(4403);
    expect(wsB.readyState).toBe(WebSocket.OPEN);
    expect(hub.getConn("adapter-9")).toBeDefined();

    const closedB = waitClose(wsB);
    expect(hub.kickDeviceConnections("room-b", "phone-1")).toBe(1);
    expect((await closedB).code).toBe(4403);
  });

  it("returns 0 for an unknown device and leaves online connections untouched", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    hello(ws, "adapter-1", { device_id: "phone-1", device_key: KEY1 });
    await waitConn("adapter-1");

    expect(hub.kickDeviceConnections("room-a", "nope")).toBe(0);
    expect(ws.readyState).toBe(WebSocket.OPEN);
    expect(hub.getConn("adapter-1")).toBeDefined();
  });

  it("returns 0 on a second kick for the same device", async () => {
    seed("phone-1", "adapter-1", KEY1);
    const ws = await connectClient();
    hello(ws, "adapter-1", { device_id: "phone-1", device_key: KEY1 });
    await waitConn("adapter-1");

    const closed = waitClose(ws);
    expect(hub.kickDeviceConnections("room-a", "phone-1")).toBe(1);
    expect((await closed).code).toBe(4403);

    const deadline = Date.now() + 3000;
    while (hub.getConn("adapter-1") !== undefined) {
      if (Date.now() > deadline) {
        throw new Error("conn adapter-1 was not cleaned up within 3000ms");
      }
      await new Promise<void>((r) => setTimeout(r, 10));
    }

    expect(hub.kickDeviceConnections("room-a", "phone-1")).toBe(0);
  });
});

describe("device-revoke-kick-rest", () => {
  let dataDir: string;
  let db: ReturnType<typeof openDb>;
  let server: ReturnType<typeof startServer>;
  let baseUrl: string;

  beforeEach(() => {
    dataDir = mkdtempSync(join(tmpdir(), "devices-revoke-kick-rest-"));
    db = openDb(join(dataDir, "dbdir"));
    server = startServer({ port: 0, dataDir: join(dataDir, "dbdir"), roomMaxMembersWorkroom: 50, roomMaxMembersPlayroom: 200, gameBroadcastThrottleMs: 500 }, db);
    const address = server.httpServer.address();
    baseUrl = `http://127.0.0.1:${typeof address === "object" && address ? address.port : 0}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  async function api(path: string, method: string, body?: unknown): Promise<{ status: number; body: any }> {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    const res = await fetch(`${baseUrl}${path}`, init);
    let parsed: any = {};
    try {
      parsed = await res.json();
    } catch {
      parsed = {};
    }
    return { status: res.status, body: parsed };
  }

  async function waitForPresenceAdapter(adapterId: string, timeoutMs = 5000): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const res = await api("/api/rooms/room1/presence", "GET");
      if (res.status === 200 && Array.isArray(res.body.members) && res.body.members.some((m: any) => m.adapter_id === adapterId)) {
        return true;
      }
      await new Promise((r) => setTimeout(r, 50));
    }
    return false;
  }

  it("revokes a device via REST and kicks its live connection", async () => {
    const createRes = await api("/api/rooms", "POST", { id: "room1", name: "Room 1", owner: "alice" });
    expect(createRes.status).toBe(201);

    const codeRes = await api("/api/rooms/room1/pairing-codes", "POST", { requester: "alice" });
    expect(codeRes.status).toBe(201);
    const code = codeRes.body.code;

    const redeemRes = await api("/api/pairing-codes/redeem", "POST", { code, adapter_id: "adapter1", device_id: "phone-1" });
    expect(redeemRes.status).toBe(200);
    const deviceKey = redeemRes.body.device_key as string;
    expect(deviceKey).toMatch(/^[0-9a-f]{64}$/);
    expect(redeemRes.body.room).toBe("room1");

    const address = server.httpServer.address();
    const port = typeof address === "object" && address ? address.port : 0;
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    const closed = new Promise<number>((resolve) => {
      ws.addEventListener("close", (ev) => resolve(ev.code));
    });

    try {
      await new Promise<void>((resolve, reject) => {
        ws.addEventListener("open", () => resolve(), { once: true });
        ws.addEventListener("error", (err) => reject(err), { once: true });
      });

      const env = makeEnvelope<HelloPayload>("hello", "adapter1", "room1", 1, 0, {
        adapter_id: "adapter1",
        protocol_version: PROTOCOL_VERSION_STR,
        last_seen_seq: 0,
        device_id: "phone-1",
        device_key: deviceKey,
      });
      ws.send(JSON.stringify(env));

      const present = await waitForPresenceAdapter("adapter1");
      expect(present).toBe(true);

      const delRes = await api("/api/rooms/room1/devices/phone-1", "DELETE", { requester: "alice" });
      expect(delRes.status).toBe(204);

      const code4403 = await closed;
      expect(code4403).toBe(4403);

      const ws2 = new WebSocket(`ws://127.0.0.1:${port}`);
      const closed2 = new Promise<number>((resolve) => {
        ws2.addEventListener("close", (ev) => resolve(ev.code));
      });
      try {
        await new Promise<void>((resolve, reject) => {
          ws2.addEventListener("open", () => resolve(), { once: true });
          ws2.addEventListener("error", (err) => reject(err), { once: true });
        });
        const env2 = makeEnvelope<HelloPayload>("hello", "adapter1", "room1", 1, 0, {
          adapter_id: "adapter1",
          protocol_version: PROTOCOL_VERSION_STR,
          last_seen_seq: 0,
          device_id: "phone-1",
          device_key: deviceKey,
        });
        ws2.send(JSON.stringify(env2));
        const code2 = await closed2;
        expect(code2).toBe(4403);
      } finally {
        ws2.terminate();
      }
    } finally {
      ws.terminate();
    }
  });

  it("returns 404 DEVICE_NOT_FOUND when revoking an unknown device", async () => {
    const createRes = await api("/api/rooms", "POST", { id: "room1", name: "Room 1", owner: "alice" });
    expect(createRes.status).toBe(201);

    const delRes = await api("/api/rooms/room1/devices/nope", "DELETE", { requester: "alice" });
    expect(delRes.status).toBe(404);
    expect(delRes.body.error).toBe("DEVICE_NOT_FOUND");
  });
});
