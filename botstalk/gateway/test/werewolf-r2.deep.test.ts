import { describe, it, expect } from "vitest";
import { createGame, nightAction, dayAction, WerewolfError, serializeForSeat } from "../src/werewolf/game.js";
import { chooseNightAction, chooseDayAction } from "../src/werewolf/ai.js";

type GameState = ReturnType<typeof createGame>;

const rng0 = () => 0;
function mk(n: number): GameState {
  return createGame(Array.from({ length: n }, (_, i) => "s" + (i + 1)), {}, rng0);
}
function seatOf(s: GameState, role: string): string {
  const p = s.players.find((x) => x.role === role)!;
  return p.seat;
}
function codeOf(fn: () => unknown): string {
  try {
    fn();
    return "NO_THROW";
  } catch (e) {
    return (e as WerewolfError).code;
  }
}

describe("werewolf-r2", () => {
  it("wolfSeesTeammates", () => {
    const s = mk(6);
    const wolf = seatOf(s, "werewolf");
    const view = serializeForSeat(s, wolf) as any;
    const wolfCount = s.players.filter((p) => p.role === "werewolf").length;
    expect(view.wolfSeats.length).toBe(wolfCount);
    view.wolfSeats.forEach((seat: string) => {
      const entry = view.players.find((p: any) => p.seat === seat);
      expect(entry.role).toBe("werewolf");
    });
  });

  it("villagerSeesOnlySelf", () => {
    const s = mk(6);
    const villager = seatOf(s, "villager");
    const view = serializeForSeat(s, villager) as any;
    const own = view.players.find((p: any) => p.seat === villager);
    expect(own.role).toBe("villager");
    view.players
      .filter((p: any) => p.seat !== villager)
      .forEach((p: any) => expect(p.role).toBeUndefined());
    expect("wolfSeats" in view).toBe(false);
  });

  it("aiNightNoThrow", () => {
    const s = mk(6);
    const wolf = seatOf(s, "werewolf");
    expect(() => chooseNightAction(s, wolf)).not.toThrow();
    const result = chooseNightAction(s, wolf);
    expect(result).toBeTruthy();
  });

  it("aiDayNoThrow", () => {
    const s = mk(6);
    const seat = s.players.find((p) => p.alive)!.seat;
    expect(() => chooseDayAction(s, seat)).not.toThrow();
  });

  it("wrongSeatThrows", () => {
    const s = mk(6);
    expect(
      codeOf(() => nightAction(s, "nonexistent", { kind: "night", target: null }))
    ).not.toBe("NO_THROW");
  });

  it("wolfKillsMateThrows", () => {
    let s = mk(10);
    const guard = seatOf(s, "guard");
    s = nightAction(s, guard, { kind: "night", target: null });
    const wolf = s.currentSeat;
    const mate = s.players.find((p) => p.role === "werewolf" && p.seat !== wolf)!.seat;
    expect(
      codeOf(() => nightAction(s, wolf, { kind: "night", target: mate }))
    ).toBe("ILLEGAL_TARGET");
  });

  it("deterministic", () => {
    const a = mk(9);
    const b = mk(9);
    expect(
      a.players.map((p) => ({ seat: p.seat, role: p.role }))
    ).toEqual(
      b.players.map((p) => ({ seat: p.seat, role: p.role }))
    );
  });

  it("twelvePlayers", () => {
    expect(mk(12).players.length).toBe(12);
  });

  it("fullFirstNight", () => {
    let s = mk(6);
    let iter = 0;
    while (s.phase === "night" && iter < 20) {
      const actor = s.currentSeat;
      s = nightAction(s, actor, { kind: "night", target: null });
      iter++;
    }
    expect(iter).toBeLessThan(20);
  });

  it("dayVoteFlow", () => {
    let s = mk(6);
    let iter = 0;
    while (s.phase === "night" && iter < 20) {
      const actor = s.currentSeat;
      s = nightAction(s, actor, { kind: "night", target: null });
      iter++;
    }
    // 白天先走完发言轮，再投票。
    let di = 0;
    while (di < 30) {
      try {
        s = dayAction(s, s.currentSeat, { kind: "vote", target: null });
        break;
      } catch (e) {
        if ((e as WerewolfError).code === "NEED_SPEAK_DONE" || String((e as Error).message).includes("发言")) {
          s = dayAction(s, s.currentSeat, { kind: "speak_done" });
        } else {
          throw e;
        }
      }
      di++;
    }
    expect(di).toBeLessThan(30);
  });
});