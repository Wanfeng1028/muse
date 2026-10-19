import { describe, it, expect } from "vitest";
import { createGame, nightAction } from "../src/werewolf/game.js";
import { chooseNightAction, chooseDayAction } from "../src/werewolf/ai.js";
import { serializeForSeat } from "../src/werewolf/game.js";
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
  return createGame(seats(n), rng0) as GameState;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

describe("AI 决策", () => {
  it("1. guard 步骤 chooseNightAction 返回 {kind:'night'} 且 target 是存活非自己", () => {
    const s = makeGame(10);
    const guard = findSeatByRole(s, "guard");
    const state: GameState = { ...s, phase: "night", night: { ...s.night, step: "guard" } };
    const act = chooseNightAction(state, guard, rng0);
    expect(isObject(act)).toBe(true);
    const a = act as { kind: string; target: string | null };
    expect(a.kind).toBe("night");
    expect(a.target).not.toBeNull();
    expect(a.target).not.toBe(guard);
    expect(aliveSeats(state)).toContain(a.target);
  });

  it("2. wolves 步骤返回 target 为存活非自己", () => {
    const s = makeGame(10);
    const wolf = findSeatByRole(s, "werewolf");
    const state: GameState = { ...s, phase: "night", night: { ...s.night, step: "wolves" } };
    const act = chooseNightAction(state, wolf, rng0) as { kind: string; target: string | null };
    expect(act.kind).toBe("night");
    expect(act.target).not.toBeNull();
    expect(act.target).not.toBe(wolf);
    expect(aliveSeats(state)).toContain(act.target);
  });

  it("3. seer 步骤返回 target 为存活非自己", () => {
    const s = makeGame(10);
    const seer = findSeatByRole(s, "seer");
    const state: GameState = { ...s, phase: "night", night: { ...s.night, step: "seer" } };
    const act = chooseNightAction(state, seer, rng0) as { kind: string; target: string | null };
    expect(act.kind).toBe("night");
    expect(act.target).not.toBeNull();
    expect(act.target).not.toBe(seer);
    expect(aliveSeats(state)).toContain(act.target);
  });

  it("4. witch 步骤返回 potion null", () => {
    const s = makeGame(10);
    const witch = findSeatByRole(s, "witch");
    const state: GameState = { ...s, phase: "night", night: { ...s.night, step: "witch" } };
    const act = chooseNightAction(state, witch, rng0) as { kind: string; potion: null };
    expect(act.kind).toBe("night");
    expect(act.potion).toBeNull();
  });

  it("5. 非 night phase 返回 {kind:'night', target:null, potion:null}", () => {
    const s = makeGame(10);
    const guard = findSeatByRole(s, "guard");
    const state: GameState = { ...s, phase: "vote" };
    const act = chooseNightAction(state, guard, rng0) as { kind: string; target: null; potion: null };
    expect(act.kind).toBe("night");
    expect(act.target).toBeNull();
    expect(act.potion).toBeNull();
  });

  it("6. chooseNightAction 永不抛错：players 为空数组的畸形 state", () => {
    const s = makeGame(10);
    const guard = findSeatByRole(s, "guard");
    const state = { ...s, phase: "night", players: [] } as unknown as GameState;
    let act: unknown;
    expect(() => {
      act = chooseNightAction(state, guard, rng0);
    }).not.toThrow();
    expect(isObject(act)).toBe(true);
    expect((act as { kind: string }).kind).toBe("night");
  });

  it("7. announce 阶段返回 {kind:'announce_done'}", () => {
    const s = makeGame(10);
    const civilian = findSeatByRole(s, "villager");
    const state: GameState = { ...s, phase: "announce", hunterShootPending: null };
    const act = chooseDayAction(state, civilian, rng0) as { kind: string };
    expect(act.kind).toBe("announce_done");
  });

  it("8. hunterShootPending === seat 时返回 {kind:'hunter_shoot'} 且 target 非自己", () => {
    const s = makeGame(9);
    const hunter = findSeatByRole(s, "hunter");
    const state: GameState = { ...s, phase: "announce", hunterShootPending: hunter };
    const act = chooseDayAction(state, hunter, rng0) as { kind: string; target: string };
    expect(act.kind).toBe("hunter_shoot");
    expect(act.target).not.toBe(hunter);
  });

  it("9. vote 阶段返回 {kind:'vote'} 且 target 为存活非自己；无人时 target null", () => {
    const s = makeGame(10);
    const voter = findSeatByRole(s, "villager");
    const state: GameState = { ...s, phase: "vote" };
    const act = chooseDayAction(state, voter, rng0) as { kind: string; target: string | null };
    expect(act.kind).toBe("vote");
    expect(act.target).not.toBeNull();
    expect(act.target).not.toBe(voter);
    expect(aliveSeats(state)).toContain(act.target);

    const s6 = makeGame(6);
    const me = findSeatByRole(s6, "villager");
    const lonely: GameState = {
      ...s6,
      phase: "vote",
      players: s6.players.map((p) => (p.seat === me ? p : { ...p, alive: false })),
    };
    const act2 = chooseDayAction(lonely, me, rng0) as { kind: string; target: string | null };
    expect(act2.kind).toBe("vote");
    expect(act2.target).toBeNull();
  });

  it("10. AI 不作弊：狼座位 wolves 步骤可能刀中另一只狼", () => {
    const s = makeGame(6);
    const wolfSeats = s.players.filter((p) => p.role === "werewolf").map((p) => p.seat);
    expect(wolfSeats.length).toBeGreaterThanOrEqual(2);
    const me = wolfSeats[0];
    const other = wolfSeats[1];
    const state: GameState = { ...s, phase: "night", night: { ...s.night, step: "wolves" } };
    let hitTeammate = 0;
    for (let i = 0; i < 200; i++) {
      const rng = () => i / 200;
      const act = chooseNightAction(state, me, rng) as { kind: string; target: string | null };
      if (act.target === other) hitTeammate++;
    }
    expect(hitTeammate).toBeGreaterThan(0);
  });
});

describe("视角隔离", () => {
  function buildFirstNight(): {
    state: GameState;
    guard: string;
    wolf: string;
    seer: string;
    witch: string;
    wolfTarget: string;
    seerTarget: string;
  } {
    let s = makeGame(10);
    const guard = findSeatByRole(s, "guard");
    const wolf = findSeatByRole(s, "werewolf");
    const seer = findSeatByRole(s, "seer");
    const witch = findSeatByRole(s, "witch");
    const civilians = s.players.filter((p) => p.role === "villager").map((p) => p.seat);
    const wolfTarget = civilians[0];
    const seerTarget = civilians[1];
    s = nightAction(s, guard, { kind: "night", target: null }) as GameState;
    s = nightAction(s, wolf, { kind: "night", target: wolfTarget }) as GameState;
    s = nightAction(s, seer, { kind: "night", target: seerTarget }) as GameState;
    s = nightAction(s, witch, { kind: "night", potion: null }) as GameState;
    return { state: s, guard, wolf, seer, witch, wolfTarget, seerTarget };
  }

  it("11. 狼人视角：狼互认 + wolfSeats 长度 3 且含自己", () => {
    const { state, wolf } = buildFirstNight();
    const view = serializeForSeat(state, wolf) as {
      players: Array<{ seat: string; role?: string }>;
      wolfSeats: string[];
    };
    const wolfSeats = state.players.filter((p) => p.role === "werewolf").map((p) => p.seat);
    for (const w of wolfSeats) {
      const pv = view.players.find((p) => p.seat === w)!;
      expect(pv.role).toBe("werewolf");
    }
    for (const p of view.players) {
      if (!wolfSeats.includes(p.seat)) {
        expect(p.role).toBeUndefined();
      }
    }
    expect(view.wolfSeats.length).toBe(3);
    expect(view.wolfSeats.length).toBe(wolfSeats.length);
    expect(view.wolfSeats).toContain(wolf);
  });

  it("12. 平民视角：仅自己有 role 'villager'，无 wolfSeats", () => {
    const { state } = buildFirstNight();
    const civilian = state.players.find((p) => p.role === "villager")!.seat;
    const view = serializeForSeat(state, civilian) as {
      players: Array<{ seat: string; role?: string }>;
      wolfSeats?: unknown;
    };
    const mine = view.players.find((p) => p.seat === civilian)!;
    expect(mine.role).toBe("villager");
    for (const p of view.players) {
      if (p.seat !== civilian) {
        expect(p.role).toBeUndefined();
      }
    }
    expect("wolfSeats" in view).toBe(false);
  });

  it("13. 预言家视角：seerHistory 长度 1 且与查验一致，seerResult 非 null", () => {
    const { state, seer, seerTarget } = buildFirstNight();
    const view = serializeForSeat(state, seer) as {
      seerHistory: Array<{ day: number; target: string; result: string }>;
      seerResult: string | null;
    };
    expect(view.seerHistory.length).toBe(1);
    expect(view.seerHistory[0].target).toBe(seerTarget);
    expect(view.seerResult).not.toBeNull();
  });

  it("14. 平民视角无 seerHistory、无 seerResult 字段", () => {
    const { state } = buildFirstNight();
    const civilian = state.players.find((p) => p.role === "villager")!.seat;
    const view = serializeForSeat(state, civilian) as Record<string, unknown>;
    expect("seerHistory" in view).toBe(false);
    expect("seerResult" in view).toBe(false);
  });

  it("15. 女巫在 witch 步骤视角含 wolfTarget 且等于 night.wolfTarget", () => {
    let s = makeGame(10);
    const guard = findSeatByRole(s, "guard");
    const wolf = findSeatByRole(s, "werewolf");
    const seer = findSeatByRole(s, "seer");
    const witch = findSeatByRole(s, "witch");
    const civilians = s.players.filter((p) => p.role === "villager").map((p) => p.seat);
    s = nightAction(s, guard, { kind: "night", target: null }) as GameState;
    s = nightAction(s, wolf, { kind: "night", target: civilians[0] }) as GameState;
    s = nightAction(s, seer, { kind: "night", target: civilians[1] }) as GameState;
    const view = serializeForSeat(s, witch) as { wolfTarget?: string | null };
    expect("wolfTarget" in view).toBe(true);
    expect(view.wolfTarget).toBe(s.night.wolfTarget);
  });

  it("16. 女巫在 announce 后视角无 wolfTarget 字段", () => {
    const { state, witch } = buildFirstNight();
    expect(state.phase).toBe("announce");
    const view = serializeForSeat(state, witch) as Record<string, unknown>;
    expect("wolfTarget" in view).toBe(false);
  });

  it("17. 公开字段对所有人可见且一致", () => {
    const { state } = buildFirstNight();
    const civilian = state.players.find((p) => p.role === "villager")!.seat;
    const view = serializeForSeat(state, civilian) as {
      deaths: unknown;
      votes: unknown;
      sheriffSeat: unknown;
    };
    expect(view.deaths).toEqual(state.deaths);
    expect(view.votes).toEqual(state.votes);
    expect(view.sheriffSeat).toEqual(state.sheriffSeat);
  });

  it("18. winner 结局可见", () => {
    const { state } = buildFirstNight();
    const finished: GameState = { ...state, winner: "good" };
    const civilian = finished.players.find((p) => p.role === "villager")!.seat;
    const view = serializeForSeat(finished, civilian) as { winner?: string };
    expect(view.winner).toBe("good");
  });

  it("19. 未知座位视角不抛错且无人有 role", () => {
    const { state } = buildFirstNight();
    let view: unknown;
    expect(() => {
      view = serializeForSeat(state, "ghost");
    }).not.toThrow();
    const v = view as { players: Array<{ role?: string }> };
    for (const p of v.players) {
      expect(p.role).toBeUndefined();
    }
  });

  it("20. 平民视角不泄露夜晚内部字段", () => {
    const { state } = buildFirstNight();
    const civilian = state.players.find((p) => p.role === "villager")!.seat;
    const view = serializeForSeat(state, civilian);
    const json = JSON.stringify(view);
    expect(json.includes("witchSaveUsed")).toBe(false);
    expect(json.includes("guardTarget")).toBe(false);
    expect(json.includes("seerTarget")).toBe(false);
  });
});