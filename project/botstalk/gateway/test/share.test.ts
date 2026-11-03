import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  generateShareToken,
  normalizeShareToken,
  hashShareToken,
  clampShareTtlHours,
  isShareExpired,
  isShareRevoked,
  isShareUsable,
  type ShareLinkRecord,
} from "../src/share.js";
import {
  openDb,
  issueShareLink,
  getShareLinkByHash,
  getShareLinkById,
  listShareLinks,
  revokeShareLink,
} from "../src/db.js";
import { startServer } from "../src/server.js";

describe("share pure 函数", () => {
  it("generateShareToken 生成 32 位字母数字串", () => {
    for (let i = 0; i < 20; i++) {
      const token = generateShareToken();
      expect(token).toMatch(/^[A-Za-z0-9]{32}$/);
    }
  });

  it("normalizeShareToken trim 合法串并拒绝非法输入", () => {
    const raw = "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0fH";
    expect(raw).toMatch(/^[A-Za-z0-9]{32}$/);
    expect(normalizeShareToken(`  ${raw} `)).toBe(raw);
    expect(normalizeShareToken("abc")).toBeNull();
    expect(normalizeShareToken("Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0-H")).toBeNull();
    expect(normalizeShareToken("Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0!H")).toBeNull();
    expect(normalizeShareToken(12345 as unknown as string)).toBeNull();
  });

  it("hashShareToken 稳定且为 64 位十六进制", () => {
    const token = generateShareToken();
    const a = hashShareToken(token);
    const b = hashShareToken(token);
    expect(a).toBe(b);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
  });

  it("clampShareTtlHours 边界与非法值", () => {
    expect(clampShareTtlHours(0)).toBe(168);
    expect(clampShareTtlHours(99999)).toBe(720);
    expect(clampShareTtlHours("x" as unknown as number)).toBe(168);
    expect(clampShareTtlHours(24)).toBe(24);
  });

  it("isShareExpired 判定边界", () => {
    const expires = 1_000_000;
    const record = { id: "s", tokenHash: "h", room: "room1", createdAtMs: 0, expiresAtMs: expires, revokedAtMs: null } as ShareLinkRecord;
    expect(isShareExpired(record, expires)).toBe(false);
    expect(isShareExpired(record, expires + 1)).toBe(true);
  });

  it("isShareRevoked 判定空与非空", () => {
    const base = { id: "s", tokenHash: "h", room: "room1", createdAtMs: 0, expiresAtMs: 999999 } as ShareLinkRecord;
    expect(isShareRevoked({ ...base, revokedAtMs: null })).toBe(false);
    expect(isShareRevoked({ ...base, revokedAtMs: 1234 })).toBe(true);
  });

  it("isShareUsable 综合判定", () => {
    const now = 5_000;
    const mk = (expiresAtMs: number, revokedAtMs: number | null) => ({ id: "s", tokenHash: "h", room: "room1", createdAtMs: 0, expiresAtMs, revokedAtMs }) as ShareLinkRecord;
    expect(isShareUsable(mk(now + 1000, null), now)).toBe(true);
    expect(isShareUsable(mk(now - 1, null), now)).toBe(false);
    expect(isShareUsable(mk(now + 1000, now), now)).toBe(false);
  });
});

describe("share db 层", () => {
  let dataDir: string;
  let db: Awaited<ReturnType<typeof openDb>>;

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "share-test-"));
    db = await openDb(dataDir);
  });

  afterEach(() => {
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("issue 后可按 hash 与 id 取回", async () => {
    const token = generateShareToken();
    const tokenHash = hashShareToken(token);
    const now = Date.now();
    const issuedId = "link-1";
    await issueShareLink(db, {
      id: issuedId,
      tokenHash,
      room: "room1",
      createdAtMs: now,
      expiresAtMs: now + 3600_000,
    });
    const byHash = await getShareLinkByHash(db, tokenHash);
    expect(byHash).not.toBeNull();
    expect(byHash!.token_hash).toBe(tokenHash);
    expect(byHash!.room).toBe("room1");
    expect(byHash!.revoked_at_ms).toBeNull();
    expect(byHash!.created_at_ms).toBe(now);
    expect(byHash!.expires_at_ms).toBe(now + 3600_000);

    const byId = await getShareLinkById(db, issuedId);
    expect(byId).not.toBeNull();
    expect(byId!.id).toBe(issuedId);
    expect(byId!.token_hash).toBe(tokenHash);
  });

  it("listShareLinks 按创建时间升序且只含本房", async () => {
    const now = Date.now();
    const hashA1 = hashShareToken(generateShareToken());
    const hashA2 = hashShareToken(generateShareToken());
    const hashB = hashShareToken(generateShareToken());
    const a2Id = "link-a2";
    await issueShareLink(db, {
      id: a2Id,
      tokenHash: hashA2,
      room: "room1",
      createdAtMs: now + 2000,
      expiresAtMs: now + 3600_000,
    });
    const a1Id = "link-a1";
    await issueShareLink(db, {
      id: a1Id,
      tokenHash: hashA1,
      room: "room1",
      createdAtMs: now + 1000,
      expiresAtMs: now + 3600_000,
    });
    await issueShareLink(db, {
      id: "link-b",
      tokenHash: hashB,
      room: "room2",
      createdAtMs: now + 500,
      expiresAtMs: now + 3600_000,
    });
    const links = await listShareLinks(db, "room1");
    expect(links.length).toBe(2);
    expect(links.map((l) => l.id)).toEqual([a1Id, a2Id]);
    expect(links[0].created_at_ms).toBeLessThanOrEqual(links[1].created_at_ms);
    expect(links.every((l) => l.room === "room1")).toBe(true);
    expect(links.some((l) => l.token_hash === hashB)).toBe(false);
  });

  it("revokeShareLink 未知返回 not_found、已知返回 ok 且可重复吊销", async () => {
    const tokenHash = hashShareToken(generateShareToken());
    const now = Date.now();
    const issuedId = "link-1";
    await issueShareLink(db, {
      id: issuedId,
      tokenHash,
      room: "room1",
      createdAtMs: now,
      expiresAtMs: now + 3600_000,
    });
    const missing = await revokeShareLink(db, "no-such-id", now);
    expect(missing).toBe("not_found");

    const first = await revokeShareLink(db, issuedId, now);
    expect(first).toBe("ok");
    const afterFirst = await getShareLinkById(db, issuedId);
    expect(afterFirst!.revoked_at_ms).not.toBeNull();
    expect(typeof afterFirst!.revoked_at_ms).toBe("number");

    const revokedAt = afterFirst!.revoked_at_ms;
    const second = await revokeShareLink(db, issuedId, now);
    expect(second).toBe("ok");
    const afterSecond = await getShareLinkById(db, issuedId);
    expect(afterSecond!.revoked_at_ms).not.toBeNull();
    expect(afterSecond!.revoked_at_ms).toBe(revokedAt);
  });
});

describe("share REST 端点正常流", () => {
  let dataDir: string;
  let db: Awaited<ReturnType<typeof openDb>>;
  let server: Awaited<ReturnType<typeof startServer>>;
  let baseUrl: string;

  const api = async (path: string, method: string, body?: unknown) => {
    const res = await fetch(baseUrl + path, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 204) {
      return { status: res.status, body: null };
    }
    return { status: res.status, body: await res.json() };
  };

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "share-test-"));
    db = await openDb(join(dataDir, "dbdir"));
    server = await startServer(
      {
        port: 0,
        dataDir: join(dataDir, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db,
    );
    const address = server.httpServer.address();
    const port = typeof address === "object" && address !== null ? address.port : 0;
    baseUrl = `http://127.0.0.1:${port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("建房 → 非房主禁止 → 房主签发 → 列表 → 查看 → 吊销 → 查看 410", async () => {
    const created = await api("/api/rooms", "POST", { id: "room1", name: "Room 1", owner: "alice" });
    expect(created.status).toBe(201);

    const forbidden = await api("/api/rooms/room1/share-links", "POST", { requester: "mallory", ttl_hours: 24 });
    expect(forbidden.status).toBe(403);
    expect(forbidden.body.error).toBe("ROOM_MANAGE_FORBIDDEN");

    const issued = await api("/api/rooms/room1/share-links", "POST", { requester: "alice", ttl_hours: 24 });
    expect(issued.status).toBe(201);
    const shareToken = issued.body.share_token as string;
    const shareId = issued.body.id as string;
    expect(shareToken).toMatch(/^[A-Za-z0-9]{32}$/);
    expect(issued.body.room).toBe("room1");
    expect(issued.body.share_url).toBe("/share/" + shareToken);
    expect(typeof issued.body.expires_at_ms).toBe("number");
    expect(issued.body.expires_at_ms).toBeGreaterThan(Date.now());

    const listRes = await api("/api/rooms/room1/share-links?requester=alice", "GET");
    expect(listRes.status).toBe(200);
    expect(Array.isArray(listRes.body.links)).toBe(true);
    expect(listRes.body.links.length).toBe(1);
    const listed = listRes.body.links[0];
    expect(listed.id).toBe(shareId);
    expect(listed.room).toBe("room1");
    expect(Object.prototype.hasOwnProperty.call(listed, "token_hash")).toBe(false);
    for (const link of listRes.body.links) {
      expect(Object.prototype.hasOwnProperty.call(link, "token_hash")).toBe(false);
    }

    const viewed = await api(`/api/share/${shareToken}`, "GET");
    expect(viewed.status).toBe(200);
    expect(viewed.body.room.id).toBe("room1");
    expect(Array.isArray(viewed.body.messages)).toBe(true);
    expect(viewed.body.share.id).toBe(shareId);

    const revoked = await api(`/api/rooms/room1/share-links/${shareId}`, "DELETE", { requester: "alice" });
    expect(revoked.status).toBe(204);
    expect(revoked.body).toBeNull();

    const afterRevoke = await api(`/api/share/${shareToken}`, "GET");
    expect(afterRevoke.status).toBe(410);
    expect(afterRevoke.body.error).toBe("SHARE_LINK_REVOKED");
  });
});

describe("share REST 失败注入", () => {
  let dataDir: string;
  let db: Awaited<ReturnType<typeof openDb>>;
  let server: Awaited<ReturnType<typeof startServer>>;
  let baseUrl: string;

  const api = async (path: string, method: string, body?: unknown) => {
    const res = await fetch(baseUrl + path, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 204) {
      return { status: res.status, body: null };
    }
    return { status: res.status, body: await res.json() };
  };

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "share-test-"));
    db = await openDb(join(dataDir, "dbdir"));
    server = await startServer(
      {
        port: 0,
        dataDir: join(dataDir, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db,
    );
    const address = server.httpServer.address();
    const port = typeof address === "object" && address !== null ? address.port : 0;
    baseUrl = `http://127.0.0.1:${port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("未知房发分享 404", async () => {
    const res = await api("/api/rooms/ghost/share-links", "POST", { requester: "alice", ttl_hours: 24 });
    expect(res.status).toBe(404);
  });

  it("格式非法 token 查看 400 INVALID_SHARE_TOKEN", async () => {
    const res = await api("/api/share/short!", "GET");
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("INVALID_SHARE_TOKEN");
  });

  it("未签发过的合法 token 查看 404 SHARE_LINK_NOT_FOUND", async () => {
    const res = await api(`/api/share/${"A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"}`, "GET");
    expect(res.status).toBe(404);
    expect(res.body.error).toBe("SHARE_LINK_NOT_FOUND");
  });

  it("已过期链接查看 410 SHARE_LINK_EXPIRED", async () => {
    const token = generateShareToken();
    const tokenHash = hashShareToken(token);
    const now = Date.now();
    await issueShareLink(db, {
      id: "link-expired",
      tokenHash,
      room: "room1",
      createdAtMs: now - 7200_000,
      expiresAtMs: now - 3600_000,
    });
    const res = await api(`/api/share/${token}`, "GET");
    expect(res.status).toBe(410);
    expect(res.body.error).toBe("SHARE_LINK_EXPIRED");
  });

  it("跨房吊销 404 SHARE_LINK_NOT_FOUND", async () => {
    const createdA = await api("/api/rooms", "POST", { id: "room1", name: "Room 1", owner: "alice" });
    expect(createdA.status).toBe(201);
    const createdB = await api("/api/rooms", "POST", { id: "room2", name: "Room 2", owner: "bob" });
    expect(createdB.status).toBe(201);

    const issued = await api("/api/rooms/room1/share-links", "POST", { requester: "alice", ttl_hours: 24 });
    expect(issued.status).toBe(201);
    const shareId = issued.body.id as string;

    const res = await api(`/api/rooms/room2/share-links/${shareId}`, "DELETE", { requester: "bob" });
    expect(res.status).toBe(404);
    expect(res.body.error).toBe("SHARE_LINK_NOT_FOUND");
  });

  it("非房主查列表 403", async () => {
    const created = await api("/api/rooms", "POST", { id: "room1", name: "Room 1", owner: "alice" });
    expect(created.status).toBe(201);
    const res = await api("/api/rooms/room1/share-links?requester=mallory", "GET");
    expect(res.status).toBe(403);
    expect(res.body.error).toBe("ROOM_MANAGE_FORBIDDEN");
  });
});

describe("share 只读强制", () => {
  let dataDir: string;
  let db: Awaited<ReturnType<typeof openDb>>;
  let server: Awaited<ReturnType<typeof startServer>>;
  let baseUrl: string;

  const api = async (path: string, method: string, body?: unknown) => {
    const res = await fetch(baseUrl + path, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 204) {
      return { status: res.status, body: null };
    }
    return { status: res.status, body: await res.json() };
  };

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "share-test-"));
    db = await openDb(join(dataDir, "dbdir"));
    server = await startServer(
      {
        port: 0,
        dataDir: join(dataDir, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db,
    );
    const address = server.httpServer.address();
    const port = typeof address === "object" && address !== null ? address.port : 0;
    baseUrl = `http://127.0.0.1:${port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("查看分享前后成员数不变", async () => {
    const created = await api("/api/rooms", "POST", { id: "room1", name: "Room 1", owner: "alice" });
    expect(created.status).toBe(201);
    const issued = await api("/api/rooms/room1/share-links", "POST", { requester: "alice", ttl_hours: 24 });
    expect(issued.status).toBe(201);
    const shareToken = issued.body.share_token as string;

    const before = await api("/api/rooms/room1/members", "GET");
    expect(before.status).toBe(200);
    expect(Array.isArray(before.body.members)).toBe(true);
    const beforeCount = before.body.members.length;

    const viewed = await api(`/api/share/${shareToken}`, "GET");
    expect(viewed.status).toBe(200);
    expect(viewed.body.room.id).toBe("room1");

    const after = await api("/api/rooms/room1/members", "GET");
    expect(after.status).toBe(200);
    expect(after.body.members.length).toBe(beforeCount);
  });

  it("share_token 当 requester 发分享 403", async () => {
    const created = await api("/api/rooms", "POST", { id: "room1", name: "Room 1", owner: "alice" });
    expect(created.status).toBe(201);
    const issued = await api("/api/rooms/room1/share-links", "POST", { requester: "alice", ttl_hours: 24 });
    expect(issued.status).toBe(201);
    const shareToken = issued.body.share_token as string;

    const res = await api("/api/rooms/room1/share-links", "POST", { requester: shareToken, ttl_hours: 24 });
    expect(res.status).toBe(403);
    expect(res.body.error).toBe("ROOM_MANAGE_FORBIDDEN");
  });

  it("share_token 当配对码兑码 400 INVALID_PAIRING_CODE", async () => {
    const created = await api("/api/rooms", "POST", { id: "room1", name: "Room 1", owner: "alice" });
    expect(created.status).toBe(201);
    const issued = await api("/api/rooms/room1/share-links", "POST", { requester: "alice", ttl_hours: 24 });
    expect(issued.status).toBe(201);
    const shareToken = issued.body.share_token as string;

    const res = await api("/api/pairing-codes/redeem", "POST", { code: shareToken, adapter_id: "x" });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("INVALID_PAIRING_CODE");
  });
});
