
import { describe, it, expect } from "vitest";
import {
  createGame,
  bid,
  play,
  serializeForSeat,
  type GameState,
} from "../src/doudizhu/game.js";
import { parseCombo } from "../src/doudizhu/cards.js";

// 固定座位
const SEATS: [string, string, string] = ["a", "b", "c"];

// 构造一个进入 playing 期的确定局面：
// 依次叫分 a=3，b=0，c=0 → a 当地主（拿到底牌）
function toPlaying(rng: () => number = () => 0.5): GameState {
  let s = createGame(SEATS, rng);
  s = bid(s, "a", 3);
  s = bid(s, "b", 0);
  s = bid(s, "c", 0);
  return s;
}

// 覆盖指定座位的手牌 / currentSeat 等，返回新状态
function withHands(
  state: GameState,
  hands: Record<string, number[]>,
  overrides: Partial<GameState> = {}
): GameState {
  const players = state.players.map((p) =>
    hands[p.seat] ? { ...p, hand: hands[p.seat]! } : { ...p, hand: p.hand.slice() }
  );
  return { ...state, players, ...overrides };
}

describe("doudizhu-game.r2", () => {
  // ---------------------------------------------------------------
  // 1. bid 四类非法 throw
  // ---------------------------------------------------------------
  it("1.1 bid 在非叫分期（playing）抛出", () => {
    const s = toPlaying();
    expect(() => bid(s, "b", 1)).toThrow(/叫分/);
  });

  it("1.2 bid 非轮到该座位抛出", () => {
    const s = createGame(SEATS, () => 0.5);
    // currentSeat 是 "a"，让 "b" 叫
    expect(() => bid(s, "b", 1)).toThrow(/还没轮到/);
  });

  it("1.3 叫过分的座位再次叫分时先命中轮次校验", () => {
    let s = createGame(SEATS, () => 0.5);
    s = bid(s, "a", 0);
    // a 已叫过且轮转到 b：源码先校验"还没轮到你叫分"，"本轮已经叫过分了"为防御分支
    expect(s.currentSeat).toBe("b");
    expect(() => bid(s, "a", 0)).toThrow(/还没轮到/);
  });

  it("1.4 bid 分值非法（非 0|1|2|3）抛出", () => {
    const s = createGame(SEATS, () => 0.5);
    expect(() => bid(s, "a", 4 as unknown as 0 | 1 | 2 | 3)).toThrow(/分/);
  });

  // ---------------------------------------------------------------
  // 2. 全不叫一次 → redeals=1、phase 回 bidding、bids 重置
  // ---------------------------------------------------------------
  it("2. 三人全叫 0 → redeals=1 且 phase 回 bidding、bids 重置", () => {
    let s = createGame(SEATS, () => 0.5);
    s = bid(s, "a", 0);
    s = bid(s, "b", 0);
    s = bid(s, "c", 0);
    expect(s.redeals).toBe(1);
    expect(s.phase).toBe("bidding");
    expect(s.bids).toEqual([null, null, null]);
    expect(s.landlordSeat).toBeUndefined();
  });

  // ---------------------------------------------------------------
  // 3. 连续四次全不叫 → 随机定地主（rng=0 → players[0]）
  // ---------------------------------------------------------------
  it("3. 连续 4 次全不叫 → rng 恒 0 时 players[0] 当地主，baseScore=1", () => {
    let s = createGame(SEATS, () => 0);
    for (let round = 0; round < 4; round++) {
      s = bid(s, "a", 0);
      s = bid(s, "b", 0);
      s = bid(s, "c", 0);
    }
    expect(s.redeals).toBe(4);
    expect(s.phase).toBe("playing");
    expect(s.landlordSeat).toBe("a");
    expect(s.baseScore).toBe(1);
  });

  // ---------------------------------------------------------------
  // 4. 叫分 2/2/1 → 顺序在前的 2 分者当地主
  // ---------------------------------------------------------------
  it("4. 叫分 2/2/1 → 顺序在前的 a 当地主", () => {
    let s = createGame(SEATS, () => 0.5);
    s = bid(s, "a", 2);
    s = bid(s, "b", 2);
    s = bid(s, "c", 1);
    expect(s.landlordSeat).toBe("a");
    expect(s.phase).toBe("playing");
  });

  // ---------------------------------------------------------------
  // 5. play 四类非法 throw
  // ---------------------------------------------------------------
  it("5.1 play 非轮到抛出", () => {
    const s = toPlaying();
    // currentSeat 应为地主 a，让 b 出
    expect(() => play(s, "b", [3])).toThrow(/还没轮到/);
  });

  it("5.2 play 手牌中没有这些牌抛出", () => {
    const s = toPlaying();
    const s2 = withHands(s, { a: [3, 4, 5] });
    expect(() => play(s2, "a", [6, 6])).toThrow(/没有|不存在|手牌/);
  });

  it("5.3 play 牌型非法（[3,4]）抛出", () => {
    const s = toPlaying();
    const s2 = withHands(s, { a: [3, 4, 7] });
    expect(() => play(s2, "a", [3, 4])).toThrow(/牌型|非法/);
  });

  it("5.4 play 压不住上家抛出", () => {
    let s = toPlaying();
    s = withHands(s, { a: [5, 9], b: [3], c: [7] }, { currentSeat: "a" });
    // a 出 5
    s = play(s, "a", [5]);
    // b 手上有 3，压不住 5
    expect(() => play(s, "b", [3])).toThrow(/压不住|大/);
  });

  // ---------------------------------------------------------------
  // 6. 不出规则
  // ---------------------------------------------------------------
  it("6.1 首家不能不出（lastPlay=null → throw）", () => {
    const s = toPlaying();
    expect(s.lastPlay).toBeNull();
    expect(() => play(s, s.currentSeat, [])).toThrow(/必须出牌|出牌/);
  });

  it("6.2 上家出牌后自己不出 → currentSeat 轮转", () => {
    let s = toPlaying();
    s = withHands(s, { a: [5, 9], b: [3], c: [7] }, { currentSeat: "a" });
    s = play(s, "a", [5]);
    expect(s.currentSeat).toBe("b");
    // b 不出
    s = play(s, "b", []);
    expect(s.currentSeat).toBe("c");
    expect(s.lastPlay?.seat).toBe("a");
  });

  it("6.3 两家连续不出 → lastPlay 置 null", () => {
    let s = toPlaying();
    s = withHands(s, { a: [5, 9], b: [3], c: [7] }, { currentSeat: "a" });
    s = play(s, "a", [5]);
    s = play(s, "b", []);
    s = play(s, "c", []);
    expect(s.lastPlay).toBeNull();
    expect(s.currentSeat).toBe("a");
  });

  // ---------------------------------------------------------------
  // 7. 炸弹 bombs++
  // ---------------------------------------------------------------
  it("7.1 出炸弹 → bombs 递增", () => {
    let s = toPlaying();
    s = withHands(s, { a: [3, 3, 3, 3], b: [4], c: [5] }, { currentSeat: "a" });
    const before = s.bombs;
    s = play(s, "a", [3, 3, 3, 3]);
    expect(s.bombs).toBe(before + 1);
  });

  it("7.2 出王炸 → bombs 递增", () => {
    let s = toPlaying();
    s = withHands(s, { a: [16, 17], b: [4], c: [5] }, { currentSeat: "a" });
    const before = s.bombs;
    s = play(s, "a", [16, 17]);
    expect(s.bombs).toBe(before + 1);
  });

  // ---------------------------------------------------------------
  // 8. 地主春天
  // ---------------------------------------------------------------
  it("8. 地主一次出完、农民未出 → spring='landlord'", () => {
    let s = toPlaying();
    // 让地主 a 一次性出完；farmerPlays 保持 0
    s = withHands(s, { a: [3, 4, 5, 6, 7], b: [8], c: [9] }, { currentSeat: "a" });
    s = play(s, "a", [3, 4, 5, 6, 7]);
    expect(s.phase).toBe("finished");
    expect(s.winner).toBe("a");
    expect(s.spring).toBe("landlord");
  });

  // ---------------------------------------------------------------
  // 9. 农民春天：地主只出过 1 次、农民出完
  // ---------------------------------------------------------------
  it("9. 地主仅出 1 次、农民出完 → spring='farmers'", () => {
    let s = toPlaying();
    // 地主 a 出单张 5（landlordPlays=1，手牌留 [9] 不结束对局）
    s = withHands(s, { a: [5, 9], b: [3], c: [7] }, { currentSeat: "a" });
    s = play(s, "a", [5]);
    // b 不出，c 出 7 压过并打空手牌 → 农民获胜
    s = play(s, "b", []);
    s = play(s, "c", [7]);
    expect(s.phase).toBe("finished");
    expect(s.winner).toBe("c");
    expect(s.spring).toBe("farmers");
  });

  // ---------------------------------------------------------------
  // 10. 不可变性
  // ---------------------------------------------------------------
  it("10. play 后原 state 的 hand 数组长度不变", () => {
    let s = toPlaying();
    s = withHands(s, { a: [3, 4, 5], b: [6], c: [7] }, { currentSeat: "a" });
    const originalLen = s.players.find((p) => p.seat === "a")!.hand.length;
    const next = play(s, "a", [3]);
    expect(next).not.toBe(s);
    expect(s.players.find((p) => p.seat === "a")!.hand.length).toBe(originalLen);
    expect(next.players.find((p) => p.seat === "a")!.hand.length).toBe(originalLen - 1);
  });

  // ---------------------------------------------------------------
  // 11. serializeForSeat 脱敏
  // ---------------------------------------------------------------
  it("11.1 bidding 期脱敏：isLandlord 全 false，不暴露 bottomCards / landlordSeat", () => {
    const s = createGame(SEATS, () => 0.5);
    const view = serializeForSeat(s, "a") as Record<string, unknown>;
    const players = view.players as Array<Record<string, unknown>>;
    expect(players.every((p) => p.isLandlord === false)).toBe(true);
    expect("bottomCards" in view).toBe(false);
    expect("landlordSeat" in view).toBe(false);
  });

  it("11.2 playing 期本人可见 hand、他人仅 handCount、bottomCards 长度 3", () => {
    const s = toPlaying();
    const view = serializeForSeat(s, "a") as Record<string, unknown>;
    const players = view.players as Array<Record<string, unknown>>;
    const self = players.find((p) => p.seat === "a")!;
    const other = players.find((p) => p.seat === "b")!;
    expect(Array.isArray(self.hand)).toBe(true);
    expect(typeof other.handCount).toBe("number");
    expect("hand" in other).toBe(false);
    expect(Array.isArray(view.bottomCards)).toBe(true);
    expect((view.bottomCards as number[]).length).toBe(3);
    expect(view.landlordSeat).toBe("a");
  });

  // ---------------------------------------------------------------
  // 12. 出完最后一张牌 → finished
  // ---------------------------------------------------------------
  it("12. 出完最后一张牌 → phase='finished'、winner 为该 seat", () => {
    let s = toPlaying();
    s = withHands(s, { a: [9], b: [3], c: [4] }, { currentSeat: "a" });
    s = play(s, "a", [9]);
    expect(s.phase).toBe("finished");
    expect(s.winner).toBe("a");
  });

  // ---------------------------------------------------------------
  // 额外边界：座位不存在
  // ---------------------------------------------------------------
  it("13. play 座位不存在抛出", () => {
    let s = toPlaying();
    // 轮次校验先于座位校验：把 currentSeat 覆盖为不存在的座位才能命中该分支
    s = withHands(s, {}, { currentSeat: "zzz" });
    expect(() => play(s, "zzz", [3])).toThrow(/座位|不存在/);
  });

  // ---------------------------------------------------------------
  // 额外边界：bidding 期 play 抛出
  // ---------------------------------------------------------------
  it("14. play 在非出牌期（bidding）抛出", () => {
    const s = createGame(SEATS, () => 0.5);
    expect(() => play(s, "a", [3])).toThrow(/出牌期|阶段|bidding/);
  });

  // ---------------------------------------------------------------
  // 额外边界：叫分后 currentSeat 轮转到下一家
  // ---------------------------------------------------------------
  it("15. bid 成功后 currentSeat 轮转到下一位", () => {
    const s = createGame(SEATS, () => 0.5);
    const next = bid(s, "a", 1);
    expect(next.currentSeat).toBe("b");
    expect(next.bids[0]).toBe(1);
  });

  // ---------------------------------------------------------------
  // 额外边界：lastPlay 结构在出牌后包含 seat 与 combo
  // ---------------------------------------------------------------
  it("16. 出牌后 lastPlay 记录 seat 与 combo", () => {
    let s = toPlaying();
    s = withHands(s, { a: [7, 7], b: [3], c: [4] }, { currentSeat: "a" });
    s = play(s, "a", [7, 7]);
    expect(s.lastPlay).not.toBeNull();
    expect(s.lastPlay!.seat).toBe("a");
    expect(s.lastPlay!.combo).toEqual(parseCombo([7, 7]));
  });

  // ---------------------------------------------------------------
  // 额外边界：createGame 初始字段
  // ---------------------------------------------------------------
  it("17. createGame 初始：phase=bidding、bombs=0、lastPlay=null、bids 全 null", () => {
    const s = createGame(SEATS, () => 0.5);
    expect(s.phase).toBe("bidding");
    expect(s.bombs).toBe(0);
    expect(s.lastPlay).toBeNull();
    expect(s.bids).toEqual([null, null, null]);
    expect(s.redeals).toBe(0);
    expect(s.players.map((p) => p.seat)).toEqual(["a", "b", "c"]);
  });

  // ---------------------------------------------------------------
  // 额外边界：baseScore 随叫分提升
  // ---------------------------------------------------------------
  it("18. 叫分最高为 3 时 baseScore=3 且该座位为地主", () => {
    let s = createGame(SEATS, () => 0.5);
    s = bid(s, "a", 1);
    s = bid(s, "b", 3);
    s = bid(s, "c", 0);
    expect(s.landlordSeat).toBe("b");
    expect(s.baseScore).toBe(3);
    expect(s.phase).toBe("playing");
  });
});
