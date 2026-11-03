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
  const res = await fetch(baseUrl + path, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const status = res.status;
  const parsed = await res.json().catch(() => null);
  return { status, body: parsed };
}
async function createRoom() {
  await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
}
beforeEach(() => {
  dataDir = mkdtempSync(join(tmpdir(), "share-ttl-test-"));
  db = openDb(join(dataDir, "dbdir"));
  server = startServer({ port: 0, dataDir: join(dataDir, "dbdir"), roomMaxMembersWorkroom: 50, roomMaxMembersPlayroom: 200, gameBroadcastThrottleMs: 500 }, db);
  const addr = server.httpServer.address() as { port: number };
  baseUrl = `http://127.0.0.1:${addr.port}`;
});
afterEach(async () => {
  await server.close();
  rmSync(dataDir, { recursive: true, force: true });
});
describe("POST /api/rooms/:room/share-links ttl_hours 收紧规则", () => {
  it("ttl_hours 为 0 返回 400 且 body 等于 INVALID_TTL_HOURS", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: 0 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_HOURS" });
  });
  it("ttl_hours 为 -1 返回 400 且 body 等于 INVALID_TTL_HOURS", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: -1 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_HOURS" });
  });
  it("ttl_hours 为 721 返回 400 且 body 等于 INVALID_TTL_HOURS", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: 721 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_HOURS" });
  });
  it("ttl_hours 为 9999 返回 400 且 body 等于 INVALID_TTL_HOURS", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: 9999 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_HOURS" });
  });
  it("ttl_hours 为 1.5 返回 400 且 body 等于 INVALID_TTL_HOURS", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: 1.5 });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_HOURS" });
  });
  it('ttl_hours 为字符串 "24" 返回 400 且 body 等于 INVALID_TTL_HOURS', async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: "24" });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_HOURS" });
  });
  it("ttl_hours 为 null 返回 400 且 body 等于 INVALID_TTL_HOURS", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: null });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_HOURS" });
  });
  it("ttl_hours 为 true 返回 400 且 body 等于 INVALID_TTL_HOURS", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: true });
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ error: "INVALID_TTL_HOURS" });
  });
  it("非房主 mallory 传 ttl_hours 0 返回 403 且 body 等于 ROOM_MANAGE_FORBIDDEN", async () => {
    await createRoom();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "mallory", ttl_hours: 0 });
    expect(res.status).toBe(403);
    expect(res.body).toEqual({ error: "ROOM_MANAGE_FORBIDDEN" });
  });
  it("ttl_hours 为 1 返回 201，share_token 长度 32，expires_at_ms 与 anchor 之差在 [3300000, 3900000]", async () => {
    await createRoom();
    const anchor = Date.now();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: 1 });
    expect(res.status).toBe(201);
    expect(typeof res.body.share_token).toBe("string");
    expect(res.body.share_token).toHaveLength(32);
    const diff = res.body.expires_at_ms - anchor;
    expect(diff).toBeGreaterThanOrEqual(3300000);
    expect(diff).toBeLessThanOrEqual(3900000);
  });
  it("ttl_hours 为 720 返回 201，share_token 长度 32，expires_at_ms 与 anchor 之差在 [2591400000, 2592600000]", async () => {
    await createRoom();
    const anchor = Date.now();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice", ttl_hours: 720 });
    expect(res.status).toBe(201);
    expect(typeof res.body.share_token).toBe("string");
    expect(res.body.share_token).toHaveLength(32);
    const diff = res.body.expires_at_ms - anchor;
    expect(diff).toBeGreaterThanOrEqual(2591400000);
    expect(diff).toBeLessThanOrEqual(2592600000);
  });
  it("缺省 ttl_hours 返回 201，share_token 长度 32，expires_at_ms 与 anchor 之差在 [604200000, 605400000]", async () => {
    await createRoom();
    const anchor = Date.now();
    const res = await api("POST", "/api/rooms/room1/share-links", { requester: "alice" });
    expect(res.status).toBe(201);
    expect(typeof res.body.share_token).toBe("string");
    expect(res.body.share_token).toHaveLength(32);
    const diff = res.body.expires_at_ms - anchor;
    expect(diff).toBeGreaterThanOrEqual(604200000);
    expect(diff).toBeLessThanOrEqual(605400000);
  });
});