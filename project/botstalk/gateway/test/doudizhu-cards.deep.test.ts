// 深测：牌型判定纵深（顺子/连对/飞机带翅边界、炸弹王炸大小）
import { describe, it, expect } from "vitest";
import { parseCombo, canBeat, sortCards } from "../src/doudizhu/cards.js";

describe("深测：牌型判定纵深", () => {
  describe("顺子边界", () => {
    it("[3,4,5,6,7] 是顺子，mainRank 为 7", () => {
      const combo = parseCombo([3, 4, 5, 6, 7]);
      expect(combo.type).toBe("straight");
      expect(combo.mainRank).toBe(7);
      expect(combo.length).toBe(5);
    });

    it("[3..14] 共 12 张是最长顺子，mainRank 为 14", () => {
      const cards = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14];
      const combo = parseCombo(cards);
      expect(combo.type).toBe("straight");
      expect(combo.mainRank).toBe(14);
      expect(combo.length).toBe(12);
    });

    it("[3,4,5,6] 只有 4 张，不足以成顺子 → invalid", () => {
      const combo = parseCombo([3, 4, 5, 6]);
      expect(combo.type).toBe("invalid");
    });

    it("顺子含 2：[10,11,12,13,15] → invalid", () => {
      const combo = parseCombo([10, 11, 12, 13, 15]);
      expect(combo.type).toBe("invalid");
    });

    it("顺子含小王：[11,12,13,14,16] → invalid", () => {
      const combo = parseCombo([11, 12, 13, 14, 16]);
      expect(combo.type).toBe("invalid");
    });
  });

  describe("A2345 口径决策（已确认非法）", () => {
    it("[14,3,4,5,6] → invalid", () => {
      // 依据 2026-10-18 决策：A 不可回绕作 1，主流口径（腾讯欢乐斗地主等）顺子最小 3、最大 A
      const combo = parseCombo([14, 3, 4, 5, 6]);
      expect(combo.type).toBe("invalid");
    });
  });

  describe("连对边界", () => {
    it("[3,3,4,4,5,5] 是连对，mainRank 为 5", () => {
      const combo = parseCombo([3, 3, 4, 4, 5, 5]);
      expect(combo.type).toBe("pair_straight");
      expect(combo.mainRank).toBe(5);
      expect(combo.length).toBe(6);
    });

    it("[3,3,4,4,5] 奇数张 → invalid", () => {
      const combo = parseCombo([3, 3, 4, 4, 5]);
      expect(combo.type).toBe("invalid");
    });

    it("连对含 2：[13,13,14,14,15,15] → invalid（2 不能进连对）", () => {
      const combo = parseCombo([13, 13, 14, 14, 15, 15]);
      expect(combo.type).toBe("invalid");
    });

    it("[3,3,4,4] 只有 2 对 → invalid", () => {
      const combo = parseCombo([3, 3, 4, 4]);
      expect(combo.type).toBe("invalid");
    });
  });

  describe("飞机带翅膀纵深", () => {
    it("[3,3,3,4,4,4,5,6] 飞机带两单，mainRank 为 4", () => {
      const combo = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
      expect(combo.type).toBe("plane_wings");
      expect(combo.mainRank).toBe(4);
    });

    it("[3,3,3,4,4,4,5,5,6,6] 飞机带两对", () => {
      const combo = parseCombo([3, 3, 3, 4, 4, 4, 5, 5, 6, 6]);
      expect(combo.type).toBe("plane_wings");
      expect(combo.mainRank).toBe(4);
    });

    it("翅膀与三张同点：[3,3,3,4,4,4,3,5] → invalid", () => {
      // 4k=8，k=2，remain=[3,5] 含 3 ∈ trioSet → wingOk=false
      const combo = parseCombo([3, 3, 3, 4, 4, 4, 3, 5]);
      expect(combo.type).toBe("invalid");
    });
  });

  describe("四带二", () => {
    it("[5,5,5,5,6,7] → four_with_two，mainRank 为 5", () => {
      const combo = parseCombo([5, 5, 5, 5, 6, 7]);
      expect(combo.type).toBe("four_with_two");
      expect(combo.mainRank).toBe(5);
    });

    it("[5,5,5,5,6,6] 带对子 → four_with_two", () => {
      const combo = parseCombo([5, 5, 5, 5, 6, 6]);
      expect(combo.type).toBe("four_with_two");
      expect(combo.mainRank).toBe(5);
    });

    it("[5,5,5,5,6] 只有 5 张 → invalid", () => {
      const combo = parseCombo([5, 5, 5, 5, 6]);
      expect(combo.type).toBe("invalid");
    });

    it("[5,5,5,5,6,7,8] 7 张 → invalid", () => {
      const combo = parseCombo([5, 5, 5, 5, 6, 7, 8]);
      expect(combo.type).toBe("invalid");
    });
  });

  describe("炸弹 vs 王炸大小", () => {
    it("炸弹 5 压不了王炸", () => {
      const bomb = parseCombo([5, 5, 5, 5]);
      const rocket = parseCombo([16, 17]);
      expect(canBeat(bomb, rocket)).toBe(false);
    });

    it("王炸压炸弹 15", () => {
      const rocket = parseCombo([16, 17]);
      const bomb = parseCombo([15, 15, 15, 15]);
      expect(canBeat(rocket, bomb)).toBe(true);
    });

    it("王炸压不了王炸", () => {
      const rocketA = parseCombo([16, 17]);
      const rocketB = parseCombo([16, 17]);
      expect(canBeat(rocketA, rocketB)).toBe(false);
    });

    it("炸弹 15 压炸弹 5", () => {
      const bombBig = parseCombo([15, 15, 15, 15]);
      const bombSmall = parseCombo([5, 5, 5, 5]);
      expect(canBeat(bombBig, bombSmall)).toBe(true);
    });

    it("炸弹 5 压不了炸弹 15", () => {
      const bombSmall = parseCombo([5, 5, 5, 5]);
      const bombBig = parseCombo([15, 15, 15, 15]);
      expect(canBeat(bombSmall, bombBig)).toBe(false);
    });
  });

  describe("同型不同长不能压", () => {
    it("顺子 5 张压不了顺子 6 张", () => {
      const straight5 = parseCombo([3, 4, 5, 6, 7]);
      const straight6 = parseCombo([3, 4, 5, 6, 7, 8]);
      expect(canBeat(straight5, straight6)).toBe(false);
    });

    it("plane 压不了 plane_wings", () => {
      const plane = parseCombo([3, 3, 3, 4, 4, 4]);
      const planeWings = parseCombo([3, 3, 3, 4, 4, 4, 5, 6]);
      expect(canBeat(plane, planeWings)).toBe(false);
    });
  });

  describe("非法参与 canBeat", () => {
    it("a 为 invalid → false", () => {
      const invalid = parseCombo([2]);
      const pair = parseCombo([3, 3]);
      expect(canBeat(invalid, pair)).toBe(false);
    });

    it("b 为 invalid → false", () => {
      const pair = parseCombo([3, 3]);
      const invalid = parseCombo([2]);
      expect(canBeat(pair, invalid)).toBe(false);
    });
  });

  describe("三带一 mainRank 取三张点数", () => {
    it("[7,7,7,3] mainRank 为 7", () => {
      const combo = parseCombo([7, 7, 7, 3]);
      expect(combo.type).toBe("trio_single");
      expect(combo.mainRank).toBe(7);
    });

    it("[3,7,7,7] mainRank 为 7", () => {
      const combo = parseCombo([3, 7, 7, 7]);
      expect(combo.type).toBe("trio_single");
      expect(combo.mainRank).toBe(7);
    });
  });

  describe("sortCards 不修改入参", () => {
    it("[5,3,4] 返回 [3,4,5] 且原数组不变", () => {
      const input = [5, 3, 4];
      const sorted = sortCards(input);
      expect(sorted).toEqual([3, 4, 5]);
      expect(input).toEqual([5, 3, 4]);
    });
  });

  describe("非法点数", () => {
    it("parseCombo([2]) → invalid", () => {
      const combo = parseCombo([2]);
      expect(combo.type).toBe("invalid");
    });

    it("parseCombo([18]) → invalid", () => {
      const combo = parseCombo([18]);
      expect(combo.type).toBe("invalid");
    });

    it("parseCombo([3,3,3,3,3]) 5 张同点 → invalid", () => {
      // 炸弹只认 4 张
      const combo = parseCombo([3, 3, 3, 3, 3]);
      expect(combo.type).toBe("invalid");
    });
  });
});
