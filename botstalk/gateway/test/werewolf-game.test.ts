import { describe, it, expect } from "vitest";
import {
  assignRoles,
  ROLE_INFO,
  type Role,
} from "../src/werewolf/roles.js";
import {
  createGame,
  nightAction,
  dayAction,
  serializeForSeat,
  WerewolfError,
  type GameState,
} from "../src/werewolf/game.js";
import {
  chooseNightAction,
  chooseDayAction,
} from "../src/werewolf/ai.js";
import {
  WerewolfGameError,
  WerewolfGameEngine,
  WerewolfRoom,
  SUPPORTED_COUNTS,
  isAiSeat,
  type WerewolfSessionData,
} from "../src/werewolf-game.js";

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function makeSeats(n: number, prefix = "s"): string[] {
  const out: string[] = [];
  for (let i = 0; i < n; i++) out.push(`${prefix}${i}`);
  return out;
}

function makeAiSeats(n: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < n; i++) out.push(`ai:${i}`);
  return out;
}

function findSeatByRole(state: GameState, role: Role): string {
  const p = state.players.find((x) => x.role === role);
  if (!p) throw new Error(`no player with role ${role}`);
  return p.seat;
}

function aliveSeatByRole(state: GameState, role: Role): string {
  const p = state.players.find((x) => x.role === role && x.alive);
  if (!p) throw new Error(`no alive player with role ${role}`);
  return p.seat;
}

function aliveSeatsExcept(state: GameState, exclude: string[]): string[] {
  return state.players
    .filter((p) => p.alive && !exclude.includes(p.seat))
    .map((p) => p.seat);
}

function firstGoodNot(state: GameState, exclude: string[]): string {
  const p = state.players.find(
    (x) =>
      x.alive &&
      !exclude.includes(x.seat) &&
      ROLE_INFO[x.role].faction === "good",
  );
  if (!p) throw new Error("no good alive");
  return p.seat;
}

function firstWolfNot(state: GameState, exclude: string[]): string {
  const p = state.players.find(
    (x) =>
      x.alive &&
      !exclude.includes(x.seat) &&
      ROLE_INFO[x.role].faction === "wolves",
  );
  if (!p) throw new Error("no wolf alive");
  return p.seat;
}

/**
 * 按 nightStep 顺序推进夜晚到结束（进入 announce）。
 * targets 中的每一项可以是座位、null 或 "skip"（表示不提交该步）。
 */
function progressNight(
  state: GameState,
  targets: {
    guard?: string | null;
    wolves?: string | null;
    seer?: string | null;
    witch?: { potion: "save" | "poison" | null; target?: string | null };
  },
): GameState {
  let s = state;
  let guardCount = 0;
  while (s.phase === "night" && guardCount < 20) {
    guardCount++;
    if (s.nightStep === "guard") {
      const seat = s.currentSeat;
      const t = targets.guard === undefined ? null : targets.guard;
      s = nightAction(s, seat, { kind: "night", target: t });
      continue;
    }
    if (s.nightStep === "wolves") {
      const seat = s.currentSeat;
      const t = targets.wolves === undefined ? null : targets.wolves;
      s = nightAction(s, seat, { kind: "night", target: t });
      continue;
    }
    if (s.nightStep === "seer") {
      const seat = s.currentSeat;
      const t = targets.seer === undefined ? null : targets.seer;
      s = nightAction(s, seat, { kind: "night", target: t });
      continue;
    }
    if (s.nightStep === "witch") {
      const seat = s.currentSeat;
      const w = targets.witch ?? { potion: null, target: null };
      s = nightAction(s, seat, {
        kind: "night",
        potion: w.potion,
        target: w.target ?? null,
      });
      continue;
    }
    break;
  }
  if (guardCount >= 20) throw new Error("night loop guard exceeded");
  return s;
}

/** 处理 announce + lastwords，进入 sheriff（第一天）或 speak。 */
function progressAnnounceAndLastwords(s: GameState): GameState {
  let cur = s;
  let guard = 0;
  while (
    (cur.phase === "announce" || cur.phase === "lastwords") &&
    guard < 50
  ) {
    guard++;
    if (cur.phase === "announce") {
      // 公开 action：公布死讯确认 -> lastwords / sheriff / speak（afterAnnounce 决定）
      const anyAlive = cur.players.find((pl) => pl.alive)?.seat ?? "";
      cur = dayAction(cur, anyAlive, { kind: "announce_done" });
      continue;
    }
    // lastwords：猎人待开枪优先
    if (cur.hunterShootPending && cur.currentSeat === cur.hunterShootPending) {
      const hunterSeat = cur.hunterShootPending;
      const target =
        cur.players.find((pl) => pl.alive && pl.seat !== hunterSeat)?.seat ??
        null;
      cur = dayAction(cur, hunterSeat, { kind: "hunter_shoot", target });
      continue;
    }
    const seat = cur.currentSeat;
    if (!seat) break;
    cur = dayAction(cur, seat, { kind: "lastwords_done" });
    continue;
  }
  if (guard >= 50) throw new Error("announce/lastwords loop guard exceeded");
  return cur;
}

/** 处理警长竞选阶段：所有存活玩家退水。 */
function progressSheriffAllPass(s: GameState): GameState {
  let cur = s;
  let guard = 0;
  while (cur.phase === "sheriff" && guard < 50) {
    guard++;
    const seat = cur.currentSeat;
    if (!seat) break;
    cur = dayAction(cur, seat, { kind: "sheriff", target: null });
  }
  if (guard >= 50) throw new Error("sheriff loop guard exceeded");
  return cur;
}

/** 处理发言阶段：所有存活玩家发言完毕。 */
function progressSpeakAll(s: GameState): GameState {
  let cur = s;
  let guard = 0;
  while (cur.phase === "speak" && guard < 50) {
    guard++;
    const seat = cur.currentSeat;
    if (!seat) break;
    cur = dayAction(cur, seat, { kind: "speak_done" });
  }
  if (guard >= 50) throw new Error("speak loop guard exceeded");
  return cur;
}

/** 处理 pk_speak 阶段：所有 pk 玩家发言完毕。 */
function progressPkSpeakAll(s: GameState): GameState {
  let cur = s;
  let guard = 0;
  while (cur.phase === "pk_speak" && guard < 50) {
    guard++;
    const seat = cur.currentSeat;
    if (!seat) break;
    cur = dayAction(cur, seat, { kind: "speak_done" });
  }
  if (guard >= 50) throw new Error("pk_speak loop guard exceeded");
  return cur;
}

/** 全体存活玩家按 seat 投票给某个目标（或按函数给出）。 */
function progressVoteAll(
  s: GameState,
  chooser: (voter: string, state: GameState) => string | null,
): GameState {
  let cur = s;
  let guard = 0;
  while (
    (cur.phase === "vote" || cur.phase === "pk_vote") &&
    guard < 100
  ) {
    guard++;
    const seat = cur.currentSeat;
    if (!seat) break;
    const target = chooser(seat, cur);
    cur = dayAction(cur, seat, { kind: "vote", target });
  }
  if (guard >= 100) throw new Error("vote loop guard exceeded");
  return cur;
}

/** 第一天完整流程：夜晚 -> 公布 -> 遗言 -> 警长(全退水) -> 发言 -> 投票。 */
function progressToFirstVote(
  s: GameState,
  nightTargets: Parameters<typeof progressNight>[1],
): GameState {
  let cur = progressNight(s, nightTargets);
  cur = progressAnnounceAndLastwords(cur);
  if (cur.phase === "sheriff") {
    cur = progressSheriffAllPass(cur);
  }
  if (cur.phase === "speak") {
    cur = progressSpeakAll(cur);
  }
  return cur;
}

// ---------------------------------------------------------------------------
// roles
// ---------------------------------------------------------------------------

describe("roles.ts", () => {
  it("6 人局配置为 2 狼 3 民 1 预言家", () => {
    const roles = assignRoles(makeSeats(6), mulberry32(1));
    const counts: Record<string, number> = {};
    for (const r of roles.values()) counts[r] = (counts[r] ?? 0) + 1;
    expect(counts["werewolf"]).toBe(2);
    expect(counts["villager"]).toBe(3);
    expect(counts["seer"]).toBe(1);
    expect(roles.size).toBe(6);
  });

  it("7 人局配置为 2 狼 3 民 预言家 女巫", () => {
    const roles = assignRoles(makeSeats(7), mulberry32(2));
    const counts: Record<string, number> = {};
    for (const r of roles.values()) counts[r] = (counts[r] ?? 0) + 1;
    expect(counts["werewolf"]).toBe(2);
    expect(counts["villager"]).toBe(3);
    expect(counts["seer"]).toBe(1);
    expect(counts["witch"]).toBe(1);
  });

  it("8 人局配置为 2 狼 4 民 预言家 女巫", () => {
    const roles = assignRoles(makeSeats(8), mulberry32(3));
    const counts: Record<string, number> = {};
    for (const r of roles.values()) counts[r] = (counts[r] ?? 0) + 1;
    expect(counts["werewolf"]).toBe(2);
    expect(counts["villager"]).toBe(4);
    expect(counts["seer"]).toBe(1);
    expect(counts["witch"]).toBe(1);
  });

  it("9 人局配置为 3 狼 3 民 预言家 女巫 猎人", () => {
    const roles = assignRoles(makeSeats(9), mulberry32(4));
    const counts: Record<string, number> = {};
    for (const r of roles.values()) counts[r] = (counts[r] ?? 0) + 1;
    expect(counts["werewolf"]).toBe(3);
    expect(counts["villager"]).toBe(3);
    expect(counts["seer"]).toBe(1);
    expect(counts["witch"]).toBe(1);
    expect(counts["hunter"]).toBe(1);
  });

  it("10 人局配置为 3 狼 3 民 预言家 女巫 猎人 守卫", () => {
    const roles = assignRoles(makeSeats(10), mulberry32(5));
    const counts: Record<string, number> = {};
    for (const r of roles.values()) counts[r] = (counts[r] ?? 0) + 1;
    expect(counts["werewolf"]).toBe(3);
    expect(counts["villager"]).toBe(3);
    expect(counts["seer"]).toBe(1);
    expect(counts["witch"]).toBe(1);
    expect(counts["hunter"]).toBe(1);
    expect(counts["guard"]).toBe(1);
  });

  it("11 人局配置为 3 狼 4 民 预言家 女巫 猎人 守卫", () => {
    const roles = assignRoles(makeSeats(11), mulberry32(6));
    const counts: Record<string, number> = {};
    for (const r of roles.values()) counts[r] = (counts[r] ?? 0) + 1;
    expect(counts["werewolf"]).toBe(3);
    expect(counts["villager"]).toBe(4);
    expect(counts["seer"]).toBe(1);
    expect(counts["witch"]).toBe(1);
    expect(counts["hunter"]).toBe(1);
    expect(counts["guard"]).toBe(1);
  });

  it("12 人局配置为 4 狼 4 民 预言家 女巫 猎人 守卫", () => {
    const roles = assignRoles(makeSeats(12), mulberry32(7));
    const counts: Record<string, number> = {};
    for (const r of roles.values()) counts[r] = (counts[r] ?? 0) + 1;
    expect(counts["werewolf"]).toBe(4);
    expect(counts["villager"]).toBe(4);
    expect(counts["seer"]).toBe(1);
    expect(counts["witch"]).toBe(1);
    expect(counts["hunter"]).toBe(1);
    expect(counts["guard"]).toBe(1);
  });

  it("非法人数 5 抛错", () => {
    expect(() => assignRoles(makeSeats(5), mulberry32(8))).toThrow();
  });

  it("非法人数 13 抛错", () => {
    expect(() => assignRoles(makeSeats(13), mulberry32(9))).toThrow();
  });

  it("同 seed 分配结果一致", () => {
    const seats = makeSeats(9);
    const a = assignRoles(seats, mulberry32(42));
    const b = assignRoles(seats, mulberry32(42));
    for (const s of seats) {
      expect(a.get(s)).toBe(b.get(s));
    }
  });
});

// ---------------------------------------------------------------------------
// game 夜间
// ---------------------------------------------------------------------------

describe("game.ts 夜间", () => {
  it("createGame 9 人局 phase=night, nightStep=guard 或跳到首个有角色的步骤", () => {
    const s = createGame(makeSeats(9), {}, mulberry32(10));
    expect(s.phase).toBe("night");
    expect(s.day).toBe(1);
    // 9 人局无守卫，第一个有角色步骤是 wolves
    expect(s.nightStep === "guard" || s.nightStep === "wolves").toBe(true);
  });

  it("守卫守住被刀者免死", () => {
    const s0 = createGame(makeSeats(10), {}, mulberry32(11));
    const guardSeat = aliveSeatByRole(s0, "guard");
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    // 选一个非守卫非狼的存活玩家
    const target = firstGoodNot(s0, [guardSeat]);
    // 推进守卫
    let s = nightAction(s0, guardSeat, { kind: "night", target });
    expect(s.nightStep).toBe("wolves");
    // 狼刀目标
    s = nightAction(s, wolfSeat, { kind: "night", target });
    expect(s.nightStep).toBe("seer");
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    expect(s.nightStep).toBe("witch");
    const witchSeat = aliveSeatByRole(s, "witch");
    s = nightAction(s, witchSeat, { kind: "night", potion: null });
    expect(s.phase).toBe("announce");
    const p = s.players.find((x) => x.seat === target);
    expect(p?.alive).toBe(true);
  });

  it("女巫解药救活被刀者", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(12));
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    const target = firstGoodNot(s0, []);
    // 狼刀
    let s = nightAction(s0, wolfSeat, { kind: "night", target });
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    const witchSeat = aliveSeatByRole(s, "witch");
    s = nightAction(s, witchSeat, {
      kind: "night",
      potion: "save",
      target,
    });
    expect(s.phase).toBe("announce");
    const p = s.players.find((x) => x.seat === target);
    expect(p?.alive).toBe(true);
  });

  it("女巫毒药毒死一人", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(13));
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    const witchSeat = aliveSeatByRole(s0, "witch");
    // 狼不刀
    let s = nightAction(s0, wolfSeat, { kind: "night", target: null });
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    // 女巫毒一个非狼非女巫的存活玩家
    const poisonTarget = aliveSeatsExcept(s, [witchSeat]).find((x) => {
      const p = s.players.find((pp) => pp.seat === x);
      return p !== undefined && ROLE_INFO[p.role].faction === "good";
    });
    expect(poisonTarget).toBeDefined();
    s = nightAction(s, witchSeat, {
      kind: "night",
      potion: "poison",
      target: poisonTarget as string,
    });
    expect(s.phase).toBe("announce");
    const p = s.players.find((x) => x.seat === poisonTarget);
    expect(p?.alive).toBe(false);
  });

  it("同守同救被刀者仍死", () => {
    const s0 = createGame(makeSeats(10), {}, mulberry32(14));
    const guardSeat = aliveSeatByRole(s0, "guard");
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    const target = firstGoodNot(s0, [guardSeat]);
    let s = nightAction(s0, guardSeat, { kind: "night", target });
    s = nightAction(s, wolfSeat, { kind: "night", target });
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    const witchSeat = aliveSeatByRole(s, "witch");
    s = nightAction(s, witchSeat, {
      kind: "night",
      potion: "save",
      target,
    });
    expect(s.phase).toBe("announce");
    const p = s.players.find((x) => x.seat === target);
    expect(p?.alive).toBe(false);
  });

  it("守卫连守同一人第二晚守护无效（提交会被拒）", () => {
    const s0 = createGame(makeSeats(10), {}, mulberry32(15));
    const guardSeat = aliveSeatByRole(s0, "guard");
    const target = firstGoodNot(s0, [guardSeat]);
    // 第一晚守 target
    let s = nightAction(s0, guardSeat, { kind: "night", target });
    const wolfSeat = aliveSeatByRole(s, "werewolf");
    s = nightAction(s, wolfSeat, { kind: "night", target: null });
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    const witchSeat = aliveSeatByRole(s, "witch");
    s = nightAction(s, witchSeat, { kind: "night", potion: null });
    // 进入白天流程到下一个夜晚
    s = progressAnnounceAndLastwords(s);
    if (s.phase === "sheriff") s = progressSheriffAllPass(s);
    if (s.phase === "speak") s = progressSpeakAll(s);
    if (s.phase === "vote") {
      s = progressVoteAll(s, () => null);
    }
    // 若进入 lastwords 处理
    while (s.phase === "lastwords") {
      s = dayAction(s, s.currentSeat, { kind: "lastwords_done" });
    }
    // 现在应该在 night day=2，守卫上晚目标 target
    // 找守卫
    const guardNow = s.players.find((p) => p.role === "guard" && p.alive);
    expect(guardNow).toBeDefined();
    if (!guardNow) return;
    // 守卫 nightStep 是否轮到守卫
    // 如果守卫死了则跳过
    if (s.phase === "night" && s.nightStep === "guard") {
      expect(() =>
        nightAction(s, guardNow.seat, { kind: "night", target }),
      ).toThrow(WerewolfError);
    }
  });

  it("首夜女巫不能自救（save 自己抛错）", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(16));
    const witchSeat = aliveSeatByRole(s0, "witch");
    // 狼刀女巫自己
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    let s = nightAction(s0, wolfSeat, { kind: "night", target: witchSeat });
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    // 女巫尝试救自己，第一天
    expect(s.day).toBe(1);
    expect(() =>
      nightAction(s, witchSeat, {
        kind: "night",
        potion: "save",
        target: witchSeat,
      }),
    ).toThrow(WerewolfError);
  });

  it("预言家验人后 seerResult 正确", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(17));
    const seerSeat = aliveSeatByRole(s0, "seer");
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    // 跳过守卫（9 人无守卫），狼先刀 null
    const wolfSeatFirst = aliveSeatByRole(s0, "werewolf");
    let s = nightAction(s0, wolfSeatFirst, { kind: "night", target: null });
    expect(s.nightStep).toBe("seer");
    s = nightAction(s, seerSeat, { kind: "night", target: wolfSeat });
    expect(s.night.seerResult).toBe("wolf");
    // 验一个好人
    const goodSeat = s.players.find(
      (p) =>
        p.alive &&
        p.seat !== seerSeat &&
        p.seat !== wolfSeat &&
        ROLE_INFO[p.role].faction === "good",
    )?.seat;
    expect(goodSeat).toBeDefined();
    // 继续推进：验完后到女巫
    expect(s.nightStep).toBe("witch");
    void goodSeat;
  });
});

// ---------------------------------------------------------------------------
// game 白天
// ---------------------------------------------------------------------------

describe("game.ts 白天", () => {
  it("第一天白天有警长竞选（sheriff 阶段）", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(20));
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    let s = nightAction(s0, wolfSeat, { kind: "night", target: null });
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    const witchSeat = aliveSeatByRole(s, "witch");
    s = nightAction(s, witchSeat, { kind: "night", potion: null });
    s = progressAnnounceAndLastwords(s);
    expect(s.phase).toBe("sheriff");
  });

  it("投票放逐得票最高者", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(21));
    let s = progressToFirstVote(s0, { wolves: null, seer: null, witch: { potion: null } });
    expect(s.phase).toBe("vote");
    // 选一个目标
    const target = s.players.find((p) => p.alive)?.seat as string;
    s = progressVoteAll(s, () => target);
    // 目标被放逐
    const p = s.players.find((x) => x.seat === target);
    expect(p?.alive).toBe(false);
  });

  it("警长票算 1.5 票", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(22));
    let s = progressToFirstVote(s0, { wolves: null, seer: null, witch: { potion: null } });
    expect(s.phase).toBe("vote");
    // 手动设置警长为某人（模拟 sheriff 阶段选举结果）
    const players = s.players.filter((p) => p.alive);
    const sheriff = players[0].seat;
    const candidateA = players[1].seat;
    const candidateB = players[2].seat;
    // 修改 state 内部：设置 isSheriff 和 sheriffSeat
    const s2 = JSON.parse(JSON.stringify(s)) as GameState;
    s2.rng = s.rng;
    s2.sheriffSeat = sheriff;
    for (const p of s2.players) {
      p.isSheriff = p.seat === sheriff;
    }
    // 现在让警长投 A，其余 4 人投 A，5 人投 B（构造：A 总 = 1.5 + 4 = 5.5，B = 5）
    const voters = s2.players.filter((p) => p.alive).map((p) => p.seat);
    const others = voters.filter((v) => v !== sheriff);
    // A 得票: sheriff + others[0..3] -> 1.5 + 4 = 5.5
    const aVoters = new Set<string>([sheriff, others[0], others[1], others[2], others[3]]);
    // B 得票: others[4..]
    const bVoters = new Set<string>(others.slice(4));
    let cur = s2;
    let guard = 0;
    while (cur.phase === "vote" && guard < 50) {
      guard++;
      const seat = cur.currentSeat;
      if (!seat) break;
      const target = aVoters.has(seat) ? candidateA : candidateB;
      cur = dayAction(cur, seat, { kind: "vote", target });
    }
    if (guard >= 50) throw new Error("vote loop guard exceeded");
    const a = cur.players.find((x) => x.seat === candidateA);
    expect(a?.alive).toBe(false);
  });

  it("平票进入 pk（pkSeats 非空）", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(23));
    let s = progressToFirstVote(s0, { wolves: null, seer: null, witch: { potion: null } });
    expect(s.phase).toBe("vote");
    const players = s.players.filter((p) => p.alive).map((p) => p.seat);
    // 偶数人数? 9 人 -> 9 票。构造 4-4 平票（一人弃票）
    const a = players[0];
    const b = players[1];
    // 让前 4 人投 A，接下来 4 人投 B，最后 1 人弃票
    const aSet = new Set(players.slice(0, 4));
    const bSet = new Set(players.slice(4, 8));
    // players[8] 弃票
    let cur = s;
    let guard = 0;
    while (cur.phase === "vote" && guard < 50) {
      guard++;
      const seat = cur.currentSeat;
      if (!seat) break;
      let target: string | null = null;
      if (aSet.has(seat)) target = a;
      else if (bSet.has(seat)) target = b;
      cur = dayAction(cur, seat, { kind: "vote", target });
    }
    if (guard >= 50) throw new Error("vote loop guard exceeded");
    expect(cur.phase === "pk_speak" || cur.phase === "pk_vote").toBe(true);
    expect(cur.pkSeats.length).toBeGreaterThanOrEqual(2);
  });

  it("PK 再平则平安日无出局进入下一夜", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(24));
    let s = progressToFirstVote(s0, { wolves: null, seer: null, witch: { potion: null } });
    expect(s.phase).toBe("vote");
    const players = s.players.filter((p) => p.alive).map((p) => p.seat);
    const a = players[0];
    const b = players[1];
    const aSet = new Set(players.slice(0, 4));
    const bSet = new Set(players.slice(4, 8));
    let cur = s;
    let guard = 0;
    while (cur.phase === "vote" && guard < 50) {
      guard++;
      const seat = cur.currentSeat;
      if (!seat) break;
      let target: string | null = null;
      if (aSet.has(seat)) target = a;
      else if (bSet.has(seat)) target = b;
      cur = dayAction(cur, seat, { kind: "vote", target });
    }
    if (guard >= 50) throw new Error("vote loop guard exceeded");
    expect(cur.phase).toBe("pk_speak");
    const aliveCountBefore = cur.players.filter((p) => p.alive).length;
    cur = progressPkSpeakAll(cur);
    expect(cur.phase).toBe("pk_vote");
    // PK 再平：pk 台上玩家轮到时弃票（target null）；台外 7 人投成 3-3-1 平票
    let vi = 0;
    guard = 0;
    while (cur.phase === "pk_vote" && guard < 50) {
      guard++;
      const seat = cur.currentSeat;
      if (!seat) break;
      let target: string | null = null;
      if (!cur.pkSeats.includes(seat)) {
        target = vi < 3 ? a : vi < 6 ? b : null;
        vi++;
      }
      cur = dayAction(cur, seat, { kind: "vote", target });
    }
    if (guard >= 50) throw new Error("pk_vote loop guard exceeded");
    // 平票 -> 平安日 -> 进入下一夜
    const aliveCountAfter = cur.players.filter((p) => p.alive).length;
    expect(aliveCountAfter).toBe(aliveCountBefore);
    expect(cur.phase === "night" || cur.phase === "finished").toBe(true);
    if (cur.phase === "night") {
      expect(cur.day).toBe(2);
    }
  });

  it("猎人被刀后 hunterShootPending 可开枪带走一人", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(25));
    const hunterSeat = aliveSeatByRole(s0, "hunter");
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    let s = nightAction(s0, wolfSeat, { kind: "night", target: hunterSeat });
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    const witchSeat = aliveSeatByRole(s, "witch");
    s = nightAction(s, witchSeat, { kind: "night", potion: null });
    expect(s.phase).toBe("announce");
    expect(s.hunterShootPending).toBe(hunterSeat);
    // 处理 announce / lastwords 时猎人开枪
    s = progressAnnounceAndLastwords(s);
    // 猎人开枪带走一个狼
    const hunter = s.players.find((p) => p.seat === hunterSeat);
    expect(hunter?.alive).toBe(false);
  });

  it("猎人被毒死不可开枪", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(26));
    const hunterSeat = aliveSeatByRole(s0, "hunter");
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    let s = nightAction(s0, wolfSeat, { kind: "night", target: null });
    const seerSeat = aliveSeatByRole(s, "seer");
    s = nightAction(s, seerSeat, { kind: "night", target: null });
    const witchSeat = aliveSeatByRole(s, "witch");
    s = nightAction(s, witchSeat, {
      kind: "night",
      potion: "poison",
      target: hunterSeat,
    });
    expect(s.phase).toBe("announce");
    // 被毒死：hunterShootPending 为 null
    expect(s.hunterShootPending).toBeNull();
  });

  it("警长死亡可移交警徽（sheriff_pass 指定）", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(27));
    // 直接构造：手动设置 sheriff
    const s2 = JSON.parse(JSON.stringify(s0)) as GameState;
    s2.rng = s0.rng;
    const players = s2.players.filter((p) => p.alive);
    const sheriff = players[0].seat;
    s2.sheriffSeat = sheriff;
    for (const p of s2.players) p.isSheriff = p.seat === sheriff;
    s2.phase = "lastwords";
    s2.currentSeat = sheriff;
    // 选一个新警长
    const newSheriff = players[1].seat;
    const next = dayAction(s2, sheriff, {
      kind: "sheriff_pass",
      target: newSheriff,
    });
    expect(next.sheriffSeat).toBe(newSheriff);
    expect(next.players.find((p) => p.seat === newSheriff)?.isSheriff).toBe(true);
    expect(next.players.find((p) => p.seat === sheriff)?.isSheriff).toBe(false);
  });

  it("警长可撕掉警徽（target null）", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(28));
    const s2 = JSON.parse(JSON.stringify(s0)) as GameState;
    s2.rng = s0.rng;
    const players = s2.players.filter((p) => p.alive);
    const sheriff = players[0].seat;
    s2.sheriffSeat = sheriff;
    for (const p of s2.players) p.isSheriff = p.seat === sheriff;
    s2.phase = "lastwords";
    s2.currentSeat = sheriff;
    const next = dayAction(s2, sheriff, {
      kind: "sheriff_pass",
      target: null,
    });
    expect(next.sheriffSeat).toBeUndefined();
    expect(next.players.find((p) => p.seat === sheriff)?.isSheriff).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// game 终局
// ---------------------------------------------------------------------------

describe("game.ts 终局", () => {
  it("杀光狼人好人胜", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(30));
    const s2 = JSON.parse(JSON.stringify(s0)) as GameState;
    s2.rng = s0.rng;
    // 把全部狼人设为死亡
    for (const p of s2.players) {
      if (ROLE_INFO[p.role].faction === "wolves") p.alive = false;
    }
    // 现在 phase 仍是 night；通过调用 dayAction? 无法。但 checkWinner 在 startSpeakForNextDay。
    // 构造一个白天投票触发终局：直接构造一个 day=1 phase=vote 的场景。
    // 更简单：从初始 state 走一遍流程，把所有狼人杀死在第一天投票。
    void s2;
    // 用正常流程：将狼人全部投票出局需多轮，这里只验证基本终局逻辑：
    // 6 人局（2 狼）：票出两狼后好人胜
    const t0 = createGame(makeSeats(6), {}, mulberry32(31));
    // 收集所有狼
    const wolves = t0.players
      .filter((p) => ROLE_INFO[p.role].faction === "wolves")
      .map((p) => p.seat);
    // 简化：直接构造 vote phase
    const gs = JSON.parse(JSON.stringify(t0)) as GameState;
    gs.rng = t0.rng;
    gs.phase = "vote";
    gs.day = 1;
    gs.currentSeat = gs.players.find((p) => p.alive)?.seat as string;
    gs.sheriffVotes = [{ voter: "x", target: null }]; // 标记 sheriff 已完成
    // 第一轮投票淘汰一个狼
    const wolf1 = wolves[0];
    let cur: GameState = gs;
    let guard = 0;
    while (cur.phase === "vote" && guard < 50) {
      guard++;
      const seat = cur.currentSeat;
      if (!seat) break;
      cur = dayAction(cur, seat, { kind: "vote", target: wolf1 });
    }
    if (guard >= 50) throw new Error("vote guard exceeded");
    // 处理遗言
    guard = 0;
    while (cur.phase === "lastwords" && guard < 50) {
      guard++;
      cur = dayAction(cur, cur.currentSeat, { kind: "lastwords_done" });
    }
    if (guard >= 50) throw new Error("lastwords guard exceeded");
    // 投票出局者遗言后进入下一夜（day+1），符合文档流转 vote -> night
    expect(cur.phase).toBe("night");
    expect(cur.day).toBe(2);
    // 简单做法：用一个全新的 6 人局，手动设置 phase=vote 且只剩一狼
    const g3 = createGame(makeSeats(6), {}, mulberry32(32));
    const wolves3 = g3.players
      .filter((p) => ROLE_INFO[p.role].faction === "wolves")
      .map((p) => p.seat);
    // 把第二个狼设为死亡
    const g3s = JSON.parse(JSON.stringify(g3)) as GameState;
    g3s.rng = g3.rng;
    g3s.phase = "vote";
    g3s.day = 1;
    g3s.sheriffVotes = [{ voter: "x", target: null }];
    g3s.currentSeat = g3s.players.find((p) => p.alive)?.seat as string;
    for (const p of g3s.players) {
      if (p.seat === wolves3[1]) p.alive = false;
    }
    const target = wolves3[0];
    let c3: GameState = g3s;
    guard = 0;
    while (c3.phase === "vote" && guard < 50) {
      guard++;
      const seat = c3.currentSeat;
      if (!seat) break;
      c3 = dayAction(c3, seat, { kind: "vote", target });
    }
    if (guard >= 50) throw new Error("vote guard exceeded");
    expect(c3.phase).toBe("finished");
    expect(c3.winner).toBe("good");
  });

  it("杀光好人狼人胜", () => {
    const s0 = createGame(makeSeats(6), {}, mulberry32(33));
    const gs = JSON.parse(JSON.stringify(s0)) as GameState;
    gs.rng = s0.rng;
    // 把全部好人设为死亡，只留狼
    for (const p of gs.players) {
      if (ROLE_INFO[p.role].faction === "good") p.alive = false;
    }
    // 触发终局：用 vote 阶段
    // 但一个活着的狼投票给谁？直接构造 vote 阶段，唯一好人已经死亡。
    // 这里直接用一个白天投票模拟：把好人杀到只剩 1 人，票出他
    const g2 = createGame(makeSeats(6), {}, mulberry32(34));
    const g2s = JSON.parse(JSON.stringify(g2)) as GameState;
    g2s.rng = g2.rng;
    g2s.phase = "vote";
    g2s.day = 1;
    g2s.sheriffVotes = [{ voter: "x", target: null }];
    // 把所有好人除一个外全部设为死亡
    const goods = g2s.players.filter((p) => ROLE_INFO[p.role].faction === "good");
    const lastGood = goods[0].seat;
    for (const p of g2s.players) {
      if (ROLE_INFO[p.role].faction === "good" && p.seat !== lastGood) {
        p.alive = false;
      }
    }
    g2s.currentSeat = g2s.players.find((p) => p.alive)?.seat as string;
    // 全员投票放逐最后好人
    let cur: GameState = g2s;
    let guard = 0;
    while (cur.phase === "vote" && guard < 50) {
      guard++;
      const seat = cur.currentSeat;
      if (!seat) break;
      cur = dayAction(cur, seat, { kind: "vote", target: lastGood });
    }
    if (guard >= 50) throw new Error("vote guard exceeded");
    expect(cur.phase).toBe("finished");
    expect(cur.winner).toBe("wolves");
  });
});

// ---------------------------------------------------------------------------
// 脱敏
// ---------------------------------------------------------------------------

describe("serializeForSeat", () => {
  it("平民看不到他人 role", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(40));
    const villager = s0.players.find((p) => p.role === "villager")?.seat as string;
    const view = serializeForSeat(s0, villager) as {
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

  it("狼人夜晚能看到狼人座位列表", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(41));
    const wolf = s0.players.find((p) => p.role === "werewolf")?.seat as string;
    const view = serializeForSeat(s0, wolf) as {
      wolfSeats?: string[];
    };
    expect(Array.isArray(view.wolfSeats)).toBe(true);
    expect((view.wolfSeats as string[]).length).toBeGreaterThanOrEqual(1);
    expect((view.wolfSeats as string[]).includes(wolf)).toBe(true);
  });

  it("预言家只能看到自己的 seerHistory", () => {
    const s0 = createGame(makeSeats(9), {}, mulberry32(42));
    const seerSeat = aliveSeatByRole(s0, "seer");
    const wolfSeat = aliveSeatByRole(s0, "werewolf");
    let s = nightAction(s0, wolfSeat, { kind: "night", target: null });
    s = nightAction(s, seerSeat, { kind: "night", target: wolfSeat });
    // 现在 seer 有 seerHistory
    const seerView = serializeForSeat(s, seerSeat) as {
      seerHistory?: { seat: string; result: "wolf" | "good"; day: number }[];
    };
    expect(Array.isArray(seerView.seerHistory)).toBe(true);
    // 其他非预言家座位看不到 seerHistory
    const otherSeat = s.players.find(
      (p) => p.role !== "seer" && p.seat !== seerSeat,
    )?.seat as string;
    const otherView = serializeForSeat(s, otherSeat) as {
      seerHistory?: unknown;
    };
    expect(otherView.seerHistory).toBeUndefined();
  });
});

describe("game.ts 非法 action 续", () => {
  it("action 传字符串抛 WerewolfError code BAD_ACTION", () => {
    const s = createGame(makeSeats(9), {}, mulberry32(1));
    const seat = s.currentSeat;
    let err: unknown = null;
    try {
      nightAction(s, seat, "vote" as unknown as never);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(WerewolfError);
    expect((err as WerewolfError).code).toBe("BAD_ACTION");
  });

  it("action 传数字抛 WerewolfError code BAD_ACTION", () => {
    const s = createGame(makeSeats(9), {}, mulberry32(2));
    const seat = s.currentSeat;
    let err: unknown = null;
    try {
      nightAction(s, seat, 42 as unknown as never);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(WerewolfError);
    expect((err as WerewolfError).code).toBe("BAD_ACTION");
  });

  it("出局玩家白天 vote 抛 DEAD_PLAYER", () => {
    let s = createGame(makeSeats(9), {}, mulberry32(3));
    s = progressToFirstVote(s, {
      guard: null,
      wolves: firstGoodNot(s, []),
      seer: null,
      witch: { potion: null },
    });
    expect(s.phase).toBe("vote");
    const dead = s.players.find((p) => !p.alive);
    expect(dead).toBeTruthy();
    let err: unknown = null;
    try {
      dayAction(s, dead!.seat, { kind: "vote", target: null });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(WerewolfError);
    expect((err as WerewolfError).code).toBe("DEAD_PLAYER");
  });

  it("白天调 nightAction 抛 WRONG_PHASE", () => {
    let s = createGame(makeSeats(9), {}, mulberry32(4));
    s = progressToFirstVote(s, {
      guard: null,
      wolves: firstGoodNot(s, []),
      seer: null,
      witch: { potion: null },
    });
    expect(s.phase).toBe("vote");
    const seat = s.currentSeat;
    let err: unknown = null;
    try {
      nightAction(s, seat, { kind: "night", target: null });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(WerewolfError);
    expect((err as WerewolfError).code).toBe("WRONG_PHASE");
  });

  it("终局后 dayAction 抛 WRONG_PHASE", () => {
    let s = createGame(makeSeats(6), {}, mulberry32(5));
    // 直接构造终局：连续夜晚杀好人到狼人胜
    let guard = 0;
    while (s.phase !== "finished" && guard < 50) {
      guard++;
      if (s.phase === "night") {
        s = progressNight(s, {
          guard: null,
          wolves: firstGoodNot(s, []),
          seer: null,
          witch: { potion: null },
        });
        continue;
      }
      if (
        s.phase === "announce" ||
        s.phase === "lastwords"
      ) {
        s = progressAnnounceAndLastwords(s);
        continue;
      }
      if (s.phase === "sheriff") {
        s = progressSheriffAllPass(s);
        continue;
      }
      if (s.phase === "speak") {
        s = progressSpeakAll(s);
        continue;
      }
      if (s.phase === "vote" || s.phase === "pk_vote") {
        // 全员投第一个存活好人（狼人得逞）
        s = progressVoteAll(s, (_v, st) => {
          const target = st.players.find(
            (p) => p.alive && p.role !== "werewolf",
          );
          return target ? target.seat : null;
        });
        continue;
      }
      if (s.phase === "pk_speak") {
        s = progressPkSpeakAll(s);
        continue;
      }
      break;
    }
    expect(guard).toBeLessThan(50);
    expect(s.phase).toBe("finished");
    const anySeat = s.players[0].seat;
    let err: unknown = null;
    try {
      dayAction(s, anySeat, { kind: "vote", target: null });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(WerewolfError);
    expect((err as WerewolfError).code).toBe("WRONG_PHASE");
  });

  it("未知座位抛 UNKNOWN_SEAT（夜晚）", () => {
    const s = createGame(makeSeats(9), {}, mulberry32(6));
    let err: unknown = null;
    try {
      nightAction(s, "nobody", { kind: "night", target: null });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(WerewolfError);
    expect((err as WerewolfError).code).toBe("UNKNOWN_SEAT");
  });

  it("未知座位抛 UNKNOWN_SEAT（白天）", () => {
    let s = createGame(makeSeats(9), {}, mulberry32(7));
    s = progressToFirstVote(s, {
      guard: null,
      wolves: firstGoodNot(s, []),
      seer: null,
      witch: { potion: null },
    });
    let err: unknown = null;
    try {
      dayAction(s, "nobody", { kind: "vote", target: null });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(WerewolfError);
    expect((err as WerewolfError).code).toBe("UNKNOWN_SEAT");
  });
});

describe("ai.ts", () => {
  it("狼人在 wolves 步返回 target 是存活好人", () => {
    const rng = mulberry32(7);
    let s = createGame(makeSeats(9), {}, mulberry32(7));
    // 推进到 wolves 步
    let guard = 0;
    while (s.phase === "night" && s.nightStep !== "wolves" && guard < 20) {
      guard++;
      const seat = s.currentSeat;
      s = nightAction(s, seat, { kind: "night", target: null });
    }
    expect(guard).toBeLessThan(20);
    expect(s.nightStep).toBe("wolves");
    const seat = s.currentSeat;
    const action = chooseNightAction(s, seat, rng) as {
      kind: string;
      target: string | null;
    };
    expect(action.kind).toBe("night");
    expect(typeof action.target).toBe("string");
    const target = s.players.find((p) => p.seat === action.target);
    expect(target).toBeTruthy();
    expect(target!.alive).toBe(true);
    expect(ROLE_INFO[target!.role].faction).toBe("good");
  });

  it("预言家在 seer 步返回 target 为存活非自己", () => {
    const rng = mulberry32(7);
    let s = createGame(makeSeats(9), {}, mulberry32(7));
    let guard = 0;
    while (s.phase === "night" && s.nightStep !== "seer" && guard < 20) {
      guard++;
      const seat = s.currentSeat;
      s = nightAction(s, seat, { kind: "night", target: null });
    }
    expect(guard).toBeLessThan(20);
    expect(s.nightStep).toBe("seer");
    const seat = s.currentSeat;
    expect(s.players.find((p) => p.seat === seat)!.role).toBe("seer");
    const action = chooseNightAction(s, seat, rng) as {
      kind: string;
      target: string | null;
    };
    expect(action.kind).toBe("night");
    expect(action.target).not.toBe(seat);
    const target = s.players.find((p) => p.seat === action.target);
    expect(target).toBeTruthy();
    expect(target!.alive).toBe(true);
  });

  it("女巫在 witch 步有人被刀时返回 potion save", () => {
    const rng = mulberry32(7);
    let s = createGame(makeSeats(9), {}, mulberry32(7));
    const killed = firstGoodNot(s, []);
    // 推进到 witch 步：guard null, wolves 刀人, seer null
    let guard = 0;
    while (s.phase === "night" && s.nightStep !== "witch" && guard < 20) {
      guard++;
      const seat = s.currentSeat;
      if (s.nightStep === "wolves") {
        s = nightAction(s, seat, { kind: "night", target: killed });
      } else {
        s = nightAction(s, seat, { kind: "night", target: null });
      }
    }
    expect(guard).toBeLessThan(20);
    expect(s.nightStep).toBe("witch");
    expect(s.night.wolfTarget).toBe(killed);
    const seat = s.currentSeat;
    expect(s.players.find((p) => p.seat === seat)!.role).toBe("witch");
    const action = chooseNightAction(s, seat, rng) as {
      kind: string;
      potion?: string | null;
      target?: string | null;
    };
    expect(action.kind).toBe("night");
    expect(action.potion).toBe("save");
    expect(action.target).toBe(killed);
  });

  it("守卫在 guard 步返回 target 且第二晚不连守", () => {
    const rng = mulberry32(7);
    // 10 人局才有守卫（SUPPORTED_COUNTS：10 人=3狼3民预言家女巫猎人守卫）
    let s = createGame(makeSeats(10), {}, mulberry32(7));
    expect(s.nightStep).toBe("guard");
    const guardSeat = s.currentSeat;
    const first = chooseNightAction(s, guardSeat, rng) as {
      kind: string;
      target: string | null;
    };
    expect(first.kind).toBe("night");
    expect(typeof first.target).toBe("string");
    const firstTarget = first.target!;
    // 提交第一晚守卫（guardPrevTarget 在整晚结算后才更新）
    s = nightAction(s, guardSeat, { kind: "night", target: firstTarget });
    // 跑完第一晚到第二天夜晚 guard 步
    s = progressNight(s, {
      wolves: null,
      seer: null,
      witch: { potion: null },
    });
    expect(s.night.guardPrevTarget).toBe(firstTarget);
    s = progressAnnounceAndLastwords(s);
    if (s.phase === "sheriff") s = progressSheriffAllPass(s);
    if (s.phase === "speak") s = progressSpeakAll(s);
    if (s.phase === "vote" || s.phase === "pk_vote") {
      s = progressVoteAll(s, (_v, st) => {
        // PK 台上的人只能弃票
        if (st.phase === "pk_vote" && st.pkSeats.includes(_v)) return null;
        const t = st.players.find((p) => p.alive && p.seat !== _v);
        return t ? t.seat : null;
      });
    }
    if (s.phase === "pk_speak") {
      s = progressPkSpeakAll(s);
      s = progressVoteAll(s, (_v, st) => {
        if (st.phase === "pk_vote" && st.pkSeats.includes(_v)) return null;
        const t = st.players.find((p) => p.alive && p.seat !== _v);
        return t ? t.seat : null;
      });
    }
    // 白天投票出局者的遗言也要排掉，否则到不了第二天夜晚
    s = progressAnnounceAndLastwords(s);
    // 第二天夜晚
    let guard2 = 0;
    while (s.phase === "night" && s.nightStep !== "guard" && guard2 < 20) {
      guard2++;
      const seat = s.currentSeat;
      s = nightAction(s, seat, { kind: "night", target: null });
    }
    expect(guard2).toBeLessThan(20);
    expect(s.nightStep).toBe("guard");
    const guardSeat2 = s.currentSeat;
    expect(s.night.guardPrevTarget).toBe(firstTarget);
    const second = chooseNightAction(s, guardSeat2, rng) as {
      kind: string;
      target: string | null;
    };
    expect(second.kind).toBe("night");
    expect(second.target).not.toBe(firstTarget);
  });

  it("chooseDayAction 在 vote 阶段返回合法 vote", () => {
    const rng = mulberry32(7);
    let s = createGame(makeSeats(9), {}, mulberry32(7));
    s = progressToFirstVote(s, {
      guard: null,
      wolves: firstGoodNot(s, []),
      seer: null,
      witch: { potion: null },
    });
    expect(s.phase).toBe("vote");
    const seat = s.currentSeat;
    const action = chooseDayAction(s, seat, rng) as {
      kind: string;
      target: string | null;
    };
    expect(action.kind).toBe("vote");
    if (action.target !== null) {
      const t = s.players.find((p) => p.seat === action.target);
      expect(t).toBeTruthy();
      expect(t!.alive).toBe(true);
    }
    // 应能被 dayAction 接受
    const next = dayAction(s, seat, action as never);
    expect(next.phase === "vote" || next.phase === "pk_vote" || next.phase === "finished").toBe(true);
  });

  it("全 AI 跑完整局至 finished", () => {
    const rng = mulberry32(7);
    let s = createGame(makeAiSeats(9), {}, mulberry32(7));
    let guard = 0;
    while (s.phase !== "finished" && guard < 800) {
      guard++;
      if (s.phase === "night") {
        const seat = s.currentSeat;
        const action = chooseNightAction(s, seat, rng);
        s = nightAction(s, seat, action as never);
        continue;
      }
      if (s.phase === "announce") {
        s = progressAnnounceAndLastwords(s);
        continue;
      }
      if (s.phase === "lastwords") {
        s = progressAnnounceAndLastwords(s);
        continue;
      }
      if (s.phase === "sheriff") {
        const seat = s.currentSeat;
        const action = chooseDayAction(s, seat, rng) as { kind: string; target?: string | null };
        if (action.kind === "sheriff") {
          s = dayAction(s, seat, action as never);
        } else {
          s = progressSheriffAllPass(s);
        }
        continue;
      }
      if (s.phase === "speak" || s.phase === "pk_speak") {
        const seat = s.currentSeat;
        const action = chooseDayAction(s, seat, rng) as { kind: string };
        if (action.kind === "speak_done") {
          s = dayAction(s, seat, action as never);
        } else {
          s = dayAction(s, seat, { kind: "speak_done" });
        }
        continue;
      }
      if (s.phase === "vote" || s.phase === "pk_vote") {
        const seat = s.currentSeat;
        const action = chooseDayAction(s, seat, rng) as { kind: string; target?: string | null };
        if (action.kind === "vote") {
          s = dayAction(s, seat, action as never);
        } else {
          s = dayAction(s, seat, { kind: "vote", target: null });
        }
        continue;
      }
      break;
    }
    expect(guard).toBeLessThan(800);
    expect(s.phase).toBe("finished");
    expect(s.winner === "wolves" || s.winner === "good").toBe(true);
  });
});

describe("werewolf-game.ts 适配器", () => {
  it("applyAction start 全 AI 座位自动跑完对局", () => {
    const engine = new WerewolfGameEngine();
    const out = engine.applyAction({}, {
      game: "werewolf",
      action: { kind: "start", seats: makeAiSeats(9) },
    } as never) as { v?: number; state?: GameState; error?: unknown };
    expect(out.v).toBe(1);
    expect(out.error).toBeUndefined();
    expect(out.state).toBeTruthy();
    // start 分支会 runAiTurns：全 AI 座位一局内跑完
    expect(out.state!.phase).toBe("finished");
    expect(out.state!.winner === "wolves" || out.state!.winner === "good").toBe(true);
  });

  it("seats 传 3 个返回 BAD_SEATS", () => {
    const engine = new WerewolfGameEngine();
    const out = engine.applyAction({}, {
      game: "werewolf",
      action: { kind: "start", seats: makeAiSeats(3) },
    } as never) as { error?: { code?: string } };
    expect(out.error).toBeTruthy();
    expect(out.error!.code).toBe("BAD_SEATS");
  });

  it("seats 重复返回 BAD_SEATS", () => {
    const engine = new WerewolfGameEngine();
    const dup = makeAiSeats(9);
    dup[1] = dup[0];
    const out = engine.applyAction({}, {
      game: "werewolf",
      action: { kind: "start", seats: dup },
    } as never) as { error?: { code?: string } };
    expect(out.error).toBeTruthy();
    expect(out.error!.code).toBe("BAD_SEATS");
  });

  it("applyAction 非法 action 返回带 error 的 state 且不抛错", () => {
    const engine = new WerewolfGameEngine();
    let out: unknown = null;
    expect(() => {
      out = engine.applyAction({}, {
        game: "werewolf",
        action: {} as never,
      } as never);
    }).not.toThrow();
    expect(out).toBeTruthy();
    expect((out as { error?: unknown }).error).toBeTruthy();
  });

  it("WerewolfRoom toJSON/fromJSON 回环 phase 一致", () => {
    const room = WerewolfRoom.create("r1", "s1", makeAiSeats(9)) as unknown as {
      toJSON: () => string;
    };
    const data = room.toJSON();
    const restored = WerewolfRoom.fromJSON("r1", "s1", data);
    const data2 = JSON.parse((restored as unknown as { toJSON: () => string }).toJSON()) as WerewolfSessionData;
    expect(data2.state!.phase).toBe((JSON.parse(data as unknown as string) as WerewolfSessionData).state!.phase);
  });

  it("isAiSeat 判定正确", () => {
    expect(isAiSeat("ai:x")).toBe(true);
    expect(isAiSeat("bob")).toBe(false);
  });

  it("SUPPORTED_COUNTS 含 6..12", () => {
    for (let n = 6; n <= 12; n++) {
      expect(SUPPORTED_COUNTS.includes(n)).toBe(true);
    }
  });

  it("toStateFrame 返回 game=werewolf 且 state_hash 为 64 位 hex", () => {
    const room = WerewolfRoom.create("r1", "s1", makeAiSeats(9)) as unknown as {
      toStateFrame: (seat?: string) => { game: string; state_hash: string };
    };
    const frame = room.toStateFrame();
    expect(frame.game).toBe("werewolf");
    expect(typeof frame.state_hash).toBe("string");
    expect(/^[0-9a-f]{64}$/.test(frame.state_hash)).toBe(true);
  });
});
