// BotsTalk gateway rooms HTTP API tests
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, type Db } from "../src/db.js";
import { startServer, type RunningServer } from "../src/server.js";

describe("rooms http api", () => {
  let root: string;
  let db: Db;
  let server: RunningServer;
  let base: string;

  beforeEach(async () => {
    root = mkdtempSync(join(tmpdir(), "botstalk-rooms-server-"));
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

  it("创建 workroom 默认类型、playroom、非法类型 400、重复 id 409", async () => {
    const a = await api("POST", "/api/rooms", { id: "r1", name: "Room One", owner: "alice" });
    expect(a.status).toBe(201);
    expect(a.json.room.id).toBe("r1");
    expect(a.json.room.name).toBe("Room One");
    expect(a.json.room.type).toBe("workroom");

    const b = await api("POST", "/api/rooms", { id: "r2", name: "Play", type: "playroom" });
    expect(b.status).toBe(201);
    expect(b.json.room.type).toBe("playroom");

    const bad = await api("POST", "/api/rooms", { id: "r3", type: "bogus" });
    expect(bad.status).toBe(400);
    expect(bad.json.error).toBe("INVALID_ROOM_TYPE");

    const dup = await api("POST", "/api/rooms", { id: "r1", name: "Dup" });
    expect(dup.status).toBe(409);
  });

  it("GET 房间列表与单个房间，单个不存在返回 404", async () => {
    await api("POST", "/api/rooms", { id: "r1", name: "One" });
    await api("POST", "/api/rooms", { id: "r2", name: "Two" });

    const list = await api("GET", "/api/rooms");
    expect(list.status).toBe(200);
    expect(Array.isArray(list.json.rooms)).toBe(true);
    const ids = list.json.rooms.map((r: any) => r.id).sort();
    expect(ids).toEqual(["r1", "r2"]);

    const one = await api("GET", "/api/rooms/r1");
    expect(one.status).toBe(200);
    expect(one.json.room.id).toBe("r1");
    expect(one.json.room.name).toBe("One");

    const missing = await api("GET", "/api/rooms/nope");
    expect(missing.status).toBe(404);
  });

  it("PATCH 改名/话题、workroom 权限、owner 改类型生效、playroom 任意改、非法类型 400", async () => {
    await api("POST", "/api/rooms", { id: "w1", name: "W", owner: "alice" });
    await api("POST", "/api/rooms", { id: "p1", name: "P", type: "playroom", owner: "bob" });

    const renamed = await api("PATCH", "/api/rooms/w1", { name: "W2", topic: "hello", requester: "alice" });
    expect(renamed.status).toBe(200);
    expect(renamed.json.room.name).toBe("W2");
    expect(renamed.json.room.topic).toBe("hello");

    const forbidden = await api("PATCH", "/api/rooms/w1", { type: "playroom", requester: "mallory" });
    expect(forbidden.status).toBe(403);
    expect(forbidden.json.error).toBe("ROOM_TYPE_FORBIDDEN");

    const ownerChange = await api("PATCH", "/api/rooms/w1", { type: "playroom", requester: "alice" });
    expect(ownerChange.status).toBe(200);
    expect(ownerChange.json.room.type).toBe("playroom");

    const playroomChange = await api("PATCH", "/api/rooms/p1", { type: "workroom", requester: "anyone" });
    expect(playroomChange.status).toBe(200);
    expect(playroomChange.json.room.type).toBe("workroom");

    const badType = await api("PATCH", "/api/rooms/p1", { type: "nope", requester: "anyone" });
    expect(badType.status).toBe(400);

    const missing = await api("PATCH", "/api/rooms/nope", { name: "X" });
    expect(missing.status).toBe(404);
  });

  it("成员增删改查与错误分支", async () => {
    await api("POST", "/api/rooms", { id: "r1", name: "R", owner: "alice" });

    const add = await api("POST", "/api/rooms/r1/members", { adapter_id: "a1", persona_role: "host" });
    expect(add.status).toBe(201);
    expect(add.json.member.adapter_id).toBe("a1");
    expect(add.json.member.persona_role).toBe("host");

    const addNoRole = await api("POST", "/api/rooms/r1/members", { adapter_id: "a2" });
    expect(addNoRole.status).toBe(201);
    expect(addNoRole.json.member.adapter_id).toBe("a2");

    const missingAdapter = await api("POST", "/api/rooms/r1/members", { persona_role: "x" });
    expect(missingAdapter.status).toBe(400);

    const list = await api("GET", "/api/rooms/r1/members");
    expect(list.status).toBe(200);
    const adapterIds = list.json.members.map((m: any) => m.adapter_id).sort();
    expect(adapterIds).toEqual(["a1", "a2"]);

    const patched = await api("PATCH", "/api/rooms/r1/members/a1", { persona_role: "moderator", requester: "alice" });
    expect(patched.status).toBe(200);
    expect(patched.json.member.persona_role).toBe("moderator");

    const del = await api("DELETE", "/api/rooms/r1/members/a2?requester=alice");
    expect(del.status).toBe(200);
    expect(del.json.ok).toBe(true);

    const delMissing = await api("DELETE", "/api/rooms/r1/members/a2?requester=alice");
    expect(delMissing.status).toBe(404);

    const listMissing = await api("GET", "/api/rooms/nope/members");
    expect(listMissing.status).toBe(404);

    const addMissingRoom = await api("POST", "/api/rooms/nope/members", { adapter_id: "a9" });
    expect(addMissingRoom.status).toBe(404);
  });

  it("游戏：workroom/playroom 清单校验、CRUD 与错误分支", async () => {
    await api("POST", "/api/rooms", { id: "w1", name: "W", owner: "alice" });
    await api("POST", "/api/rooms", { id: "p1", name: "P", type: "playroom", owner: "bob" });

    const g1 = await api("POST", "/api/rooms/w1/games", { game: "vote_plan" });
    expect(g1.status).toBe(201);
    expect(g1.json.session.game).toBe("vote_plan");
    const sid = g1.json.session.id;
    expect(typeof sid).toBe("string");

    const gForbidden = await api("POST", "/api/rooms/w1/games", { game: "who_is_undercover" });
    expect(gForbidden.status).toBe(403);
    expect(gForbidden.json.error).toBe("ROOM_TYPE_FORBIDDEN");

    const gPlay = await api("POST", "/api/rooms/p1/games", { game: "who_is_undercover" });
    expect(gPlay.status).toBe(201);
    expect(gPlay.json.session.game).toBe("who_is_undercover");
    const pid = gPlay.json.session.id;

    const gMissingGame = await api("POST", "/api/rooms/w1/games", {});
    expect(gMissingGame.status).toBe(400);

    const gMissingRoom = await api("POST", "/api/rooms/nope/games", { game: "vote_plan" });
    expect(gMissingRoom.status).toBe(404);

    const list = await api("GET", "/api/rooms/w1/games");
    expect(list.status).toBe(200);
    expect(Array.isArray(list.json.sessions)).toBe(true);
    const listIds = list.json.sessions.map((s: any) => s.id);
    expect(listIds).toContain(sid);

    const patched = await api("PATCH", `/api/rooms/w1/games/${sid}`, { state: { step: 2 } });
    expect(patched.status).toBe(200);
    expect(patched.json.session.id).toBe(sid);

    const patchMissingState = await api("PATCH", `/api/rooms/w1/games/${sid}`, {});
    expect(patchMissingState.status).toBe(400);

    const patchMissing = await api("PATCH", "/api/rooms/w1/games/nope", { state: {} });
    expect(patchMissing.status).toBe(404);

    const del = await api("DELETE", `/api/rooms/p1/games/${pid}`);
    expect(del.status).toBe(200);
    expect(del.json.ok).toBe(true);

    const delMissing = await api("DELETE", `/api/rooms/p1/games/${pid}`);
    expect(delMissing.status).toBe(404);
  });
});