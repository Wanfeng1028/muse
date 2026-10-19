import { assignRoles, SUPPORTED_COUNTS } from "./roles.js";
import type { Role } from "./roles.js";

/**
 * 狼人杀对局状态机。
 * 纯函数式：所有导出函数返回新的 GameState，不修改入参。
 * 夜晚顺序固定：guard -> wolves -> seer -> witch。
 * 白天流程：announce -> lastwords -> sheriff(可选) -> speak -> vote -> (pk_speak -> pk_vote) -> 下一夜。
 * 胜利判定按屠边：狼全灭好人胜；平民全灭或神职全灭狼胜。
 */

export type Phase =
  | "night"
  | "announce"
  | "lastwords"
  | "sheriff"
  | "speak"
  | "vote"
  | "pk_speak"
  | "pk_vote"
  | "finished";

export type NightStep = "guard" | "wolves" | "seer" | "witch";

export interface WerewolfConfig {
  sheriff?: boolean;
}

export interface PlayerState {
  seat: string;
  role: Role;
  alive: boolean;
  isSheriff: boolean;
}

export interface NightState {
  step: NightStep;
  guardTarget: string | null;
  lastGuardTarget: string | null;
  wolfTarget: string | null;
  seerTarget: string | null;
  seerResult: "wolf" | "good" | null;
  seerHistory: { day: number; target: string; result: "wolf" | "good" }[];
  witchSaveUsed: boolean;
  witchPoisonUsed: boolean;
  witchSaveTarget: string | null;
  witchPoisonTarget: string | null;
}

export interface GameState {
  phase: Phase;
  day: number;
  players: PlayerState[];
  currentSeat: string;
  night: NightState;
  votes: { seat: string; target: string | null }[];
  sheriffVotes: { seat: string; target: string | null }[];
  sheriffSeat: string | null;
  sheriffOrderStart: string | null;
  spokenSeats: string[];
  pkSeats: string[];
  pkVotes: { seat: string; target: string | null }[];
  deaths: { seat: string; reason: "wolf" | "witch" | "vote" | "hunter" }[];
  deathsTonight: string[];
  lastwordsQueue: string[];
  lastwordsDone: string[];
  hunterShootPending: string | null;
  winner?: "wolves" | "good";
  config: WerewolfConfig;
  rng: () => number;
}

export class WerewolfError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = "WerewolfError";
    this.code = code;
  }
}

function clonePlayer(p: PlayerState): PlayerState {
  return {
    seat: p.seat,
    role: p.role,
    alive: p.alive,
    isSheriff: p.isSheriff,
  };
}

function cloneNight(n: NightState): NightState {
  return {
    step: n.step,
    guardTarget: n.guardTarget,
    lastGuardTarget: n.lastGuardTarget,
    wolfTarget: n.wolfTarget,
    seerTarget: n.seerTarget,
    seerResult: n.seerResult,
    seerHistory: n.seerHistory.map((h) => ({ day: h.day, target: h.target, result: h.result })),
    witchSaveUsed: n.witchSaveUsed,
    witchPoisonUsed: n.witchPoisonUsed,
    witchSaveTarget: n.witchSaveTarget,
    witchPoisonTarget: n.witchPoisonTarget,
  };
}

function cloneState(state: GameState): GameState {
  const next: GameState = {
    phase: state.phase,
    day: state.day,
    players: state.players.map(clonePlayer),
    currentSeat: state.currentSeat,
    night: cloneNight(state.night),
    votes: state.votes.map((v) => ({ seat: v.seat, target: v.target })),
    sheriffVotes: state.sheriffVotes.map((v) => ({ seat: v.seat, target: v.target })),
    sheriffSeat: state.sheriffSeat,
    sheriffOrderStart: state.sheriffOrderStart,
    spokenSeats: state.spokenSeats.slice(),
    pkSeats: state.pkSeats.slice(),
    pkVotes: state.pkVotes.map((v) => ({ seat: v.seat, target: v.target })),
    deaths: state.deaths.map((d) => ({ seat: d.seat, reason: d.reason })),
    deathsTonight: state.deathsTonight.slice(),
    lastwordsQueue: state.lastwordsQueue.slice(),
    lastwordsDone: state.lastwordsDone.slice(),
    hunterShootPending: state.hunterShootPending,
    config: { ...state.config },
    rng: state.rng,
  };
  if (state.winner !== undefined) next.winner = state.winner;
  return next;
}

function findPlayer(state: GameState, seat: string): PlayerState | undefined {
  return state.players.find((p) => p.seat === seat);
}

function alivePlayers(state: GameState): PlayerState[] {
  return state.players.filter((p) => p.alive);
}

function aliveWithRole(state: GameState, role: Role): PlayerState[] {
  return state.players.filter((p) => p.alive && p.role === role);
}

function hasRole(state: GameState, role: Role): boolean {
  return state.players.some((p) => p.role === role);
}

// 找下一个可行动夜晚步骤（跳过缺席/出局角色）
function advanceNightStep(state: GameState, from: NightStep): NightStep | null {
  const order: NightStep[] = ["guard", "wolves", "seer", "witch"];
  let idx = order.indexOf(from);
  if (idx < 0) idx = 0;
  for (let i = idx; i < order.length; i++) {
    const step = order[i];
    if (step === "guard") {
      if (aliveWithRole(state, "guard").length > 0) return "guard";
    } else if (step === "wolves") {
      if (aliveWithRole(state, "werewolf").length > 0) return "wolves";
    } else if (step === "seer") {
      if (aliveWithRole(state, "seer").length > 0) return "seer";
    } else if (step === "witch") {
      if (aliveWithRole(state, "witch").length > 0) return "witch";
    }
  }
  return null;
}

// 计算胜利：返回 winner 或 undefined
function checkWinner(state: GameState): "wolves" | "good" | undefined {
  const wolvesAlive = aliveWithRole(state, "werewolf");
  const villagersAlive = aliveWithRole(state, "villager");
  const godsAlive: PlayerState[] = [];
  const godRoles: Role[] = ["seer", "witch", "hunter", "guard"];
  for (const r of godRoles) {
    if (hasRole(state, r)) {
      for (const p of aliveWithRole(state, r)) godsAlive.push(p);
    }
  }
  const anyGodInGame = godRoles.some((r) => hasRole(state, r));
  const anyVillagerInGame = hasRole(state, "villager");

  if (wolvesAlive.length === 0) return "good";
  if (anyVillagerInGame && villagersAlive.length === 0) return "wolves";
  if (anyGodInGame && godsAlive.length === 0) return "wolves";
  return undefined;
}

function applyWinner(state: GameState): void {
  const w = checkWinner(state);
  if (w !== undefined) {
    state.winner = w;
    state.phase = "finished";
  }
}

function beginNight(state: GameState): void {
  state.phase = "night";
  state.day += 1;
  state.night = {
    step: "guard",
    guardTarget: null,
    lastGuardTarget: state.night.guardTarget,
    wolfTarget: null,
    seerTarget: null,
    seerResult: null,
    seerHistory: state.night.seerHistory.map((h) => ({ day: h.day, target: h.target, result: h.result })),
    witchSaveUsed: state.night.witchSaveUsed,
    witchPoisonUsed: state.night.witchPoisonUsed,
    witchSaveTarget: null,
    witchPoisonTarget: null,
  };
  state.votes = [];
  state.pkSeats = [];
  state.pkVotes = [];
  state.deathsTonight = [];
  state.lastwordsQueue = [];
  state.lastwordsDone = [];
  state.spokenSeats = [];
  state.sheriffOrderStart = null;
  state.hunterShootPending = null;
  const step = advanceNightStep(state, "guard");
  if (step === null) {
    // 没有可行动的夜晚角色，直接进入白天
    enterAnnounce(state);
  } else {
    state.night.step = step;
    setNightCurrentSeat(state);
  }
}

function setNightCurrentSeat(state: GameState): void {
  const step = state.night.step;
  if (step === "guard") {
    const p = aliveWithRole(state, "guard")[0];
    state.currentSeat = p ? p.seat : "";
  } else if (step === "wolves") {
    const wolves = aliveWithRole(state, "werewolf");
    // 第一个存活的狼人代表发言，实际所有狼人都可提交，最后一个完成结算
    state.currentSeat = wolves.length > 0 ? wolves[0].seat : "";
  } else if (step === "seer") {
    const p = aliveWithRole(state, "seer")[0];
    state.currentSeat = p ? p.seat : "";
  } else if (step === "witch") {
    const p = aliveWithRole(state, "witch")[0];
    state.currentSeat = p ? p.seat : "";
  } else {
    state.currentSeat = "";
  }
}

// 结算夜晚：确定死亡
function resolveNight(state: GameState): void {
  const deathsTonight: string[] = [];
  const wolfTarget = state.night.wolfTarget;
  const guardTarget = state.night.guardTarget;
  const saveTarget = state.night.witchSaveTarget;
  const poisonTarget = state.night.witchPoisonTarget;

  if (wolfTarget !== null) {
    const guarded = guardTarget === wolfTarget;
    const saved = saveTarget === wolfTarget;
    if (!guarded && !saved) {
      const p = findPlayer(state, wolfTarget);
      if (p && p.alive) {
        p.alive = false;
        deathsTonight.push(wolfTarget);
        state.deaths.push({ seat: wolfTarget, reason: "wolf" });
      }
    }
  }

  if (poisonTarget !== null) {
    const p = findPlayer(state, poisonTarget);
    if (p && p.alive) {
      p.alive = false;
      deathsTonight.push(poisonTarget);
      state.deaths.push({ seat: poisonTarget, reason: "witch" });
    }
  }

  state.deathsTonight = deathsTonight;
  state.lastwordsQueue = deathsTonight.slice();

  // 猎人被狼刀/被毒：猎人开枪留到白天 announce 后？按流程，猎人夜晚死亡时也需白天发言阶段处理。
  // 这里简单处理：夜晚死亡中如果有猎人，进入白天流程后再触发 hunterShootPending。
  // 规则简化：猎人夜晚死亡也触发开枪（放在进入 lastwords 前 announce 中处理）。
  enterAnnounce(state);
}

// 进入 announce 阶段
function enterAnnounce(state: GameState): void {
  state.phase = "announce";
  state.currentSeat = "";
  applyWinner(state);
  if (state.winner !== undefined) return;
  // 无死亡直接跳过 announce 到下一阶段
  if (state.deathsTonight.length === 0) {
    enterAfterAnnounce(state);
  }
}

// announce 后：有死亡进 lastwords，无死亡进 speak/sheriff
function enterAfterAnnounce(state: GameState): void {
  // 猎人夜晚死亡开枪（如果本轮夜晚死亡里有猎人）
  const hunterDead = state.deathsTonight.find((seat) => {
    const p = findPlayer(state, seat);
    return p && p.role === "hunter";
  });
  if (hunterDead !== undefined) {
    state.hunterShootPending = hunterDead;
    state.currentSeat = hunterDead;
    // 猎人开枪阶段仍处于 announce 阶段，用 announce_done 触发前先要求 hunter_shoot
    // 简化：用一个临时状态——保持 announce，但 currentSeat 为猎人，需要 hunter_shoot 动作
    // 但适配层 phase 需要是 announce/lastwords/sheriff/speak/vote/pk_speak/pk_vote/finished
    // 我们让猎人开枪在 lastwords 之前，使用 announce 阶段并等待 hunter_shoot 动作
    state.phase = "announce";
    return;
  }
  if (state.lastwordsQueue.length > 0) {
    state.phase = "lastwords";
    state.currentSeat = state.lastwordsQueue[0];
    return;
  }
  // 无死亡：进入 sheriff/speak
  enterSheriffOrSpeak(state);
}

// 无死亡或发言完毕后：进入 sheriff(若开启) 或 speak
function enterSheriffOrSpeak(state: GameState): void {
  if (state.config.sheriff && state.day === 1 && state.sheriffSeat === null) {
    state.phase = "sheriff";
    // 全体存活玩家可竞选；currentSeat 置空（自由动作）
    state.currentSeat = "";
    state.sheriffVotes = [];
    return;
  }
  enterSpeak(state);
}

// 进入 speak
function enterSpeak(state: GameState): void {
  state.phase = "speak";
  state.spokenSeats = [];
  const order = speakOrder(state);
  if (order.length === 0) {
    enterVote(state);
    return;
  }
  state.currentSeat = order[0];
}

// 存活玩家按座位顺序（可从 sheriffOrderStart 开始）
function speakOrder(state: GameState): string[] {
  const alive = state.players.filter((p) => p.alive).map((p) => p.seat);
  if (alive.length === 0) return [];
  let startIdx = 0;
  if (state.sheriffOrderStart !== null) {
    const i = alive.indexOf(state.sheriffOrderStart);
    if (i >= 0) startIdx = i;
  }
  const order: string[] = [];
  for (let i = 0; i < alive.length; i++) {
    order.push(alive[(startIdx + i) % alive.length]);
  }
  return order;
}

// 进入 vote
function enterVote(state: GameState): void {
  state.phase = "vote";
  state.votes = [];
  state.spokenSeats = [];
  const alive = state.players.filter((p) => p.alive).map((p) => p.seat);
  if (alive.length === 0) {
    enterNightAfterDay(state);
    return;
  }
  state.currentSeat = alive[0];
}

// 进入下一夜
function enterNightAfterDay(state: GameState): void {
  applyWinner(state);
  if (state.phase === "finished") return;
  beginNight(state);
}

// 结算白天投票
function resolveVote(state: GameState): void {
  // 统计票数
  const tally = new Map<string, number>();
  for (const v of state.votes) {
    if (v.target === null) continue;
    tally.set(v.target, (tally.get(v.target) ?? 0) + 1);
  }
  let maxVotes = 0;
  const top: string[] = [];
  for (const [seat, cnt] of tally.entries()) {
    if (cnt > maxVotes) {
      maxVotes = cnt;
      top.length = 0;
      top.push(seat);
    } else if (cnt === maxVotes) {
      top.push(seat);
    }
  }
  if (maxVotes === 0) {
    // 全弃票，无人出局
    enterNightAfterDay(state);
    return;
  }
  if (top.length > 1) {
    // 平票进 PK
    state.pkSeats = top.slice();
    state.pkVotes = [];
    state.phase = "pk_speak";
    state.spokenSeats = [];
    state.currentSeat = state.pkSeats[0];
    return;
  }
  // 唯一最高票，放逐
  eliminateByVote(state, top[0]);
}

function eliminateByVote(state: GameState, seat: string): void {
  const p = findPlayer(state, seat);
  if (p && p.alive) {
    p.alive = false;
    state.deaths.push({ seat, reason: "vote" });
    state.lastwordsQueue = [seat];
    state.lastwordsDone = [];
    if (p.role === "hunter") {
      state.hunterShootPending = seat;
    }
  }
  // 进入 lastwords
  state.phase = "lastwords";
  state.currentSeat = seat;
}

// 结算 PK 投票
function resolvePkVote(state: GameState): void {
  const tally = new Map<string, number>();
  for (const v of state.pkVotes) {
    if (v.target === null) continue;
    tally.set(v.target, (tally.get(v.target) ?? 0) + 1);
  }
  let maxVotes = 0;
  const top: string[] = [];
  for (const [seat, cnt] of tally.entries()) {
    if (cnt > maxVotes) {
      maxVotes = cnt;
      top.length = 0;
      top.push(seat);
    } else if (cnt === maxVotes) {
      top.push(seat);
    }
  }
  if (maxVotes === 0 || top.length > 1) {
    // 再平或全弃：无人出局
    enterNightAfterDay(state);
    return;
  }
  eliminateByVote(state, top[0]);
}

// 排空 lastwords 后决定下一阶段
function afterLastwords(state: GameState): void {
  // 判断是夜晚死亡还是投票放逐：调用方已把队列排空，需回看最后一条死亡原因
  const lastDeath = state.deaths[state.deaths.length - 1];
  const isVoteDeath = lastDeath !== undefined && lastDeath.reason === "vote";
  if (isVoteDeath) {
    // 投票放逐：进入下一夜
    state.lastwordsQueue = [];
    state.lastwordsDone = [];
    enterNightAfterDay(state);
    return;
  }
  // 夜晚死亡：走白天流程（sheriff/speak/vote）
  state.lastwordsQueue = [];
  state.lastwordsDone = [];
  enterSheriffOrSpeak(state);
}

// 上警结果处理：平票则警徽流失
function resolveSheriffVote(state: GameState): void {
  const tally = new Map<string, number>();
  for (const v of state.sheriffVotes) {
    if (v.target === null) continue;
    tally.set(v.target, (tally.get(v.target) ?? 0) + 1);
  }
  let maxVotes = 0;
  const top: string[] = [];
  for (const [seat, cnt] of tally.entries()) {
    if (cnt > maxVotes) {
      maxVotes = cnt;
      top.length = 0;
      top.push(seat);
    } else if (cnt === maxVotes) {
      top.push(seat);
    }
  }
  if (maxVotes > 0 && top.length === 1) {
    const winner = findPlayer(state, top[0]);
    if (winner) {
      winner.isSheriff = true;
      state.sheriffSeat = top[0];
    }
  } else {
    // 平票或无人得票：警徽流失
    state.sheriffSeat = null;
  }
  state.sheriffVotes = [];
  enterSpeak(state);
}

// 狼人回合提交后，是否所有存活狼人都提交了
function allWolvesActed(state: GameState): boolean {
  // 简化：由第一个狼人代表全队决定，一次提交即完成
  return true;
}

export function createGame(
  seats: string[],
  config?: WerewolfConfig,
  rng?: () => number,
): GameState {
  if (!Array.isArray(seats)) {
    throw new WerewolfError("BAD_SEATS", "座位必须是数组");
  }
  if (!Object.prototype.hasOwnProperty.call(SUPPORTED_COUNTS, seats.length)) {
    throw new WerewolfError(
      "BAD_SEATS",
      `不支持的人数：${seats.length}（支持 6 到 12）`,
    );
  }
  const seen = new Set<string>();
  for (const s of seats) {
    if (typeof s !== "string" || s.length === 0) {
      throw new WerewolfError("BAD_SEATS", "座位必须是非空字符串");
    }
    if (seen.has(s)) {
      throw new WerewolfError("BAD_SEATS", `座位重复：${s}`);
    }
    seen.add(s);
  }

  const random = rng ?? Math.random;
  const roles = assignRoles(seats, random);
  const players: PlayerState[] = seats.map((seat) => {
    const role = roles.get(seat);
    if (!role) {
      throw new WerewolfError("BAD_SEATS", "角色分配失败");
    }
    return { seat, role, alive: true, isSheriff: false };
  });

  const cfg: WerewolfConfig = {};
  if (config && config.sheriff !== undefined) cfg.sheriff = config.sheriff;

  const state: GameState = {
    phase: "night",
    day: 0,
    players,
    currentSeat: "",
    night: {
      step: "guard",
      guardTarget: null,
      lastGuardTarget: null,
      wolfTarget: null,
      seerTarget: null,
      seerResult: null,
      seerHistory: [],
      witchSaveUsed: false,
      witchPoisonUsed: false,
      witchSaveTarget: null,
      witchPoisonTarget: null,
    },
    votes: [],
    sheriffVotes: [],
    sheriffSeat: null,
    sheriffOrderStart: null,
    spokenSeats: [],
    pkSeats: [],
    pkVotes: [],
    deaths: [],
    deathsTonight: [],
    lastwordsQueue: [],
    lastwordsDone: [],
    hunterShootPending: null,
    config: cfg,
    rng: random,
  };

  // 初始化第一夜（day 从 1 开始）
  beginNight(state);
  return state;
}

export function nightAction(state: GameState, seat: string, action: unknown): GameState {
  if (state.phase !== "night") {
    throw new WerewolfError("WRONG_PHASE", "现在不是夜晚");
  }
  const player = findPlayer(state, seat);
  if (!player) {
    throw new WerewolfError("UNKNOWN_SEAT", `没有这个座位：${seat}`);
  }
  if (!player.alive) {
    throw new WerewolfError("DEAD_PLAYER", "你已经出局了");
  }

  const act = action as { kind?: unknown; target?: unknown; potion?: unknown };
  if (!act || typeof act !== "object" || act.kind !== "night") {
    throw new WerewolfError("BAD_ACTION", "夜晚动作不合法");
  }

  const next = cloneState(state);
  const me = findPlayer(next, seat);
  if (!me) {
    throw new WerewolfError("UNKNOWN_SEAT", `没有这个座位：${seat}`);
  }

  const step = next.night.step;

  if (step === "guard") {
    if (me.role !== "guard") {
      throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
    }
    const target = act.target;
    if (target !== null && target !== undefined) {
      if (typeof target !== "string") {
        throw new WerewolfError("BAD_ACTION", "守护目标不合法");
      }
      const tp = findPlayer(next, target);
      if (!tp || !tp.alive) {
        throw new WerewolfError("ILLEGAL_TARGET", "守护目标必须是存活玩家");
      }
      if (next.night.lastGuardTarget === target) {
        throw new WerewolfError("ILLEGAL_TARGET", "不能连续两晚守同一个人");
      }
      next.night.guardTarget = target;
    } else {
      next.night.guardTarget = null;
    }
    // 推进到下一可行动步骤
    const nextStep = advanceNightStep(next, "wolves");
    if (nextStep === null) {
      resolveNight(next);
      return next;
    }
    next.night.step = nextStep;
    setNightCurrentSeat(next);
    return next;
  }

  if (step === "wolves") {
    if (me.role !== "werewolf") {
      throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
    }
    const target = act.target;
    if (target !== null && target !== undefined) {
      if (typeof target !== "string") {
        throw new WerewolfError("BAD_ACTION", "狼刀目标不合法");
      }
      const tp = findPlayer(next, target);
      if (!tp || !tp.alive) {
        throw new WerewolfError("ILLEGAL_TARGET", "狼刀目标必须是存活玩家");
      }
      if (tp.role === "werewolf") {
        throw new WerewolfError("ILLEGAL_TARGET", "不能刀自己的狼队友");
      }
      next.night.wolfTarget = target;
    } else {
      next.night.wolfTarget = null;
    }
    if (!allWolvesActed(next)) {
      return next;
    }
    const nextStep = advanceNightStep(next, "seer");
    if (nextStep === null) {
      resolveNight(next);
      return next;
    }
    next.night.step = nextStep;
    setNightCurrentSeat(next);
    return next;
  }

  if (step === "seer") {
    if (me.role !== "seer") {
      throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
    }
    const target = act.target;
    if (target !== null && target !== undefined) {
      if (typeof target !== "string") {
        throw new WerewolfError("BAD_ACTION", "查验目标不合法");
      }
      const tp = findPlayer(next, target);
      if (!tp || !tp.alive) {
        throw new WerewolfError("ILLEGAL_TARGET", "查验目标必须是存活玩家");
      }
      if (target === seat) {
        throw new WerewolfError("ILLEGAL_TARGET", "不能查验自己");
      }
      const result: "wolf" | "good" = tp.role === "werewolf" ? "wolf" : "good";
      next.night.seerTarget = target;
      next.night.seerResult = result;
      next.night.seerHistory = next.night.seerHistory.concat([
        { day: next.day, target, result },
      ]);
    } else {
      next.night.seerTarget = null;
      next.night.seerResult = null;
    }
    const nextStep = advanceNightStep(next, "witch");
    if (nextStep === null) {
      resolveNight(next);
      return next;
    }
    next.night.step = nextStep;
    setNightCurrentSeat(next);
    return next;
  }

  if (step === "witch") {
    if (me.role !== "witch") {
      throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
    }
    const potion = act.potion;
    const target = act.target;
    if (potion === "save") {
      if (next.night.witchSaveUsed) {
        throw new WerewolfError("BAD_ACTION", "解药已经用过了");
      }
      if (typeof target !== "string") {
        throw new WerewolfError("BAD_ACTION", "解药必须有目标");
      }
      const tp = findPlayer(next, target);
      if (!tp || !tp.alive) {
        throw new WerewolfError("ILLEGAL_TARGET", "解药目标必须是存活玩家");
      }
      if (next.night.wolfTarget !== target) {
        throw new WerewolfError("ILLEGAL_TARGET", "解药只能救被狼刀的人");
      }
      if (next.day === 1 && target === seat) {
        throw new WerewolfError("ILLEGAL_TARGET", "首夜不能自救");
      }
      next.night.witchSaveUsed = true;
      next.night.witchSaveTarget = target;
    } else if (potion === "poison") {
      if (next.night.witchPoisonUsed) {
        throw new WerewolfError("BAD_ACTION", "毒药已经用过了");
      }
      if (typeof target !== "string") {
        throw new WerewolfError("BAD_ACTION", "毒药必须有目标");
      }
      const tp = findPlayer(next, target);
      if (!tp || !tp.alive) {
        throw new WerewolfError("ILLEGAL_TARGET", "毒药目标必须是存活玩家");
      }
      next.night.witchPoisonUsed = true;
      next.night.witchPoisonTarget = target;
    } else if (potion === null || potion === undefined) {
      // 不用药
    } else {
      throw new WerewolfError("BAD_ACTION", "女巫动作不合法");
    }
    resolveNight(next);
    return next;
  }

  throw new WerewolfError("BAD_ACTION", "夜晚步骤异常");
}

export function dayAction(state: GameState, seat: string, action: unknown): GameState {
  const player = findPlayer(state, seat);
  if (!player) {
    throw new WerewolfError("UNKNOWN_SEAT", `没有这个座位：${seat}`);
  }

  const act = action as { kind?: unknown; target?: unknown; orderStart?: unknown };

  if (state.phase === "finished") {
    throw new WerewolfError("WRONG_PHASE", "对局已经结束");
  }

  // 猎人开枪优先处理（announce 阶段或 lastwords 阶段）
  if (state.hunterShootPending !== null && state.hunterShootPending === seat) {
    if (!act || act.kind !== "hunter_shoot") {
      throw new WerewolfError("BAD_ACTION", "猎人必须开枪");
    }
    const target = act.target;
    if (typeof target !== "string") {
      throw new WerewolfError("BAD_ACTION", "开枪目标不合法");
    }
    const tp = findPlayer(state, target);
    if (!tp || !tp.alive) {
      throw new WerewolfError("ILLEGAL_TARGET", "开枪目标必须是存活玩家");
    }
    const next = cloneState(state);
    const tp2 = findPlayer(next, target);
    if (!tp2) {
      throw new WerewolfError("UNKNOWN_SEAT", "目标不存在");
    }
    tp2.alive = false;
    next.deaths.push({ seat: target, reason: "hunter" });
    next.hunterShootPending = null;
    // 开枪后继续原本的流程
    const shooter = findPlayer(next, seat);
    if (shooter) {
      // 猎人自己也已在死亡队列中，不重复
    }
    // 开枪死亡的人进入 lastwords
    next.lastwordsQueue = [target];
    next.lastwordsDone = [];
    next.phase = "lastwords";
    next.currentSeat = target;
    applyWinner(next);
    return next;
  }

  if (state.phase === "announce") {
    if (!act || act.kind !== "announce_done") {
      throw new WerewolfError("BAD_ACTION", "现在需要确认看过死讯");
    }
    const next = cloneState(state);
    enterAfterAnnounce(next);
    return next;
  }

  if (state.phase === "lastwords") {
    if (!act || act.kind !== "lastwords_done") {
      throw new WerewolfError("BAD_ACTION", "现在需要发表遗言");
    }
    if (state.currentSeat !== seat && state.currentSeat !== "") {
      // 允许队列头部发言
      if (state.lastwordsQueue[0] !== seat) {
        throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
      }
    }
    const next = cloneState(state);
    if (!next.lastwordsDone.includes(seat)) {
      next.lastwordsDone.push(seat);
    }
    next.lastwordsQueue = next.lastwordsQueue.filter((s) => s !== seat);
    if (next.lastwordsQueue.length > 0) {
      next.currentSeat = next.lastwordsQueue[0];
      return next;
    }
    afterLastwords(next);
    return next;
  }

  if (state.phase === "sheriff") {
    const next = cloneState(state);
    const me = findPlayer(next, seat);
    if (!me || !me.alive) {
      throw new WerewolfError("DEAD_PLAYER", "你已经出局了");
    }
    if (!act || typeof act.kind !== "string") {
      throw new WerewolfError("BAD_ACTION", "上警动作不合法");
    }
    if (act.kind === "sheriff") {
      const target = act.target;
      if (target === undefined) {
        // 上警报名
        if (!next.spokenSeats.includes(seat)) {
          next.spokenSeats.push(seat);
        }
        return next;
      }
      // 上警投票
      if (target === null || typeof target !== "string") {
        throw new WerewolfError("BAD_ACTION", "上警投票目标不合法");
      }
      const tp = findPlayer(next, target);
      if (!tp || !tp.alive) {
        throw new WerewolfError("ILLEGAL_TARGET", "上警目标必须是存活玩家");
      }
      if (!next.spokenSeats.includes(target)) {
        throw new WerewolfError("ILLEGAL_TARGET", "该玩家没有上警");
      }
      next.sheriffVotes = next.sheriffVotes.filter((v) => v.seat !== seat);
      next.sheriffVotes.push({ seat, target });
      return next;
    }
    if (act.kind === "sheriff_pass") {
      // 退水：不进入 spokenSeats
      return next;
    }
    if (act.kind === "sheriff_done") {
      // 结束上警阶段，结算
      resolveSheriffVote(next);
      return next;
    }
    throw new WerewolfError("BAD_ACTION", "上警动作不合法");
  }

  if (state.phase === "speak") {
    if (!act || act.kind !== "speak_done") {
      throw new WerewolfError("BAD_ACTION", "现在需要发言完成");
    }
    if (state.currentSeat !== seat && state.currentSeat !== "") {
      throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
    }
    const next = cloneState(state);
    if (!next.spokenSeats.includes(seat)) {
      next.spokenSeats.push(seat);
    }
    const order = speakOrder(next);
    const remaining = order.filter((s) => !next.spokenSeats.includes(s));
    if (remaining.length > 0) {
      next.currentSeat = remaining[0];
      return next;
    }
    enterVote(next);
    return next;
  }

  if (state.phase === "vote") {
    if (!act || act.kind !== "vote") {
      throw new WerewolfError("BAD_ACTION", "现在需要投票");
    }
    if (state.currentSeat !== seat && state.currentSeat !== "") {
      throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
    }
    const me = findPlayer(state, seat);
    if (!me || !me.alive) {
      throw new WerewolfError("DEAD_PLAYER", "你已经出局了");
    }
    const target = act.target;
    if (target !== null && typeof target !== "string") {
      throw new WerewolfError("BAD_ACTION", "投票目标不合法");
    }
    if (typeof target === "string") {
      const tp = findPlayer(state, target);
      if (!tp || !tp.alive) {
        throw new WerewolfError("ILLEGAL_TARGET", "投票目标必须是存活玩家");
      }
    }
    const next = cloneState(state);
    next.votes = next.votes.filter((v) => v.seat !== seat);
    next.votes.push({ seat, target: target === null ? null : target });
    const alive = next.players.filter((p) => p.alive).map((p) => p.seat);
    const notVoted = alive.filter((s) => !next.votes.some((v) => v.seat === s));
    if (notVoted.length > 0) {
      next.currentSeat = notVoted[0];
      return next;
    }
    resolveVote(next);
    return next;
  }

  if (state.phase === "pk_speak") {
    if (!act || act.kind !== "speak_done") {
      throw new WerewolfError("BAD_ACTION", "现在需要发言完成");
    }
    if (state.currentSeat !== seat && state.currentSeat !== "") {
      throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
    }
    const next = cloneState(state);
    if (!next.spokenSeats.includes(seat)) {
      next.spokenSeats.push(seat);
    }
    const remaining = next.pkSeats.filter((s) => !next.spokenSeats.includes(s));
    if (remaining.length > 0) {
      next.currentSeat = remaining[0];
      return next;
    }
    // PK 发言完毕，进入 PK 投票
    next.phase = "pk_vote";
    next.pkVotes = [];
    const alive = next.players.filter((p) => p.alive).map((p) => p.seat);
    if (alive.length === 0) {
      enterNightAfterDay(next);
      return next;
    }
    next.currentSeat = alive[0];
    return next;
  }

  if (state.phase === "pk_vote") {
    if (!act || act.kind !== "vote") {
      throw new WerewolfError("BAD_ACTION", "现在需要投票");
    }
    if (state.currentSeat !== seat && state.currentSeat !== "") {
      throw new WerewolfError("NOT_YOUR_TURN", "现在不是你的回合");
    }
    const me = findPlayer(state, seat);
    if (!me || !me.alive) {
      throw new WerewolfError("DEAD_PLAYER", "你已经出局了");
    }
    const target = act.target;
    if (target !== null && typeof target !== "string") {
      throw new WerewolfError("BAD_ACTION", "投票目标不合法");
    }
    if (typeof target === "string") {
      if (!state.pkSeats.includes(target)) {
        throw new WerewolfError("ILLEGAL_TARGET", "PK 阶段只能投平票玩家");
      }
      const tp = findPlayer(state, target);
      if (!tp || !tp.alive) {
        throw new WerewolfError("ILLEGAL_TARGET", "投票目标必须是存活玩家");
      }
    }
    const next = cloneState(state);
    next.pkVotes = next.pkVotes.filter((v) => v.seat !== seat);
    next.pkVotes.push({ seat, target: target === null ? null : target });
    const alive = next.players.filter((p) => p.alive).map((p) => p.seat);
    const notVoted = alive.filter((s) => !next.pkVotes.some((v) => v.seat === s));
    if (notVoted.length > 0) {
      next.currentSeat = notVoted[0];
      return next;
    }
    resolvePkVote(next);
    return next;
  }

  throw new WerewolfError("WRONG_PHASE", "当前阶段不能行动");
}

export function serializeForSeat(state: GameState, seat: string): unknown {
  const me = state.players.find((p) => p.seat === seat);
  const iAmWolf = me !== undefined && me.role === "werewolf";
  const iAmSeer = me !== undefined && me.role === "seer";
  const iAmWitch = me !== undefined && me.role === "witch";

  const players = state.players.map((p) => {
    const view: {
      seat: string;
      alive: boolean;
      isSheriff: boolean;
      role?: Role;
    } = {
      seat: p.seat,
      alive: p.alive,
      isSheriff: p.isSheriff,
    };
    if (p.seat === seat) {
      view.role = p.role;
    } else if (iAmWolf && p.role === "werewolf") {
      view.role = p.role;
    }
    return view;
  });

  const out: {
    phase: Phase;
    day: number;
    players: typeof players;
    currentSeat: string;
    deaths: { seat: string; reason: "wolf" | "witch" | "vote" | "hunter" }[];
    lastwordsQueue: string[];
    sheriffSeat: string | null;
    votes: { seat: string; target: string | null }[];
    sheriffVotes: { seat: string; target: string | null }[];
    pkSeats: string[];
    pkVotes: { seat: string; target: string | null }[];
    wolfSeats?: string[];
    seerHistory?: { day: number; target: string; result: "wolf" | "good" }[];
    seerResult?: "wolf" | "good" | null;
    wolfTarget?: string | null;
    winner?: "wolves" | "good";
  } = {
    phase: state.phase,
    day: state.day,
    players,
    currentSeat: state.currentSeat,
    deaths: state.deaths.map((d) => ({ seat: d.seat, reason: d.reason })),
    lastwordsQueue: state.lastwordsQueue.slice(),
    sheriffSeat: state.sheriffSeat,
    votes: state.votes.map((v) => ({ seat: v.seat, target: v.target })),
    sheriffVotes: state.sheriffVotes.map((v) => ({ seat: v.seat, target: v.target })),
    pkSeats: state.pkSeats.slice(),
    pkVotes: state.pkVotes.map((v) => ({ seat: v.seat, target: v.target })),
  };

  if (iAmWolf) {
    out.wolfSeats = state.players
      .filter((p) => p.role === "werewolf")
      .map((p) => p.seat);
  }

  if (iAmSeer) {
    out.seerHistory = state.night.seerHistory.map((h) => ({
      day: h.day,
      target: h.target,
      result: h.result,
    }));
    out.seerResult = state.night.seerResult;
  }

  if (iAmWitch && state.phase === "night" && state.night.step === "witch") {
    out.wolfTarget = state.night.wolfTarget;
  }

  if (state.winner !== undefined) {
    out.winner = state.winner;
  }

  return out;
}
