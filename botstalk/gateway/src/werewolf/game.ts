import { assignRoles, ROLE_INFO } from "./roles.js";
import type { Faction, Role } from "./roles.js";

/**
 * 狼人杀对局状态机（纯函数式）。
 * 所有导出函数返回新的 GameState，不修改入参。
 *
 * 阶段流转：
 *   night (nightStep: guard -> wolves -> seer -> witch)
 *     -> announce（公布夜晚死讯）
 *     -> lastwords（死者遗言，按死亡顺序逐个）
 *     -> [仅第 1 天] sheriff（竞选警长）
 *     -> speak（发言）
 *     -> vote（放逐投票）
 *       平票 -> pk_speak -> pk_vote -> 出局 / 平安日
 *     -> night (day+1) 或 finished
 *
 * 终局：狼人全死 -> good 胜；好人全死 -> wolves 胜。
 */

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

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

export interface PlayerState {
  seat: string;
  role: Role;
  alive: boolean;
  isSheriff: boolean;
}

export interface DeathRecord {
  seat: string;
  reason: "wolf" | "poison" | "vote" | "shot";
  day: number;
}

export interface VoteRecord {
  voter: string;
  target: string | null; // null = 弃票
}

export interface SheriffVoteRecord {
  voter: string;
  target: string | null; // null = 退水 / 弃票
}

export interface WerewolfConfig {
  sheriff?: boolean;
}

export interface GameState {
  phase: Phase;
  day: number; // 第几天，从 1 开始；夜晚结束时 day 保持为当前天数
  players: PlayerState[]; // 固定座位顺序
  currentSeat: string; // 当前该谁行动（依 phase/nightStep 含义不同）
  nightStep: NightStep; // 仅在 phase === "night" 有意义
  winner?: "wolves" | "good";

  // 公开信息（serializeForSeat 无差别下发）
  deaths: DeathRecord[]; // 全部已公开的死亡记录
  lastwordsQueue: string[]; // 待遗言的座位（按死亡顺序）
  lastwordsIdx: number; // 当前遗言索引
  sheriffSeat?: string; // 当前警长（可能死亡后移交或撕掉）
  votes: { day: number; records: VoteRecord[]; exiled: string | null }[]; // 放逐投票历史
  pkSeats: string[]; // 当前 PK 台上座位（空=非 pk）
  sheriffVotes: SheriffVoteRecord[]; // 警长竞选投票记录

  // —— 内部字段 ——
  config: WerewolfConfig;
  // 夜间提交的动作（每次进入新夜晚清空）
  night: {
    guardTarget: string | null; // 守卫提交的守护目标
    guardPrevTarget: string | null; // 上一晚守护目标（用于连守判定）
    wolfTarget: string | null; // 狼人刀目标
    seerTarget: string | null; // 预言家查验目标
    seerResult: "wolf" | "good" | null; // 预言家查验结果（本人可见）
    seerHistory: { seat: string; result: "wolf" | "good"; day: number }[]; // 预言家历史
    witchSaveUsed: boolean; // 解药是否已用（全局）
    witchPoisonUsed: boolean; // 毒药是否已用（全局）
    witchSaveTarget: string | null; // 女巫解药目标
    witchPoisonTarget: string | null; // 女巫毒药目标
    witchActed: boolean; // 女巫是否已提交
    deathsTonight: { seat: string; reason: "wolf" | "poison" }[]; // 今夜死亡结算
  };
  hunterShootPending: string | null; // 待开枪猎人座位（null = 无）
  lastwordsToNight: boolean; // 遗言排空后去向：true=进入下一夜（投票出局），false=走白天流程（夜晚死亡）
  // 每个阶段完成的座位集合（用于推进）
  spokenSeats: string[]; // 已发言完的座位（当天）
  sheriffOrderStart: string | null; // 警长指定的发言顺序起点
  // 记录夜间是否有人被守卫救（用于结算）
  rng: () => number;
}

// ---------------------------------------------------------------------------
// 错误
// ---------------------------------------------------------------------------

export class WerewolfError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "WerewolfError";
  }
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

function err(code: string, message: string): WerewolfError {
  return new WerewolfError(code, message);
}

function isWolf(role: Role): boolean {
  return ROLE_INFO[role].faction === "wolves";
}

function factionOf(role: Role): Faction {
  return ROLE_INFO[role].faction;
}

function clonePlayer(p: PlayerState): PlayerState {
  return { seat: p.seat, role: p.role, alive: p.alive, isSheriff: p.isSheriff };
}

function cloneState(state: GameState): GameState {
  const next: GameState = {
    phase: state.phase,
    day: state.day,
    players: state.players.map(clonePlayer),
    currentSeat: state.currentSeat,
    nightStep: state.nightStep,
    deaths: state.deaths.map((d) => ({ ...d })),
    lastwordsQueue: state.lastwordsQueue.slice(),
    lastwordsIdx: state.lastwordsIdx,
    votes: state.votes.map((v) => ({
      day: v.day,
      records: v.records.map((r) => ({ ...r })),
      exiled: v.exiled,
    })),
    pkSeats: state.pkSeats.slice(),
    sheriffVotes: state.sheriffVotes.map((r) => ({ ...r })),
    config: { ...state.config },
    night: {
      guardTarget: state.night.guardTarget,
      guardPrevTarget: state.night.guardPrevTarget,
      wolfTarget: state.night.wolfTarget,
      seerTarget: state.night.seerTarget,
      seerResult: state.night.seerResult,
      seerHistory: state.night.seerHistory.map((h) => ({ ...h })),
      witchSaveUsed: state.night.witchSaveUsed,
      witchPoisonUsed: state.night.witchPoisonUsed,
      witchSaveTarget: state.night.witchSaveTarget,
      witchPoisonTarget: state.night.witchPoisonTarget,
      witchActed: state.night.witchActed,
      deathsTonight: state.night.deathsTonight.map((d) => ({ ...d })),
    },
    hunterShootPending: state.hunterShootPending,
    lastwordsToNight: state.lastwordsToNight,
    spokenSeats: state.spokenSeats.slice(),
    sheriffOrderStart: state.sheriffOrderStart,
    rng: state.rng,
  };
  if (state.winner !== undefined) next.winner = state.winner;
  if (state.sheriffSeat !== undefined) next.sheriffSeat = state.sheriffSeat;
  return next;
}

function findPlayer(state: GameState, seat: string): PlayerState | undefined {
  return state.players.find((p) => p.seat === seat);
}

function alivePlayers(state: GameState): PlayerState[] {
  return state.players.filter((p) => p.alive);
}

function aliveWolves(state: GameState): PlayerState[] {
  return state.players.filter((p) => p.alive && isWolf(p.role));
}

function aliveGood(state: GameState): PlayerState[] {
  return state.players.filter((p) => p.alive && !isWolf(p.role));
}

function firstAliveSeat(state: GameState): string {
  const a = alivePlayers(state);
  if (a.length === 0) return "";
  return a[0].seat;
}

// 从 start 座位开始，按座位表顺序找下一个存活座位（含 start 本身）
function nextAliveFrom(state: GameState, start: string): string {
  const idx = state.players.findIndex((p) => p.seat === start);
  if (idx < 0) return firstAliveSeat(state);
  const n = state.players.length;
  for (let step = 0; step < n; step++) {
    const p = state.players[(idx + step) % n];
    if (p.alive) return p.seat;
  }
  return "";
}

// 下一个尚未发言的存活座位（按座位顺序循环），返回 null 表示全部发言完
function nextUnspoken(
  state: GameState,
  fromSeat: string,
  spoken: string[],
): string | null {
  const idx = state.players.findIndex((p) => p.seat === fromSeat);
  if (idx < 0) return null;
  const n = state.players.length;
  for (let step = 0; step < n; step++) {
    const p = state.players[(idx + step) % n];
    if (!p.alive) continue;
    if (spoken.includes(p.seat)) continue;
    return p.seat;
  }
  return null;
}

// ---------------------------------------------------------------------------
// 终局判定
// ---------------------------------------------------------------------------

function checkWinner(state: GameState): "wolves" | "good" | null {
  const wolves = aliveWolves(state).length;
  const good = aliveGood(state).length;
  if (wolves === 0) return "good";
  if (good === 0) return "wolves";
  return null;
}

// ---------------------------------------------------------------------------
// 初始化
// ---------------------------------------------------------------------------

export function createGame(
  seats: string[],
  config: WerewolfConfig = {},
  rng: () => number = Math.random,
): GameState {
  if (!Array.isArray(seats)) throw err("BAD_SEATS", "seats 必须是数组");
  for (const s of seats) {
    if (typeof s !== "string" || s.length === 0) {
      throw err("BAD_SEATS", "座位必须是非空字符串");
    }
  }
  if (new Set(seats).size !== seats.length) {
    throw err("BAD_SEATS", "座位必须互不相同");
  }
  let roles: Map<string, Role>;
  try {
    roles = assignRoles(seats, rng);
  } catch (e) {
    throw err("BAD_SEATS", e instanceof Error ? e.message : "分配角色失败");
  }
  const players: PlayerState[] = seats.map((seat) => ({
    seat,
    role: roles.get(seat) as Role,
    alive: true,
    isSheriff: false,
  }));

  const state: GameState = {
    phase: "night",
    day: 1,
    players,
    currentSeat: "",
    nightStep: "guard",
    deaths: [],
    lastwordsQueue: [],
    lastwordsIdx: 0,
    votes: [],
    pkSeats: [],
    sheriffVotes: [],
    config: { ...config },
    night: {
      guardTarget: null,
      guardPrevTarget: null,
      wolfTarget: null,
      seerTarget: null,
      seerResult: null,
      seerHistory: [],
      witchSaveUsed: false,
      witchPoisonUsed: false,
      witchSaveTarget: null,
      witchPoisonTarget: null,
      witchActed: false,
      deathsTonight: [],
    },
    hunterShootPending: null,
    lastwordsToNight: false,
    spokenSeats: [],
    sheriffOrderStart: null,
    rng,
  };

  advanceNightStep(state);
  return state;
}

// ---------------------------------------------------------------------------
// 夜晚阶段推进
// ---------------------------------------------------------------------------

// 判断某角色是否存在且存活
function roleAlive(state: GameState, role: Role): PlayerState | null {
  for (const p of state.players) {
    if (p.alive && p.role === role) return p;
  }
  return null;
}

// 根据 nightStep 设置 currentSeat（该谁行动）；无对应角色则跳过。
// 修改传入 state（调用方必须已 clone）。
function advanceNightStep(state: GameState): void {
  while (true) {
    if (state.nightStep === "guard") {
      const g = roleAlive(state, "guard");
      if (g) {
        state.currentSeat = g.seat;
        return;
      }
      state.nightStep = "wolves";
      continue;
    }
    if (state.nightStep === "wolves") {
      const w = aliveWolves(state);
      if (w.length > 0) {
        // 狼人共享行动：currentSeat 设为第一个活狼
        state.currentSeat = w[0].seat;
        return;
      }
      state.nightStep = "seer";
      continue;
    }
    if (state.nightStep === "seer") {
      const s = roleAlive(state, "seer");
      if (s) {
        state.currentSeat = s.seat;
        return;
      }
      state.nightStep = "witch";
      continue;
    }
    if (state.nightStep === "witch") {
      const wi = roleAlive(state, "witch");
      if (wi) {
        state.currentSeat = wi.seat;
        return;
      }
      // 女巫不存在，直接结算
      resolveNight(state);
      return;
    }
    return;
  }
}

// ---------------------------------------------------------------------------
// 夜间结算
// ---------------------------------------------------------------------------

// 修改传入 state
function resolveNight(state: GameState): void {
  const deaths: { seat: string; reason: "wolf" | "poison" }[] = [];
  const wolfTarget = state.night.wolfTarget;
  const guardTarget = state.night.guardTarget;
  const guardPrev = state.night.guardPrevTarget;

  // 守卫守护是否有效：不能连守同一人
  const guardEffective =
    guardTarget !== null && guardTarget !== guardPrev;

  let wolfKilled = false;
  if (wolfTarget !== null) {
    const guarded = guardEffective && guardTarget === wolfTarget;
    const savedByWitch =
      state.night.witchSaveTarget !== null &&
      state.night.witchSaveTarget === wolfTarget;
    // 同守同救：仍死
    if (guarded && savedByWitch) {
      deaths.push({ seat: wolfTarget, reason: "wolf" });
      wolfKilled = true;
    } else if (guarded) {
      // 守卫救活
    } else if (savedByWitch) {
      // 女巫解药救活
    } else {
      deaths.push({ seat: wolfTarget, reason: "wolf" });
      wolfKilled = true;
    }
  }

  if (state.night.witchPoisonTarget !== null) {
    // 毒药：若目标已被守卫守护或已被解药救，毒药仍然生效（毒是另一来源）
    const poisonTarget = state.night.witchPoisonTarget;
    // 若目标已经在死亡列表中（被刀），不重复添加
    if (!deaths.some((d) => d.seat === poisonTarget)) {
      deaths.push({ seat: poisonTarget, reason: "poison" });
    }
  }

  state.night.deathsTonight = deaths;
  // 记录下一晚守卫的上次目标
  state.night.guardPrevTarget = state.night.guardTarget;
  void wolfKilled;

  // 应用死亡
  for (const d of deaths) {
    const p = findPlayer(state, d.seat);
    if (p && p.alive) {
      p.alive = false;
      state.deaths.push({ seat: d.seat, reason: d.reason, day: state.day });
      state.lastwordsQueue.push(d.seat);
    }
  }

  // 检查是否有人是猎人且因狼刀死亡 -> 需要开枪（白天出局才不可开枪，这里被刀可以）
  // 猎人被毒死不可开枪；被狼刀可开枪
  for (const d of deaths) {
    const p = findPlayer(state, d.seat);
    if (p && p.role === "hunter" && d.reason === "wolf") {
      state.hunterShootPending = p.seat;
    }
  }

  // 清除夜晚动作
  state.night.guardTarget = null;
  state.night.wolfTarget = null;
  state.night.seerTarget = null;
  state.night.seerResult = null;
  state.night.witchSaveTarget = null;
  state.night.witchPoisonTarget = null;
  state.night.witchActed = false;

  // 终局检查
  const w = checkWinner(state);
  if (w) {
    state.phase = "finished";
    state.winner = w;
    state.currentSeat = "";
    return;
  }

  // 进入公布死讯阶段
  state.phase = "announce";
  state.currentSeat = "";
}

// 从 announce 阶段推进到下一个阶段
function afterAnnounce(state: GameState): void {
  // 若猎人待开枪 -> 进入猎人开枪（此处直接处理为 lastwords 前插入）
  // 简化：先处理遗言队列，猎人开枪在遗言阶段由 hunter_shoot action 触发
  // 若遗言队列为空则跳过
  if (state.lastwordsQueue.length > state.lastwordsIdx) {
    state.phase = "lastwords";
    state.currentSeat = state.lastwordsQueue[state.lastwordsIdx];
    state.lastwordsToNight = false;
    return;
  }
  afterLastwords(state);
}

function afterLastwords(state: GameState): void {
  // 遗言阶段结束，进入 sheriff（仅第 1 天）或 speak
  // 第 1 天且启用警长且尚未竞选
  if (state.day === 1 && state.config.sheriff !== false && !sheriffDone(state)) {
    startSheriff(state);
    return;
  }
  startSpeak(state);
}

// 判断是否已经完成过警长竞选（用 sheriffVotes 是否非空标记已进行过）
function sheriffDone(state: GameState): boolean {
  // 一旦竞选过（有投票记录）就不再竞选
  return state.sheriffVotes.length > 0;
}

// 修改传入 state：进入警长竞选
function startSheriff(state: GameState): void {
  state.phase = "sheriff";
  state.sheriffVotes = [];
  state.spokenSeats = [];
  // currentSeat 标记为第一个存活座位（用于上警阶段）——警长竞选阶段任何活人都可上警/退水，
  // 但协议上用 currentSeat 表示"当前轮到谁上警决策"，采用顺序决策。
  const first = firstAliveSeat(state);
  state.currentSeat = first;
  // 用 pkSeats 复用存储上警候选人
  state.pkSeats = [];
}

// 修改传入 state：进入发言阶段
function startSpeak(state: GameState): void {
  state.phase = "speak";
  state.spokenSeats = [];
  state.pkSeats = [];
  // 发言起点：若警长存在则从警长开始，否则从第一个存活座位
  const start = state.sheriffSeat && findPlayer(state, state.sheriffSeat)?.alive
    ? state.sheriffSeat
    : firstAliveSeat(state);
  state.sheriffOrderStart = start;
  state.currentSeat = start;
}

// 修改传入 state：进入投票阶段
function startVote(state: GameState): void {
  state.phase = "vote";
  state.pkSeats = [];
  state.currentSeat = firstAliveSeat(state);
}

// 修改传入 state：进入 pk_speak
function startPkSpeak(state: GameState, pkSeats: string[]): void {
  state.phase = "pk_speak";
  state.pkSeats = pkSeats.slice();
  state.spokenSeats = [];
  state.currentSeat = pkSeats[0];
}

// 修改传入 state：进入 pk_vote
function startPkVote(state: GameState, pkSeats: string[]): void {
  state.phase = "pk_vote";
  state.pkSeats = pkSeats.slice();
  state.currentSeat = firstAliveSeat(state);
}

// ---------------------------------------------------------------------------
// 夜晚动作
// ---------------------------------------------------------------------------

export function nightAction(
  state: GameState,
  seat: string,
  action: unknown,
): GameState {
  if (state.phase !== "night") throw err("WRONG_PHASE", "当前不是夜晚阶段");
  const me = findPlayer(state, seat);
  if (!me) throw err("UNKNOWN_SEAT", `未知座位: ${seat}`);
  if (!me.alive) throw err("DEAD_PLAYER", "出局玩家不能行动");
  if (state.currentSeat !== seat) throw err("NOT_YOUR_TURN", `当前轮到 ${state.currentSeat}`);

  if (typeof action !== "object" || action === null) {
    throw err("BAD_ACTION", "动作必须是对象");
  }
  const act = action as { kind?: unknown; target?: unknown; potion?: unknown };
  if (act.kind !== "night") throw err("BAD_ACTION", `未知动作: ${String(act.kind)}`);

  const next = cloneState(state);

  if (next.nightStep === "guard") {
    if (me.role !== "guard") throw err("NOT_YOUR_TURN", "当前不是你的行动");
    const target = act.target;
    if (target !== null && typeof target !== "string") {
      throw err("ILLEGAL_TARGET", "target 必须是座位或 null");
    }
    if (target !== null) {
      const tp = findPlayer(next, target);
      if (!tp) throw err("ILLEGAL_TARGET", `未知目标: ${target}`);
      if (!tp.alive) throw err("ILLEGAL_TARGET", "不能守护出局玩家");
      if (next.night.guardPrevTarget === target) {
        throw err("ILLEGAL_TARGET", "不能连续两晚守护同一人");
      }
    }
    next.night.guardTarget = target as string | null;
    next.nightStep = "wolves";
    advanceNightStep(next);
    return next;
  }

  if (next.nightStep === "wolves") {
    if (!isWolf(me.role)) throw err("NOT_YOUR_TURN", "当前不是你的行动");
    const target = act.target;
    if (target !== null && typeof target !== "string") {
      throw err("ILLEGAL_TARGET", "target 必须是座位或 null");
    }
    if (target !== null) {
      const tp = findPlayer(next, target);
      if (!tp) throw err("ILLEGAL_TARGET", `未知目标: ${target}`);
      if (!tp.alive) throw err("ILLEGAL_TARGET", "不能击杀出局玩家");
      if (isWolf(tp.role)) throw err("ILLEGAL_TARGET", "不能击杀狼人");
    }
    next.night.wolfTarget = target as string | null;
    next.nightStep = "seer";
    advanceNightStep(next);
    return next;
  }

  if (next.nightStep === "seer") {
    if (me.role !== "seer") throw err("NOT_YOUR_TURN", "当前不是你的行动");
    const target = act.target;
    if (target !== null && typeof target !== "string") {
      throw err("ILLEGAL_TARGET", "target 必须是座位或 null");
    }
    if (target !== null) {
      const tp = findPlayer(next, target);
      if (!tp) throw err("ILLEGAL_TARGET", `未知目标: ${target}`);
      if (!tp.alive) throw err("ILLEGAL_TARGET", "不能查验出局玩家");
      if (tp.seat === seat) throw err("ILLEGAL_TARGET", "不能查验自己");
      const result: "wolf" | "good" = isWolf(tp.role) ? "wolf" : "good";
      next.night.seerTarget = target;
      next.night.seerResult = result;
      next.night.seerHistory.push({ seat: target, result, day: next.day });
    }
    next.nightStep = "witch";
    advanceNightStep(next);
    return next;
  }

  if (next.nightStep === "witch") {
    if (me.role !== "witch") throw err("NOT_YOUR_TURN", "当前不是你的行动");
    if (next.night.witchActed) throw err("WRONG_PHASE", "女巫本晚已行动");
    const potion = act.potion;
    if (potion !== null && potion !== undefined && potion !== "save" && potion !== "poison") {
      throw err("BAD_ACTION", `非法 potion: ${String(potion)}`);
    }
    const target = act.target;
    if (target !== null && target !== undefined && typeof target !== "string") {
      throw err("ILLEGAL_TARGET", "target 必须是座位或 null");
    }
    if (potion === "save") {
      if (next.night.witchSaveUsed) throw err("ILLEGAL_TARGET", "解药已用完");
      if (typeof target !== "string") throw err("ILLEGAL_TARGET", "使用解药必须指定目标");
      const tp = findPlayer(next, target);
      if (!tp) throw err("ILLEGAL_TARGET", `未知目标: ${target}`);
      if (!tp.alive) throw err("ILLEGAL_TARGET", "不能救治出局玩家");
      if (next.day === 1 && target === seat) {
        throw err("ILLEGAL_TARGET", "首夜不能自救");
      }
      next.night.witchSaveTarget = target;
      next.night.witchSaveUsed = true;
    } else if (potion === "poison") {
      if (next.night.witchPoisonUsed) throw err("ILLEGAL_TARGET", "毒药已用完");
      if (typeof target !== "string") throw err("ILLEGAL_TARGET", "使用毒药必须指定目标");
      const tp = findPlayer(next, target);
      if (!tp) throw err("ILLEGAL_TARGET", `未知目标: ${target}`);
      if (!tp.alive) throw err("ILLEGAL_TARGET", "不能毒杀出局玩家");
      next.night.witchPoisonTarget = target;
      next.night.witchPoisonUsed = true;
    }
    // 不用药：potion === null 或 undefined
    next.night.witchActed = true;
    // 结算夜晚
    resolveNight(next);
    return next;
  }

  throw err("WRONG_PHASE", "未知夜晚步骤");
}

// ---------------------------------------------------------------------------
// 白天动作
// ---------------------------------------------------------------------------

export function dayAction(
  state: GameState,
  seat: string,
  action: unknown,
): GameState {
  if (state.phase === "night") throw err("WRONG_PHASE", "当前是夜晚阶段，请用 nightAction");
  if (state.phase === "finished") throw err("WRONG_PHASE", "对局已结束");
  const me = findPlayer(state, seat);
  if (!me) throw err("UNKNOWN_SEAT", `未知座位: ${seat}`);

  if (typeof action !== "object" || action === null) {
    throw err("BAD_ACTION", "动作必须是对象");
  }
  const act = action as { kind?: unknown; target?: unknown };
  const kind = act.kind;

  // 公布死讯确认：announce -> lastwords / sheriff / speak（afterAnnounce 决定）
  if (kind === "announce_done") {
    if (state.phase !== "announce") throw err("WRONG_PHASE", "当前不是公布死讯阶段");
    const next = cloneState(state);
    afterAnnounce(next);
    return next;
  }

  // 遗言阶段：死者说完了
  if (kind === "lastwords_done") {
    if (state.phase !== "lastwords") throw err("WRONG_PHASE", "当前不是遗言阶段");
    if (state.currentSeat !== seat) throw err("NOT_YOUR_TURN", `当前轮到 ${state.currentSeat}`);
    const next = cloneState(state);
    next.lastwordsIdx++;
    if (next.lastwordsIdx >= next.lastwordsQueue.length) {
      // 遗言完毕
      // 若有猎人待开枪且未处理，先让猎人开枪
      if (next.hunterShootPending) {
        const hp = next.hunterShootPending;
        if (next.lastwordsQueue[next.lastwordsQueue.length - 1] !== hp) {
          // 保持在 lastwords 阶段，但切换到猎人
          next.currentSeat = hp;
          // 用一个特殊标记：等待 hunter_shoot
          next.phase = "lastwords";
          next.lastwordsQueue.push(hp);
          // 不推进 idx
        } else {
          // 猎人已在待发言位却发了 lastwords_done：视为放弃开枪
          next.hunterShootPending = null;
          if (next.lastwordsToNight) startSpeakForNextDay(next);
          else afterLastwords(next);
        }
      } else if (next.lastwordsToNight) {
        startSpeakForNextDay(next);
      } else {
        afterLastwords(next);
      }
    } else {
      next.currentSeat = next.lastwordsQueue[next.lastwordsIdx];
    }
    return next;
  }

  // 猎人开枪
  if (kind === "hunter_shoot") {
    const hunterSeat = state.hunterShootPending;
    if (hunterSeat === null) throw err("WRONG_PHASE", "当前没有待开枪的猎人");
    if (seat !== hunterSeat) throw err("NOT_YOUR_TURN", "只有猎人本人可以开枪");
    const target = act.target;
    if (typeof target !== "string") throw err("ILLEGAL_TARGET", "必须指定开枪目标");
    const tp = findPlayer(state, target);
    if (!tp) throw err("ILLEGAL_TARGET", `未知目标: ${target}`);
    if (!tp.alive) throw err("ILLEGAL_TARGET", "不能带走出局玩家");
    if (tp.seat === seat) throw err("ILLEGAL_TARGET", "不能带走自己");

    const next = cloneState(state);
    next.hunterShootPending = null;
    tp.alive = false;
    next.deaths.push({ seat: target, reason: "shot", day: next.day });
    // 猎人开枪带走的人也进入遗言队列？标准：被带走的人无遗言（仅被投票/被刀者有）。
    // 简化：被枪杀者不进入遗言队列。
    // 若目标也是猎人，不连锁（一人一枪）。
    const w = checkWinner(next);
    if (w) {
      next.phase = "finished";
      next.winner = w;
      next.currentSeat = "";
      return next;
    }
    // 处理剩余的遗言队列
    if (next.lastwordsIdx < next.lastwordsQueue.length) {
      next.phase = "lastwords";
      next.currentSeat = next.lastwordsQueue[next.lastwordsIdx];
    } else if (next.lastwordsToNight) {
      startSpeakForNextDay(next);
    } else {
      afterLastwords(next);
    }
    return next;
  }

  // 警长竞选阶段：上警 / 退水
  if (kind === "sheriff") {
    if (state.phase !== "sheriff") throw err("WRONG_PHASE", "当前不是警长竞选阶段");
    if (!me.alive) throw err("DEAD_PLAYER", "出局玩家不能参与竞选");
    if (state.currentSeat !== seat) throw err("NOT_YOUR_TURN", `当前轮到 ${state.currentSeat}`);
    const target = act.target;
    // 语义：target=seat 自己 => 上警；target=null => 退水/不上警
    // 简化：任意 target 字符串表示投给该候选人（或自己上警），null 表示不上警/退水
    const next = cloneState(state);
    if (target === null) {
      // 不上警 / 退水
      next.sheriffVotes.push({ voter: seat, target: null });
    } else if (typeof target === "string") {
      // 上警：把自己加入 pkSeats 候选人，并记录"投票给自己"
      if (!next.pkSeats.includes(seat)) {
        next.pkSeats.push(seat);
      }
      next.sheriffVotes.push({ voter: seat, target: seat });
      void target;
    } else {
      throw err("ILLEGAL_TARGET", "target 必须是座位或 null");
    }
    // 推进到下一个存活座位；全部处理完则计票
    const nextSeat = nextAliveFrom(next, seat);
    const doneSeats = new Set(next.sheriffVotes.map((v) => v.voter));
    let allDone = true;
    for (const p of alivePlayers(next)) {
      if (!doneSeats.has(p.seat)) {
        allDone = false;
        break;
      }
    }
    if (allDone) {
      // 计票：统计每个候选人的票数（上警者算自己一票）
      const tally = new Map<string, number>();
      for (const v of next.sheriffVotes) {
        if (v.target !== null) {
          tally.set(v.target, (tally.get(v.target) ?? 0) + 1);
        }
      }
      let maxVotes = 0;
      let winners: string[] = [];
      for (const [s, c] of tally) {
        if (c > maxVotes) {
          maxVotes = c;
          winners = [s];
        } else if (c === maxVotes) {
          winners.push(s);
        }
      }
      if (winners.length === 1 && maxVotes > 0) {
        const sheriff = findPlayer(next, winners[0]);
        if (sheriff) sheriff.isSheriff = true;
        next.sheriffSeat = winners[0];
      } else {
        // 平票无警长
        next.sheriffSeat = undefined;
      }
      startSpeak(next);
    } else {
      // 找下一个未投票的存活座位
      let ns: string | null = null;
      for (const p of alivePlayers(next)) {
        if (!doneSeats.has(p.seat)) {
          ns = p.seat;
          break;
        }
      }
      next.currentSeat = ns ?? firstAliveSeat(next);
      void nextSeat;
    }
    return next;
  }

  // 发言结束
  if (kind === "speak_done") {
    if (state.phase !== "speak" && state.phase !== "pk_speak") {
      throw err("WRONG_PHASE", "当前不是发言阶段");
    }
    if (!me.alive) throw err("DEAD_PLAYER", "出局玩家不能发言");
    if (state.currentSeat !== seat) throw err("NOT_YOUR_TURN", `当前轮到 ${state.currentSeat}`);
    const next = cloneState(state);
    if (!next.spokenSeats.includes(seat)) next.spokenSeats.push(seat);
    if (next.phase === "speak") {
      const nextSeat = nextUnspoken(next, nextAliveFrom(next, seat), next.spokenSeats);
      if (nextSeat === null) {
        startVote(next);
      } else {
        next.currentSeat = nextSeat;
      }
    } else {
      // pk_speak：仅 PK 台上的人发言
      const remaining = next.pkSeats.filter((s) => !next.spokenSeats.includes(s));
      if (remaining.length === 0) {
        startPkVote(next, next.pkSeats);
      } else {
        next.currentSeat = remaining[0];
      }
    }
    return next;
  }

  // 警长移交警徽 / 撕掉
  if (kind === "sheriff_pass") {
    if (state.sheriffSeat !== seat) throw err("NOT_YOUR_TURN", "只有警长可以移交警徽");
    const target = act.target;
    const next = cloneState(state);
    if (target === null) {
      // 撕掉
      const cur = findPlayer(next, seat);
      if (cur) cur.isSheriff = false;
      next.sheriffSeat = undefined;
    } else if (typeof target === "string") {
      const tp = findPlayer(next, target);
      if (!tp) throw err("ILLEGAL_TARGET", `未知目标: ${target}`);
      if (!tp.alive) throw err("ILLEGAL_TARGET", "不能移交给出局玩家");
      const cur = findPlayer(next, seat);
      if (cur) cur.isSheriff = false;
      tp.isSheriff = true;
      next.sheriffSeat = target;
    } else {
      throw err("ILLEGAL_TARGET", "target 必须是座位或 null");
    }
    return next;
  }

  // 放逐投票
  if (kind === "vote") {
    if (state.phase !== "vote" && state.phase !== "pk_vote") {
      throw err("WRONG_PHASE", "当前不是投票阶段");
    }
    if (!me.alive) throw err("DEAD_PLAYER", "出局玩家不能投票");
    const target = act.target;
    if (target !== null && typeof target !== "string") {
      throw err("ILLEGAL_TARGET", "target 必须是座位或 null");
    }
    if (target !== null) {
      const tp = findPlayer(state, target);
      if (!tp) throw err("ILLEGAL_TARGET", `未知目标: ${target}`);
      if (!tp.alive) throw err("ILLEGAL_TARGET", "不能投票给已出局玩家");
      if (state.phase === "pk_vote" && state.pkSeats.includes(seat)) {
        throw err("ILLEGAL_TARGET", "PK 台上的人不能投票");
      }
    }
    const next = cloneState(state);
    // 记录本日投票
    let record = next.votes.find((v) => v.day === next.day && v.records.length >= 0 && !v.exiled && v.records.every((r) => r.voter !== seat) && v.day === next.day);
    // 更稳的做法：找当前阶段对应的 vote 记录
    record = next.votes.find(
      (v) => v.day === next.day && !v.records.some((r) => r.voter === seat) && v.exiled === null,
    );
    if (!record) {
      record = { day: next.day, records: [], exiled: null };
      next.votes.push(record);
    }
    record.records.push({ voter: seat, target: target as string | null });

    // 检查是否所有该投票的人都投了
    const eligibleVoters =
      next.phase === "pk_vote"
        ? alivePlayers(next).filter((p) => !next.pkSeats.includes(p.seat))
        : alivePlayers(next);
    const votedSet = new Set(record.records.map((r) => r.voter));
    const allVoted = eligibleVoters.every((p) => votedSet.has(p.seat));
    if (allVoted) {
      // 计票
      const tally = new Map<string, number>();
      for (const r of record.records) {
        if (r.target === null) continue;
        const voter = findPlayer(next, r.voter);
        const weight = voter && voter.isSheriff ? 1.5 : 1;
        tally.set(r.target, (tally.get(r.target) ?? 0) + weight);
      }
      let maxVotes = 0;
      let winners: string[] = [];
      for (const [s, c] of tally) {
        if (c > maxVotes) {
          maxVotes = c;
          winners = [s];
        } else if (c === maxVotes) {
          winners.push(s);
        }
      }
      if (next.phase === "vote") {
        if (winners.length === 0 || maxVotes === 0) {
          // 全体弃票 -> 平安日
          record.exiled = null;
          startSpeakForNextDay(next);
        } else if (winners.length === 1) {
          // 出局
          const exiled = findPlayer(next, winners[0]);
          if (exiled) {
            exiled.alive = false;
            record.exiled = winners[0];
            next.deaths.push({ seat: winners[0], reason: "vote", day: next.day });
            next.lastwordsQueue.push(winners[0]);
            next.lastwordsToNight = true;
            // 猎人被投票出局 -> 可开枪
            if (exiled.role === "hunter") {
              next.hunterShootPending = winners[0];
            }
          }
          const w = checkWinner(next);
          if (w) {
            next.phase = "finished";
            next.winner = w;
            next.currentSeat = "";
            return next;
          }
          // 进入遗言
          if (next.lastwordsIdx < next.lastwordsQueue.length) {
            next.phase = "lastwords";
            next.currentSeat = next.lastwordsQueue[next.lastwordsIdx];
          } else {
            startSpeakForNextDay(next);
          }
        } else {
          // 平票进 PK
          startPkSpeak(next, winners);
        }
      } else {
        // pk_vote
        if (winners.length === 0 || maxVotes === 0) {
          // 平安日
          record.exiled = null;
          startSpeakForNextDay(next);
        } else if (winners.length === 1) {
          const exiled = findPlayer(next, winners[0]);
          if (exiled) {
            exiled.alive = false;
            record.exiled = winners[0];
            next.deaths.push({ seat: winners[0], reason: "vote", day: next.day });
            next.lastwordsQueue.push(winners[0]);
            next.lastwordsToNight = true;
            if (exiled.role === "hunter") {
              next.hunterShootPending = winners[0];
            }
          }
          const w = checkWinner(next);
          if (w) {
            next.phase = "finished";
            next.winner = w;
            next.currentSeat = "";
            return next;
          }
          if (next.lastwordsIdx < next.lastwordsQueue.length) {
            next.phase = "lastwords";
            next.currentSeat = next.lastwordsQueue[next.lastwordsIdx];
          } else {
            startSpeakForNextDay(next);
          }
        } else {
          // 再平：平安日
          record.exiled = null;
          startSpeakForNextDay(next);
        }
      }
    } else {
      // 找下一个未投票的合格投票人
      let ns: string | null = null;
      for (const p of eligibleVoters) {
        if (!votedSet.has(p.seat)) {
          ns = p.seat;
          break;
        }
      }
      next.currentSeat = ns ?? firstAliveSeat(next);
    }
    return next;
  }

  throw err("BAD_ACTION", `未知动作: ${String(kind)}`);
}

// 从白天结束进入下一夜或终局
function startSpeakForNextDay(state: GameState): void {
  const w = checkWinner(state);
  if (w) {
    state.phase = "finished";
    state.winner = w;
    state.currentSeat = "";
    return;
  }
  // 进入下一夜
  state.day += 1;
  state.phase = "night";
  state.nightStep = "guard";
  state.night.guardTarget = null;
  state.night.wolfTarget = null;
  state.night.seerTarget = null;
  state.night.seerResult = null;
  state.night.witchSaveTarget = null;
  state.night.witchPoisonTarget = null;
  state.night.witchActed = false;
  state.night.deathsTonight = [];
  state.spokenSeats = [];
  state.pkSeats = [];
  state.sheriffOrderStart = null;
  advanceNightStep(state);
}

// ---------------------------------------------------------------------------
// 序列化（按座位脱敏）
// ---------------------------------------------------------------------------

export function serializeForSeat(state: GameState, seat: string): unknown {
  const me = findPlayer(state, seat);
  const isWolfViewer = me !== undefined && isWolf(me.role);
  const showWolfInfo = isWolfViewer && state.phase === "night";

  const players = state.players.map((p) => {
    const view: { seat: string; alive: boolean; isSheriff: boolean; role?: Role } = {
      seat: p.seat,
      alive: p.alive,
      isSheriff: p.isSheriff,
    };
    // 狼人夜晚互见：仅当观察者是狼人且 phase=night，才能看到其他狼人的角色
    if (showWolfInfo && isWolf(p.role)) {
      view.role = p.role;
    }
    // 自己能看到自己的角色
    if (p.seat === seat) {
      view.role = p.role;
    }
    return view;
  });

  const out: {
    phase: Phase;
    day: number;
    currentSeat: string;
    nightStep?: NightStep;
    players: typeof players;
    deaths: DeathRecord[];
    lastwordsQueue: string[];
    lastwordsIdx: number;
    sheriffSeat?: string;
    votes: { day: number; records: VoteRecord[]; exiled: string | null }[];
    pkSeats: string[];
    sheriffVotes: SheriffVoteRecord[];
    hunterShootPending?: string;
    wolfSeats?: string[];
    seerHistory?: { seat: string; result: "wolf" | "good"; day: number }[];
    seerResult?: "wolf" | "good" | null;
    winner?: "wolves" | "good";
  } = {
    phase: state.phase,
    day: state.day,
    currentSeat: state.currentSeat,
    players,
    deaths: state.deaths.map((d) => ({ ...d })),
    lastwordsQueue: state.lastwordsQueue.slice(),
    lastwordsIdx: state.lastwordsIdx,
    votes: state.votes.map((v) => ({
      day: v.day,
      records: v.records.map((r) => ({ ...r })),
      exiled: v.exiled,
    })),
    pkSeats: state.pkSeats.slice(),
    sheriffVotes: state.sheriffVotes.map((r) => ({ ...r })),
  };

  if (state.phase === "night") {
    out.nightStep = state.nightStep;
  }
  if (state.sheriffSeat !== undefined) {
    out.sheriffSeat = state.sheriffSeat;
  }
  if (state.hunterShootPending !== null) {
    out.hunterShootPending = state.hunterShootPending;
  }
  if (state.winner !== undefined) {
    out.winner = state.winner;
  }

  // 狼人夜晚互见：仅当 seat 是狼人且 phase=night
  if (showWolfInfo) {
    out.wolfSeats = aliveWolves(state).map((p) => p.seat);
  }

  // 预言家查验历史只给本人
  if (me !== undefined && me.role === "seer") {
    out.seerHistory = state.night.seerHistory.map((h) => ({ ...h }));
    if (state.phase === "night" && state.nightStep === "witch") {
      // 已验完，可显示本晚结果
      out.seerResult = state.night.seerResult;
    }
  }

  return out;
}
