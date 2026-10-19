import { describe, it, expect } from "vitest";
import { createGame, nightAction, dayAction, WerewolfError } from "../src/werewolf/game.js";
import { SUPPORTED_COUNTS } from "../src/werewolf/roles.js";
import type { GameState } from "../src/werewolf/game.js";
import type { Role } from "../src/werewolf/roles.js";

const rng0 = () => 0;

function seats(n: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < n; i++) out.push(`s${i + 1}`);
  return out;
}

function roleOf(state: GameState, seat: string): Role {
  const p = state.players.find((x) => x.seat === seat);
  if (!p) throw new Error(`no such seat ${seat}`);
  return p.role;
}

function findSeatByRole(state: GameState, role: Role, aliveOnly = false): string {
  const p = state.players.find((x) => x.role === role && (!aliveOnly || x.alive));
  if (!p) throw new Error(`no seat with role ${role}`);
  return p.seat;
}

function anyAlive(st: GameState): string {
  const p = st.players.find((x) => x.alive);
  if (!p) throw new Error("no alive player");
  return p.seat;
}

function countRole(state: GameState, role: Role): number {
  return state.players.filter((p) => p.role === role).length;
}

function expectCode(fn: () => unknown, code: string): void {
  let caught: unknown;
  try {
    fn();
  } catch (e) {
    caught = e;
  }
  expect(caught).toBeInstanceOf(WerewolfError);
  expect((caught as WerewolfError).code).toBe(code);
}

describe("createGame 配置", () => {
  it("6 人局角色构成恰为 2 狼 3 民 1 预言家", () => {
    const state = createGame(seats(6), {}, rng0);
    expect(state.players.length).toBe(6);
    expect(countRole(state, "werewolf")).toBe(2);
    expect(countRole(state, "villager")).toBe(3);
    expect(countRole(state, "seer")).toBe(1);
    expect(SUPPORTED_COUNTS[6].filter((r) => r === "werewolf").length).toBe(2);
    expect(SUPPORTED_COUNTS[6].filter((r) => r === "villager").length).toBe(3);
    expect(SUPPORTED_COUNTS[6].filter((r) => r === "seer").length).toBe(1);
  });

  it("12 人局角色构成 4 狼 4 民 + 预言家女巫猎人守卫各 1", () => {
    const state = createGame(seats(12), {}, rng0);
    expect(state.players.length).toBe(12);
    expect(countRole(state, "werewolf")).toBe(4);
    expect(countRole(state, "villager")).toBe(4);
    expect(countRole(state, "seer")).toBe(1);
    expect(countRole(state, "witch")).toBe(1);
    expect(countRole(state, "hunter")).toBe(1);
    expect(countRole(state, "guard")).toBe(1);
  });

  it("6..12 每种人数角色总数等于人数且狼数与 SUPPORTED_COUNTS 一致", () => {
    for (let n = 6; n <= 12; n++) {
      const state = createGame(seats(n), {}, rng0);
      expect(state.players.length).toBe(n);
      const wolves = countRole(state, "werewolf");
      const expectedWolves = SUPPORTED_COUNTS[n].filter((r) => r === "werewolf").length;
      expect(wolves).toBe(expectedWolves);
    }
  });

  it("rng0 确定性：两次 createGame(seats(9), {}, rng0) 每个座位角色完全相同", () => {
    const a = createGame(seats(9), {}, rng0);
    const b = createGame(seats(9), {}, rng0);
    for (let i = 0; i < 9; i++) {
      const seat = `s${i + 1}`;
      expect(roleOf(a, seat)).toBe(roleOf(b, seat));
    }
  });

  it("5 人与 13 人抛 BAD_SEATS", () => {
    expectCode(() => createGame(seats(5), {}, rng0), "BAD_SEATS");
    expectCode(() => createGame(seats(13), {}, rng0), "BAD_SEATS");
  });

  it("重复座位抛 BAD_SEATS；含空字符串座位抛 BAD_SEATS", () => {
    expectCode(() => createGame(["a", "b", "c", "d", "e", "a"], {}, rng0), "BAD_SEATS");
    expectCode(() => createGame(["a", "b", "c", "d", "e", ""], {}, rng0), "BAD_SEATS");
  });

  it("初始状态 phase night、day 1、step guard（10 人局，守卫存活）、currentSeat 为守卫座位", () => {
    const state = createGame(seats(10), {}, rng0);
    expect(state.phase).toBe("night");
    expect(state.day).toBe(1);
    expect(state.night.step).toBe("guard");
    const guardSeat = findSeatByRole(state, "guard", true);
    expect(state.currentSeat).toBe(guardSeat);
  });
});

describe("夜晚状态机", () => {
  it("守卫守人后 step 推进到 wolves，currentSeat 为第一只存活狼", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const target = state.players.find((p) => p.seat !== guardSeat)!.seat;
    const next = nightAction(state, guardSeat, { kind: "night", target });
    expect(next.night.step).toBe("wolves");
    const firstWolf = next.players.find((p) => p.role === "werewolf" && p.alive)!.seat;
    expect(next.currentSeat).toBe(firstWolf);
  });

  it("狼刀队友抛 ILLEGAL_TARGET", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const afterGuard = nightAction(state, guardSeat, { kind: "night", target: null });
    const wolfSeat = afterGuard.currentSeat;
    const mate = afterGuard.players.find(
      (p) => p.role === "werewolf" && p.alive && p.seat !== wolfSeat
    )!.seat;
    expectCode(() => nightAction(afterGuard, wolfSeat, { kind: "night", target: mate }), "ILLEGAL_TARGET");
  });

  it("狼空刀（target null）后 step 到 seer", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const afterGuard = nightAction(state, guardSeat, { kind: "night", target: null });
    const wolfSeat = afterGuard.currentSeat;
    const afterWolf = nightAction(afterGuard, wolfSeat, { kind: "night", target: null });
    expect(afterWolf.night.step).toBe("seer");
    const seerSeat = findSeatByRole(afterWolf, "seer", true);
    expect(afterWolf.currentSeat).toBe(seerSeat);
  });

  it("非守卫在 guard 步骤行动抛 NOT_YOUR_TURN", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const other = state.players.find((p) => p.seat !== guardSeat)!.seat;
    expectCode(() => nightAction(state, other, { kind: "night", target: null }), "NOT_YOUR_TURN");
  });

  it("预言家验狼得 wolf、验好人得 good，seerHistory 长度 1 且 day/target/result 正确", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const afterGuard = nightAction(state, guardSeat, { kind: "night", target: null });
    const wolfSeat = afterGuard.currentSeat;
    const afterWolf = nightAction(afterGuard, wolfSeat, { kind: "night", target: null });
    const seerSeat = afterWolf.currentSeat;
    const wolfTarget = afterWolf.players.find((p) => p.role === "werewolf" && p.alive)!.seat;
    const afterSeer = nightAction(afterWolf, seerSeat, { kind: "night", target: wolfTarget });
    expect(afterSeer.night.seerResult).toBe("wolf");
    expect(afterSeer.night.seerHistory.length).toBe(1);
    expect(afterSeer.night.seerHistory[0].day).toBe(1);
    expect(afterSeer.night.seerHistory[0].target).toBe(wolfTarget);
    expect(afterSeer.night.seerHistory[0].result).toBe("wolf");

    const state2 = createGame(seats(10), {}, rng0);
    const g2 = findSeatByRole(state2, "guard", true);
    const ag2 = nightAction(state2, g2, { kind: "night", target: null });
    const w2 = ag2.currentSeat;
    const aw2 = nightAction(ag2, w2, { kind: "night", target: null });
    const seer2 = aw2.currentSeat;
    const goodTarget = aw2.players.find((p) => p.role === "villager" && p.alive)!.seat;
    const as2 = nightAction(aw2, seer2, { kind: "night", target: goodTarget });
    expect(as2.night.seerResult).toBe("good");
    expect(as2.night.seerHistory.length).toBe(1);
    expect(as2.night.seerHistory[0].result).toBe("good");
  });

  it("预言家验自己抛 ILLEGAL_TARGET", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const afterGuard = nightAction(state, guardSeat, { kind: "night", target: null });
    const afterWolf = nightAction(afterGuard, afterGuard.currentSeat, { kind: "night", target: null });
    const seerSeat = afterWolf.currentSeat;
    expectCode(() => nightAction(afterWolf, seerSeat, { kind: "night", target: seerSeat }), "ILLEGAL_TARGET");
  });

  it("守卫守中狼刀目标：resolveNight 后被守者 alive 仍 true，deathsTonight 为空", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const victim = state.players.find((p) => p.role === "villager" && p.alive)!.seat;
    const afterGuard = nightAction(state, guardSeat, { kind: "night", target: victim });
    const wolfSeat = afterGuard.currentSeat;
    const afterWolf = nightAction(afterGuard, wolfSeat, { kind: "night", target: victim });
    const afterSeer = nightAction(afterWolf, afterWolf.currentSeat, { kind: "night", target: null });
    const witchSeat = afterSeer.currentSeat;
    const afterWitch = nightAction(afterSeer, witchSeat, { kind: "night", potion: null });
    expect(afterWitch.deathsTonight).toEqual([]);
    const p = afterWitch.players.find((x) => x.seat === victim)!;
    expect(p.alive).toBe(true);
  });

  it("女巫解药救非被刀者抛 ILLEGAL_TARGET", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const afterGuard = nightAction(state, guardSeat, { kind: "night", target: null });
    const afterWolf = nightAction(afterGuard, afterGuard.currentSeat, { kind: "night", target: null });
    const afterSeer = nightAction(afterWolf, afterWolf.currentSeat, { kind: "night", target: null });
    const witchSeat = afterSeer.currentSeat;
    const notVictim = afterSeer.players.find(
      (p) => p.alive && p.seat !== witchSeat && p.seat !== afterSeer.night.wolfTarget
    )!.seat;
    expectCode(
      () => nightAction(afterSeer, witchSeat, { kind: "night", potion: "save", target: notVictim }),
      "ILLEGAL_TARGET"
    );
  });

  it("首夜狼刀女巫自己、女巫对自己用 save 抛 ILLEGAL_TARGET（首夜不能自救）", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const witchSeat = findSeatByRole(state, "witch", true);
    const afterGuard = nightAction(state, guardSeat, { kind: "night", target: null });
    const afterWolf = nightAction(afterGuard, afterGuard.currentSeat, { kind: "night", target: witchSeat });
    const afterSeer = nightAction(afterWolf, afterWolf.currentSeat, { kind: "night", target: null });
    expect(afterSeer.currentSeat).toBe(witchSeat);
    expectCode(
      () => nightAction(afterSeer, witchSeat, { kind: "night", potion: "save", target: witchSeat }),
      "ILLEGAL_TARGET"
    );
  });

  it("女巫首夜用掉解药后，第二夜再 save 抛 BAD_ACTION", () => {
    let state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const witchSeat = findSeatByRole(state, "witch", true);
    const victim = state.players.find((p) => p.role === "villager" && p.alive)!.seat;

    let s = nightAction(state, guardSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", target: victim });
    s = nightAction(s, s.currentSeat, { kind: "night", target: null });
    s = nightAction(s, witchSeat, { kind: "night", potion: "save", target: victim });
    expect(s.night.witchSaveUsed).toBe(true);

    // 女巫救人后无死亡，announce 被跳过直进 speak；有死亡才需 announce_done
    if (s.phase === "announce") {
      s = dayAction(s, anyAlive(s), { kind: "announce_done" });
    }
    while (s.phase === "lastwords") {
      s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
    }
    while (s.phase === "speak") {
      s = dayAction(s, s.currentSeat, { kind: "speak_done" });
    }
    expect(s.phase).toBe("vote");
    while (s.phase === "vote") {
      s = dayAction(s, s.currentSeat, { kind: "vote", target: null });
    }
    expect(s.phase).toBe("night");
    expect(s.day).toBe(2);

    const guard2 = findSeatByRole(s, "guard", true);
    const witch2 = findSeatByRole(s, "witch", true);
    let n = nightAction(s, guard2, { kind: "night", target: null });
    const victim2 = n.players.find((p) => p.alive && p.role === "villager")!.seat;
    n = nightAction(n, n.currentSeat, { kind: "night", target: victim2 });
    n = nightAction(n, n.currentSeat, { kind: "night", target: null });
    expect(n.currentSeat).toBe(witch2);
    expectCode(
      () => nightAction(n, witch2, { kind: "night", potion: "save", target: victim2 }),
      "BAD_ACTION"
    );
  });

  it("女巫毒杀存活玩家：resolveNight 后目标 alive false，deaths 含 reason witch", () => {
    const state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const afterGuard = nightAction(state, guardSeat, { kind: "night", target: null });
    const afterWolf = nightAction(afterGuard, afterGuard.currentSeat, { kind: "night", target: null });
    const afterSeer = nightAction(afterWolf, afterWolf.currentSeat, { kind: "night", target: null });
    const witchSeat = afterSeer.currentSeat;
    const poisonTarget = afterSeer.players.find(
      (p) => p.alive && p.seat !== witchSeat && p.role === "villager"
    )!.seat;
    const afterWitch = nightAction(afterSeer, witchSeat, {
      kind: "night",
      potion: "poison",
      target: poisonTarget,
    });
    expect(afterWitch.night.witchPoisonUsed).toBe(true);
    const victim = afterWitch.players.find((p) => p.seat === poisonTarget)!;
    expect(victim.alive).toBe(false);
    expect(afterWitch.deaths.some((d) => d.seat === poisonTarget && d.reason === "witch")).toBe(true);
  });
});

describe("白天与胜负", () => {
  it("无警长配置白天流程：announce_done -> 全部 lastwords_done -> 全部 speak_done -> phase 进入 vote", () => {
    let state = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(state, "guard", true);
    const victim = state.players.find((p) => p.role === "villager" && p.alive)!.seat;
    let s = nightAction(state, guardSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", target: victim });
    s = nightAction(s, s.currentSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", potion: null });
    expect(s.phase).toBe("announce");

    s = dayAction(s, anyAlive(s), { kind: "announce_done" });
    while (s.phase === "lastwords") {
      s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
    }
    while (s.phase === "speak") {
      s = dayAction(s, s.currentSeat, { kind: "speak_done" });
    }
    expect(s.phase).toBe("vote");
  });

  it("投票放逐：全体投同一目标后 deaths 含 reason vote，phase 回到 night 且 day+1", () => {
    let s = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(s, "guard", true);
    const victim = s.players.find((p) => p.role === "villager" && p.alive)!.seat;
    s = nightAction(s, guardSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", target: victim });
    s = nightAction(s, s.currentSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", potion: null });
    s = dayAction(s, anyAlive(s), { kind: "announce_done" });
    while (s.phase === "lastwords") {
      s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
    }
    while (s.phase === "speak") {
      s = dayAction(s, s.currentSeat, { kind: "speak_done" });
    }
    expect(s.phase).toBe("vote");
    const dayBefore = s.day;
    const lynchTarget = s.players.find((p) => p.alive && p.role === "werewolf")!.seat;
    while (s.phase === "vote" || s.phase === "pk_vote") {
      s = dayAction(s, s.currentSeat, { kind: "vote", target: lynchTarget });
    }
    expect(s.deaths.some((d) => d.seat === lynchTarget && d.reason === "vote")).toBe(true);
    // 放逐后先走遗言，再入夜（enterNightAfterDay 内判胜负）
    while (s.phase === "lastwords") {
      s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
    }
    expect(s.phase).toBe("night");
    expect(s.day).toBe(dayBefore + 1);
  });

  it("狼全灭判好人胜：6 人局，白天全体投票放逐两只狼，winner good 且 phase finished", () => {
    let s = createGame(seats(6), {}, rng0);
    for (let round = 0; round < 2; round++) {
      if (s.phase === "finished") break;
      if (s.phase === "night") {
        const wolfSeat = s.players.find((p) => p.role === "werewolf" && p.alive)!.seat;
        const villagerSeat = s.players.find((p) => p.role === "villager" && p.alive)!.seat;
        s = nightAction(s, wolfSeat, { kind: "night", target: villagerSeat });
        s = nightAction(s, s.currentSeat, { kind: "night", target: null });
      }
      if (s.phase === "announce") {
        s = dayAction(s, anyAlive(s), { kind: "announce_done" });
      }
      while (s.phase === "lastwords") {
        s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
      }
      while (s.phase === "speak") {
        s = dayAction(s, s.currentSeat, { kind: "speak_done" });
      }
      if (s.phase === "vote" || s.phase === "pk_vote") {
        const lynchTarget = s.players.find((p) => p.role === "werewolf" && p.alive)!.seat;
        while (s.phase === "vote" || s.phase === "pk_vote") {
          s = dayAction(s, s.currentSeat, { kind: "vote", target: lynchTarget });
        }
        while (s.phase === "lastwords") {
          s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
        }
      }
    }
    expect(s.winner).toBe("good");
    expect(s.phase).toBe("finished");
  });

  it("平民全灭判狼胜：手动置两名平民死亡后，投票放逐第三名平民，winner wolves", () => {
    let s = createGame(seats(6), {}, rng0);
    const villagers = s.players.filter((p) => p.role === "villager").map((p) => p.seat);
    expect(villagers.length).toBe(3);
    for (let i = 0; i < 2; i++) {
      const p = s.players.find((x) => x.seat === villagers[i])!;
      p.alive = false;
    }
    const lastVillager = villagers[2];
    const wolfSeat = s.players.find((p) => p.role === "werewolf" && p.alive)!.seat;
    const goodTarget = s.players.find(
      (p) => p.alive && p.role !== "werewolf" && p.seat !== lastVillager
    );
    if (goodTarget) {
      s = nightAction(s, wolfSeat, { kind: "night", target: goodTarget.seat });
      s = nightAction(s, s.currentSeat, { kind: "night", target: null });
    } else {
      s = nightAction(s, wolfSeat, { kind: "night", target: null });
      s = nightAction(s, s.currentSeat, { kind: "night", target: null });
    }
    while (s.phase === "announce") {
      s = dayAction(s, anyAlive(s), { kind: "announce_done" });
    }
    while (s.phase === "lastwords") {
      s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
    }
    while (s.phase === "speak") {
      s = dayAction(s, s.currentSeat, { kind: "speak_done" });
    }
    if (s.phase === "vote" || s.phase === "pk_vote") {
      while (s.phase === "vote" || s.phase === "pk_vote") {
        s = dayAction(s, s.currentSeat, { kind: "vote", target: lastVillager });
      }
      while (s.phase === "lastwords") {
        s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
      }
    }
    expect(s.winner).toBe("wolves");
    expect(s.phase).toBe("finished");
  });

  it("finished 后 nightAction 抛 WRONG_PHASE，dayAction 抛 WRONG_PHASE", () => {
    let s = createGame(seats(6), {}, rng0);
    const wolves = s.players.filter((p) => p.role === "werewolf").map((p) => p.seat);
    for (let round = 0; round < 2; round++) {
      if (s.phase === "finished") break;
      if (s.phase === "night") {
        const wolfSeat = s.players.find((p) => p.role === "werewolf" && p.alive)!.seat;
        const villagerSeat = s.players.find((p) => p.role === "villager" && p.alive)!.seat;
        s = nightAction(s, wolfSeat, { kind: "night", target: villagerSeat });
        s = nightAction(s, s.currentSeat, { kind: "night", target: null });
      }
      if (s.phase === "announce") {
        s = dayAction(s, anyAlive(s), { kind: "announce_done" });
      }
      while (s.phase === "lastwords") {
        s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
      }
      while (s.phase === "speak") {
        s = dayAction(s, s.currentSeat, { kind: "speak_done" });
      }
      if (s.phase === "vote" || s.phase === "pk_vote") {
        const lynchTarget = s.players.find((p) => p.role === "werewolf" && p.alive)!.seat;
        while (s.phase === "vote" || s.phase === "pk_vote") {
          s = dayAction(s, s.currentSeat, { kind: "vote", target: lynchTarget });
        }
        while (s.phase === "lastwords") {
          s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
        }
      }
    }
    expect(s.phase).toBe("finished");
    const anySeat = wolves[0];
    expectCode(() => nightAction(s, anySeat, { kind: "night", target: null }), "WRONG_PHASE");
    expectCode(() => dayAction(s, anySeat, { kind: "announce_done" }), "WRONG_PHASE");
  });

  it("出局玩家在夜晚行动抛 DEAD_PLAYER", () => {
    let s = createGame(seats(10), {}, rng0);
    const guardSeat = findSeatByRole(s, "guard", true);
    const victim = s.players.find((p) => p.role === "villager" && p.alive)!.seat;
    s = nightAction(s, guardSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", target: victim });
    s = nightAction(s, s.currentSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", potion: null });
    expect(s.players.find((p) => p.seat === victim)!.alive).toBe(false);

    s = dayAction(s, anyAlive(s), { kind: "announce_done" });
    while (s.phase === "lastwords") {
      s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
    }
    while (s.phase === "speak") {
      s = dayAction(s, s.currentSeat, { kind: "speak_done" });
    }
    while (s.phase === "vote") {
      s = dayAction(s, s.currentSeat, { kind: "vote", target: null });
    }
    expect(s.phase).toBe("night");
    expect(s.day).toBe(2);
    const guard2 = findSeatByRole(s, "guard", true);
    const n = nightAction(s, guard2, { kind: "night", target: null });
    expectCode(() => nightAction(n, victim, { kind: "night", target: null }), "DEAD_PLAYER");
  });

  it("未知座位行动抛 UNKNOWN_SEAT", () => {
    const s = createGame(seats(10), {}, rng0);
    expectCode(() => nightAction(s, "no-such-seat", { kind: "night", target: null }), "UNKNOWN_SEAT");
    expectCode(() => dayAction(s, "no-such-seat", { kind: "announce_done" }), "UNKNOWN_SEAT");
  });

  it("猎人被毒后开枪：9 人局，女巫毒猎人，announce 后 hunterShootPending 为猎人座位；hunter_shoot 带走存活玩家", () => {
    let s = createGame(seats(9), {}, rng0);
    const witchSeat = findSeatByRole(s, "witch", true);
    const hunterSeat = findSeatByRole(s, "hunter", true);
    const wolfSeat = s.players.find((p) => p.role === "werewolf" && p.alive)!.seat;

    s = nightAction(s, wolfSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", target: null });
    expect(s.currentSeat).toBe(witchSeat);
    s = nightAction(s, witchSeat, { kind: "night", potion: "poison", target: hunterSeat });
    expect(s.players.find((p) => p.seat === hunterSeat)!.alive).toBe(false);
    expect(s.phase).toBe("announce");
    expect(s.hunterShootPending).toBe(null);

    // 任意存活者确认死讯，enterAfterAnnounce 才挂起猎人开枪
    s = dayAction(s, anyAlive(s), { kind: "announce_done" });
    expect(s.phase).toBe("announce");
    expect(s.hunterShootPending).toBe(hunterSeat);

    const shootTarget = s.players.find((p) => p.alive && p.seat !== hunterSeat)!.seat;
    s = dayAction(s, hunterSeat, { kind: "hunter_shoot", target: shootTarget });
    expect(s.players.find((p) => p.seat === shootTarget)!.alive).toBe(false);
    expect(s.deaths.some((d) => d.seat === shootTarget && d.reason === "hunter")).toBe(true);
  });

  it("猎人开枪阶段出别的 kind（announce_done）抛 BAD_ACTION", () => {
    let s = createGame(seats(9), {}, rng0);
    const witchSeat = findSeatByRole(s, "witch", true);
    const hunterSeat = findSeatByRole(s, "hunter", true);
    const wolfSeat = s.players.find((p) => p.role === "werewolf" && p.alive)!.seat;

    s = nightAction(s, wolfSeat, { kind: "night", target: null });
    s = nightAction(s, s.currentSeat, { kind: "night", target: null });
    s = nightAction(s, witchSeat, { kind: "night", potion: "poison", target: hunterSeat });
    s = dayAction(s, anyAlive(s), { kind: "announce_done" });
    expect(s.hunterShootPending).toBe(hunterSeat);

    expectCode(() => dayAction(s, hunterSeat, { kind: "announce_done" }), "BAD_ACTION");
  });
});