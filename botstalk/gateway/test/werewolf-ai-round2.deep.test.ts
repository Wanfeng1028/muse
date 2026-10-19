import { describe, it, expect } from "vitest";
import { createGame } from "../src/werewolf/game.js";
import { chooseNightAction, chooseDayAction } from "../src/werewolf/ai.js";
import type { GameState } from "../src/werewolf/game.js";

const rng0 = () => 0;

function seats(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `p${i + 1}`);
}

function aliveSeats(state: GameState): string[] {
  return state.players.filter((p) => p.alive).map((p) => p.seat);
}

function findSeatByRole(state: GameState, role: string): string {
  const p = state.players.find((pl) => pl.role === role);
  if (!p) throw new Error(`no seat with role ${role}`);
  return p.seat;
}

function makeGame(n: number): GameState {
  return createGame(seats(n), undefined, rng0) as GameState;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

describe("AI 决策 round2：投票/遗言/女巫边界", () => {
  it("1. vote 阶段：三种确定性 rng 下 target 恒为存活者且永不为自己", () => {
    const state = makeGame(6);
    state.phase = "vote";
    const me = state.players[0].seat;
    const rngs = [() => 0, () => 0.99, () => 0.5];
    for (const rng of rngs) {
      const action = chooseDayAction(state, me, rng);
      expect(isObject(action)).toBe(true);
      const a = action as { kind: string; target: string | null };
      expect(a.kind).toBe("vote");
      expect(a.target).not.toBe(me);
      expect(aliveSeats(state)).toContain(a.target);
    }
  });

  it("2. pk_vote 阶段：rng0 时从 pkSeats 中选 p2，target 必落在 pkSeats 内", () => {
    const state = makeGame(6);
    state.phase = "pk_vote";
    state.pkSeats = ["p2", "p3"];
    const me = "p1";
    const action = chooseDayAction(state, me, rng0);
    expect(isObject(action)).toBe(true);
    const a = action as { kind: string; target: string | null };
    expect(a.kind).toBe("vote");
    expect(a.target).toBe("p2");
    expect(["p2", "p3"]).toContain(a.target);
  });

  it("3. pk_vote 阶段 pkSeats 为空数组：返回 kind vote 且 target null", () => {
    const state = makeGame(6);
    state.phase = "pk_vote";
    state.pkSeats = [];
    const me = state.players[0].seat;
    const action = chooseDayAction(state, me, rng0);
    expect(isObject(action)).toBe(true);
    const a = action as { kind: string; target: string | null };
    expect(a.kind).toBe("vote");
    expect(a.target).toBeNull();
  });

  it("4. vote 阶段除自己外全部 alive false：返回 kind vote 且 target null", () => {
    const state = makeGame(6);
    state.phase = "vote";
    const me = state.players[0].seat;
    for (let i = 1; i < state.players.length; i += 1) {
      state.players[i].alive = false;
    }
    const action = chooseDayAction(state, me, rng0);
    expect(isObject(action)).toBe(true);
    const a = action as { kind: string; target: string | null };
    expect(a.kind).toBe("vote");
    expect(a.target).toBeNull();
  });

  it("5. lastwords 阶段：返回 kind 恰为 lastwords_done，与 announce_done 明确区分", () => {
    const state = makeGame(6);
    state.phase = "lastwords";
    const me = state.players[0].seat;
    const action = chooseDayAction(state, me, rng0);
    expect(isObject(action)).toBe(true);
    const a = action as { kind: string };
    expect(a.kind).toBe("lastwords_done");
    expect(a.kind).not.toBe("announce_done");
  });

  it("6. 女巫 witch 步骤且 night.wolfTarget 有值：AI 读不到该字段，仍返回 potion null", () => {
    const state = makeGame(7);
    state.phase = "night";
    state.night.step = "witch";
    state.night.wolfTarget = "p3";
    const witch = findSeatByRole(state, "witch");
    const action = chooseNightAction(state, witch, rng0);
    expect(isObject(action)).toBe(true);
    const a = action as { kind: string; potion: string | null };
    expect(a.kind).toBe("night");
    expect(a.potion).toBeNull();
  });

  it("7. 女巫 witch 步骤连续多夜 wolfTarget 依次为 p3 p5 null：每次 potion 均为 null", () => {
    const state = makeGame(7);
    state.phase = "night";
    state.night.step = "witch";
    const witch = findSeatByRole(state, "witch");
    const targets: (string | null)[] = ["p3", "p5", null];
    for (const t of targets) {
      state.night.wolfTarget = t;
      const action = chooseNightAction(state, witch, rng0);
      expect(isObject(action)).toBe(true);
      const a = action as { kind: string; potion: string | null };
      expect(a.kind).toBe("night");
      expect(a.potion).toBeNull();
    }
  });

  it("8. hunter_shoot：pending 为自己且有他人存活时 target 为他人且非自己", () => {
    const state = makeGame(9);
    state.phase = "announce";
    const hunter = findSeatByRole(state, "hunter");
    state.hunterShootPending = hunter;
    const action = chooseDayAction(state, hunter, rng0);
    expect(isObject(action)).toBe(true);
    const a = action as { kind: string; target: string | null };
    expect(a.kind).toBe("hunter_shoot");
    expect(a.target).not.toBe(hunter);
    expect(aliveSeats(state)).toContain(a.target);
  });

  it("9. hunter_shoot：pending 为自己且除自己外无人存活时 target 恰好为自己（兜底形状）", () => {
    const state = makeGame(9);
    state.phase = "announce";
    const hunter = findSeatByRole(state, "hunter");
    state.hunterShootPending = hunter;
    for (const p of state.players) {
      if (p.seat !== hunter) p.alive = false;
    }
    const action = chooseDayAction(state, hunter, rng0);
    expect(isObject(action)).toBe(true);
    const a = action as { kind: string; target: string | null };
    expect(a.kind).toBe("hunter_shoot");
    expect(a.target).toBe(hunter);
  });

  it("10. sheriff 阶段：rng 0.4 上警 sheriff，rng 0.6 弃权 sheriff_pass（50 边界两侧）", () => {
    const state = makeGame(6);
    state.phase = "sheriff";
    const me = state.players[0].seat;
    const low = chooseDayAction(state, me, () => 0.4);
    expect(isObject(low)).toBe(true);
    expect((low as { kind: string }).kind).toBe("sheriff");
    const high = chooseDayAction(state, me, () => 0.6);
    expect(isObject(high)).toBe(true);
    expect((high as { kind: string }).kind).toBe("sheriff_pass");
  });

  it("11. announce 阶段 hunterShootPending 为他人：返回 announce_done", () => {
    const state = makeGame(6);
    state.phase = "announce";
    const me = state.players[0].seat;
    const other = state.players.find((p) => p.seat !== me && p.alive);
    if (!other) throw new Error("no other alive seat");
    state.hunterShootPending = other.seat;
    const action = chooseDayAction(state, me, rng0);
    expect(isObject(action)).toBe(true);
    expect((action as { kind: string }).kind).toBe("announce_done");
  });

  it("12. pk_speak 阶段：与 speak 同值，返回 speak_done", () => {
    const state = makeGame(6);
    state.phase = "pk_speak";
    const me = state.players[0].seat;
    const action = chooseDayAction(state, me, rng0);
    expect(isObject(action)).toBe(true);
    const a = action as { kind: string };
    expect(a.kind).toBe("speak_done");
    expect(a.kind).not.toBe("lastwords_done");
  });
});
