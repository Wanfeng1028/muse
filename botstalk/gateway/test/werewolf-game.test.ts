import { describe, it, expect } from "vitest";
import {
  createGame,
  nightAction,
  dayAction,
  serializeForSeat,
  WerewolfError,
} from "../src/werewolf/game.js";
import type { GameState, NightStep } from "../src/werewolf/game.js";
import type { Role } from "../src/werewolf/roles.js";

const rng0 = () => 0;

function seats(n: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < n; i++) out.push(`s${i}`);
  return out;
}

function roleOf(state: GameState, seat: string): Role {
  const p = state.players.find((x) => x.seat === seat);
  if (!p) throw new Error(`no seat ${seat}`);
  return p.role;
}

function findSeatByRole(state: GameState, role: Role): string {
  const p = state.players.find((x) => x.role === role);
  if (!p) throw new Error(`no role ${role}`);
  return p.seat;
}

function aliveByRole(state: GameState, role: Role): string[] {
  return state.players.filter((p) => p.alive && p.role === role).map((p) => p.seat);
}

function codeOf(fn: () => unknown): string {
  try {
    fn();
  } catch (e) {
    return (e as WerewolfError).code;
  }
  throw new Error("expected throw but none");
}

// 6 人局：2 狼 3 民 1 预言家（无守卫无女巫）
function makeGame6(): GameState {
  return createGame(seats(6), undefined, rng0);
}

// 7 人局：2 狼 3 民 预言家 女巫
function makeGame7(): GameState {
  return createGame(seats(7), undefined, rng0);
}

// 10 人局：3 狼 3 民 预言家 女巫 猎人 守卫
function makeGame10(sheriff = false): GameState {
  return createGame(seats(10), { sheriff }, rng0);
}

// 推进一个 6 人局的夜晚：guard 不存在 -> wolves -> seer -> resolve
function runNight6(state: GameState, wolfTarget: string, seerTarget: string): GameState {
  let s = state;
  const wolf = aliveByRole(s, "werewolf")[0];
  s = nightAction(s, wolf, { kind: "night", target: wolfTarget});
  const seer = findSeatByRole(s, "seer");
  s = nightAction(s, seer, { kind: "night", target: seerTarget});
  return s;
}

describe("createGame 参数校验", () => {
  it("人数 5 抛 BAD_SEATS 且信息含 6 到 12", () => {
    try {
      createGame(seats(5), undefined, rng0);
      throw new Error("should throw");
    } catch (e) {
      expect((e as WerewolfError).code).toBe("BAD_SEATS");
      expect((e as WerewolfError).message).toContain("6 到 12");
    }
  });

  it("人数 13 抛 BAD_SEATS 且信息含 6 到 12", () => {
    try {
      createGame(seats(13), undefined, rng0);
      throw new Error("should throw");
    } catch (e) {
      expect((e as WerewolfError).code).toBe("BAD_SEATS");
      expect((e as WerewolfError).message).toContain("6 到 12");
    }
  });

  it("座位重复抛 BAD_SEATS", () => {
    const dup = ["s0", "s0", "s1", "s2", "s3", "s4"];
    expect(codeOf(() => createGame(dup, undefined, rng0))).toBe("BAD_SEATS");
  });

  it("空字符串座位抛 BAD_SEATS", () => {
    const withEmpty = ["s0", "s1", "s2", "s3", "s4", ""];
    expect(codeOf(() => createGame(withEmpty, undefined, rng0))).toBe("BAD_SEATS");
  });

  it("非数组抛 BAD_SEATS", () => {
    expect(
      codeOf(() => createGame("not-an-array" as unknown as string[], undefined, rng0)),
    ).toBe("BAD_SEATS");
  });

  it("相同 rng 两次 createGame 角色分配一致", () => {
    const a = createGame(seats(6), undefined, () => 0);
    const b = createGame(seats(6), undefined, () => 0);
    const aRoles = a.players.map((p) => `${p.seat}:${p.role}`).join(",");
    const bRoles = b.players.map((p) => `${p.seat}:${p.role}`).join(",");
    expect(aRoles).toBe(bRoles);
  });

  it("6 人局角色数量为 2 狼 3 民 1 预言家", () => {
    const g = makeGame6();
    const counts: Record<string, number> = {};
    for (const p of g.players) {
      counts[p.role] = (counts[p.role] ?? 0) + 1;
    }
    expect(counts.werewolf).toBe(2);
    expect(counts.villager).toBe(3);
    expect(counts.seer).toBe(1);
  });
});

describe("夜晚流程 - 基础推进", () => {
  it("6 人局夜晚从 wolves 步骤开始（无守卫）", () => {
    const g = makeGame6();
    expect(g.phase).toBe("night");
    expect(g.night.step).toBe("wolves");
  });

  it("狼人行动后进入 seer 步骤", () => {
    let g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    const target = aliveByRole(g, "villager")[0];
    g = nightAction(g, wolf, { kind: "night", target });
    expect(g.night.step).toBe("seer");
    expect(g.night.wolfTarget).toBe(target);
  });

  it("预言家行动后无女巫直接结算进入 announce", () => {
    let g = makeGame6();
    const villager = aliveByRole(g, "villager")[0];
    const seerSelf = findSeatByRole(g, "seer");
    g = runNight6(g, villager, seerSelf === villager ? aliveByRole(g, "werewolf")[0] : villager);
    expect(g.phase).toBe("announce");
  });

  it("非夜晚阶段调用 nightAction 抛 WRONG_PHASE", () => {
    let g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    const villager = aliveByRole(g, "villager")[0];
    g = runNight6(g, villager, villager);
    // 现在 phase 可能是 announce 或 lastwords
    expect(g.phase).not.toBe("night");
    expect(codeOf(() => nightAction(g, wolf, { kind: "night", target: null }))).toBe(
      "WRONG_PHASE",
    );
  });

  it("不是该步骤的角色行动抛 NOT_YOUR_TURN", () => {
    const g = makeGame6();
    const seer = findSeatByRole(g, "seer");
    expect(codeOf(() => nightAction(g, seer, { kind: "night", target: null }))).toBe(
      "NOT_YOUR_TURN",
    );
  });

  it("夜晚 kind 错误抛 BAD_ACTION", () => {
    const g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    expect(codeOf(() => nightAction(g, wolf, { kind: "day", target: null }))).toBe(
      "BAD_ACTION",
    );
  });

  it("未知座位抛 UNKNOWN_SEAT", () => {
    const g = makeGame6();
    expect(codeOf(() => nightAction(g, "s99", { kind: "night", target: null }))).toBe(
      "UNKNOWN_SEAT",
    );
  });

  it("已出局玩家行动抛 DEAD_PLAYER", () => {
    let g = makeGame6();
    const villager = aliveByRole(g, "villager")[0];
    g = runNight6(g, villager, villager);
    // 让存活的狼人尝试在 announce 之后阶段行动已不适用夜晚；
    // 直接构造：手动把某狼设为出局后调 nightAction
    const wolf = findSeatByRole(g, "werewolf");
    const deadState: GameState = {
      ...g,
      phase: "night",
      players: g.players.map((p) => (p.seat === wolf ? { ...p, alive: false } : p)),
      night: { ...g.night, step: "wolves" },
    };
    expect(
      codeOf(() => nightAction(deadState, wolf, { kind: "night", target: null })),
    ).toBe("DEAD_PLAYER");
  });
});

describe("夜晚流程 - 守卫", () => {
  it("10 人局夜晚第一步为 guard", () => {
    const g = makeGame10();
    expect(g.night.step).toBe("guard");
  });

  it("守卫连续两晚守同一人抛 ILLEGAL_TARGET", () => {
    let g = makeGame10();
    const guard = findSeatByRole(g, "guard");
    const target = aliveByRole(g, "villager")[0];
    g = nightAction(g, guard, { kind: "night", target });
    expect(g.night.guardTarget).toBe(target);
    // 推进夜晚到下一夜
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target });
    const seer = findSeatByRole(g, "seer");
    const seerT = aliveByRole(g, "werewolf")[0];
    g = nightAction(g, seer, { kind: "night", target: seerT });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    // 现在应该进入 announce/lastwords
    // 直接快进到下一夜：模拟进入 announce_done 再流程
    // 若在 announce 阶段需要 announce_done
    if (g.phase === "announce") {
      g = dayAction(g, g.players[0].seat, { kind: "announce_done" });
    }
    // 可能进入 lastwords 或 speak/vote
    // 简化：手动构造下一夜：把状态 day+1 并 step guard 由 beginNight 逻辑处理
    // 用合法途径走：如进入 lastwords 就 lastwords_done，进入 speak 就依次 speak_done
    g = forceToNextNight(g);
    expect(g.phase).toBe("night");
    expect(g.night.step).toBe("guard");
    expect(g.night.lastGuardTarget).toBe(target);
    // 守卫再守同一人应抛错
    const guard2 = findSeatByRole(g, "guard");
    expect(
      codeOf(() => nightAction(g, guard2, { kind: "night", target })),
    ).toBe("ILLEGAL_TARGET");
  });

  it("守卫目标必须存活，否则 ILLEGAL_TARGET", () => {
    const g = makeGame10();
    const guard = findSeatByRole(g, "guard");
    expect(
      codeOf(() => nightAction(g, guard, { kind: "night", target: "s99" })),
    ).toBe("ILLEGAL_TARGET");
  });
});

describe("夜晚流程 - 女巫", () => {
  it("女巫 save 只能救 wolfTarget，否则 ILLEGAL_TARGET", () => {
    let g = makeGame7();
    const wolf = findSeatByRole(g, "werewolf");
    const wolfTarget = aliveByRole(g, "villager")[0];
    g = nightAction(g, wolf, { kind: "night", target: wolfTarget });
    const seer = findSeatByRole(g, "seer");
    const other = g.players.find(
      (p) => p.alive && p.seat !== wolfTarget && p.role !== "werewolf",
    )!.seat;
    g = nightAction(g, seer, { kind: "night", target: other });
    expect(g.night.step).toBe("witch");
    const witch = findSeatByRole(g, "witch");
    const wrongTarget = g.players.find(
      (p) => p.alive && p.seat !== wolfTarget && p.seat !== witch,
    )!.seat;
    expect(
      codeOf(() => nightAction(g, witch, { kind: "night", potion: "save", target: wrongTarget })),
    ).toBe("ILLEGAL_TARGET");
  });

  it("女巫首夜自救抛 ILLEGAL_TARGET", () => {
    let g = makeGame7();
    const wolf = findSeatByRole(g, "werewolf");
    const witch = findSeatByRole(g, "witch");
    // 狼刀女巫
    g = nightAction(g, wolf, { kind: "night", target: witch });
    const seer = findSeatByRole(g, "seer");
    const seerT = g.players.find((p) => p.alive && p.seat !== witch)!.seat;
    g = nightAction(g, seer, { kind: "night", target: seerT });
    expect(g.night.step).toBe("witch");
    const witchNow = findSeatByRole(g, "witch");
    expect(
      codeOf(() => nightAction(g, witchNow, { kind: "night", potion: "save", target: witchNow })),
    ).toBe("ILLEGAL_TARGET");
  });

  it("女巫 save 合法时救下狼刀目标", () => {
    let g = makeGame7();
    const wolf = findSeatByRole(g, "werewolf");
    const target = aliveByRole(g, "villager")[0];
    g = nightAction(g, wolf, { kind: "night", target });
    const seer = findSeatByRole(g, "seer");
    const seerT = g.players.find(
      (p) => p.alive && p.seat !== target && p.seat !== findSeatByRole(g, "witch"),
    )!.seat;
    g = nightAction(g, seer, { kind: "night", target: seerT });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: "save", target });
    expect(g.night.witchSaveTarget).toBe(target);
    const saved = g.players.find((p) => p.seat === target)!;
    expect(saved.alive).toBe(true);
    expect(g.deathsTonight).not.toContain(target);
  });

  it("女巫毒药 kill 毒目标，reason witch", () => {
    let g = makeGame7();
    const wolf = findSeatByRole(g, "werewolf");
    const wolfTarget = aliveByRole(g, "villager")[0];
    g = nightAction(g, wolf, { kind: "night", target: wolfTarget });
    const seer = findSeatByRole(g, "seer");
    const seerT = g.players.find(
      (p) =>
        p.alive &&
        p.seat !== wolfTarget &&
        p.seat !== findSeatByRole(g, "witch") &&
        p.role !== "werewolf",
    )!.seat;
    g = nightAction(g, seer, { kind: "night", target: seerT });
    const witch = findSeatByRole(g, "witch");
    const poisonTarget = g.players.find(
      (p) => p.alive && p.seat !== witch && p.seat !== wolfTarget,
    )!.seat;
    g = nightAction(g, witch, {
      kind: "night",
      potion: "poison",
      target: poisonTarget,
    });
    expect(g.night.witchPoisonTarget).toBe(poisonTarget);
    const dead = g.players.find((p) => p.seat === poisonTarget)!;
    expect(dead.alive).toBe(false);
    const record = g.deaths.find((d) => d.seat === poisonTarget);
    expect(record).toBeDefined();
    expect(record!.reason).toBe("witch");
  });

  it("女巫重复用解药抛 BAD_ACTION", () => {
    let g = makeGame7();
    const wolf = findSeatByRole(g, "werewolf");
    const target = aliveByRole(g, "villager")[0];
    g = nightAction(g, wolf, { kind: "night", target });
    const seer = findSeatByRole(g, "seer");
    const seerT = g.players.find(
      (p) => p.alive && p.seat !== target && p.seat !== findSeatByRole(g, "witch"),
    )!.seat;
    g = nightAction(g, seer, { kind: "night", target: seerT });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: "save", target });
    // 手动构造再入 witch 步骤检查重复用药
    const recheck: GameState = {
      ...g,
      phase: "night",
      night: { ...g.night, step: "witch" as NightStep },
      players: g.players.map((p) =>
        p.seat === witch ? { ...p, alive: true } : p,
      ),
    };
    expect(
      codeOf(() => nightAction(recheck, witch, { kind: "night", potion: "save", target })),
    ).toBe("BAD_ACTION");
  });
});

describe("夜晚结算 - 死讯与 announce", () => {
  it("狼刀目标无人守无人救则死亡，reason wolf", () => {
    let g = makeGame6();
    const target = aliveByRole(g, "villager")[0];
    g = runNight6(g, target, target);
    const p = g.players.find((x) => x.seat === target)!;
    expect(p.alive).toBe(false);
    expect(g.deathsTonight).toContain(target);
    const rec = g.deaths.find((d) => d.seat === target);
    expect(rec!.reason).toBe("wolf");
  });

  it("守卫守住狼刀目标则不死", () => {
    let g = makeGame10();
    const guard = findSeatByRole(g, "guard");
    const target = aliveByRole(g, "villager")[0];
    g = nightAction(g, guard, { kind: "night", target });
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target });
    const seer = findSeatByRole(g, "seer");
    const seerT = aliveByRole(g, "werewolf")[0];
    g = nightAction(g, seer, { kind: "night", target: seerT });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    const p = g.players.find((x) => x.seat === target)!;
    expect(p.alive).toBe(true);
    expect(g.deathsTonight).not.toContain(target);
  });

  it("进入 announce 后需要 announce_done 确认", () => {
    let g = makeGame6();
    const target = aliveByRole(g, "villager")[0];
    g = runNight6(g, target, target);
    expect(g.phase).toBe("announce");
    const any = g.players[0].seat;
    expect(codeOf(() => dayAction(g, any, { kind: "speak_done" }))).toBe("BAD_ACTION");
    g = dayAction(g, any, { kind: "announce_done" });
    expect(g.phase === "lastwords" || g.phase === "speak" || g.phase === "vote").toBe(
      true,
    );
  });

  it("有死亡进入 lastwords 遗言队列", () => {
    let g = makeGame6();
    const target = aliveByRole(g, "villager")[0];
    g = runNight6(g, target, target);
    const any = g.players[0].seat;
    g = dayAction(g, any, { kind: "announce_done" });
    expect(g.phase).toBe("lastwords");
    expect(g.lastwordsQueue).toContain(target);
  });
});

describe("猎人", () => {
  it("夜晚被狼刀死的猎人在 announce 阶段触发 hunterShootPending", () => {
    let g = makeGame10();
    const guard = findSeatByRole(g, "guard");
    const hunter = findSeatByRole(g, "hunter");
    // 守卫不守猎人
    const notHunter = g.players.find((p) => p.alive && p.seat !== hunter)!.seat;
    g = nightAction(g, guard, { kind: "night", target: notHunter });
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: hunter });
    const seer = findSeatByRole(g, "seer");
    const seerT = aliveByRole(g, "werewolf")[0];
    g = nightAction(g, seer, { kind: "night", target: seerT });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    expect(g.phase).toBe("announce");
    const any = g.players[0].seat;
    g = dayAction(g, any, { kind: "announce_done" });
    expect(g.hunterShootPending).toBe(hunter);
  });

  it("猎人只能发 hunter_shoot，其他 kind 抛 BAD_ACTION", () => {
    let g = makeGame10();
    const guard = findSeatByRole(g, "guard");
    const hunter = findSeatByRole(g, "hunter");
    const notHunter = g.players.find((p) => p.alive && p.seat !== hunter)!.seat;
    g = nightAction(g, guard, { kind: "night", target: notHunter });
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: hunter });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: aliveByRole(g, "werewolf")[0] });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    const any = g.players[0].seat;
    g = dayAction(g, any, { kind: "announce_done" });
    expect(g.hunterShootPending).toBe(hunter);
    expect(codeOf(() => dayAction(g, hunter, { kind: "speak_done" }))).toBe("BAD_ACTION");
  });

  it("猎人开枪后目标死亡 reason hunter 并进入 lastwords", () => {
    let g = makeGame10();
    const guard = findSeatByRole(g, "guard");
    const hunter = findSeatByRole(g, "hunter");
    const notHunter = g.players.find((p) => p.alive && p.seat !== hunter)!.seat;
    g = nightAction(g, guard, { kind: "night", target: notHunter });
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: hunter });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: aliveByRole(g, "werewolf")[0] });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    const any = g.players[0].seat;
    g = dayAction(g, any, { kind: "announce_done" });
    expect(g.hunterShootPending).toBe(hunter);
    const shootTarget = g.players.find(
      (p) => p.alive && p.seat !== hunter,
    )!.seat;
    g = dayAction(g, hunter, { kind: "hunter_shoot", target: shootTarget });
    const tp = g.players.find((p) => p.seat === shootTarget)!;
    expect(tp.alive).toBe(false);
    const rec = g.deaths.find((d) => d.seat === shootTarget);
    expect(rec!.reason).toBe("hunter");
    expect(g.hunterShootPending).toBeNull();
    expect(g.phase).toBe("lastwords");
    expect(g.lastwordsQueue).toContain(shootTarget);
  });
});

describe("白天流程 - speak 与 vote", () => {
  it("无死亡时进入 speak，全部发言完进入 vote", () => {
    let g = makeGame6();
    // 狼刀空
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    // 无死亡，直接进入 speak
    expect(g.phase).toBe("speak");
    // 依次发言
    let guardCount = 0;
    while (g.phase === "speak" && guardCount < 20) {
      const cur = g.currentSeat;
      g = dayAction(g, cur, { kind: "speak_done" });
      guardCount++;
    }
    expect(g.phase).toBe("vote");
  });

  it("投票全弃票无人出局进入下一夜", () => {
    let g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    let c = 0;
    while (g.phase === "speak" && c < 20) {
      g = dayAction(g, g.currentSeat, { kind: "speak_done" });
      c++;
    }
    expect(g.phase).toBe("vote");
    c = 0;
    while (g.phase === "vote" && c < 20) {
      g = dayAction(g, g.currentSeat, { kind: "vote", target: null });
      c++;
    }
    expect(g.phase).toBe("night");
    expect(g.day).toBe(2);
  });

  it("投票放逐后进入 lastwords，再下一夜", () => {
    let g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    let c = 0;
    while (g.phase === "speak" && c < 20) {
      g = dayAction(g, g.currentSeat, { kind: "speak_done" });
      c++;
    }
    // 选一个非猎人目标，避免开枪复杂化
    const voteTarget = g.players.find((p) => p.alive && p.role !== "hunter")!.seat;
    c = 0;
    while (g.phase === "vote" && c < 20) {
      g = dayAction(g, g.currentSeat, { kind: "vote", target: voteTarget });
      c++;
    }
    expect(g.phase).toBe("lastwords");
    const rec = g.deaths.find((d) => d.seat === voteTarget);
    expect(rec!.reason).toBe("vote");
    // 遗言完成
    g = dayAction(g, voteTarget, { kind: "lastwords_done" });
    expect(g.phase).toBe("night");
  });

  it("平票进入 pk_speak/pk_vote", () => {
    let g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    let c = 0;
    while (g.phase === "speak" && c < 20) {
      g = dayAction(g, g.currentSeat, { kind: "speak_done" });
      c++;
    }
    expect(g.phase).toBe("vote");
    const alive = g.players.filter((p) => p.alive).map((p) => p.seat);
    const a = alive[0];
    const b = alive[1];
    // 前两位各投一人，剩下全弃票形成 1:1 平票
    c = 0;
    while (g.phase === "vote" && c < 20) {
      const cur = g.currentSeat;
      let tgt: string | null = null;
      if (cur === a) tgt = b;
      else if (cur === b) tgt = a;
      g = dayAction(g, cur, { kind: "vote", target: tgt });
      c++;
    }
    expect(g.phase).toBe("pk_speak");
    expect(g.pkSeats.length).toBe(2);
  });

  it("pk_vote 只能投 pkSeats 里的座位", () => {
    let g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    let c = 0;
    while (g.phase === "speak" && c < 20) {
      g = dayAction(g, g.currentSeat, { kind: "speak_done" });
      c++;
    }
    const alive = g.players.filter((p) => p.alive).map((p) => p.seat);
    const a = alive[0];
    const b = alive[1];
    c = 0;
    while (g.phase === "vote" && c < 20) {
      const cur = g.currentSeat;
      let tgt: string | null = null;
      if (cur === a) tgt = b;
      else if (cur === b) tgt = a;
      g = dayAction(g, cur, { kind: "vote", target: tgt });
      c++;
    }
    expect(g.phase).toBe("pk_speak");
    // 走完 pk_speak
    c = 0;
    while (g.phase === "pk_speak" && c < 20) {
      g = dayAction(g, g.currentSeat, { kind: "speak_done" });
      c++;
    }
    expect(g.phase).toBe("pk_vote");
    // 找一个不在 pkSeats 里的存活玩家
    const outside = g.players.find(
      (p) => p.alive && !g.pkSeats.includes(p.seat),
    )?.seat;
    if (outside !== undefined) {
      const cur = g.currentSeat;
      expect(
        codeOf(() => dayAction(g, cur, { kind: "vote", target: outside })),
      ).toBe("ILLEGAL_TARGET");
    }
  });
});

describe("警长", () => {
  it("config sheriff:true，第一夜之后进入 sheriff 阶段", () => {
    let g = makeGame10(true);
    // 夜晚走完，无死亡
    const guard = findSeatByRole(g, "guard");
    const gTarget = g.players.find((p) => p.alive)!.seat;
    g = nightAction(g, guard, { kind: "night", target: gTarget });
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    expect(g.phase).toBe("sheriff");
  });

  it("最高票当选警长", () => {
    let g = makeGame10(true);
    const guard = findSeatByRole(g, "guard");
    g = nightAction(g, guard, { kind: "night", target: g.players[0].seat });
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    expect(g.phase).toBe("sheriff");
    const a = g.players[0].seat;
    const b = g.players[1].seat;
    g = dayAction(g, a, { kind: "sheriff" });
    g = dayAction(g, b, { kind: "sheriff" });
    g = dayAction(g, a, { kind: "sheriff", target: a });
    g = dayAction(g, b, { kind: "sheriff", target: a });
    g = dayAction(g, a, { kind: "sheriff_done" });
    expect(g.sheriffSeat).toBe(a);
    const sp = g.players.find((p) => p.seat === a)!;
    expect(sp.isSheriff).toBe(true);
  });

  it("平票警徽流失 sheriffSeat 为 null", () => {
    let g = makeGame10(true);
    const guard = findSeatByRole(g, "guard");
    g = nightAction(g, guard, { kind: "night", target: g.players[0].seat });
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    expect(g.phase).toBe("sheriff");
    const a = g.players[0].seat;
    const b = g.players[1].seat;
    g = dayAction(g, a, { kind: "sheriff" });
    g = dayAction(g, b, { kind: "sheriff" });
    g = dayAction(g, a, { kind: "sheriff", target: b });
    g = dayAction(g, b, { kind: "sheriff", target: a });
    g = dayAction(g, a, { kind: "sheriff_done" });
    expect(g.sheriffSeat).toBeNull();
  });

  it("上警投票目标必须是已上警玩家，否则 ILLEGAL_TARGET", () => {
    let g = makeGame10(true);
    const guard = findSeatByRole(g, "guard");
    g = nightAction(g, guard, { kind: "night", target: g.players[0].seat });
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    const witch = findSeatByRole(g, "witch");
    g = nightAction(g, witch, { kind: "night", potion: null });
    const a = g.players[0].seat;
    const b = g.players[1].seat;
    g = dayAction(g, a, { kind: "sheriff" });
    // b 未上警，a 投 b 应抛错
    expect(
      codeOf(() => dayAction(g, a, { kind: "sheriff", target: b })),
    ).toBe("ILLEGAL_TARGET");
  });
});

describe("胜负判定", () => {
  // 白天从 announce 推进到 vote，然后全体投同一目标（或全体弃票 target null）
  function runDayVote(g: GameState, target: string | null): GameState {
    let s = g;
    // 若在 announce：先确认死讯（有死亡时才需要）
    if (s.phase === "announce") {
      const anyAlive = s.players.find((p) => p.alive)!.seat;
      s = dayAction(s, anyAlive, { kind: "announce_done" });
    }
    // 若进入 lastwords：逐个遗言（夜晚死亡）
    while (s.phase === "lastwords") {
      const seat = s.currentSeat !== "" ? s.currentSeat : s.lastwordsQueue[0];
      s = dayAction(s, seat, { kind: "lastwords_done" });
    }
    // 无死亡则可能直接进入 speak
    while (s.phase === "speak") {
      const seat = s.currentSeat !== "" ? s.currentSeat : s.players.find((p) => p.alive)!.seat;
      s = dayAction(s, seat, { kind: "speak_done" });
    }
    // vote：全体按 currentSeat 顺序投票
    while (s.phase === "vote") {
      const seat = s.currentSeat !== "" ? s.currentSeat : s.players.find((p) => p.alive)!.seat;
      s = dayAction(s, seat, { kind: "vote", target });
    }
    // 投票放逐产生新的遗言，排完
    while (s.phase === "lastwords") {
      const seat = s.currentSeat !== "" ? s.currentSeat : s.lastwordsQueue[0];
      s = dayAction(s, seat, { kind: "lastwords_done" });
    }
    return s;
  }

  it("杀光所有狼好人胜", () => {
    let g = makeGame6();
    const wolf1 = findSeatByRole(g, "werewolf");
    const seer1 = findSeatByRole(g, "seer");
    const villager1 = aliveByRole(g, "villager")[0];
    // night1：狼空刀、预言家查验 wolf1（不能查验自己；空刀无死亡故进 speak）
    g = runNight6(g, null as any, wolf1);
    expect(g.phase).toBe("speak");
    // day1 全体投 wolf1
    g = runDayVote(g, wolf1);
    // 遗言已在 runDayVote 中走完；此时应进入 night2
    expect(g.phase).toBe("night");
    // night2：狼刀一个平民、预言家查验
    const wolfAlive = aliveByRole(g, "werewolf")[0];
    g = runNight6(g, villager1, wolfAlive);
    // 白天处理遗言后投票放逐 wolf2
    expect(g.phase).toBe("announce");
    const wolf2 = aliveByRole(g, "werewolf")[0];
    g = runDayVote(g, wolf2);
    // 狼全灭 -> applyWinner 判定好人胜
    expect(g.phase).toBe("finished");
    expect(g.winner).toBe("good");
  });

  it("杀光所有平民狼胜", () => {
    let g = makeGame6();
    const wolfSeat = findSeatByRole(g, "werewolf");
    const seerSeat = findSeatByRole(g, "seer");

    // night1 狼刀 villager1
    let v1 = aliveByRole(g, "villager")[0];
    g = runNight6(g, v1, wolfSeat);
    // day1 全体弃票
    g = runDayVote(g, null);
    expect(g.phase).toBe("night");

    // night2 狼刀 villager2
    let v2 = aliveByRole(g, "villager")[0];
    g = runNight6(g, v2, wolfSeat);
    // day2 全体弃票
    g = runDayVote(g, null);
    expect(g.phase).toBe("night");

    // night3 狼刀最后一个 villager3
    let v3 = aliveByRole(g, "villager")[0];
    g = runNight6(g, v3, wolfSeat);
    // 平民全灭 -> applyWinner 判定狼胜
    expect(g.phase).toBe("finished");
    expect(g.winner).toBe("wolves");
  });

  it("杀光神职狼胜（10 人局有守卫）", () => {
    let g = makeGame10();
    const guard = findSeatByRole(g, "guard");
    const wolf = findSeatByRole(g, "werewolf");
    const seer = findSeatByRole(g, "seer");
    const witch = findSeatByRole(g, "witch");

    // 4 个夜晚：按 seer -> witch -> guard -> hunter 顺序杀神职，猎人最后
    const killOrder: Role[] = ["seer", "witch", "guard", "hunter"];
    for (let i = 0; i < killOrder.length; i++) {
      const target = findSeatByRole(g, killOrder[i]);
      // guard 跳过（守卫存活且当前 step 为 guard 时才行动）
      if (g.players.find((p) => p.seat === guard)?.alive && g.night?.step === "guard") {
        g = nightAction(g, guard, { kind: "night", target: null});
      }
      // 狼刀神职
      g = nightAction(g, wolf, { kind: "night", target });
      // 预言家查验任意存活者（若预言家已死则跳过该步）
      const seerAlive = g.players.find((p) => p.seat === seer && p.alive);
      if (seerAlive && g.night.step === "seer") {
        const checkTarget = g.players.find((p) => p.alive && p.seat !== seer)!.seat;
        g = nightAction(g, seer, { kind: "night", target: checkTarget });
      }
      // 女巫不用药（若女巫已死则跳过该步）
      const witchAlive = g.players.find((p) => p.seat === witch && p.alive);
      if (witchAlive && g.night.step === "witch") {
        g = nightAction(g, witch, { kind: "night", potion: null });
      }
      // 白天全体弃票
      g = runDayVote(g, null);
    }

    // 神职全灭 -> applyWinner 判定狼胜
    expect(g.phase).toBe("finished");
    expect(g.winner).toBe("wolves");
  });
});

describe("serializeForSeat", () => {
  it("狼人视角能看到 wolfSeats", () => {
    const g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    const view = serializeForSeat(g, wolf) as {
      wolfSeats?: string[];
      players: { seat: string; role?: Role }[];
    };
    expect(view.wolfSeats).toBeDefined();
    const wolves = g.players.filter((p) => p.role === "werewolf").map((p) => p.seat);
    expect(view.wolfSeats!.sort()).toEqual(wolves.sort());
  });

  it("预言家视角有 seerHistory 和 seerResult", () => {
    let g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    const target = aliveByRole(g, "villager")[0];
    g = nightAction(g, wolf, { kind: "night", target });
    const seer = findSeatByRole(g, "seer");
    const checkTarget = g.players.find(
      (p) => p.alive && p.seat !== seer && p.seat !== target,
    )!.seat;
    g = nightAction(g, seer, { kind: "night", target: checkTarget });
    const view = serializeForSeat(g, seer) as {
      seerHistory?: { day: number; target: string; result: "wolf" | "good" }[];
      seerResult?: "wolf" | "good" | null;
    };
    expect(view.seerHistory).toBeDefined();
    expect(view.seerHistory!.length).toBe(1);
    expect(view.seerHistory![0].target).toBe(checkTarget);
    expect(view.seerResult).toBeDefined();
  });

  it("其他玩家视角看不到他人 role", () => {
    const g = makeGame6();
    const villager = aliveByRole(g, "villager")[0];
    const view = serializeForSeat(g, villager) as {
      players: { seat: string; role?: Role }[];
    };
    for (const p of view.players) {
      if (p.seat === villager) {
        expect(p.role).toBe("villager");
      } else {
        expect(p.role).toBeUndefined();
      }
    }
  });

  it("女巫在 witch 步骤能看到 wolfTarget，其他步骤看不到", () => {
    let g = makeGame7();
    const wolf = findSeatByRole(g, "werewolf");
    const wolfTarget = aliveByRole(g, "villager")[0];
    g = nightAction(g, wolf, { kind: "night", target: wolfTarget });
    const seer = findSeatByRole(g, "seer");
    const seerT = g.players.find(
      (p) =>
        p.alive &&
        p.seat !== wolfTarget &&
        p.seat !== findSeatByRole(g, "witch"),
    )!.seat;
    g = nightAction(g, seer, { kind: "night", target: seerT });
    expect(g.night.step).toBe("witch");
    const witch = findSeatByRole(g, "witch");
    const view1 = serializeForSeat(g, witch) as { wolfTarget?: string | null };
    expect(view1.wolfTarget).toBe(wolfTarget);

    // 非 witch 步骤：手动构造 wolves 步骤
    const other: GameState = {
      ...g,
      night: { ...g.night, step: "wolves" as NightStep },
    };
    const view2 = serializeForSeat(other, witch) as { wolfTarget?: string | null };
    expect(view2.wolfTarget).toBeUndefined();
  });
});

describe("纯函数性 - 不修改入参 state", () => {
  it("nightAction 不修改入参 state", () => {
    const g = makeGame6();
    const snapshot = JSON.stringify({
      players: g.players,
      night: g.night,
      deaths: g.deaths,
      deathsTonight: g.deathsTonight,
      phase: g.phase,
      day: g.day,
    });
    const wolf = findSeatByRole(g, "werewolf");
    const target = aliveByRole(g, "villager")[0];
    nightAction(g, wolf, { kind: "night", target });
    const after = JSON.stringify({
      players: g.players,
      night: g.night,
      deaths: g.deaths,
      deathsTonight: g.deathsTonight,
      phase: g.phase,
      day: g.day,
    });
    expect(after).toBe(snapshot);
  });

  it("dayAction 不修改入参 state", () => {
    let g = makeGame6();
    const wolf = findSeatByRole(g, "werewolf");
    g = nightAction(g, wolf, { kind: "night", target: null });
    const seer = findSeatByRole(g, "seer");
    g = nightAction(g, seer, { kind: "night", target: null });
    expect(g.phase).toBe("speak");
    const snapshot = JSON.stringify({
      players: g.players,
      night: g.night,
      spokenSeats: g.spokenSeats,
      currentSeat: g.currentSeat,
      phase: g.phase,
    });
    dayAction(g, g.currentSeat, { kind: "speak_done" });
    const after = JSON.stringify({
      players: g.players,
      night: g.night,
      spokenSeats: g.spokenSeats,
      currentSeat: g.currentSeat,
      phase: g.phase,
    });
    expect(after).toBe(snapshot);
  });
});

// 辅助：把状态推进到下一夜。只用于测试中，让当前白天/遗言流程走到 next night。
function forceToNextNight(g: GameState): GameState {
  let s = g;
  let guard = 0;
  while (s.phase !== "night" && s.phase !== "finished" && guard < 50) {
    guard++;
    if (s.phase === "announce") {
      const alive = s.players.find((p) => p.alive);
      if (!alive) return s;
      s = dayAction(s, alive.seat, { kind: "announce_done" });
      continue;
    }
    if (s.phase === "lastwords") {
      const cur = s.lastwordsQueue[0] ?? s.currentSeat;
      if (!cur) {
        const alive = s.players.find((p) => p.alive);
        if (!alive) return s;
        s = dayAction(s, alive.seat, { kind: "lastwords_done" });
        continue;
      }
      s = dayAction(s, cur, { kind: "lastwords_done" });
      continue;
    }
    if (s.phase === "sheriff") {
      const alive = s.players.find((p) => p.alive);
      if (!alive) return s;
      s = dayAction(s, alive.seat, { kind: "sheriff_done" });
      continue;
    }
    if (s.phase === "speak") {
      const cur = s.currentSeat;
      if (!cur) {
        const alive = s.players.find((p) => p.alive);
        if (!alive) return s;
        s = dayAction(s, alive.seat, { kind: "speak_done" });
        continue;
      }
      s = dayAction(s, cur, { kind: "speak_done" });
      continue;
    }
    if (s.phase === "vote") {
      const cur = s.currentSeat;
      if (!cur) {
        const alive = s.players.find((p) => p.alive);
        if (!alive) return s;
        s = dayAction(s, alive.seat, { kind: "vote", target: null });
        continue;
      }
      s = dayAction(s, cur, { kind: "vote", target: null });
      continue;
    }
    if (s.phase === "pk_speak") {
      const cur = s.currentSeat;
      if (!cur) {
        const alive = s.players.find((p) => p.alive);
        if (!alive) return s;
        s = dayAction(s, alive.seat, { kind: "speak_done" });
        continue;
      }
      s = dayAction(s, cur, { kind: "speak_done" });
      continue;
    }
    if (s.phase === "pk_vote") {
      const cur = s.currentSeat;
      if (!cur) {
        const alive = s.players.find((p) => p.alive);
        if (!alive) return s;
        s = dayAction(s, alive.seat, { kind: "vote", target: null });
        continue;
      }
      s = dayAction(s, cur, { kind: "vote", target: null });
      continue;
    }
    break;
  }
  return s;
}
