// 第 7 轮：管理操作矩阵 REST 行为（踢人房主专属、改人设/改名/改话题 guest 否决）
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, setPermRole, type Db } from "../src/db.js";
import { startServer, type RunningServer } from "../src/server.js";

describe("management matrix r7", () => {
  let root: string;
  let db: Db;
  let server: RunningServer;
  let base: string;

  beforeEach(async () => {
    root = mkdtempSync(join(tmpdir(), "botstalk-mgmt-r7-"));
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

  it("workroom：无身份改名 403、房主改名 200、非房主改人设 403、房主改人设 200、非房主踢人 403、房主踢人 200", async () => {
    await api("POST", "/api/rooms", { id: "w1", name: "W", owner: "alice" });
    await api("POST", "/api/rooms/w1/members", { adapter_id: "a1", requester: "alice" });
    await api("POST", "/api/rooms/w1/members", { adapter_id: "a2", requester: "alice" });

    const noId = await api("PATCH", "/api/rooms/w1", { name: "W2" });
    expect(noId.status).toBe(403);
    expect(noId.json.error).toBe("ROOM_MANAGE_FORBIDDEN");

    const renamed = await api("PATCH", "/api/rooms/w1", { name: "W2", requester: "alice" });
    expect(renamed.status).toBe(200);
    expect(renamed.json.room.name).toBe("W2");

    const personaDenied = await api("PATCH", "/api/rooms/w1/members/a1", { persona_role: "moderator", requester: "mallory" });
    expect(personaDenied.status).toBe(403);
    expect(personaDenied.json.error).toBe("ROOM_MANAGE_FORBIDDEN");

    const personaOk = await api("PATCH", "/api/rooms/w1/members/a1", { persona_role: "moderator", requester: "alice" });
    expect(personaOk.status).toBe(200);
    expect(personaOk.json.member.persona_role).toBe("moderator");

    const kickDenied = await api("DELETE", "/api/rooms/w1/members/a2?requester=mallory");
    expect(kickDenied.status).toBe(403);
    expect(kickDenied.json.error).toBe("ROOM_MANAGE_FORBIDDEN");

    const kickOk = await api("DELETE", "/api/rooms/w1/members/a2?requester=alice");
    expect(kickOk.status).toBe(200);
    expect(kickOk.json.ok).toBe(true);

    const kickMissing = await api("DELETE", "/api/rooms/w1/members/a2?requester=alice");
    expect(kickMissing.status).toBe(404);
  });

  it("playroom：guest 改名与改类型 403、普通成员改名 200、普通成员踢人仍 403（踢人只限房主）、房主踢人 200", async () => {
    await api("POST", "/api/rooms", { id: "p1", name: "P", type: "playroom", owner: "bob" });
    await api("POST", "/api/rooms/p1/members", { adapter_id: "g1", requester: "bob" });
    await api("POST", "/api/rooms/p1/members", { adapter_id: "m1", requester: "bob" });
    setPermRole(db, "p1", "g1", "guest");

    const guestRename = await api("PATCH", "/api/rooms/p1", { name: "P2", requester: "g1" });
    expect(guestRename.status).toBe(403);
    expect(guestRename.json.error).toBe("ROOM_MANAGE_FORBIDDEN");

    const memberRename = await api("PATCH", "/api/rooms/p1", { name: "P2", requester: "m1" });
    expect(memberRename.status).toBe(200);
    expect(memberRename.json.room.name).toBe("P2");

    const guestType = await api("PATCH", "/api/rooms/p1", { type: "workroom", requester: "g1" });
    expect(guestType.status).toBe(403);
    expect(guestType.json.error).toBe("ROOM_TYPE_FORBIDDEN");

    const memberKick = await api("DELETE", "/api/rooms/p1/members/g1?requester=m1");
    expect(memberKick.status).toBe(403);
    expect(memberKick.json.error).toBe("ROOM_MANAGE_FORBIDDEN");

    const ownerKick = await api("DELETE", "/api/rooms/p1/members/g1?requester=bob");
    expect(ownerKick.status).toBe(200);
    expect(ownerKick.json.ok).toBe(true);
  });
});
