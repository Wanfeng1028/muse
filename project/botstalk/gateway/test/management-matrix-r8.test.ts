// 第 8 轮：拉人守卫 + 设权限角色端点（仅房主）
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, setPermRole, type Db } from "../src/db.js";
import { startServer, type RunningServer } from "../src/server.js";

describe("management matrix r8", () => {
  let root: string;
  let db: Db;
  let server: RunningServer;
  let base: string;

  beforeEach(async () => {
    root = mkdtempSync(join(tmpdir(), "botstalk-mgmt-r8-"));
    db = openDb(join(root, "dbdir"));
    server = startServer(
      { port: 0, dataDir: join(root, "dbdir"), roomMaxMembersWorkroom: 50, roomMaxMembersPlayroom: 200, gameBroadcastThrottleMs: 500 },
      db,
    );
    const addr = server.httpServer.address();
    if (addr === null || typeof addr === "string") throw new Error("no port");
    base = `http://127.0.0.1:${addr.port}`;
  });

  afterEach(async () => {
    await server.close();
    try { rmSync(root, { recursive: true, force: true }); } catch { /* ignore */ }
  });

  async function api(method: string, path: string, body?: unknown): Promise<{ status: number; json: any }> {
    const res = await fetch(base + path, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const json = await res.json().catch(() => null);
    return { status: res.status, json };
  }

  it("拉人：workroom 无身份与非房主 403、房主 201；playroom guest 403、普通成员 201", async () => {
    await api("POST", "/api/rooms", { id: "w1", name: "W", owner: "alice" });
    const noId = await api("POST", "/api/rooms/w1/members", { adapter_id: "a1" });
    expect(noId.status).toBe(403);
    const nonOwner = await api("POST", "/api/rooms/w1/members", { adapter_id: "a1", requester: "mallory" });
    expect(nonOwner.status).toBe(403);
    const ownerOk = await api("POST", "/api/rooms/w1/members", { adapter_id: "a1", requester: "alice" });
    expect(ownerOk.status).toBe(201);

    await api("POST", "/api/rooms", { id: "p1", name: "P", type: "playroom", owner: "bob" });
    await api("POST", "/api/rooms/p1/members", { adapter_id: "g1", requester: "bob" });
    await api("POST", "/api/rooms/p1/members", { adapter_id: "m1", requester: "bob" });
    setPermRole(db, "p1", "g1", "guest");
    const guestInvite = await api("POST", "/api/rooms/p1/members", { adapter_id: "x1", requester: "g1" });
    expect(guestInvite.status).toBe(403);
    const memberInvite = await api("POST", "/api/rooms/p1/members", { adapter_id: "x1", requester: "m1" });
    expect(memberInvite.status).toBe(201);
  });

  it("设权限：非房主 403、房主改 guest 200 且降级后改名 403、非法角色 400、非成员 404、房主自降 403、房主恢复 member 200", async () => {
    await api("POST", "/api/rooms", { id: "w1", name: "W", owner: "alice" });
    await api("POST", "/api/rooms/w1/members", { adapter_id: "m1", requester: "alice" });

    const nonOwner = await api("PATCH", "/api/rooms/w1/members/m1/perm", { perm_role: "guest", requester: "mallory" });
    expect(nonOwner.status).toBe(403);

    const badRole = await api("PATCH", "/api/rooms/w1/members/m1/perm", { perm_role: "superuser", requester: "alice" });
    expect(badRole.status).toBe(400);
    expect(badRole.json.error).toBe("INVALID_PERM_ROLE");

    const missing = await api("PATCH", "/api/rooms/w1/members/nope/perm", { perm_role: "guest", requester: "alice" });
    expect(missing.status).toBe(404);

    const selfDemote = await api("PATCH", "/api/rooms/w1/members/alice/perm", { perm_role: "guest", requester: "alice" });
    expect(selfDemote.status).toBe(403);

    const demote = await api("PATCH", "/api/rooms/w1/members/m1/perm", { perm_role: "guest", requester: "alice" });
    expect(demote.status).toBe(200);
    expect(demote.json.member.perm_role).toBe("guest");

    // 降级后：该成员在 playroom 改名应被否决——用 playroom 复核降级语义
    await api("POST", "/api/rooms", { id: "p1", name: "P", type: "playroom", owner: "bob" });
    await api("POST", "/api/rooms/p1/members", { adapter_id: "m1", requester: "bob" });
    await api("PATCH", "/api/rooms/p1/members/m1/perm", { perm_role: "guest", requester: "bob" });
    const guestRename = await api("PATCH", "/api/rooms/p1", { name: "P2", requester: "m1" });
    expect(guestRename.status).toBe(403);

    const restore = await api("PATCH", "/api/rooms/w1/members/m1/perm", { perm_role: "member", requester: "alice" });
    expect(restore.status).toBe(200);
    expect(restore.json.member.perm_role).toBe("member");
  });
});
