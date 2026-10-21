import { describe, it, expect } from "vitest";
import { createGame, bid } from "../src/doudizhu/game.js";
import { choosePlay } from "../src/doudizhu/ai.js";
import { parseCombo } from "../src/doudizhu/cards.js";

function playing(): any {
  let s: any = createGame(["a", "b", "c"], () => 0.5);
  s = bid(s, "a", 3);
  s = bid(s, "b", 0);
  s = bid(s, "c", 0);
  return s;
}

function setHand(s: any, cards: number[]): void {
  s.players[0].hand = cards;
  s.lastPlay = null;
  s.currentSeat = "a";
}

function isSubset(play: number[], hand: number[]): boolean {
  const h = [...hand];
  for (const c of play) {
    const i = h.indexOf(c);
    if (i < 0) return false;
    h.splice(i, 1);
  }
  return true;
}

describe("doudizhu-ai-deep", () => {
  it("leadSmallest", () => {
    const s = playing();
    setHand(s, [8, 5, 13, 3]);
    expect(choosePlay(s, "a")).toEqual([3]);
  });

  it("singleCard", () => {
    const s = playing();
    setHand(s, [10]);
    expect(choosePlay(s, "a")).toEqual([10]);
  });

  it("subset1", () => {
    const s = playing();
    setHand(s, [7, 7, 9, 12]);
    const p = choosePlay(s, "a");
    expect(p.length > 0 && isSubset(p, [7, 7, 9, 12])).toBe(true);
  });

  it("subset2", () => {
    const s = playing();
    setHand(s, [5, 5, 8, 9, 11]);
    const p = choosePlay(s, "a");
    expect(isSubset(p, [5, 5, 8, 9, 11])).toBe(true);
  });

  it("respondNoThrow", () => {
    const s = playing();
    setHand(s, [8, 9]);
    s.lastPlay = { seat: "b", combo: { type: "single", cards: [6], mainRank: 6, length: 1 } } as any;
    expect(() => choosePlay(s, "a")).not.toThrow();
    const p = choosePlay(s, "a");
    expect(Array.isArray(p)).toBe(true);
  });

  it("emptyHandNoThrow", () => {
    const s = playing();
    setHand(s, []);
    expect(() => choosePlay(s, "a")).not.toThrow();
  });

  it("deterministic", () => {
    const s = playing();
    setHand(s, [4, 7, 7, 9]);
    const a = choosePlay(s, "a");
    const b = choosePlay(s, "a");
    expect(a).toEqual(b);
  });

  it("twentyRandomHands", () => {
    const s = playing();
    for (let i = 0; i < 20; i++) {
      const hand = [i % 13 + 3, (i * 2) % 13 + 3, (i * 3) % 13 + 3];
      setHand(s, hand);
      const p = choosePlay(s, "a");
      expect(isSubset(p, hand)).toBe(true);
    }
  });

  it("parseComboNoThrow", () => {
    expect(() => parseCombo([3, 3, 3])).not.toThrow();
    expect(() => parseCombo([5])).not.toThrow();
  });

  it("bidFlow", () => {
    let s: any = createGame(["a", "b", "c"], () => 0.5);
    s = bid(s, "a", 3);
    expect(s.players.length).toBe(3);
  });
});