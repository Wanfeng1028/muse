// 单元测试：packages/protocol/src/rooms-types.ts
import { describe, it, expect } from "vitest";
import {
  ROOM_TYPE_WORKROOM,
  ROOM_TYPE_PLAYROOM,
  ROOM_TYPES,
  DEFAULT_ROOM_TYPE,
  isRoomType,
  WORKROOM_GAMES,
  PLAYROOM_GAMES,
  gamesForRoomType,
  isGameAllowed,
  canUpdateRoom,
  canInvite,
  canStartTopic,
  canClearOrKick,
  routeStrategyFor,
  type RoomType,
} from "../src/index.js";

describe("rooms-types 常量", () => {
  it("ROOM_TYPE_WORKROOM 为 'workroom'", () => {
    expect(ROOM_TYPE_WORKROOM).toBe("workroom");
  });

  it("ROOM_TYPE_PLAYROOM 为 'playroom'", () => {
    expect(ROOM_TYPE_PLAYROOM).toBe("playroom");
  });

  it("ROOM_TYPES 长度为 2 且包含两种房间类型", () => {
    expect(ROOM_TYPES).toHaveLength(2);
    expect(ROOM_TYPES).toContain(ROOM_TYPE_WORKROOM);
    expect(ROOM_TYPES).toContain(ROOM_TYPE_PLAYROOM);
  });

  it("DEFAULT_ROOM_TYPE 为 'workroom'", () => {
    expect(DEFAULT_ROOM_TYPE).toBe("workroom");
    expect(DEFAULT_ROOM_TYPE).toBe(ROOM_TYPE_WORKROOM);
  });
});

describe("isRoomType", () => {
  it("接受合法的房间类型", () => {
    expect(isRoomType("workroom")).toBe(true);
    expect(isRoomType("playroom")).toBe(true);
  });

  it("拒绝大小写不匹配的字符串", () => {
    expect(isRoomType("WORKROOM")).toBe(false);
    expect(isRoomType("Playroom")).toBe(false);
  });

  it("拒绝空串", () => {
    expect(isRoomType("")).toBe(false);
  });

  it("拒绝 null 与 undefined", () => {
    expect(isRoomType(null)).toBe(false);
    expect(isRoomType(undefined)).toBe(false);
  });

  it("拒绝数字与对象", () => {
    expect(isRoomType(123)).toBe(false);
    expect(isRoomType({})).toBe(false);
    expect(isRoomType({ type: "workroom" })).toBe(false);
  });
});

describe("游戏清单常量", () => {
  it("WORKROOM_GAMES 有 3 个且含 vote_plan", () => {
    expect(WORKROOM_GAMES).toHaveLength(3);
    expect(WORKROOM_GAMES).toContain("vote_plan");
  });

  it("PLAYROOM_GAMES 有 4 个且含 who_is_undercover", () => {
    expect(PLAYROOM_GAMES).toHaveLength(4);
    expect(PLAYROOM_GAMES).toContain("who_is_undercover");
  });

  it("两份清单没有交集", () => {
    const intersection = WORKROOM_GAMES.filter((g) => PLAYROOM_GAMES.includes(g));
    expect(intersection).toHaveLength(0);
  });
});

describe("gamesForRoomType", () => {
  it("workroom 返回工作坊清单", () => {
    expect(gamesForRoomType(ROOM_TYPE_WORKROOM)).toBe(WORKROOM_GAMES);
  });

  it("playroom 返回游戏厅清单", () => {
    expect(gamesForRoomType(ROOM_TYPE_PLAYROOM)).toBe(PLAYROOM_GAMES);
  });
});

describe("isGameAllowed", () => {
  it("本房间的游戏允许", () => {
    expect(isGameAllowed("workroom", "vote_plan")).toBe(true);
    expect(isGameAllowed("workroom", "timed_brainstorm")).toBe(true);
    expect(isGameAllowed("playroom", "who_is_undercover")).toBe(true);
    expect(isGameAllowed("playroom", "draw_and_guess")).toBe(true);
  });

  it("跨房间的游戏不允许", () => {
    expect(isGameAllowed("workroom", "who_is_undercover")).toBe(false);
    expect(isGameAllowed("playroom", "vote_plan")).toBe(false);
  });

  it("空串或未知游戏不允许", () => {
    expect(isGameAllowed("workroom", "")).toBe(false);
    expect(isGameAllowed("playroom", "")).toBe(false);
    expect(isGameAllowed("workroom", "nonexistent_game")).toBe(false);
    expect(isGameAllowed("playroom", "nonexistent_game")).toBe(false);
  });
});

describe("权限矩阵：canUpdateRoom / canInvite / canStartTopic", () => {
  const cases: ReadonlyArray<[string, (roomType: RoomType, isOwner: boolean) => boolean]> = [
    ["canUpdateRoom", canUpdateRoom],
    ["canInvite", canInvite],
    ["canStartTopic", canStartTopic],
  ];

  for (const [name, fn] of cases) {
    describe(name, () => {
      it("playroom 下非房主也允许", () => {
        expect(fn("playroom", false)).toBe(true);
      });

      it("playroom 下房主允许", () => {
        expect(fn("playroom", true)).toBe(true);
      });

      it("workroom 下非房主禁止", () => {
        expect(fn("workroom", false)).toBe(false);
      });

      it("workroom 下房主允许", () => {
        expect(fn("workroom", true)).toBe(true);
      });
    });
  }
});

describe("权限矩阵：canClearOrKick 只看房主", () => {
  it("playroom 下非房主禁止", () => {
    expect(canClearOrKick("playroom", false)).toBe(false);
  });

  it("playroom 下房主允许", () => {
    expect(canClearOrKick("playroom", true)).toBe(true);
  });

  it("workroom 下非房主禁止", () => {
    expect(canClearOrKick("workroom", false)).toBe(false);
  });

  it("workroom 下房主允许", () => {
    expect(canClearOrKick("workroom", true)).toBe(true);
  });
});

describe("routeStrategyFor", () => {
  it("workroom 使用定向策略", () => {
    expect(routeStrategyFor("workroom")).toBe("directed");
  });

  it("playroom 使用广播策略", () => {
    expect(routeStrategyFor("playroom")).toBe("broadcast");
  });
});
