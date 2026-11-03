import { describe, it, expect } from "vitest";
import { createGame, bid } from "../src/doudizhu/game.js";
import type { GameState } from "../src/doudizhu/game.js";
import { choosePlay } from "../src/doudizhu/ai.js";
import { parseCombo } from "../src/doudizhu/cards.js";

function makePlaying(): GameState {
  let s = createGame(["a", "b", "c"], () => 0.5);
  s = bid(s, "a", 3);
  s = bid(s, "b", 0);
  s = bid(s, "c", 0);
  return s;
}

describe("doudizhu-ai-lead.r3 AI 自由领出", () => {
  it("手牌多张时领出最小单张：hand=[8,5,13,3] 应出 [3]", () => {
    const s = makePlaying();
    s.players[0].hand = [8, 5, 13, 3];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([3]);
  });

  it("只剩一张时直接出：hand=[10] 应出 [10]", () => {
    const s = makePlaying();
    s.players[0].hand = [10];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([10]);
  });

  it("手牌只有王炸时出王炸：hand=[16,17] 应出 [16,17]", () => {
    const s = makePlaying();
    s.players[0].hand = [16, 17];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([16, 17]);
  });

  it("手牌只有炸弹时全出：hand=[9,9,9,9] 应出 [9,9,9,9]", () => {
    const s = makePlaying();
    s.players[0].hand = [9, 9, 9, 9];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([9, 9, 9, 9]);
  });

  it("手牌 [16,17,5] 时不出王炸而出最小单张：应出 [5]", () => {
    const s = makePlaying();
    s.players[0].hand = [16, 17, 5];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([5]);
  });

  it("手牌 4 张但不是炸弹时出最小单张：hand=[7,7,8,3] 应出 [3]", () => {
    const s = makePlaying();
    s.players[0].hand = [7, 7, 8, 3];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([3]);
  });

  it("lastPlay.seat===自己时视为自由领出：hand=[9,4] 应出 [4]", () => {
    const s = makePlaying();
    s.players[0].hand = [9, 4];
    s.lastPlay = { seat: "a", combo: parseCombo([5]) };
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([4]);
  });

  it("非 playing 阶段抛错：未 bid 状态调 choosePlay 应抛出含指定消息的错误", () => {
    const s = createGame(["a", "b", "c"], () => 0.5);
    expect(() => choosePlay(s, "a")).toThrowError("AI 只能在轮到自己出牌时决策");
  });

  it("currentSeat 不是自己时抛错：currentSeat=a 调 choosePlay(s,'b') 应抛错", () => {
    const s = makePlaying();
    s.players[0].hand = [5];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(() => choosePlay(s, "b")).toThrowError("AI 只能在轮到自己出牌时决策");
  });

  it("领出最小单张会拆对子：hand=[6,6,9] 应出 [6]", () => {
    const s = makePlaying();
    s.players[0].hand = [6, 6, 9];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([6]);
  });

  it("手牌含大小王散牌领出最小：hand=[17,16,8,4] 应出 [4]", () => {
    const s = makePlaying();
    s.players[0].hand = [17, 16, 8, 4];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([4]);
  });

  it("领出返回数组升序：hand=[12,5,9] 应出 [5]", () => {
    const s = makePlaying();
    s.players[0].hand = [12, 5, 9];
    s.lastPlay = null;
    s.currentSeat = "a";
    expect(choosePlay(s, "a")).toEqual([5]);
  });
});