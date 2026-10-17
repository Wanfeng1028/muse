import { describe, it, expect } from "vitest";
import { parseCombo, canBeat, sortCards } from "../src/doudizhu/cards.js";
import type { Combo } from "../src/doudizhu/cards.js";

describe("sortCards", () => {
  it("升序排列乱序数组", () => {
    expect(sortCards([5, 3, 9, 4])).toEqual([3, 4, 5, 9]);
  });

  it("已排序数组保持不变", () => {
    expect(sortCards([3, 4, 5, 6])).toEqual([3, 4, 5, 6]);
  });

  it("不修改原数组", () => {
    const input = [7, 3, 5];
    const copy = input.slice();
    sortCards(input);
    expect(input).toEqual(copy);
  });

  it("空数组返回空数组", () => {
    expect(sortCards([])).toEqual([]);
  });

  it("包含重复点数仍升序", () => {
    expect(sortCards([9, 3, 9, 3, 5])).toEqual([3, 3, 5, 9, 9]);
  });
});

describe("parseCombo-基本牌型", () => {
  it("单张 5 判 single", () => {
    const c = parseCombo([5]);
    expect(c.type).toBe("single");
    expect(c.mainRank).toBe(5);
    expect(c.length).toBe(1);
  });

  it("单张大王 17 判 single", () => {
    const c = parseCombo([17]);
    expect(c.type).toBe("single");
    expect(c.mainRank).toBe(17);
  });

  it("对子 88 判 pair", () => {
    const c = parseCombo([8, 8]);
    expect(c.type).toBe("pair");
    expect(c.mainRank).toBe(8);
    expect(c.length).toBe(2);
  });

  it("对子 AA 判 pair", () => {
    const c = parseCombo([14, 14]);
    expect(c.type).toBe("pair");
    expect(c.mainRank).toBe(14);
  });

  it("对子 22(15) 判 pair", () => {
    const c = parseCombo([15, 15]);
    expect(c.type).toBe("pair");
    expect(c.mainRank).toBe(15);
  });

  it("[17,17] 判 pair", () => {
    const c = parseCombo([17, 17]);
    expect(c.type).toBe("pair");
    expect(c.mainRank).toBe(17);
  });

  it("三张 999 判 trio", () => {
    const c = parseCombo([9, 9, 9]);
    expect(c.type).toBe("trio");
    expect(c.mainRank).toBe(9);
    expect(c.length).toBe(3);
  });

  it("三张 KKK 判 trio", () => {
    const c = parseCombo([13, 13, 13]);
    expect(c.type).toBe("trio");
    expect(c.mainRank).toBe(13);
  });

  it("三带一 333+4 判 trio_single", () => {
    const c = parseCombo([3, 3, 3, 4]);
    expect(c.type).toBe("trio_single");
    expect(c.mainRank).toBe(3);
    expect(c.length).toBe(4);
  });

  it("三带一 777+9 判 trio_single", () => {
    const c = parseCombo([7, 7, 7, 9]);
    expect(c.type).toBe("trio_single");
    expect(c.mainRank).toBe(7);
  });

  it("三带对 333+44 判 trio_pair", () => {
    const c = parseCombo([3, 3, 3, 4, 4]);
    expect(c.type).toBe("trio_pair");
    expect(c.mainRank).toBe(3);
    expect(c.length).toBe(5);
  });

  it("三带对 555+KK 判 trio_pair", () => {
    const c = parseCombo([5, 5, 5, 13, 13]);
    expect(c.type).toBe("trio_pair");
    expect(c.mainRank).toBe(5);
  });

  it("cards 字段为排序后的数组", () => {
    const c = parseCombo([4, 3, 3, 3]);
    expect(c.cards).toEqual([3, 3, 3, 4]);
  });
});

describe("parseCombo-顺子连对飞机", () => {
  it("顺子 34567 合法 mainRank=7", () => {
    const c = parseCombo([3, 4, 5, 6, 7]);
    expect(c.type).toBe("straight");
    expect(c.mainRank).toBe(7);
    expect(c.length).toBe(5);
  });

  it("顺子 45678 合法 mainRank=8", () => {
    const c = parseCombo([4, 5, 6, 7, 8]);
    expect(c.type).toBe("straight");
    expect(c.mainRank).toBe(8);
  });

  it("连对 334455 合法 mainRank=5", () => {
    const c = parseCombo([3, 3, 4, 4, 5, 5]);
    expect(c.type).toBe("pair_straight");
    expect(c.mainRank).toBe(5);
    expect(c.length).toBe(6);
  });

  it("连对 445566 合法 mainRank=6", () => {
    const c = parseCombo([4, 4, 5, 5, 6, 6]);
    expect(c.type).toBe("pair_straight");
    expect(c.mainRank).toBe(6);
  });

  it("连对 2 对 3344 判 invalid", () => {
    expect(parseCombo([3, 3, 4, 4]).type).toBe("invalid");
  });

  it("飞机 333444 合法 mainRank=4", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4]);
    expect(c.type).toBe("plane");
    expect(c.mainRank).toBe(4);
    expect(c.length).toBe(6);
  });

  it("飞机 555666 合法 mainRank=6", () => {
    const c = parseCombo([5, 5, 5, 6, 6, 6]);
    expect(c.type).toBe("plane");
    expect(c.mainRank).toBe(6);
  });

  it("飞机带单张翅膀 333444+5+6 共 8 张合法", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
    expect(c.type).toBe("plane_wings");
    expect(c.mainRank).toBe(4);
    expect(c.length).toBe(8);
  });

  it("飞机带对子翅膀 333444+55+66 共 10 张合法", () => {
    const c = parseCombo([3, 3, 3, 4, 4, 4, 5, 5, 6, 6]);
    expect(c.type).toBe("plane_wings");
    expect(c.mainRank).toBe(4);
    expect(c.length).toBe(10);
  });

  it("翅膀与三张同点数 333444+3+5 判 invalid", () => {
    expect(parseCombo([3, 3, 3, 4, 4, 4, 3, 5]).type).toBe("invalid");
  });
});

describe("parseCombo-炸弹王炸", () => {
  it("炸弹 3333 判 bomb mainRank=3", () => {
    const c = parseCombo([3, 3, 3, 3]);
    expect(c.type).toBe("bomb");
    expect(c.mainRank).toBe(3);
    expect(c.length).toBe(4);
  });

  it("炸弹 8888 判 bomb mainRank=8", () => {
    const c = parseCombo([8, 8, 8, 8]);
    expect(c.type).toBe("bomb");
    expect(c.mainRank).toBe(8);
  });

  it("王炸 [16,17] 判 rocket", () => {
    const c = parseCombo([16, 17]);
    expect(c.type).toBe("rocket");
    expect(c.mainRank).toBe(17);
    expect(c.length).toBe(2);
  });

  it("王炸 [17,16] 乱序输入判 rocket", () => {
    const c = parseCombo([17, 16]);
    expect(c.type).toBe("rocket");
  });

  it("四带二 3333+5+6 合法 mainRank=3", () => {
    const c = parseCombo([3, 3, 3, 3, 5, 6]);
    expect(c.type).toBe("four_with_two");
    expect(c.mainRank).toBe(3);
    expect(c.length).toBe(6);
  });

  it("四带二 8888+3+3 对子作翅膀合法", () => {
    const c = parseCombo([8, 8, 8, 8, 3, 3]);
    expect(c.type).toBe("four_with_two");
    expect(c.mainRank).toBe(8);
  });
});

describe("parseCombo-非法", () => {
  it("空数组判 invalid", () => {
    expect(parseCombo([]).type).toBe("invalid");
  });

  it("顺子含 2(15) 34562 判 invalid", () => {
    expect(parseCombo([3, 4, 5, 6, 15]).type).toBe("invalid");
  });

  it("顺子 34567A2 共 7 张含 15 判 invalid", () => {
    expect(parseCombo([3, 4, 5, 6, 7, 14, 15]).type).toBe("invalid");
  });

  it("顺子含小王 3456+16 判 invalid", () => {
    expect(parseCombo([3, 4, 5, 6, 16]).type).toBe("invalid");
  });

  it("顺子含大王 3456+17 判 invalid", () => {
    expect(parseCombo([3, 4, 5, 6, 17]).type).toBe("invalid");
  });

  it("连对含 2 对 A A 22 判 invalid", () => {
    expect(parseCombo([14, 14, 15, 15]).type).toBe("invalid");
  });

  it("飞机含 2 三张 AAA222 判 invalid", () => {
    expect(parseCombo([14, 14, 14, 15, 15, 15]).type).toBe("invalid");
  });

  it("含 1 的点数判 invalid", () => {
    expect(parseCombo([1]).type).toBe("invalid");
  });

  it("含 18 的点数判 invalid", () => {
    expect(parseCombo([18]).type).toBe("invalid");
  });

  it("五张相同点数 33333 判 invalid", () => {
    expect(parseCombo([3, 3, 3, 3, 3]).type).toBe("invalid");
  });

  it("不连续三张 333555 判 invalid", () => {
    expect(parseCombo([3, 3, 3, 5, 5, 5]).type).toBe("invalid");
  });

  it("invalid 的 cards 为排序后数组", () => {
    const c = parseCombo([5, 1, 9]);
    expect(c.type).toBe("invalid");
    expect(c.cards).toEqual([1, 5, 9]);
  });
});

describe("canBeat", () => {
  it("炸弹压三带二 true", () => {
    const bomb = parseCombo([3, 3, 3, 3]);
    const trioPair = parseCombo([5, 5, 5, 6, 6]);
    expect(canBeat(bomb, trioPair)).toBe(true);
  });

  it("炸弹被王炸压 true", () => {
    const bomb = parseCombo([14, 14, 14, 14]);
    const rocket = parseCombo([16, 17]);
    expect(canBeat(rocket, bomb)).toBe(true);
  });

  it("小炸弹压不过大炸弹 false", () => {
    const small = parseCombo([3, 3, 3, 3]);
    const big = parseCombo([8, 8, 8, 8]);
    expect(canBeat(small, big)).toBe(false);
  });

  it("大炸弹压小炸弹 true", () => {
    const big = parseCombo([8, 8, 8, 8]);
    const small = parseCombo([3, 3, 3, 3]);
    expect(canBeat(big, small)).toBe(true);
  });

  it("四带二不能压顺子 false", () => {
    const fourWithTwo = parseCombo([3, 3, 3, 3, 5, 6]);
    const straight = parseCombo([4, 5, 6, 7, 8]);
    expect(canBeat(fourWithTwo, straight)).toBe(false);
  });

  it("顺子 34567 压不过 45678 false", () => {
    const a = parseCombo([3, 4, 5, 6, 7]);
    const b = parseCombo([4, 5, 6, 7, 8]);
    expect(canBeat(a, b)).toBe(false);
  });

  it("顺子 45678 压 34567 true", () => {
    const a = parseCombo([4, 5, 6, 7, 8]);
    const b = parseCombo([3, 4, 5, 6, 7]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("不同长度顺子互不压 5 张 vs 6 张 false", () => {
    const a = parseCombo([4, 5, 6, 7, 8]);
    const b = parseCombo([3, 4, 5, 6, 7, 8]);
    expect(canBeat(a, b)).toBe(false);
  });

  it("不同牌型互不压 三带一 vs 三带二 false", () => {
    const a = parseCombo([3, 3, 3, 4]);
    const b = parseCombo([5, 5, 5, 6, 6]);
    expect(canBeat(a, b)).toBe(false);
  });

  it("对子不能压单张 false", () => {
    const pair = parseCombo([5, 5]);
    const single = parseCombo([9]);
    expect(canBeat(pair, single)).toBe(false);
  });

  it("单张压单张比 mainRank true", () => {
    const a = parseCombo([9]);
    const b = parseCombo([5]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("三带二压三带二比 mainRank true", () => {
    const a = parseCombo([7, 7, 7, 8, 8]);
    const b = parseCombo([3, 3, 3, 4, 4]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("a 为 invalid 时压什么都 false", () => {
    const a = parseCombo([1]);
    const b = parseCombo([5]);
    expect(canBeat(a, b)).toBe(false);
  });

  it("b 为 invalid 时什么都压不了 false", () => {
    const a = parseCombo([5]);
    const b = parseCombo([1]);
    expect(canBeat(a, b)).toBe(false);
  });

  it("双方都 invalid 时 false", () => {
    const a = parseCombo([1]);
    const b = parseCombo([2]);
    expect(canBeat(a, b)).toBe(false);
  });

  it("炸弹不能压王炸 false", () => {
    const bomb = parseCombo([17, 17, 17, 17]);
    const rocket = parseCombo([16, 17]);
    expect(canBeat(bomb, rocket)).toBe(false);
  });

  it("王炸不能压王炸 false", () => {
    const r1 = parseCombo([16, 17]);
    const r2 = parseCombo([17, 16]);
    expect(canBeat(r1, r2)).toBe(false);
  });

  it("连对压连对比 mainRank true", () => {
    const a = parseCombo([5, 5, 6, 6, 7, 7]);
    const b = parseCombo([3, 3, 4, 4, 5, 5]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("飞机压飞机比 mainRank true", () => {
    const a = parseCombo([5, 5, 5, 6, 6, 6]);
    const b = parseCombo([3, 3, 3, 4, 4, 4]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("飞机带翅膀压同结构飞机带翅膀 true", () => {
    const a = parseCombo([5, 5, 5, 6, 6, 6, 7, 8]);
    const b = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("四带二压四带二比 mainRank true", () => {
    const a = parseCombo([8, 8, 8, 8, 3, 4]);
    const b = parseCombo([3, 3, 3, 3, 5, 6]);
    expect(canBeat(a, b)).toBe(true);
  });
});