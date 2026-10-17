// BotsTalk gateway — rooms & game sessions DB unit tests
import { describe, it, expect, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  openDb,
  createRoom,
  getRoom,
  listRooms,
  setRoomType,
  updateRoom,
  getRoomType,
  addRoomMember,
  removeRoomMember,
  listRoomMembers,
  setPersonaRole,
  getPersonaRole,
  countRoomMembers,
  createGameSession,
  getGameSession,
  listGameSessions,
  updateGameSessionState,
  endGameSession,
  countGameSessions,
} from "../src/db.js";
import type { Db } from "../src/db.js";

let dirs: string[] = [];
let dbs: Db[] = [];

function makeDb(): Db {
  const dir = mkdtempSync(join(tmpdir(), "roomdb-"));
  dirs.push(dir);
  const db = openDb(join(dir, "test.db"));
  dbs.push(db);
  return db;
}

afterEach(() => {
  for (const db of dbs) {
    try {
      db.close();
    } catch {
      // ignore
    }
  }
  dbs = [];
  for (const dir of dirs) {
    rmSync(dir, { recursive: true, force: true });
  }
  dirs = [];
});

describe("房间基础操作", () => {
  it("createRoom 缺省 type 为 workroom 并返回完整字段", () => {
    const db = makeDb();
    const room = createRoom(db, { id: "r1" });
    expect(room.id).toBe("r1");
    expect(room.type).toBe("workroom");
    expect(typeof room.created_at_ms).toBe("number");
  });

  it("createRoom 可显式指定 playroom", () => {
    const db = makeDb();
    const room = createRoom(db, { id: "r1", type: "playroom", name: "游戏厅", topic: "t", owner: "o" });
    expect(room.type).toBe("playroom");
    expect(room.name).toBe("游戏厅");
    expect(room.topic).toBe("t");
    expect(room.owner).toBe("o");
  });

  it("getRoom 不存在返回 undefined", () => {
    const db = makeDb();
    expect(getRoom(db, "nope")).toBeUndefined();
  });

  it("listRooms 按 created_at_ms 升序返回", () => {
    const db = makeDb();
    createRoom(db, { id: "a" });
    createRoom(db, { id: "b" });
    createRoom(db, { id: "c" });
    const rows = listRooms(db);
    expect(rows.map((r) => r.id)).toEqual(["a", "b", "c"]);
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i]!.created_at_ms).toBeGreaterThanOrEqual(rows[i - 1]!.created_at_ms);
    }
  });
});

describe("房间类型与更新", () => {
  it("setRoomType 生效并可通过 getRoom 观察到", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    expect(setRoomType(db, "r1", "playroom")).toBe(true);
    expect(getRoom(db, "r1")!.type).toBe("playroom");
  });

  it("setRoomType 对不存在房间返回 false", () => {
    const db = makeDb();
    expect(setRoomType(db, "ghost", "playroom")).toBe(false);
  });

  it("updateRoom 只更新传入字段", () => {
    const db = makeDb();
    createRoom(db, { id: "r1", name: "旧名", topic: "旧题" });
    expect(updateRoom(db, "r1", { name: "新名" })).toBe(true);
    const room = getRoom(db, "r1")!;
    expect(room.name).toBe("新名");
    expect(room.topic).toBe("旧题");
  });

  it("updateRoom 空 patch 且房间存在返回 true", () => {
    const db = makeDb();
    createRoom(db, { id: "r1", name: "名" });
    expect(updateRoom(db, "r1", {})).toBe(true);
    expect(getRoom(db, "r1")!.name).toBe("名");
  });

  it("updateRoom 对不存在房间返回 false", () => {
    const db = makeDb();
    expect(updateRoom(db, "ghost", { name: "x" })).toBe(false);
  });

  it("getRoomType 未注册房间返回 workroom", () => {
    const db = makeDb();
    expect(getRoomType(db, "nope")).toBe("workroom");
  });

  it("getRoomType 注册为 playroom 时返回 playroom", () => {
    const db = makeDb();
    createRoom(db, { id: "r1", type: "playroom" });
    expect(getRoomType(db, "r1")).toBe("playroom");
  });
});

describe("房间成员", () => {
  it("addRoomMember 后 list 有 1 人", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    addRoomMember(db, "r1", "a1", "member");
    const members = listRoomMembers(db, "r1");
    expect(members.length).toBe(1);
    expect(members[0]!.adapter_id).toBe("a1");
    expect(countRoomMembers(db, "r1")).toBe(1);
  });

  it("重复 add 更新 persona_role 不翻倍", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    addRoomMember(db, "r1", "a1", "member");
    addRoomMember(db, "r1", "a1", "moderator");
    expect(countRoomMembers(db, "r1")).toBe(1);
    expect(getPersonaRole(db, "r1", "a1")).toBe("moderator");
  });

  it("setPersonaRole 对新成员自动添加", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    setPersonaRole(db, "r1", "a2", "owner");
    expect(getPersonaRole(db, "r1", "a2")).toBe("owner");
    expect(countRoomMembers(db, "r1")).toBe(1);
  });

  it("getPersonaRole 非成员返回 undefined", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    expect(getPersonaRole(db, "r1", "ghost")).toBeUndefined();
  });

  it("removeRoomMember 成功后 count 为 0", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    addRoomMember(db, "r1", "a1");
    expect(removeRoomMember(db, "r1", "a1")).toBe(true);
    expect(countRoomMembers(db, "r1")).toBe(0);
  });

  it("removeRoomMember 对不存在成员返回 false", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    expect(removeRoomMember(db, "r1", "ghost")).toBe(false);
  });

  it("listRoomMembers 按 joined_at_ms 升序", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    addRoomMember(db, "r1", "a1");
    addRoomMember(db, "r1", "a2");
    addRoomMember(db, "r1", "a3");
    const rows = listRoomMembers(db, "r1");
    expect(rows.map((r) => r.adapter_id)).toEqual(["a1", "a2", "a3"]);
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i]!.joined_at_ms).toBeGreaterThanOrEqual(rows[i - 1]!.joined_at_ms);
    }
  });
});

describe("游戏会话", () => {
  it("createGameSession 默认 state 为 '{}'", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    const gs = createGameSession(db, { id: "g1", room_id: "r1", game: "chess" });
    expect(gs.state).toBe("{}");
    expect(gs.id).toBe("g1");
    expect(gs.room_id).toBe("r1");
    expect(gs.game).toBe("chess");
  });

  it("getGameSession 不存在返回 undefined", () => {
    const db = makeDb();
    expect(getGameSession(db, "nope")).toBeUndefined();
  });

  it("listGameSessions 按 created_at_ms 倒序", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    createGameSession(db, { id: "g1", room_id: "r1", game: "chess" });
    createGameSession(db, { id: "g2", room_id: "r1", game: "go" });
    createGameSession(db, { id: "g3", room_id: "r1", game: "othello" });
    const rows = listGameSessions(db, "r1");
    expect(rows.map((r) => r.id).sort()).toEqual(["g1", "g2", "g3"]);
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i]!.created_at_ms).toBeLessThanOrEqual(rows[i - 1]!.created_at_ms);
    }
  });

  it("updateGameSessionState 生效", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    createGameSession(db, { id: "g1", room_id: "r1", game: "chess" });
    expect(updateGameSessionState(db, "g1", '{"turn":1}')).toBe(true);
    expect(getGameSession(db, "g1")!.state).toBe('{"turn":1}');
  });

  it("updateGameSessionState 对不存在会话返回 false", () => {
    const db = makeDb();
    expect(updateGameSessionState(db, "ghost", "{}")).toBe(false);
  });

  it("endGameSession 后 get 返回 undefined", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    createGameSession(db, { id: "g1", room_id: "r1", game: "chess" });
    expect(endGameSession(db, "g1")).toBe(true);
    expect(getGameSession(db, "g1")).toBeUndefined();
  });

  it("endGameSession 对不存在会话返回 false", () => {
    const db = makeDb();
    expect(endGameSession(db, "ghost")).toBe(false);
  });

  it("countGameSessions 正确统计", () => {
    const db = makeDb();
    createRoom(db, { id: "r1" });
    createRoom(db, { id: "r2" });
    createGameSession(db, { id: "g1", room_id: "r1", game: "chess" });
    createGameSession(db, { id: "g2", room_id: "r1", game: "go" });
    createGameSession(db, { id: "g3", room_id: "r2", game: "chess" });
    expect(countGameSessions(db, "r1")).toBe(2);
    expect(countGameSessions(db, "r2")).toBe(1);
    expect(countGameSessions(db, "r3")).toBe(0);
  });
});