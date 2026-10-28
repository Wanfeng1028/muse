import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { startServer } from "../src/server.js";
import { openDb } from "../src/db.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let dataDir: string;
let db: ReturnType<typeof openDb>;
let server: ReturnType<typeof startServer>;
let baseUrl: string;

async function api(method: string, path: string, body?: unknown) {
  const res = await fetch(baseUrl + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const status = res.status;
  const parsed = await res.json().catch(() => null);
  return { status, body: parsed };
}

async function createRoom() {
  await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
}

describe("POST /api/rooms/:room/pairing-codes ttl_minutes 收紧规则", () => {
  beforeEach(() => {
    dataDir = mkdtempSync(join(tmpdir(), "pairing-ttl-test-"));
    db = openDb(join(dataDir, "dbdir"));
    server = startServer(
      {
        port: 0,
        dataDir: join(dataDir, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db
    );
    const address = server.httpServer.address() as { port: number };
    baseUrl = `http://127.0.0.1:${address.port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("ttl_minutes 为 0 返回 400 且 error 为 INVALID_TTL_MINUTES", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: 0 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_MINUTES" });
  });

  it("ttl_minutes 为 -1 返回 400 且 error 为 INVALID_TTL_MINUTES", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: -1 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_MINUTES" });
  });

  it("ttl_minutes 为 61 返回 400 且 error 为 INVALID_TTL_MINUTES", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: 61 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_MINUTES" });
  });

  it("ttl_minutes 为 999 返回 400 且 error 为 INVALID_TTL_MINUTES", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: 999 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_MINUTES" });
  });

  it("ttl_minutes 为 1.5 返回 400 且 error 为 INVALID_TTL_MINUTES", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: 1.5 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_MINUTES" });
  });

  it("ttl_minutes 为字符串 \"10\" 返回 400 且 error 为 INVALID_TTL_MINUTES", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: "10" });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_MINUTES" });
  });

  it("ttl_minutes 为 null 返回 400 且 error 为 INVALID_TTL_MINUTES", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: null });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_MINUTES" });
  });

  it("ttl_minutes 为 true 返回 400 且 error 为 INVALID_TTL_MINUTES", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: true });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_MINUTES" });
  });

  it("非房主 mallory 传非法 ttl_minutes 仍返回 403 且 error 为 ROOM_MANAGE_FORBIDDEN", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "mallory", ttl_minutes: 0 });
    expect(res.status).toBe(403);
    expect(res.body).toEqual({ error: "ROOM_MANAGE_FORBIDDEN" });
  });

  it("ttl_minutes 为 1 返回 201 且 expires_at_ms 约等于请求时刻加 1 分钟", async () => {
    await createRoom();
    const anchor = Date.now();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: 1 });
    expect(res.status).toBe(201);
    expect(typeof res.body.code).toBe("string");
    expect(res.body.code.length).toBeGreaterThan(0);
    const diff = res.body.expires_at_ms - anchor;
    expect(diff).toBeGreaterThanOrEqual(30000);
    expect(diff).toBeLessThanOrEqual(90000);
  });

  it("ttl_minutes 为 60 返回 201 且 expires_at_ms 约等于请求时刻加 60 分钟", async () => {
    await createRoom();
    const anchor = Date.now();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice", ttl_minutes: 60 });
    expect(res.status).toBe(201);
    expect(typeof res.body.code).toBe("string");
    expect(res.body.code.length).toBeGreaterThan(0);
    const diff = res.body.expires_at_ms - anchor;
    expect(diff).toBeGreaterThanOrEqual(3540000);
    expect(diff).toBeLessThanOrEqual(3660000);
  });

  it("缺省 ttl_minutes 返回 201 且 expires_at_ms 约等于请求时刻加 10 分钟", async () => {
    await createRoom();
    const anchor = Date.now();
    const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    expect(res.status).toBe(201);
    expect(typeof res.body.code).toBe("string");
    expect(res.body.code.length).toBeGreaterThan(0);
    const diff = res.body.expires_at_ms - anchor;
    expect(diff).toBeGreaterThanOrEqual(540000);
    expect(diff).toBeLessThanOrEqual(660000);
  });
});
