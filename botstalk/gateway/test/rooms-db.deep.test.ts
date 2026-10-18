// 深测：rooms-db 迁移幂等与房间/成员/游戏会话边界
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { DatabaseSync } from "node:sqlite";
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
import { DEFAULT_ROOM_TYPE } from "@botstalk/protocol";

let dir: string;
let db: DatabaseSync;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "rooms-db-deep-"));
  db = openDb(dir);
});

afterEach(() => {
  try {
    db.close();
  } catch {
    // 已关闭时忽略
  }
  rmSync(dir, { recursive: true, force: true });
});

describe("rooms-db 深测", () => {
  it("老库缺表时再次 openDb 自动补建，各 API 正常工作", () => {
    createRoom(db, { id: "legacy-room", name: "旧房" });
    db.close();
    db = openDb(dir);
    db.exec("DROP TABLE rooms");
    db.exec("DROP TABLE room_members");
    db.exec("DROP TABLE game_sessions");
    db.close();

    // 模拟老版本库后再次打开：CREATE TABLE IF NOT EXISTS 幂等，不抛错
    expect(() => {
      db = openDb(dir);
    }).not.toThrow();

    expect(() => createRoom(db, { id: "new-room" })).not.toThrow();
    expect(getRoomType(db, "new-room")).toBe(DEFAULT_ROOM_TYPE);
    expect(() => addRoomMember(db, "new-room", "adapter-1")).not.toThrow();
    expect(() =>
      createGameSession(db, { id: "gs-1", room_id: "new-room", game: "werewolf" }),
    ).not.toThrow();
    expect(getGameSession(db, "gs-1")?.game).toBe("werewolf");
  });

  it("openDb 对同一目录重复调用不抛错且数据保留", () => {
    createRoom(db, { id: "keep-room", name: "留存" });
    db.close();
    db = openDb(dir);
    expect(getRoom(db, "keep-room")?.name).toBe("留存");
    db.close();
    expect(() => {
      db = openDb(dir);
    }).not.toThrow();
    expect(getRoom(db, "keep-room")?.name).toBe("留存");
    expect(listRooms(db).some((r) => r.id === "keep-room")).toBe(true);
  });

  it("createRoom 主键冲突时抛错", () => {
    createRoom(db, { id: "dup" });
    expect(() => createRoom(db, { id: "dup" })).toThrow();
  });

  it("getRoomType 对未注册房间与非法 type 均回退 DEFAULT_ROOM_TYPE", () => {
    expect(getRoomType(db, "not-exist")).toBe(DEFAULT_ROOM_TYPE);
    createRoom(db, { id: "bad-type" });
    db.exec("UPDATE rooms SET type='office' WHERE id='bad-type'");
    expect(getRoomType(db, "bad-type")).toBe(DEFAULT_ROOM_TYPE);
  });

  it("setRoomType 房间不存在返回 false，updateRoom 空 patch 行为正确", () => {
    expect(setRoomType(db, "ghost", "playroom")).toBe(false);
    createRoom(db, { id: "exists" });
    expect(updateRoom(db, "exists", {})).toBe(true);
    expect(updateRoom(db, "ghost", {})).toBe(false);
  });

  it("addRoomMember upsert 同一成员更新 persona_role 且计数不变", () => {
    addRoomMember(db, "r1", "m1");
    addRoomMember(db, "r1", "m1", "host");
    expect(getPersonaRole(db, "r1", "m1")).toBe("host");
    expect(countRoomMembers(db, "r1")).toBe(1);
  });

  it("listRoomMembers 返回全部成员集合", () => {
    addRoomMember(db, "r2", "a");
    addRoomMember(db, "r2", "b");
    const members = listRoomMembers(db, "r2");
    expect(members).toHaveLength(2);
    const ids = members.map((m) => m.adapter_id);
    expect(ids).toContain("a");
    expect(ids).toContain("b");
    expect(new Set(ids)).toEqual(new Set(["a", "b"]));
  });

  it("removeRoomMember 对不存在成员返回 false", () => {
    expect(removeRoomMember(db, "r3", "nobody")).toBe(false);
  });

  it("createGameSession state 缺省为 {} 且 id 冲突抛错", () => {
    const s = createGameSession(db, { id: "gs-def", room_id: "r", game: "g" });
    expect(s.state).toBe("{}");
    expect(() =>
      createGameSession(db, { id: "gs-def", room_id: "r", game: "g" }),
    ).toThrow();
  });

  it("listGameSessions 按 created_at_ms 降序", () => {
    createGameSession(db, { id: "gs-a", room_id: "r4", game: "g" });
    createGameSession(db, { id: "gs-b", room_id: "r4", game: "g" });
    const list = listGameSessions(db, "r4");
    expect(list).toHaveLength(2);
    expect(list[0].created_at_ms).toBeGreaterThanOrEqual(list[1].created_at_ms);
  });

  it("updateGameSessionState 更新 state 与 updated_at_ms，不存在返回 false", () => {
    const before = createGameSession(db, { id: "gs-upd", room_id: "r5", game: "g" });
    expect(updateGameSessionState(db, "gs-upd", '{"step":1}')).toBe(true);
    const after = getGameSession(db, "gs-upd");
    expect(after?.state).toBe('{"step":1}');
    expect(after!.updated_at_ms).toBeGreaterThanOrEqual(before.updated_at_ms);
    expect(updateGameSessionState(db, "gs-missing", "{}")).toBe(false);
  });

  it("endGameSession 删除会话并递减计数，不存在返回 false", () => {
    createGameSession(db, { id: "gs-end", room_id: "r6", game: "g" });
    createGameSession(db, { id: "gs-keep", room_id: "r6", game: "g" });
    expect(countGameSessions(db, "r6")).toBe(2);
    expect(endGameSession(db, "gs-end")).toBe(true);
    expect(getGameSession(db, "gs-end")).toBeUndefined();
    expect(countGameSessions(db, "r6")).toBe(1);
    expect(endGameSession(db, "gs-none")).toBe(false);
  });

  it("countGameSessions 按 room_id 隔离", () => {
    createGameSession(db, { id: "ga-1", room_id: "room-a", game: "g" });
    createGameSession(db, { id: "ga-2", room_id: "room-a", game: "g" });
    createGameSession(db, { id: "gb-1", room_id: "room-b", game: "g" });
    expect(countGameSessions(db, "room-a")).toBe(2);
    expect(countGameSessions(db, "room-b")).toBe(1);
  });

  it("setPersonaRole 为 void 且 upsert 语义：不存在的成员会被先添加", () => {
    addRoomMember(db, "r7", "m7");
    setPersonaRole(db, "r7", "m7", "judge");
    expect(getPersonaRole(db, "r7", "m7")).toBe("judge");
    setPersonaRole(db, "r7", "ghost", "judge");
    expect(getPersonaRole(db, "r7", "ghost")).toBe("judge");
    expect(countRoomMembers(db, "r7")).toBe(2);
  });

  it("getPersonaRole 对不存在成员返回 undefined，清空后返回 null", () => {
    expect(getPersonaRole(db, "r8", "nobody")).toBeUndefined();
    addRoomMember(db, "r8", "m8", "host");
    expect(getPersonaRole(db, "r8", "m8")).toBe("host");
    setPersonaRole(db, "r8", "m8", null);
    expect(getPersonaRole(db, "r8", "m8")).toBeNull();
  });

  it("updateRoom 只更新传入字段，未传字段保持不变", () => {
    createRoom(db, { id: "r9", name: "原名", topic: "原话题" });
    expect(updateRoom(db, "r9", { name: "新名" })).toBe(true);
    const row = getRoom(db, "r9");
    expect(row?.name).toBe("新名");
    expect(row?.topic).toBe("原话题");
  });

  it("listRooms 包含多个已创建房间", () => {
    createRoom(db, { id: "lr-1" });
    createRoom(db, { id: "lr-2" });
    const ids = listRooms(db).map((r) => r.id);
    expect(ids).toContain("lr-1");
    expect(ids).toContain("lr-2");
  });

  it("setRoomType 切换类型后 getRoomType 反映新值", () => {
    createRoom(db, { id: "r10" });
    expect(setRoomType(db, "r10", "playroom")).toBe(true);
    expect(getRoomType(db, "r10")).toBe("playroom");
    expect(setRoomType(db, "r10", "workroom")).toBe(true);
    expect(getRoomType(db, "r10")).toBe("workroom");
  });

  it("countRoomMembers 对空房间返回 0，删成员后递减", () => {
    expect(countRoomMembers(db, "empty")).toBe(0);
    addRoomMember(db, "r11", "m1");
    addRoomMember(db, "r11", "m2");
    expect(countRoomMembers(db, "r11")).toBe(2);
    expect(removeRoomMember(db, "r11", "m1")).toBe(true);
    expect(countRoomMembers(db, "r11")).toBe(1);
  });

  it("createGameSession 自定义 state 被持久化", () => {
    createRoom(db, { id: "r12" });
    createGameSession(db, {
      id: "gs-state",
      room_id: "r12",
      game: "werewolf",
      state: '{"phase":"night"}',
    });
    const row = getGameSession(db, "gs-state");
    expect(row?.state).toBe('{"phase":"night"}');
    expect(row?.room_id).toBe("r12");
  });

  it("listGameSessions 对无会话房间返回空数组", () => {
    createRoom(db, { id: "r13" });
    expect(listGameSessions(db, "r13")).toEqual([]);
  });
});
