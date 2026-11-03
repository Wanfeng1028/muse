// 深测：rooms-types 边界与防御行为锁定
import { describe, it, expect } from "vitest";
import {
  ROOM_TYPE_WORKROOM,
  ROOM_TYPE_PLAYROOM,
  ROOM_TYPES,
  isRoomType,
  DEFAULT_ROOM_TYPE,
  WORKROOM_GAMES,
  PLAYROOM_GAMES,
  gamesForRoomType,
  isGameAllowed,
  canUpdateRoom,
  canInvite,
  canStartTopic,
  canClearOrKick,
  routeStrategyFor,
} from "../src/index.js";
import type { RoomType } from "../src/index.js";

describe("isRoomType 边界值深测", () => {
  it("Symbol 值应返回 false", () => {
    expect(isRoomType(Symbol("workroom"))).toBe(false);
  });

  it("BigInt 值应返回 false", () => {
    expect(isRoomType(BigInt(1))).toBe(false);
  });

  it("数组 [\"workroom\"] 应返回 false", () => {
    expect(isRoomType(["workroom"])).toBe(false);
  });

  it("String 对象 new String(\"workroom\") 应返回 false（非原始 string）", () => {
    // String 对象 typeof 为 "object"，与原始字符串不严格相等
    expect(isRoomType(new String("workroom"))).toBe(false);
  });

  it("\"workroom \" 带尾随空格应返回 false", () => {
    expect(isRoomType("workroom ")).toBe(false);
  });

  it("\" workroom\" 带前导空格应返回 false", () => {
    expect(isRoomType(" workroom")).toBe(false);
  });
});

describe("canClearOrKick 忽略 roomType 参数", () => {
  it("非法 roomType 下，房主为 true 时返回 true", () => {
    expect(canClearOrKick("office" as RoomType, true)).toBe(true);
  });

  it("非法 roomType 下，非房主为 false 时返回 false", () => {
    expect(canClearOrKick("office" as RoomType, false)).toBe(false);
  });

  it("合法 roomType 与非法 roomType 在相同 isOwner 下结果一致（true）", () => {
    expect(canClearOrKick(ROOM_TYPE_WORKROOM, true)).toBe(
      canClearOrKick("office" as RoomType, true),
    );
    expect(canClearOrKick(ROOM_TYPE_PLAYROOM, true)).toBe(
      canClearOrKick("office" as RoomType, true),
    );
  });

  it("合法 roomType 与非法 roomType 在相同 isOwner 下结果一致（false）", () => {
    expect(canClearOrKick(ROOM_TYPE_WORKROOM, false)).toBe(
      canClearOrKick("office" as RoomType, false),
    );
    expect(canClearOrKick(ROOM_TYPE_PLAYROOM, false)).toBe(
      canClearOrKick("office" as RoomType, false),
    );
  });
});

describe("权限函数对非法 roomType 的防御行为锁定", () => {
  it("canUpdateRoom 非法 roomType 走 workroom 分支：非房主为 false", () => {
    expect(canUpdateRoom("office" as RoomType, false)).toBe(false);
  });

  it("canUpdateRoom 非法 roomType 走 workroom 分支：房主为 true", () => {
    expect(canUpdateRoom("office" as RoomType, true)).toBe(true);
  });

  it("canInvite 非法 roomType 走 workroom 分支：非房主为 false", () => {
    expect(canInvite("office" as RoomType, false)).toBe(false);
  });

  it("canInvite 非法 roomType 走 workroom 分支：房主为 true", () => {
    expect(canInvite("office" as RoomType, true)).toBe(true);
  });

  it("canStartTopic 非法 roomType 走 workroom 分支：非房主为 false", () => {
    expect(canStartTopic("office" as RoomType, false)).toBe(false);
  });

  it("canStartTopic 非法 roomType 走 workroom 分支：房主为 true", () => {
    expect(canStartTopic("office" as RoomType, true)).toBe(true);
  });

  it("非法 roomType 下三个权限函数与 workroom 行为一致", () => {
    for (const isOwner of [true, false]) {
      expect(canUpdateRoom("office" as RoomType, isOwner)).toBe(
        canUpdateRoom(ROOM_TYPE_WORKROOM, isOwner),
      );
      expect(canInvite("office" as RoomType, isOwner)).toBe(
        canInvite(ROOM_TYPE_WORKROOM, isOwner),
      );
      expect(canStartTopic("office" as RoomType, isOwner)).toBe(
        canStartTopic(ROOM_TYPE_WORKROOM, isOwner),
      );
    }
  });
});

describe("gamesForRoomType 引用稳定性", () => {
  it("workroom 两次调用返回同一数组引用", () => {
    expect(gamesForRoomType(ROOM_TYPE_WORKROOM)).toBe(
      gamesForRoomType(ROOM_TYPE_WORKROOM),
    );
  });

  it("playroom 两次调用返回同一数组引用", () => {
    expect(gamesForRoomType(ROOM_TYPE_PLAYROOM)).toBe(
      gamesForRoomType(ROOM_TYPE_PLAYROOM),
    );
  });
});

describe("isGameAllowed 大小写敏感", () => {
  it("\"Vote_Plan\" 在 workroom 为 false", () => {
    expect(isGameAllowed(ROOM_TYPE_WORKROOM, "Vote_Plan")).toBe(false);
  });

  it("\"DOUDIZHU\" 在 playroom 为 false", () => {
    expect(isGameAllowed(ROOM_TYPE_PLAYROOM, "DOUDIZHU")).toBe(false);
  });
});

describe("游戏清单不可变性现状", () => {
  it("WORKROOM_GAMES 当前未被冻结（已知可变风险）", () => {
    // 现状锁定：readonly 仅为编译期约束，运行时仍是普通数组
    expect(Object.isFrozen(WORKROOM_GAMES)).toBe(false);
  });

  it("PLAYROOM_GAMES 当前未被冻结（已知可变风险）", () => {
    expect(Object.isFrozen(PLAYROOM_GAMES)).toBe(false);
  });
});

describe("ROOM_TYPES 结构约束", () => {
  it("长度为 2", () => {
    expect(ROOM_TYPES.length).toBe(2);
  });

  it("无重复元素（Set 大小为 2）", () => {
    expect(new Set(ROOM_TYPES).size).toBe(2);
  });
});

describe("routeStrategyFor 非 workroom 分支行为锁定", () => {
  it("非法 roomType 走非 workroom 分支返回 \"broadcast\"", () => {
    // 这是 routeStrategyFor 三元表达式 (roomType === ROOM_TYPE_WORKROOM ? "directed" : "broadcast") 的直接后果，已锁定。
    expect(routeStrategyFor("office" as RoomType)).toBe("broadcast");
  });
});

describe("DEFAULT_ROOM_TYPE 与常量一致性", () => {
  it("默认值为 workroom 常量", () => {
    expect(DEFAULT_ROOM_TYPE).toBe(ROOM_TYPE_WORKROOM);
  });

  it("默认值可被 isRoomType 识别", () => {
    expect(isRoomType(DEFAULT_ROOM_TYPE)).toBe(true);
  });
});
