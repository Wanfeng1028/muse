// 第 7 轮：管理操作矩阵 canManageRoom
import { describe, it, expect } from "vitest";
import {
  ROOM_TYPE_WORKROOM,
  ROOM_TYPE_PLAYROOM,
  canManageRoom,
} from "../src/index.js";

describe("canManageRoom 管理操作矩阵", () => {
  it("guest 一律不得，即使 isOwner 为 true 也不放行", () => {
    expect(canManageRoom(ROOM_TYPE_WORKROOM, true, "guest")).toBe(false);
    expect(canManageRoom(ROOM_TYPE_PLAYROOM, true, "guest")).toBe(false);
  });

  it("workroom 房主可管理、非房主不可", () => {
    expect(canManageRoom(ROOM_TYPE_WORKROOM, true, "member")).toBe(true);
    expect(canManageRoom(ROOM_TYPE_WORKROOM, false, "member")).toBe(false);
    expect(canManageRoom(ROOM_TYPE_WORKROOM, false, undefined)).toBe(false);
  });

  it("playroom 非 guest 均可管理、guest 不可", () => {
    expect(canManageRoom(ROOM_TYPE_PLAYROOM, false, "member")).toBe(true);
    expect(canManageRoom(ROOM_TYPE_PLAYROOM, false, undefined)).toBe(true);
    expect(canManageRoom(ROOM_TYPE_PLAYROOM, false, "guest")).toBe(false);
  });
});
