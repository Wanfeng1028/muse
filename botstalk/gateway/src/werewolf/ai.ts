/**
 * 狼人杀 AI（纯函数）。
 *
 * 约定：
 *   - chooseNightAction(state, seat, rng) 在 phase==="night" 且 currentSeat===seat 时调用。
 *   - chooseDayAction(state, seat, rng) 在非夜晚阶段调用。
 *   - 返回的 action 必须能被 game.ts 的 nightAction/dayAction 接受。
 *   - 本模块与引擎同进程，可直接读取 state.night.* 内部字段。
 */

import type { GameState, PlayerState } from "./game.js";
import { ROLE_INFO } from "./roles.js";
import type { Role } from "./roles.js";

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

function isWolfRole(role: Role): boolean {
  return ROLE_INFO[role].faction === "wolves";
}

function isGodRole(role: Role): boolean {
  return role === "seer" || role === "witch" || role === "guard" || role === "hunter";
}

function alivePlayers(state: GameState): PlayerState[] {
  return state.players.filter((p) => p.alive);
}

function aliveGoodPlayers(state: GameState): PlayerState[] {
  return state.players.filter((p) => p.alive && !isWolfRole(p.role));
}

function aliveWolfPlayers(state: GameState): PlayerState[] {
  return state.players.filter((p) => p.alive && isWolfRole(p.role));
}

function findPlayer(state: GameState, seat: string): PlayerState | undefined {
  return state.players.find((p) => p.seat === seat);
}

// 按玩家在 state.players 中的顺序排序（视为"发言顺序"）
function sortBySeatOrder(state: GameState, list: PlayerState[]): PlayerState[] {
  const order = new Map<string, number>();
  state.players.forEach((p, i) => order.set(p.seat, i));
  return list.slice().sort((a, b) => (order.get(a.seat) ?? 0) - (order.get(b.seat) ?? 0));
}

function pickRandom<T>(list: T[], rng: () => number): T | null {
  if (list.length === 0) return null;
  const idx = Math.floor(rng() * list.length);
  const clamped = idx < 0 ? 0 : idx >= list.length ? list.length - 1 : idx;
  return list[clamped];
}

// ---------------------------------------------------------------------------
// 夜晚
// ---------------------------------------------------------------------------

export function chooseNightAction(
  state: GameState,
  seat: string,
  rng: () => number,
): unknown {
  const me = findPlayer(state, seat);
  if (!me) return { kind: "night", target: null };

  const step = state.nightStep;

  if (step === "guard" && me.role === "guard") {
    const prev = state.night.guardPrevTarget;
    const candidates = alivePlayers(state).filter((p) => p.seat !== prev);
    const target = pickRandom(sortBySeatOrder(state, candidates), rng);
    return { kind: "night", target: target ? target.seat : null };
  }

  if (step === "wolves" && isWolfRole(me.role)) {
    // 优先非神职好人里发言顺序靠前者
    const goodAlive = aliveGoodPlayers(state);
    const nonGod = sortBySeatOrder(
      state,
      goodAlive.filter((p) => !isGodRole(p.role)),
    );
    if (nonGod.length > 0) {
      // 靠前者中带一定随机：取前一半里随机
      const topN = Math.max(1, Math.ceil(nonGod.length / 2));
      const pool = nonGod.slice(0, topN);
      const target = pickRandom(pool, rng);
      if (target) return { kind: "night", target: target.seat };
    }
    const fallback = pickRandom(sortBySeatOrder(state, goodAlive), rng);
    return { kind: "night", target: fallback ? fallback.seat : null };
  }

  if (step === "seer" && me.role === "seer") {
    const checked = new Set(state.night.seerHistory.map((h) => h.seat));
    const candidates = sortBySeatOrder(
      state,
      alivePlayers(state).filter(
        (p) => p.seat !== seat && !checked.has(p.seat),
      ),
    );
    const target = candidates.length > 0 ? candidates[0] : pickRandom(alivePlayers(state), rng);
    return { kind: "night", target: target ? target.seat : null };
  }

  if (step === "witch" && me.role === "witch") {
    // 注意：deathsTonight 在女巫提交后才结算；女巫决策依据是狼人已提交的刀口 wolfTarget
    const wolfTarget = state.night.wolfTarget;
    const killed = typeof wolfTarget === "string" ? wolfTarget : null;
    if (
      killed &&
      !state.night.witchSaveUsed &&
      // 首夜不能自救
      !(state.day === 1 && killed === seat)
    ) {
      return { kind: "night", potion: "save", target: killed };
    }
    return { kind: "night", potion: null };
  }

  // 兜底：不行动（女巫不用药 / 非本人步骤）
  return { kind: "night", potion: null, target: null };
}

// ---------------------------------------------------------------------------
// 白天
// ---------------------------------------------------------------------------

function currentVoteTally(state: GameState): Map<string, number> {
  const tally = new Map<string, number>();
  const record = state.votes.find(
    (v) => v.day === state.day && v.exiled === null,
  );
  if (!record) return tally;
  for (const r of record.records) {
    if (r.target === null) continue;
    const voter = findPlayer(state, r.voter);
    const weight = voter && voter.isSheriff ? 1.5 : 1;
    tally.set(r.target, (tally.get(r.target) ?? 0) + weight);
  }
  return tally;
}

function highestVotedGood(state: GameState): string | null {
  const tally = currentVoteTally(state);
  let best: string | null = null;
  let bestCount = -1;
  for (const [target, count] of tally) {
    const p = findPlayer(state, target);
    if (!p || !p.alive) continue;
    if (isWolfRole(p.role)) continue;
    if (count > bestCount) {
      bestCount = count;
      best = target;
    }
  }
  return best;
}

export function chooseDayAction(
  state: GameState,
  seat: string,
  rng: () => number,
): unknown {
  const me = findPlayer(state, seat);
  if (!me) return { kind: "vote", target: null };

  const phase = state.phase;

  // 公布死讯确认
  if (phase === "announce") {
    return { kind: "announce_done" };
  }

  // 猎人开枪：必须在 lastwords 分支之前，否则猎人永远发 lastwords_done 导致引擎反复入队死循环
  if (state.hunterShootPending === seat) {
    const wolves = sortBySeatOrder(state, aliveWolfPlayers(state));
    const target = pickRandom(wolves, rng) ?? pickRandom(alivePlayers(state).filter((p) => p.seat !== seat), rng);
    return { kind: "hunter_shoot", target: target ? target.seat : null };
  }




  // 遗言
  if (phase === "lastwords") {
    return { kind: "lastwords_done" };
  }

  // 发言
  if (phase === "speak" || phase === "pk_speak") {
    return { kind: "speak_done" };
  }

  // 警长竞选
  if (phase === "sheriff") {
    return { kind: "sheriff", target: null };
  }

  // 投票
  if (phase === "vote" || phase === "pk_vote") {
    // PK 台上的人不能投票，只能弃票（game.ts 会校验）
    if (phase === "pk_vote" && state.pkSeats.includes(seat)) {
      return { kind: "vote", target: null };
    }
    if (isWolfRole(me.role)) {
      const target = highestVotedGood(state);
      if (target) return { kind: "vote", target };
      // 无跟票对象：投第一个非自己好人
      const goodAlive = sortBySeatOrder(
        state,
        aliveGoodPlayers(state).filter((p) => p.seat !== seat),
      );
      const fallback = goodAlive.length > 0 ? goodAlive[0] : pickRandom(alivePlayers(state).filter((p) => p.seat !== seat), rng);
      return { kind: "vote", target: fallback ? fallback.seat : null };
    }
    if (me.role === "seer") {
      const wolfChecked = state.night.seerHistory.find(
        (h) => h.result === "wolf" && findPlayer(state, h.seat)?.alive,
      );
      if (wolfChecked) {
        return { kind: "vote", target: wolfChecked.seat };
      }
    }
    // 其他好人：投第一个非自己的存活者
    const candidates = sortBySeatOrder(
      state,
      alivePlayers(state).filter((p) => p.seat !== seat),
    );
    const target = candidates.length > 0 ? candidates[0] : null;
    return { kind: "vote", target: target ? target.seat : null };
  }

  // 警长移交警徽（若本座位是警长且需要）
  if (state.sheriffSeat === seat) {
    return { kind: "sheriff_pass", target: null };
  }

  // 兜底
  return { kind: "vote", target: null };
}
