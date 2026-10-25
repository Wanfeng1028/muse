import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  generatePairingCode,
  normalizePairingCode,
  formatPairingCode,
  hashPairingCode,
  clampPairingTtlMinutes,
  isPairingExpired,
  isPairingRedeemed,
  PairingCodeRecord,
} from "../src/pairing.js";
import {
  openDb,
  issuePairingCode,
  getPairingCode,
  redeemPairingCode,
} from "../src/db.js";
import { startServer } from "../src/server.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("pairing", () => {
  describe("pure functions", () => {
    it("generatePairingCode", () => {
      const regex = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}$/;
      const forbidden = /[IO01]/;
      for (let i = 0; i < 20; i++) {
        const code = generatePairingCode();
        expect(code).toMatch(regex);
        expect(forbidden.test(code)).toBe(false);
      }
    });

    it("normalizePairingCode", () => {
      expect(normalizePairingCode("abcd-efgh")).toBe("ABCDEFGH");
      expect(normalizePairingCode(" abcd efgh ")).toBe("ABCDEFGH");
      expect(normalizePairingCode("ABCD-0FGH")).toBeNull();
      expect(normalizePairingCode("ABC")).toBeNull();
      expect(normalizePairingCode(123 as any)).toBeNull();
    });

    it("formatPairingCode", () => {
      expect(formatPairingCode("ABCDEFGH")).toBe("ABCD-EFGH");
    });

    it("hashPairingCode", () => {
      const h1 = hashPairingCode("ABCDEFGH");
      const h2 = hashPairingCode("ABCDEFGH");
      expect(h1).toBe(h2);
      expect(h1).toMatch(/^[0-9a-f]{64}$/);
    });

    it("clampPairingTtlMinutes", () => {
      expect(clampPairingTtlMinutes(0)).toBe(10);
      expect(clampPairingTtlMinutes(999)).toBe(60);
      expect(clampPairingTtlMinutes("x" as any)).toBe(10);
      expect(clampPairingTtlMinutes(5)).toBe(5);
    });

    it("isPairingExpired", () => {
      const now = 1000;
      const record = { expiresAtMs: now } as PairingCodeRecord;
      expect(isPairingExpired(record, now)).toBe(false);
      expect(isPairingExpired(record, now + 1)).toBe(true);
    });

    it("isPairingRedeemed", () => {
      expect(isPairingRedeemed({ redeemedAtMs: null } as PairingCodeRecord)).toBe(false);
      expect(isPairingRedeemed({ redeemedAtMs: 1000 } as PairingCodeRecord)).toBe(true);
    });
  });

  describe("db", () => {
    let db: any;
    let dataDir: string;

    beforeEach(async () => {
      dataDir = mkdtempSync(join(tmpdir(), "pairing-test-"));
      db = await openDb(dataDir);
    });

    afterEach(() => {
      rmSync(dataDir, { recursive: true, force: true });
    });

    it("issue and get", async () => {
      const normalized = normalizePairingCode(generatePairingCode())!;
      const codeHash = hashPairingCode(normalized);
      const now = Date.now();
      await issuePairingCode(db, { codeHash, room: "room1", createdAtMs: now, expiresAtMs: now + 60000 });
      const record = await getPairingCode(db, codeHash);
      expect(record).toBeTruthy();
      expect(record.code_hash).toBe(codeHash);
      expect(record.redeemed_at_ms).toBeNull();
    });

    it("redeem ok and already", async () => {
      const normalized = normalizePairingCode(generatePairingCode())!;
      const codeHash = hashPairingCode(normalized);
      const now = Date.now();
      await issuePairingCode(db, { codeHash, room: "room1", createdAtMs: now, expiresAtMs: now + 60000 });
      const res1 = await redeemPairingCode(db, codeHash, "adapter1", now);
      expect(res1).toBe("ok");
      const res2 = await redeemPairingCode(db, codeHash, "adapter2", now);
      expect(res2).toBe("already");
    });

    it("not found", async () => {
      const res = await redeemPairingCode(db, "unknownhash", "adapter1", Date.now());
      expect(res).toBe("not_found");
    });

    it("expired", async () => {
      const normalized = normalizePairingCode(generatePairingCode())!;
      const codeHash = hashPairingCode(normalized);
      const past = Date.now() - 100000;
      const now = Date.now();
      await issuePairingCode(db, { codeHash, room: "room1", createdAtMs: past - 60000, expiresAtMs: past });
      const res = await redeemPairingCode(db, codeHash, "adapter1", now);
      expect(res).toBe("expired");
    });
  });

  describe("REST", () => {
    let server: any;
    let db: any;
    let baseUrl: string;
    let dataDir: string;

    beforeEach(async () => {
      dataDir = mkdtempSync(join(tmpdir(), "pairing-test-"));
      db = openDb(join(dataDir, "dbdir"));
      server = startServer({
        port: 0,
        dataDir: join(dataDir, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      }, db);
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
      const json = await res.json();
      return { status: res.status, body: json };
    };

    it("non-owner 403", async () => {
      await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
      const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "mallory" });
      expect(res.status).toBe(403);
      expect(res.body.error).toBe("ROOM_MANAGE_FORBIDDEN");
    });

    it("unknown room 404", async () => {
      const res = await api("POST", "/api/rooms/unknown/pairing-codes", { requester: "alice" });
      expect(res.status).toBe(404);
    });

    it("owner issues code 201", async () => {
      await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
      const res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
      expect(res.status).toBe(201);
      expect(res.body.code).toMatch(/^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}$/);
      expect(res.body.room).toBe("room1");
      expect(res.body.expires_at_ms).toBeGreaterThan(Date.now());
    });

    it("redeem wrong format 400", async () => {
      const res = await api("POST", "/api/pairing-codes/redeem", { code: "bad-code!", adapter_id: "adapter1" });
      expect(res.status).toBe(400);
      expect(res.body.error).toBe("INVALID_PAIRING_CODE");
    });

    it("redeem unknown code 404", async () => {
      const code = generatePairingCode();
      const res = await api("POST", "/api/pairing-codes/redeem", { code, adapter_id: "adapter1" });
      expect(res.status).toBe(404);
      expect(res.body.error).toBe("PAIRING_CODE_NOT_FOUND");
    });

    it("missing adapter_id 400", async () => {
      const res = await api("POST", "/api/pairing-codes/redeem", { code: "ABCD-EFGH" });
      expect(res.status).toBe(400);
    });

    it("normal redeem 200 and in members", async () => {
      await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
      const issueRes = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
      const redeemRes = await api("POST", "/api/pairing-codes/redeem", { code: issueRes.body.code, adapter_id: "adapter1" });
      expect(redeemRes.status).toBe(200);
      expect(redeemRes.body.room).toBe("room1");
      expect(redeemRes.body.adapter_id).toBe("adapter1");
      expect(typeof redeemRes.body.redeemed_at_ms).toBe("number");

      const membersRes = await api("GET", "/api/rooms/room1/members");
      expect(Array.isArray(membersRes.body.members)).toBe(true);
      const hasAdapter = membersRes.body.members.some((m: any) => m.adapter_id === "adapter1");
      expect(hasAdapter).toBe(true);
    });

    it("second redeem 409", async () => {
      await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
      const issueRes = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
      await api("POST", "/api/pairing-codes/redeem", { code: issueRes.body.code, adapter_id: "adapter1" });
      const redeemRes2 = await api("POST", "/api/pairing-codes/redeem", { code: issueRes.body.code, adapter_id: "adapter2" });
      expect(redeemRes2.status).toBe(409);
      expect(redeemRes2.body.error).toBe("PAIRING_CODE_USED");
    });
  });
});
