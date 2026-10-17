import { describe, it, expect } from "vitest";
import { createGame, bid, play, serializeForSeat } from "../src/doudizhu/game.js";
import type { GameState } from "../src/doudizhu/game.js";

const seats: [string, string, string] = ["s0", "s1", "s2"];
const rng = () => 0.999;

function fresh(): GameState {
  return createGame(seats, rng);
}

// 推进到出牌阶段：s0 叫 1、s1 叫 2、s2 叫 3 → s2 当地主
function toPlaying(): GameState {
  let s = fresh();
  s = bid(s, "s0", 1);
  s = bid(s, "s1", 2);
  s = bid(s, "s2", 3);
  return s;
}

describe("createGame", () => {
  it("每人发 17 张牌", () => {
    const s = fresh();
    expect(s.players[0].hand.length).toBe(17);
    expect(s.players[1].hand.length).toBe(17);
    expect(s.players[2].hand.length).toBe(17);
  });

  it("底牌 3 张且总数为 54", () => {
    const s = fresh();
    const total =
      s.players[0].hand.length +
      s.players[1].hand.length +
      s.players[2].hand.length +
      s.bottomCards.length;
    expect(s.bottomCards.length).toBe(3);
    expect(total).toBe(54);
  });

  it("初始 phase 为 bidding", () => {
    const s = fresh();
    expect(s.phase).toBe("bidding");
  });

  it("初始 currentSeat 为 seats[0]", () => {
    const s = fresh();
    expect(s.currentSeat).toBe("s0");
  });

  it("初始手牌已排序", () => {
    const s = fresh();
    for (const p of s.players) {
      const sorted = p.hand.slice().sort((a, b) => a - b);
      expect(p.hand).toEqual(sorted);
    }
  });

  it("确定性 rng 两次发牌结果一致", () => {
    const a = createGame(seats, rng);
    const b = createGame(seats, rng);
    expect(a.players.map((p) => p.hand)).toEqual(b.players.map((p) => p.hand));
    expect(a.bottomCards).toEqual(b.bottomCards);
  });

  it("初始 lastPlay 为 null", () => {
    const s = fresh();
    expect(s.lastPlay).toBeNull();
  });

  it("初始 baseScore 为 0、bombs 为 0", () => {
    const s = fresh();
    expect(s.baseScore).toBe(0);
    expect(s.bombs).toBe(0);
  });
});

describe("叫分", () => {
  it("s0 叫 1、s1 叫 2、s2 叫 3 后 s2 当地主", () => {
    const s = toPlaying();
    expect(s.landlordSeat).toBe("s2");
  });

  it("地主手牌为 20 张", () => {
    const s = toPlaying();
    const landlord = s.players.find((p) => p.seat === "s2")!;
    expect(landlord.hand.length).toBe(20);
  });

  it("叫分结束后 phase 为 playing", () => {
    const s = toPlaying();
    expect(s.phase).toBe("playing");
  });

  it("叫分结束后 currentSeat 为地主", () => {
    const s = toPlaying();
    expect(s.currentSeat).toBe("s2");
  });

  it("baseScore 为最高叫分", () => {
    const s = toPlaying();
    expect(s.baseScore).toBe(3);
  });

  it("叫分结束后 lastPlay 为 null", () => {
    const s = toPlaying();
    expect(s.lastPlay).toBeNull();
  });

  it("没轮到叫分时 throw", () => {
    const s = fresh();
    expect(() => bid(s, "s1", 1)).toThrow();
  });

  it("重复叫分 throw", () => {
    let s = fresh();
    s = bid(s, "s0", 1);
    expect(() => bid(s, "s0", 2)).toThrow();
  });

  it("叫分期调用 play throw", () => {
    const s = fresh();
    expect(() => play(s, "s0", [3])).toThrow();
  });

  it("三人都叫 0 后 redeals 为 1 且重新发牌仍 bidding", () => {
    // 用递增序列 rng，保证重发洗牌结果与首发不同
    let n = 0;
    const seqRng = () => (n++ % 97) / 97;
    let s = createGame(seats, seqRng);
    const before = s.players.map((p) => p.hand.slice());
    s = bid(s, "s0", 0);
    s = bid(s, "s1", 0);
    s = bid(s, "s2", 0);
    expect(s.redeals).toBe(1);
    expect(s.phase).toBe("bidding");
    expect(s.bids).toEqual([null, null, null]);
    const changed = s.players.some(
      (p, i) => JSON.stringify(p.hand) !== JSON.stringify(before[i])
    );
    expect(changed).toBe(true);
  });
});

describe("出牌轮转", () => {
  it("地主首出单张后 currentSeat 轮转到下一家", () => {
    let s = toPlaying();
    const card = s.players.find((p) => p.seat === "s2")!.hand[0];
    s = play(s, "s2", [card]);
    expect(s.currentSeat).toBe("s0");
  });

  it("首出单张后 lastPlay 记录正确", () => {
    let s = toPlaying();
    const card = s.players.find((p) => p.seat === "s2")!.hand[0];
    s = play(s, "s2", [card]);
    expect(s.lastPlay).not.toBeNull();
    expect(s.lastPlay!.seat).toBe("s2");
    expect(s.lastPlay!.combo.cards).toEqual([card]);
  });

  it("下家出更大的单张压过", () => {
    let s = toPlaying();
    const landlord = s.players.find((p) => p.seat === "s2")!;
    const first = landlord.hand[0];
    s = play(s, "s2", [first]);
    const s0 = s.players.find((p) => p.seat === "s0")!;
    const bigger = s0.hand.find((c) => c > first);
    if (bigger === undefined) {
      // 若手中无更大牌，跳过压牌断言
      expect(s.currentSeat).toBe("s0");
      return;
    }
    s = play(s, "s0", [bigger]);
    expect(s.lastPlay!.seat).toBe("s0");
    expect(s.lastPlay!.combo.cards).toEqual([bigger]);
  });

  it("下家出更小单张 throw", () => {
    let s = toPlaying();
    const landlord = s.players.find((p) => p.seat === "s2")!;
    const first = landlord.hand[landlord.hand.length - 1];
    s = play(s, "s2", [first]);
    const s0 = s.players.find((p) => p.seat === "s0")!;
    const smaller = s0.hand.find((c) => c < first);
    if (smaller === undefined) {
      expect(s.currentSeat).toBe("s0");
      return;
    }
    expect(() => play(s, "s0", [smaller])).toThrow("压不住上家的牌");
  });

  it("有 lastPlay 且非自己出时不出合法且轮转", () => {
    let s = toPlaying();
    const landlord = s.players.find((p) => p.seat === "s2")!;
    const first = landlord.hand[0];
    s = play(s, "s2", [first]);
    const lastBefore = s.lastPlay;
    s = play(s, "s0", []);
    expect(s.currentSeat).toBe("s1");
    expect(s.lastPlay).toEqual(lastBefore);
  });

  it("两家都不出后轮回到 lastPlay.seat 时 lastPlay 为 null", () => {
    let s = toPlaying();
    const landlord = s.players.find((p) => p.seat === "s2")!;
    const first = landlord.hand[0];
    s = play(s, "s2", [first]);
    s = play(s, "s0", []);
    s = play(s, "s1", []);
    expect(s.currentSeat).toBe("s2");
    expect(s.lastPlay).toBeNull();
  });
});

describe("非法操作", () => {
  it("首出时不出 throw", () => {
    const s = toPlaying();
    expect(() => play(s, "s2", [])).toThrow();
  });

  it("出不存在于手牌的牌 throw", () => {
    const s = toPlaying();
    const landlord = s.players.find((p) => p.seat === "s2")!;
    // 找一张手牌里肯定没有的点数（20 张手牌至少缺一个点数，兜底用 99 触发非法牌型）
    const missing =
      [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17].find(
        (v) => !landlord.hand.includes(v)
      ) ?? 99;
    expect(() => play(s, "s2", [missing])).toThrow();
  });

  it("出非法牌型 [3,4] throw", () => {
    let s = toPlaying();
    const landlord = s.players.find((p) => p.seat === "s2")!;
    if (landlord.hand.includes(3) && landlord.hand.includes(4)) {
      expect(() => play(s, "s2", [3, 4])).toThrow();
    } else {
      expect(() => play(s, "s2", [3, 4])).toThrow();
    }
  });

  it("没轮到自己出牌 throw", () => {
    const s = toPlaying();
    expect(() => play(s, "s0", [s.players[0].hand[0]])).toThrow();
  });
});

describe("炸弹与结算", () => {
  it("出炸弹后 bombs 加 1", () => {
    let s = toPlaying();
    const landlord = s.players.find((p) => p.seat === "s2")!;
    // 找一组四张相同的牌
    const counts = new Map<number, number>();
    for (const c of landlord.hand) counts.set(c, (counts.get(c) ?? 0) + 1);
    let bombRank: number | null = null;
    for (const [rank, n] of counts) {
      if (n >= 4) {
        bombRank = rank;
        break;
      }
    }
    if (bombRank === null) {
      expect(s.bombs).toBe(0);
      return;
    }
    const bomb = [bombRank, bombRank, bombRank, bombRank];
    s = play(s, "s2", bomb);
    expect(s.bombs).toBe(1);
  });

  it("地主一手出完获胜且春天", () => {
    let s = toPlaying();
    // 摆拍：给地主一手可出完的牌，农民未出过牌
    s.players = s.players.map((p) =>
      p.seat === "s2"
        ? { ...p, hand: [3] }
        : { ...p, hand: p.hand.slice() }
    );
    s = play(s, "s2", [3]);
    expect(s.phase).toBe("finished");
    expect(s.winner).toBe("s2");
    expect(s.spring).toBe("landlord");
  });

  it("双方都出过牌则无春天", () => {
    let s = toPlaying();
    // 摆拍：地主 s2 手牌 [14,17]，农民 s0 手牌 [15,3]，农民 s1 手牌 [4]
    s.players = s.players.map((p) => {
      if (p.seat === "s2") return { ...p, hand: [14, 17] };
      if (p.seat === "s0") return { ...p, hand: [3, 15] };
      return { ...p, hand: [4] };
    });
    s = play(s, "s2", [14]); // 地主领出单张 14
    s = play(s, "s0", [15]); // 农民压上（farmerPlays=1）
    s = play(s, "s1", []); // 农民 s1 不出
    s = play(s, "s2", [17]); // 地主用 17 压回并出完
    expect(s.phase).toBe("finished");
    expect(s.winner).toBe("s2");
    expect(s.spring).toBeUndefined(); // 农民出过牌，无春天
  });

  it("农民先出完获胜", () => {
    let s = toPlaying();
    s.players = s.players.map((p) => {
      if (p.seat === "s2") return { ...p, hand: p.hand.slice() };
      if (p.seat === "s0") return { ...p, hand: [3] };
      return { ...p, hand: p.hand.slice() };
    });
    // 地主先出一张让出牌权轮转到 s0
    const landlordCard = s.players.find((p) => p.seat === "s2")!.hand[0];
    s = play(s, "s2", [landlordCard]);
    // s0 出完
    s.players = s.players.map((p) =>
      p.seat === "s0" ? { ...p, hand: [15] } : p
    );
    s = play(s, "s0", [15]);
    expect(s.phase).toBe("finished");
    expect(s.winner).toBe("s0");
  });
});

describe("脱敏", () => {
  it("自己能看到 hand", () => {
    const s = fresh();
    const view = serializeForSeat(s, "s0") as { players: { seat: string; hand?: number[] }[] };
    const me = view.players.find((p) => p.seat === "s0")!;
    expect(me.hand).toBeDefined();
  });

  it("别人只能看到 handCount 看不到 hand", () => {
    const s = fresh();
    const view = serializeForSeat(s, "s0") as { players: { seat: string; hand?: number[]; handCount: number }[] };
    const other = view.players.find((p) => p.seat === "s1")!;
    expect(other.hand).toBeUndefined();
    expect(other.handCount).toBe(17);
  });

  it("叫分期 isLandlord 全为 false", () => {
    const s = fresh();
    const view = serializeForSeat(s, "s0") as { players: { isLandlord: boolean }[] };
    for (const p of view.players) {
      expect(p.isLandlord).toBe(false);
    }
  });

  it("叫分期没有 landlordSeat 字段", () => {
    const s = fresh();
    const view = serializeForSeat(s, "s0") as Record<string, unknown>;
    expect("landlordSeat" in view).toBe(false);
  });

  it("出牌期有 landlordSeat 与 bottomCards", () => {
    const s = toPlaying();
    const view = serializeForSeat(s, "s0") as { landlordSeat?: string; bottomCards?: number[] };
    expect(view.landlordSeat).toBe("s2");
    expect(view.bottomCards).toBeDefined();
    expect(view.bottomCards!.length).toBe(3);
  });
});