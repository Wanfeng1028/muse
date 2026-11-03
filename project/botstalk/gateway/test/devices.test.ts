import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { generatePairingCode, normalizePairingCode, hashPairingCode } from "../src/pairing.js";
import { generateDeviceKey, hashDeviceKey, normalizeDeviceId, isDeviceRevoked } from "../src/devices.js";
import { openDb, issuePairingCode, upsertDevice, getDevice, listDevicesByRoom, revokeDevice } from "../src/db.js";
import { startServer } from "../src/server.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("devices", () => {
  describe("pure functions", () => {
    it("generateDeviceKey returns 64 lowercase hex chars, and two calls differ", () => {
      const k1 = generateDeviceKey();
      const k2 = generateDeviceKey();
      expect(k1).toMatch(/^[0-9a-f]{64}$/);
      expect(k2).toMatch(/^[0-9a-f]{64}$/);
      expect(k1).not.toBe(k2);
    });

    it("hashDeviceKey is deterministic and matches /^[0-9a-f]{64}$/", () => {
      const h1 = hashDeviceKey("some-key");
      const h2 = hashDeviceKey("some-key");
      expect(h1).toMatch(/^[0-9a-f]{64}$/);
      expect(h1).toBe(h2);
    });

    it("normalizeDeviceId trims valid ids and rejects empty, non-string, or too long", () => {
      expect(normalizeDeviceId("  dev-1 ")).toBe("dev-1");
      expect(normalizeDeviceId("")).toBeNull();
      expect(normalizeDeviceId(123 as any)).toBeNull();
      expect(normalizeDeviceId("x".repeat(129))).toBeNull();
    });

    it("isDeviceRevoked checks revoked_at_ms", () => {
      expect(isDeviceRevoked({ revoked_at_ms: null } as any)).toBe(false);
      expect(isDeviceRevoked({ revoked_at_ms: 1000 } as any)).toBe(true);
    });
  });

  describe("db", () => {
    let dataDir: string;
    let db: Awaited<ReturnType<typeof openDb>>;

    beforeEach(async () => {
      dataDir = mkdtempSync(join(tmpdir(), "devices-test-"));
      db = await openDb(dataDir);
    });

    afterEach(() => {
      rmSync(dataDir, { recursive: true, force: true });
    });

    it("upsert create then get", () => {
      expect(upsertDevice(db, { deviceId: "d1", room: "room1", deviceKeyHash: "h1", adapterId: "a1", nowMs: 1000 })).toBe("created");
      const d = getDevice(db, "d1", "room1");
      expect(d?.device_key_hash).toBe("h1");
      expect(d?.created_at_ms).toBe(1000);
      expect(d?.last_seen_ms).toBe(1000);
      expect(d?.revoked_at_ms).toBeNull();
    });

    it("upsert update", () => {
      upsertDevice(db, { deviceId: "d1", room: "room1", deviceKeyHash: "h1", adapterId: "a1", nowMs: 1000 });
      expect(upsertDevice(db, { deviceId: "d1", room: "room1", deviceKeyHash: "h2", adapterId: "a2", nowMs: 2000 })).toBe("updated");
      const d = getDevice(db, "d1", "room1");
      expect(d?.device_key_hash).toBe("h2");
      expect(d?.adapter_id).toBe("a2");
      expect(d?.last_seen_ms).toBe(2000);
      expect(d?.created_at_ms).toBe(1000);
    });

    it("upsert revoked", () => {
      upsertDevice(db, { deviceId: "d1", room: "room1", deviceKeyHash: "h1", adapterId: "a1", nowMs: 1000 });
      expect(revokeDevice(db, "d1", "room1", 3000)).toBe("ok");
      expect(upsertDevice(db, { deviceId: "d1", room: "room1", deviceKeyHash: "h3", adapterId: "a3", nowMs: 4000 })).toBe("revoked");
      const d = getDevice(db, "d1", "room1");
      expect(d?.device_key_hash).toBe("h1");
    });

    it("revoke unknown and already revoked", () => {
      expect(revokeDevice(db, "unknown", "room1", 1000)).toBe("not_found");
      upsertDevice(db, { deviceId: "d1", room: "room1", deviceKeyHash: "h1", adapterId: "a1", nowMs: 1000 });
      expect(revokeDevice(db, "d1", "room1", 2000)).toBe("ok");
      expect(revokeDevice(db, "d1", "room1", 3000)).toBe("already");
    });

    it("listDevicesByRoom", () => {
      upsertDevice(db, { deviceId: "d1", room: "room1", deviceKeyHash: "h1", adapterId: "a1", nowMs: 1000 });
      upsertDevice(db, { deviceId: "d2", room: "room1", deviceKeyHash: "h2", adapterId: "a2", nowMs: 1001 });
      upsertDevice(db, { deviceId: "d1", room: "room2", deviceKeyHash: "h1", adapterId: "a1", nowMs: 1002 });
      const r1 = listDevicesByRoom(db, "room1");
      expect(r1).toHaveLength(2);
      expect(r1.map(d => d.device_id)).toEqual(["d1", "d2"]);
      const r2 = listDevicesByRoom(db, "room2");
      expect(r2).toHaveLength(1);
      expect(r2[0].device_id).toBe("d1");
    });
  });

describe("REST", () => {
  let dataDir: string;
  let db: Awaited<ReturnType<typeof openDb>>;
  let server: any;
  let baseUrl: string;
  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "devices-test-"));
    db = openDb(join(dataDir, "dbdir"));
    server = startServer({ port: 0, dataDir: join(dataDir, "dbdir"), roomMaxMembersWorkroom: 50, roomMaxMembersPlayroom: 200, gameBroadcastThrottleMs: 500 }, db);
    const address = server.httpServer.address();
    baseUrl = `http://127.0.0.1:${address.port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  const api = async (method: string, path: string, body?: any) => {
    const res = await fetch(`${baseUrl}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const json = await res.json().catch(() => ({}));
    return { status: res.status, body: json };
  };

  it("redeem issues device key once", async () => {
    await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
    const codeRes = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    const res = await api("POST", "/api/pairing-codes/redeem", { code: codeRes.body.code, adapter_id: "adapter1", device_id: "phone-1" });
    expect(res.status).toBe(200);
    expect(res.body.device_id).toBe("phone-1");
    expect(res.body.device_key).toMatch(/^[0-9a-f]{64}$/);
    expect(res.body.room).toBe("room1");
  });

  it("redeem defaults device_id to adapter_id", async () => {
    await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
    const codeRes = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    const res = await api("POST", "/api/pairing-codes/redeem", { code: codeRes.body.code, adapter_id: "adapter2" });
    expect(res.status).toBe(200);
    expect(res.body.device_id).toBe("adapter2");
    expect(res.body.device_key).toMatch(/^[0-9a-f]{64}$/);
  });

  it("redeem invalid device_id 400", async () => {
    await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
    const codeRes = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    const res = await api("POST", "/api/pairing-codes/redeem", { code: codeRes.body.code, adapter_id: "adapter3", device_id: "" });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("INVALID_DEVICE_ID");
  });

  it("list devices hides hashes", async () => {
    await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
    const codeRes1 = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    await api("POST", "/api/pairing-codes/redeem", { code: codeRes1.body.code, adapter_id: "adapter1", device_id: "phone-1" });
    const codeRes2 = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    await api("POST", "/api/pairing-codes/redeem", { code: codeRes2.body.code, adapter_id: "adapter2" });
    const res = await api("GET", "/api/rooms/room1/devices?requester=alice");
    expect(res.status).toBe(200);
    expect(res.body.devices).toHaveLength(2);
    for (const entry of res.body.devices) {
      expect(entry).toHaveProperty("device_id");
      expect(entry).toHaveProperty("room");
      expect(entry).toHaveProperty("adapter_id");
      expect(entry).toHaveProperty("created_at_ms");
      expect(entry).toHaveProperty("last_seen_ms");
      expect(entry).toHaveProperty("revoked_at_ms");
      expect("device_key_hash" in entry).toBe(false);
    }
  });

  it("list non-owner 403", async () => {
    await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
    const res = await api("GET", "/api/rooms/room1/devices?requester=mallory");
    expect(res.status).toBe(403);
    expect(res.body.error).toBe("ROOM_MANAGE_FORBIDDEN");
  });

  it("re-redeem rotates key, one row", async () => {
    await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
    const codeRes1 = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    const first = await api("POST", "/api/pairing-codes/redeem", { code: codeRes1.body.code, adapter_id: "adapter1", device_id: "phone-1" });
    expect(first.status).toBe(200);
    const codeRes2 = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    const second = await api("POST", "/api/pairing-codes/redeem", { code: codeRes2.body.code, adapter_id: "adapter1", device_id: "phone-1" });
    expect(second.status).toBe(200);
    expect(second.body.device_key).not.toBe(first.body.device_key);
    const list = await api("GET", "/api/rooms/room1/devices?requester=alice");
    expect(list.status).toBe(200);
    expect(list.body.devices).toHaveLength(1);
    expect(list.body.devices[0].device_id).toBe("phone-1");
  });

  it("revoke then redeem 403", async () => {
    await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
    const codeRes1 = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    await api("POST", "/api/pairing-codes/redeem", { code: codeRes1.body.code, adapter_id: "adapter1", device_id: "phone-1" });
    const revoke = await api("DELETE", "/api/rooms/room1/devices/phone-1", { requester: "alice" });
    expect(revoke.status).toBe(204);
    const list = await api("GET", "/api/rooms/room1/devices?requester=alice");
    const phone1 = list.body.devices.find((d: any) => d.device_id === "phone-1");
    expect(phone1.revoked_at_ms).not.toBeNull();
    const codeRes2 = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
    const redeem = await api("POST", "/api/pairing-codes/redeem", { code: codeRes2.body.code, adapter_id: "adapter1", device_id: "phone-1" });
    expect(redeem.status).toBe(403);
    expect(redeem.body.error).toBe("DEVICE_REVOKED");
  });

  it("revoke unknown 404", async () => {
    await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
    const res = await api("DELETE", "/api/rooms/room1/devices/nope", { requester: "alice" });
    expect(res.status).toBe(404);
    expect(res.body.error).toBe("DEVICE_NOT_FOUND");
  });
});
});
