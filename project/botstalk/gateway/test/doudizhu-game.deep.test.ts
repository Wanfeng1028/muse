// 深测：叫分状态机/春天判定/AI 不犯规
import { describe, it, expect } from "vitest";
import {
  createGame,
  bid,
  play,
  serializeForSeat,
  type GameState,
} from "../src/doudizhu/game.js";
import { choosePlay } from "../src/doudizhu/ai.js";

// 牌面数字映射：3=3 … 13=K，14=A，15=2，16=小王，17=大王

/** 确定性 rng：始终返回固定值 */
function fixedRng(v: number): () => number {
  return () => v;
}

/** 依次返回给定序列的 rng，用尽后返回最后一个值 */
function seqRng(values: number[]): () => number {
  let i = 0;
  return () => {
    const v = values[Math.min(i, values.length - 1)];
    i++;
    return v;
  };
}

/** 推进到 playing 阶段：s0 叫 3 直接当地主 */
function toPlaying(rng: () => number = fixedRng(0.5)): GameState {
  let s = createGame(["s0", "s1", "s2"], rng);
  s = bid(s, "s0", 3);
  s = bid(s, "s1", 0);
  s = bid(s, "s2", 0);
  return s;
}

/** 取某座位手牌 */
function handOf(state: GameState, seat: string): number[] {
  const p = state.players.find((x) => x.seat === seat);
  if (!p) throw new Error("seat not found: " + seat);
  return p.hand;
}

/** 多重集包含检查：sub 的每个元素计数不超过 sup */
function multisetContains(sup: number[], sub: number[]): boolean {
  const counts = new Map<number, number>();
  for (const c of sup) counts.set(c, (counts.get(c) ?? 0) + 1);
  for (const c of sub) {
    const n = counts.get(c) ?? 0;
    if (n <= 0) return false;
    counts.set(c, n - 1);
  }
  return true;
}

/** 简易牌型解析（仅供本测试断言使用） */
type ParsedCombo =
  | { type: "invalid" }
  | { type: "single"; rank: number }
  | { type: "pair"; rank: number }
  | { type: "triple"; rank: number }
  | { type: "bomb"; rank: number }
  | { type: "rocket" }
  | { type: "other" };

function parseCombo(cards: number[]): ParsedCombo {
  if (cards.length === 0) return { type: "invalid" };
  const sorted = [...cards].sort((a, b) => a - b);
  const counts = new Map<number, number>();
  for (const c of sorted) counts.set(c, (counts.get(c) ?? 0) + 1);
  const distinct = [...counts.keys()];
  if (sorted.length === 1) return { type: "single", rank: sorted[0] };
  if (sorted.length === 2 && sorted[0] === 16 && sorted[1] === 17) {
    return { type: "rocket" };
  }
  if (sorted.length === 2 && distinct.length === 1) {
    return { type: "pair", rank: sorted[0] };
  }
  if (sorted.length === 3 && distinct.length === 1) {
    return { type: "triple", rank: sorted[0] };
  }
  if (sorted.length === 4 && distinct.length === 1) {
    return { type: "bomb", rank: sorted[0] };
  }
  return { type: "other" };
}

/** 单张压过判断（仅 single 场景） */
function singleBeats(a: number, b: number): boolean {
  return a > b;
}

describe("深测：叫分状态机", () => {
  it("A1. 抢叫抛错：s1 在 s0 之前叫分", () => {
    const s = createGame(["s0", "s1", "s2"], fixedRng(0.5));
    expect(s.bidTurn).toBe(0);
    expect(() => bid(s, "s1", 1)).toThrow();
  });

  it("A2. 叫分阶段结束后继续叫分抛错", () => {
    const s = toPlaying();
    expect(s.phase).toBe("playing");
    expect(() => bid(s, "s0", 1)).toThrow();
  });

  it("A3. 并列最高分先叫者得：s0 叫 2、s1 叫 3、s2 叫 3 → 地主为 s1", () => {
    let s = createGame(["s0", "s1", "s2"], fixedRng(0.5));
    s = bid(s, "s0", 2);
    s = bid(s, "s1", 3);
    s = bid(s, "s2", 3);
    expect(s.landlordSeat).toBe("s1");
    expect(s.baseScore).toBe(3);
    expect(s.phase).toBe("playing");
  });

  it("A4. 全不叫流局重发：phase 仍 bidding，redeals=1，bids 重置，每人 17 张", () => {
    let s = createGame(["s0", "s1", "s2"], fixedRng(0.5));
    s = bid(s, "s0", 0);
    s = bid(s, "s1", 0);
    s = bid(s, "s2", 0);
    expect(s.phase).toBe("bidding");
    expect(s.redeals).toBe(1);
    expect(s.bids).toEqual([null, null, null]);
    expect(s.bidTurn).toBe(0);
    expect(s.currentSeat).toBe("s0");
    expect(handOf(s, "s0").length).toBe(17);
    expect(handOf(s, "s1").length).toBe(17);
    expect(handOf(s, "s2").length).toBe(17);
    expect(s.bottomCards.length).toBe(3);
  });

  it("A5a. 连续 4 次全不叫后 rng=0 → 地主为 s0，baseScore=1", () => {
    let s = createGame(["s0", "s1", "s2"], fixedRng(0));
    for (let round = 0; round < 4; round++) {
      s = bid(s, "s0", 0);
      s = bid(s, "s1", 0);
      s = bid(s, "s2", 0);
    }
    expect(s.phase).toBe("playing");
    expect(s.landlordSeat).toBe("s0");
    expect(s.baseScore).toBe(1);
  });

  it("A5b. 连续 4 次全不叫后 rng=0.999 → 地主为 s2，baseScore=1", () => {
    let s = createGame(["s0", "s1", "s2"], fixedRng(0.999));
    for (let round = 0; round < 4; round++) {
      s = bid(s, "s0", 0);
      s = bid(s, "s1", 0);
      s = bid(s, "s2", 0);
    }
    expect(s.phase).toBe("playing");
    expect(s.landlordSeat).toBe("s2");
    expect(s.baseScore).toBe(1);
  });

  it("A6. bid 纯函数：原 state.bids 不被修改", () => {
    const s = createGame(["s0", "s1", "s2"], fixedRng(0.5));
    const before = JSON.stringify(s.bids);
    const s2 = bid(s, "s0", 2);
    expect(JSON.stringify(s.bids)).toBe(before);
    expect(s.bids).toEqual([null, null, null]);
    expect(s2.bids[0]).toBe(2);
  });
});

describe("深测：春天判定纵深", () => {
  it("B7. 农民获胜且 landlordPlays===1 → spring==='farmers'（用 choosePlay 驱动）", () => {
    const state = toPlaying(fixedRng(0.999));
    const landlord = state.landlordSeat!;
    // 地主先手，出最小单张（此时 landlordPlays 变 1）
    let s = state;
    // 让地主出一张最小单张
    const landlordHand = handOf(s, landlord);
    const minCard = Math.min(...landlordHand);
    s = play(s, landlord, [minCard]);
    expect(s.landlordPlays).toBe(1);

    let guard = 0;
    let finished = false;
    while (guard < 500 && !finished) {
      guard++;
      if (s.phase === "finished") {
        finished = true;
        break;
      }
      const seat = s.currentSeat;
      if (seat === landlord) {
        // 地主每次 pass（要求 lastPlay 不是自己出的，上一轮农民已经压过）
        s = play(s, seat, []);
      } else {
        const cards = choosePlay(s, seat);
        s = play(s, seat, cards);
      }
    }
    expect(guard).toBeLessThan(500);
    expect(s.phase).toBe("finished");
    if (s.winner && s.winner !== landlord) {
      expect(s.landlordPlays).toBe(1);
      expect(s.spring).toBe("farmers");
    }
  });

  it("B8. 春天判定与计数器一致性：spring 只在 landlordPlays===1 农民胜 / farmerPlays===0 地主胜时出现", () => {
    const state = toPlaying(fixedRng(0.999));
    const landlord = state.landlordSeat!;
    let s = state;
    // 地主出最小单张
    const lh = handOf(s, landlord);
    const minCard = Math.min(...lh);
    s = play(s, landlord, [minCard]);
    expect(s.landlordPlays).toBe(1);

    // 找到下一个农民座位并让其出一张能压过的牌
    const nextSeat = s.currentSeat;
    expect(nextSeat).not.toBe(landlord);
    const farmerHand = handOf(s, nextSeat);
    const candidate = [...farmerHand].sort((a, b) => a - b).find((c) => c > minCard);
    if (candidate !== undefined) {
      s = play(s, nextSeat, [candidate]);
      expect(s.farmerPlays).toBeGreaterThanOrEqual(1);
    }

    let guard = 0;
    let finished = false;
    while (guard < 500 && !finished) {
      guard++;
      if (s.phase === "finished") {
        finished = true;
        break;
      }
      const seat = s.currentSeat;
      if (seat === landlord) {
        s = play(s, seat, []);
      } else {
        const cards = choosePlay(s, seat);
        s = play(s, seat, cards);
      }
    }
    expect(guard).toBeLessThan(500);
    expect(s.phase).toBe("finished");
    // 春天判定与计数器一致性（源码规则逐字锁定）：
    // 地主获胜：farmerPlays===0 → spring="landlord"，否则 undefined
    // 农民获胜：landlordPlays===1 → spring="farmers"，否则 undefined
    const winnerIsLandlord = s.winner === landlord;
    if (winnerIsLandlord) {
      if (s.farmerPlays === 0) expect(s.spring).toBe("landlord");
      else expect(s.spring).toBeUndefined();
    } else {
      if (s.landlordPlays === 1) expect(s.spring).toBe("farmers");
      else expect(s.spring).toBeUndefined();
    }
  });
});

describe("深测：AI 不犯规", () => {
  it("C9. choosePlay 返回牌是手牌的子集（多重集包含）", () => {
    const s = toPlaying(fixedRng(0.999));
    const landlord = s.landlordSeat!;
    const hand = handOf(s, landlord);
    const chosen = choosePlay(s, landlord);
    expect(multisetContains(hand, chosen)).toBe(true);
  });

  it("C10. AI 压牌要么 []，要么组合合法且能压过 target", () => {
    // s2 地主先手出最小单张，s0 出更大单张压过，然后 s1 决策
    const s0 = toPlaying(fixedRng(0.999));
    const landlord = s0.landlordSeat!;
    let s = s0;
    const lh = handOf(s, landlord);
    const minCard = Math.min(...lh);
    s = play(s, landlord, [minCard]);

    const s0Seat = s.currentSeat;
    const s0Hand = handOf(s, s0Seat);
    const bigger = [...s0Hand].sort((a, b) => a - b).find((c) => c > minCard);
    expect(bigger).toBeDefined();
    s = play(s, s0Seat, [bigger!]);

    const nextSeat = s.currentSeat;
    const result = choosePlay(s, nextSeat);
    if (result.length > 0) {
      const parsed = parseCombo(result);
      expect(parsed.type).not.toBe("invalid");
      // 上家出的单张，压过需要单张或炸弹/王炸
      if (parsed.type === "single") {
        expect(singleBeats(parsed.rank, bigger!)).toBe(true);
      } else {
        expect(["bomb", "rocket"]).toContain(parsed.type);
      }
    } else {
      expect(result).toEqual([]);
    }
  });

  it("C11. 队友让牌：s1（农民）出牌后 s2（农民）choosePlay 返回 []", () => {
    const s0 = toPlaying(fixedRng(0.999));
    const landlord = s0.landlordSeat!;
    expect(landlord).toBe("s0"); // toPlaying 里 s0 叫 3，直接当地主
    let s = s0;
    // 地主 s0 先手出最小单张
    const lh = handOf(s, "s0");
    const minCard = Math.min(...lh);
    s = play(s, "s0", [minCard]);
    // s1（农民）出更大单张压过
    const s1Hand = handOf(s, "s1");
    const bigger = [...s1Hand].sort((a, b) => a - b).find((c) => c > minCard);
    expect(bigger).toBeDefined();
    s = play(s, "s1", [bigger!]);
    expect(s.currentSeat).toBe("s2");
    // s2 是农民，上家 s1 是队友 → 按规则 4 直接不出
    const result = choosePlay(s, "s2");
    expect(result).toEqual([]);
  });

  it("C12. 自由领出时 AI 返回长度为 1 且为其手牌最小值", () => {
    const s = toPlaying(fixedRng(0.999));
    const landlord = s.landlordSeat!;
    const hand = handOf(s, landlord);
    const minCard = Math.min(...hand);
    const result = choosePlay(s, landlord);
    expect(result.length).toBe(1);
    expect(result[0]).toBe(minCard);
  });

  it("C13a. bidding 阶段调用 choosePlay 抛错", () => {
    const s = createGame(["s0", "s1", "s2"], fixedRng(0.5));
    expect(s.phase).toBe("bidding");
    expect(() => choosePlay(s, "s0")).toThrow();
  });

  it("C13b. currentSeat 不是该 seat 时 choosePlay 抛错", () => {
    const s = toPlaying(fixedRng(0.999));
    const landlord = s.landlordSeat!;
    const other = s.players.map((p) => p.seat).find((x) => x !== landlord)!;
    expect(s.currentSeat).toBe(landlord);
    expect(() => choosePlay(s, other)).toThrow();
  });

  it("C14. AI 永不返回非法组合（[] 除外）", () => {
    const s = toPlaying(fixedRng(0.999));
    const landlord = s.landlordSeat!;
    const result = choosePlay(s, landlord);
    if (result.length > 0) {
      const parsed = parseCombo(result);
      expect(parsed.type).not.toBe("invalid");
      expect(parsed.type).not.toBe("other");
    } else {
      expect(result).toEqual([]);
    }
  });
});
