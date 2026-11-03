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

describe("doudizhu-ai-respond.r3 AI 压牌策略", () => {
  it("队友出的牌一律不出（isTeammate 直接返回空数组）", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "c", combo: parseCombo([5]) };
    s.players.find((p) => p.seat === "b")!.hand = [6, 9];
    expect(choosePlay(s, "b")).toEqual([]);
  });

  it("地主出单张 5，农民用最小单张 6 压过", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([5]) };
    s.players.find((p) => p.seat === "a")!.hand = [3, 4, 5, 6, 7];
    s.players.find((p) => p.seat === "b")!.hand = [6, 9];
    s.players.find((p) => p.seat === "c")!.hand = [7, 8];
    expect(choosePlay(s, "b")).toEqual([6]);
  });

  it("无牌可压且对手剩多张则不出", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([10]) };
    s.players.find((p) => p.seat === "b")!.hand = [3, 4];
    s.players.find((p) => p.seat === "a")!.hand = [5, 6, 7];
    expect(choosePlay(s, "b")).toEqual([]);
  });

  it("对手剩 1 张且无非炸弹解时用炸弹拦截", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([10]) };
    s.players.find((p) => p.seat === "a")!.hand = [3];
    s.players.find((p) => p.seat === "b")!.hand = [7, 7, 7, 7, 9];
    s.players.find((p) => p.seat === "c")!.hand = [6, 8];
    expect(choosePlay(s, "b")).toEqual([7, 7, 7, 7]);
  });

  it("只剩一手对子且能压过则全出", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([5, 5]) };
    s.players.find((p) => p.seat === "b")!.hand = [9, 9];
    expect(choosePlay(s, "b")).toEqual([9, 9]);
  });

  it("地主身份有非炸弹解就压（单张 8 压 5）", () => {
    const s = makePlaying();
    s.currentSeat = "a";
    s.lastPlay = { seat: "b", combo: parseCombo([5]) };
    s.players.find((p) => p.seat === "a")!.hand = [8, 3];
    expect(choosePlay(s, "a")).toEqual([8]);
  });

  it("队友剩 1 张时农民优先压过地主", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([7]) };
    s.players.find((p) => p.seat === "a")!.hand = [10, 11, 12];
    s.players.find((p) => p.seat === "b")!.hand = [9, 5];
    s.players.find((p) => p.seat === "c")!.hand = [4];
    expect(choosePlay(s, "b")).toEqual([9]);
  });

  it("有单张大王可压时优先出单张大王而非王炸（findSameTypeCandidates 先命中）", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([12]) };
    s.players.find((p) => p.seat === "a")!.hand = [3];
    s.players.find((p) => p.seat === "b")!.hand = [16, 17, 5];
    s.players.find((p) => p.seat === "c")!.hand = [6, 7];
    expect(choosePlay(s, "b")).toEqual([16]);
  });

  it("农民用对子 8 压过地主对子 6", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([6, 6]) };
    s.players.find((p) => p.seat === "b")!.hand = [8, 8, 3];
    s.players.find((p) => p.seat === "a")!.hand = [7, 9];
    s.players.find((p) => p.seat === "c")!.hand = [4, 5];
    expect(choosePlay(s, "b")).toEqual([8, 8]);
  });

  it("手牌为空时返回空数组", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.players.find((p) => p.seat === "b")!.hand = [];
    s.lastPlay = { seat: "a", combo: parseCombo([5]) };
    expect(choosePlay(s, "b")).toEqual([]);
  });

  it("只剩王炸且能压过单张 K 时打出王炸", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([13]) };
    s.players.find((p) => p.seat === "b")!.hand = [16, 17];
    expect(choosePlay(s, "b")).toEqual([16, 17]);
  });

  it("只剩王炸时即使上家也是王炸仍打出（出炸弹后能出完分支不检查 canBeat）", () => {
    const s = makePlaying();
    s.currentSeat = "b";
    s.lastPlay = { seat: "a", combo: parseCombo([16, 17]) };
    s.players.find((p) => p.seat === "b")!.hand = [16, 17];
    expect(choosePlay(s, "b")).toEqual([16, 17]);
  });
});