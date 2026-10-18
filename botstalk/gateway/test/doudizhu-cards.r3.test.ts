import { describe, it, expect } from "vitest";
import { parseCombo, canBeat, sortCards } from "../src/doudizhu/cards.js";

describe("doudizhu-cards.r3 牌型判定纵深", () => {
  it("连对：3~A 共 12 对 24 张合法 pair_straight，mainRank=14，length=24", () => {
    const cards: number[] = [];
    for (let r = 3; r <= 14; r++) {
      cards.push(r, r);
    }
    const c = parseCombo(cards);
    expect(c.type).toBe("pair_straight");
    expect(c.mainRank).toBe(14);
    expect(c.length).toBe(24);
  });

  it("连对：10,J,Q,K,A 对子共 10 张合法 pair_straight，mainRank=14，length=10", () => {
    const c = parseCombo([10, 10, 11, 11, 12, 12, 13, 13, 14, 14]);
    expect(c.type).toBe("pair_straight");
    expect(c.mainRank).toBe(14);
    expect(c.length).toBe(10);
  });

  it("连对：3344556 共 7 张奇数判 invalid，length=7", () => {
    const c = parseCombo([3, 3, 4, 4, 5, 5, 6]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(7);
  });

  it("连对：33445577 缺 6 非连续判 invalid，length=8", () => {
    const c = parseCombo([3, 3, 4, 4, 5, 5, 7, 7]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(8);
  });

  it("连对：33445522 含对子 2 判 invalid，length=8", () => {
    const c = parseCombo([3, 3, 4, 4, 5, 5, 15, 15]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(8);
  });

  it("飞机带翅：333444+5 共 7 张翅膀 1 张判 invalid，length=7", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 5]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(7);
  });

  it("飞机带翅：333444555+7+8+9 三连飞机带 3 单翅合法 plane_wings，mainRank=5，length=12", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 5, 5, 5, 7, 8, 9]);
    expect(c.type).toBe("plane_wings");
    expect(c.mainRank).toBe(5);
    expect(c.length).toBe(12);
  });

  it("飞机带翅：333444+55+66+77 共 12 张对子翅膀 3 对≠2 判 invalid，length=12", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 7]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(12);
  });

  it("飞机带翅：333444555+66+77+88 三连飞机带 3 对翅合法 plane_wings，mainRank=5，length=15", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 7, 7, 8, 8]);
    expect(c.type).toBe("plane_wings");
    expect(c.mainRank).toBe(5);
    expect(c.length).toBe(15);
  });

  it("飞机带翅：333444+15+5 单张翅膀为 2 合法 plane_wings，mainRank=4，length=8", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 15, 5]);
    expect(c.type).toBe("plane_wings");
    expect(c.mainRank).toBe(4);
    expect(c.length).toBe(8);
  });

  it("飞机带翅：333444+1515+55 对子翅膀为 22 合法 plane_wings，mainRank=4，length=10", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 15, 15, 5, 5]);
    expect(c.type).toBe("plane_wings");
    expect(c.mainRank).toBe(4);
    expect(c.length).toBe(10);
  });

  it("飞机带翅：333555+7+8 飞机本体三张点数不连续判 invalid，length=8", () => {
    const c = parseCombo([3, 3, 3, 5, 5, 5, 7, 8]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(8);
  });

  it("飞机带翅：333444555+7 共 10 张长度 4k/5k 都不满足判 invalid，length=10", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 5, 5, 5, 7]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(10);
  });

  it("四带二：3333+5 共 5 张四带一判 invalid，length=5", () => {
    const c = parseCombo([3, 3, 3, 3, 5]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(5);
  });

  it("四带二：3333+5+5+6+6 共 8 张判 invalid，length=8", () => {
    const c = parseCombo([3, 3, 3, 3, 5, 5, 6, 6]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(8);
  });

  it("四带二：3333+16+17 带两张王合法 four_with_two，mainRank=3，length=6", () => {
    const c = parseCombo([3, 3, 3, 3, 16, 17]);
    expect(c.type).toBe("four_with_two");
    expect(c.mainRank).toBe(3);
    expect(c.length).toBe(6);
  });

  it("四带二：15151515+3+4 四张为 2 合法 four_with_two，mainRank=15，length=6", () => {
    const c = parseCombo([15, 15, 15, 15, 3, 4]);
    expect(c.type).toBe("four_with_two");
    expect(c.mainRank).toBe(15);
    expect(c.length).toBe(6);
  });

  it("顺子：3~A 共 12 张最长顺子合法 straight，mainRank=14，length=12", () => {
    const cards: number[] = [];
    for (let r = 3; r <= 14; r++) cards.push(r);
    const c = parseCombo(cards);
    expect(c.type).toBe("straight");
    expect(c.mainRank).toBe(14);
    expect(c.length).toBe(12);
  });

  it("顺子：3456 共 4 张不足 5 张判 invalid，length=4", () => {
    const c = parseCombo([3, 4, 5, 6]);
    expect(c.type).toBe("invalid");
    expect(c.length).toBe(4);
  });

  it("sortCards：入参不被修改且返回升序新数组", () => {
    const input = [9, 3, 14, 5, 3];
    const snapshot = input.slice();
    const out = sortCards(input);
    expect(input).toEqual(snapshot);
    expect(out).toEqual([3, 3, 5, 9, 14]);
    expect(out).not.toBe(input);
  });

  it("canBeat：炸弹可压同长其他牌型，非炸弹同型同长比 mainRank", () => {
    const bomb3 = parseCombo([3, 3, 3, 3]);
    const bomb4 = parseCombo([4, 4, 4, 4]);
    const pair3 = parseCombo([3, 3]);
    const pair4 = parseCombo([4, 4]);
    const pair4b = parseCombo([4, 4]);
    expect(canBeat(bomb3, pair3)).toBe(true);
    expect(canBeat(bomb4, bomb3)).toBe(true);
    expect(canBeat(bomb3, bomb4)).toBe(false);
    expect(canBeat(pair4, pair3)).toBe(true);
    expect(canBeat(pair4b, pair4)).toBe(false);
  });
});