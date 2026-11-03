import { describe, it, expect } from "vitest";
import { createGame, bid } from "../src/doudizhu/game.js";

const seats: [string, string, string] = ["a", "b", "c"];
const rng = () => 0.5;

describe("doudizhu-game.r3 叫分状态机纵深", () => {
  it("叫 3 分直接当地主：phase playing、landlordSeat=a、baseScore=3、currentSeat=a、地主 20 张手牌", () => {
    let s = createGame(seats, rng);
    s = bid(s, "a", 3);
    s = bid(s, "b", 0);
    s = bid(s, "c", 0);
    expect(s.phase).toBe("playing");
    expect(s.landlordSeat).toBe("a");
    expect(s.baseScore).toBe(3);
    expect(s.currentSeat).toBe("a");
    const landlord = s.players.find((p) => p.seat === "a")!;
    expect(landlord.hand.length).toBe(20);
    expect(landlord.isLandlord).toBe(true);
  });

  it("叫分递增最高者当地主：a 叫 1、b 叫 2、c 叫 0 → landlordSeat=b、baseScore=2", () => {
    let s = createGame(seats, rng);
    s = bid(s, "a", 1);
    s = bid(s, "b", 2);
    s = bid(s, "c", 0);
    expect(s.landlordSeat).toBe("b");
    expect(s.baseScore).toBe(2);
    expect(s.phase).toBe("playing");
    expect(s.players.find((p) => p.seat === "b")!.isLandlord).toBe(true);
  });

  it("并列最高分取先叫者：a 叫 2、b 叫 2、c 叫 1 → landlordSeat=a", () => {
    let s = createGame(seats, rng);
    s = bid(s, "a", 2);
    s = bid(s, "b", 2);
    s = bid(s, "c", 1);
    expect(s.landlordSeat).toBe("a");
    expect(s.baseScore).toBe(2);
    expect(s.players.find((p) => p.seat === "a")!.isLandlord).toBe(true);
    expect(s.players.find((p) => p.seat === "b")!.isLandlord).toBe(false);
  });

  it("叫分后 currentSeat 轮转：初始 a，a 叫 1 后 b，b 叫 0 后 c", () => {
    let s = createGame(seats, rng);
    expect(s.currentSeat).toBe("a");
    s = bid(s, "a", 1);
    expect(s.currentSeat).toBe("b");
    s = bid(s, "b", 0);
    expect(s.currentSeat).toBe("c");
  });

  it("非轮次叫分抛错：轮到 a 时 b 叫分 → 抛错含「还没轮到你叫分」", () => {
    const s = createGame(seats, rng);
    expect(() => bid(s, "b", 1)).toThrowError(/还没轮到你叫分/);
  });

  it("非叫分阶段再叫分抛错：进入 playing 后再 bid → 抛错含「当前不在叫分阶段」", () => {
    let s = createGame(seats, rng);
    s = bid(s, "a", 3);
    s = bid(s, "b", 0);
    s = bid(s, "c", 0);
    expect(s.phase).toBe("playing");
    expect(() => bid(s, "a", 1)).toThrowError(/当前不在叫分阶段/);
  });

  it("非法分数抛错：bid(state, \"a\", 5 as any) → 抛错含「叫分不合法」", () => {
    const s = createGame(seats, rng);
    expect(() => bid(s, "a", 5 as any)).toThrowError(/叫分不合法/);
  });

  it("三人全不叫触发重发：redeals=1、phase=bidding、bids 重置、bidTurn=0、currentSeat=a", () => {
    let s = createGame(seats, rng);
    s = bid(s, "a", 0);
    s = bid(s, "b", 0);
    s = bid(s, "c", 0);
    expect(s.redeals).toBe(1);
    expect(s.phase).toBe("bidding");
    expect(s.bids).toEqual([null, null, null]);
    expect(s.bidTurn).toBe(0);
    expect(s.currentSeat).toBe("a");
    expect(s.landlordSeat).toBeUndefined();
  });

  it("连续 4 次全不叫后随机定地主：redeals=4、phase=playing、landlordSeat=a、baseScore=1", () => {
    let s = createGame(seats, () => 0);
    for (let round = 0; round < 4; round++) {
      expect(s.phase).toBe("bidding");
      expect(s.currentSeat).toBe("a");
      s = bid(s, "a", 0);
      expect(s.currentSeat).toBe("b");
      s = bid(s, "b", 0);
      expect(s.currentSeat).toBe("c");
      s = bid(s, "c", 0);
    }
    expect(s.redeals).toBe(4);
    expect(s.phase).toBe("playing");
    expect(s.landlordSeat).toBe("a");
    expect(s.baseScore).toBe(1);
    expect(s.players.find((p) => p.seat === "a")!.hand.length).toBe(20);
  });

  it("重发后手牌重新洗牌：a 的手牌与第一轮不同（递增 rng 序列）", () => {
    let n = 0;
    const seqRng = () => {
      n += 0.1;
      return n % 1;
    };
    let s = createGame(seats, seqRng);
    const firstHandA = s.players.find((p) => p.seat === "a")!.hand.slice();
    s = bid(s, "a", 0);
    s = bid(s, "b", 0);
    s = bid(s, "c", 0);
    expect(s.redeals).toBe(1);
    const secondHandA = s.players.find((p) => p.seat === "a")!.hand;
    expect(secondHandA.length).toBe(17);
    expect(secondHandA).not.toEqual(firstHandA);
  });

  it("底牌并入地主手牌且排序：a 当地主后手牌升序", () => {
    let s = createGame(seats, rng);
    s = bid(s, "a", 3);
    s = bid(s, "b", 0);
    s = bid(s, "c", 0);
    const hand = s.players.find((p) => p.seat === "a")!.hand;
    expect(hand.length).toBe(20);
    for (let i = 0; i + 1 < hand.length; i++) {
      expect(hand[i] <= hand[i + 1]).toBe(true);
    }
  });

  it("bids 记录正确：a 叫 1 后 bids 为 [1,null,null]", () => {
    let s = createGame(seats, rng);
    s = bid(s, "a", 1);
    expect(s.bids).toEqual([1, null, null]);
    expect(s.bidTurn).toBe(1);
  });

  it("叫分结束 lastPlay 为 null：a3/b0/c0 后 lastPlay===null", () => {
    let s = createGame(seats, rng);
    s = bid(s, "a", 3);
    s = bid(s, "b", 0);
    s = bid(s, "c", 0);
    expect(s.phase).toBe("playing");
    expect(s.lastPlay).toBeNull();
  });
});