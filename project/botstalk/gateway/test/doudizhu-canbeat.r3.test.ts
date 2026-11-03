import { describe, it, expect } from "vitest";
import { parseCombo, canBeat } from "../src/doudizhu/cards.js";

describe("doudizhu-canbeat.r3 压牌纵深", () => {
  it("飞机带单翅 333444+5+6 压不过 444555+7+8", () => {
    const a = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
    const b = parseCombo([4, 4, 4, 5, 5, 5, 7, 8]);
    expect(a.type).toBe("plane_wings");
    expect(b.type).toBe("plane_wings");
    expect(a.length).toBe(8);
    expect(b.length).toBe(8);
    expect(canBeat(a, b)).toBe(false);
  });

  it("飞机带单翅 444555+7+8 压 333444+5+6", () => {
    const a = parseCombo([4, 4, 4, 5, 5, 5, 7, 8]);
    const b = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("飞机带对翅 333444+55+66 压不过 444555+77+88", () => {
    const a = parseCombo([3, 3, 3, 4, 4, 4, 5, 5, 6, 6]);
    const b = parseCombo([4, 4, 4, 5, 5, 5, 7, 7, 8, 8]);
    expect(a.type).toBe("plane_wings");
    expect(b.type).toBe("plane_wings");
    expect(a.length).toBe(10);
    expect(b.length).toBe(10);
    expect(canBeat(a, b)).toBe(false);
  });

  it("飞机带对翅 444555+77+88 压 333444+55+66", () => {
    const a = parseCombo([4, 4, 4, 5, 5, 5, 7, 7, 8, 8]);
    const b = parseCombo([3, 3, 3, 4, 4, 4, 5, 5, 6, 6]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("8 张飞机带单翅与 10 张飞机带对翅长度不同互不压", () => {
    const a = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
    const b = parseCombo([4, 4, 4, 5, 5, 5, 7, 7, 8, 8]);
    expect(a.type).toBe("plane_wings");
    expect(b.type).toBe("plane_wings");
    expect(a.length).not.toBe(b.length);
    expect(canBeat(a, b)).toBe(false);
  });

  it("四带二 3333+5+6 压不过 4444+7+8", () => {
    const a = parseCombo([3, 3, 3, 3, 5, 6]);
    const b = parseCombo([4, 4, 4, 4, 7, 8]);
    expect(a.type).toBe("four_with_two");
    expect(b.type).toBe("four_with_two");
    expect(canBeat(a, b)).toBe(false);
  });

  it("四带二 4444+7+8 压 3333+5+6", () => {
    const a = parseCombo([4, 4, 4, 4, 7, 8]);
    const b = parseCombo([3, 3, 3, 3, 5, 6]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("炸弹压飞机带翅", () => {
    const a = parseCombo([5, 5, 5, 5]);
    const b = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
    expect(a.type).toBe("bomb");
    expect(b.type).toBe("plane_wings");
    expect(canBeat(a, b)).toBe(true);
  });

  it("炸弹压连对", () => {
    const a = parseCombo([6, 6, 6, 6]);
    const b = parseCombo([3, 3, 4, 4, 5, 5]);
    expect(a.type).toBe("bomb");
    expect(b.type).toBe("pair_straight");
    expect(canBeat(a, b)).toBe(true);
  });

  it("王炸压四带二", () => {
    const a = parseCombo([16, 17]);
    const b = parseCombo([3, 3, 3, 3, 5, 6]);
    expect(a.type).toBe("rocket");
    expect(b.type).toBe("four_with_two");
    expect(canBeat(a, b)).toBe(true);
  });

  it("王炸对王炸不能压", () => {
    const a = parseCombo([16, 17]);
    const b = parseCombo([16, 17]);
    expect(a.type).toBe("rocket");
    expect(b.type).toBe("rocket");
    expect(canBeat(a, b)).toBe(false);
  });

  it("炸弹压单张大王", () => {
    const a = parseCombo([7, 7, 7, 7]);
    const b = parseCombo([17]);
    expect(a.type).toBe("bomb");
    expect(b.type).toBe("single");
    expect(canBeat(a, b)).toBe(true);
  });

  it("单张小王压不过单张大王", () => {
    const a = parseCombo([16]);
    const b = parseCombo([17]);
    expect(a.type).toBe("single");
    expect(b.type).toBe("single");
    expect(canBeat(a, b)).toBe(false);
  });

  it("连对 33445566 压不过 7788991010", () => {
    const a = parseCombo([3, 3, 4, 4, 5, 5, 6, 6]);
    const b = parseCombo([7, 7, 8, 8, 9, 9, 10, 10]);
    expect(a.type).toBe("pair_straight");
    expect(b.type).toBe("pair_straight");
    expect(a.length).toBe(8);
    expect(b.length).toBe(8);
    expect(canBeat(a, b)).toBe(false);
  });

  it("连对 7788991010 压 33445566", () => {
    const a = parseCombo([7, 7, 8, 8, 9, 9, 10, 10]);
    const b = parseCombo([3, 3, 4, 4, 5, 5, 6, 6]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("飞机不带翅 333444 压不过 444555", () => {
    const a = parseCombo([3, 3, 3, 4, 4, 4]);
    const b = parseCombo([4, 4, 4, 5, 5, 5]);
    expect(a.type).toBe("plane");
    expect(b.type).toBe("plane");
    expect(a.length).toBe(6);
    expect(b.length).toBe(6);
    expect(canBeat(a, b)).toBe(false);
  });

  it("飞机不带翅 444555 压 333444", () => {
    const a = parseCombo([4, 4, 4, 5, 5, 5]);
    const b = parseCombo([3, 3, 3, 4, 4, 4]);
    expect(canBeat(a, b)).toBe(true);
  });

  it("三带一 444+5 压 333+4", () => {
    const a = parseCombo([4, 4, 4, 5]);
    const b = parseCombo([3, 3, 3, 4]);
    expect(a.type).toBe("trio_single");
    expect(b.type).toBe("trio_single");
    expect(a.length).toBe(4);
    expect(b.length).toBe(4);
    expect(canBeat(a, b)).toBe(true);
  });

  it("三带一 333+4 压不过 444+5", () => {
    const a = parseCombo([3, 3, 3, 4]);
    const b = parseCombo([4, 4, 4, 5]);
    expect(canBeat(a, b)).toBe(false);
  });

  it("对子 AA 压对子 KK", () => {
    const a = parseCombo([14, 14]);
    const b = parseCombo([13, 13]);
    expect(a.type).toBe("pair");
    expect(b.type).toBe("pair");
    expect(a.length).toBe(2);
    expect(b.length).toBe(2);
    expect(canBeat(a, b)).toBe(true);
  });

  it("飞机带翅压不过顺子", () => {
    const a = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
    const b = parseCombo([3, 4, 5, 6, 7]);
    expect(a.type).toBe("plane_wings");
    expect(b.type).toBe("straight");
    expect(canBeat(a, b)).toBe(false);
  });

  it("炸弹压不过王炸", () => {
    const a = parseCombo([5, 5, 5, 5]);
    const b = parseCombo([16, 17]);
    expect(a.type).toBe("bomb");
    expect(b.type).toBe("rocket");
    expect(canBeat(a, b)).toBe(false);
  });

  it("王炸压炸弹", () => {
    const a = parseCombo([16, 17]);
    const b = parseCombo([5, 5, 5, 5]);
    expect(a.type).toBe("rocket");
    expect(b.type).toBe("bomb");
    expect(canBeat(a, b)).toBe(true);
  });
});