import type { GameState, Phase } from "./game.js";

/**
 * 狼人杀 AI。
 * 只读 state 的公开信息做决策（phase / day / players 的 seat 与 alive / currentSeat /
 * deaths / lastwordsQueue / votes / pkSeats / pkVotes / sheriffSeat）。
 * 不读 role / night 内部字段（AI 不作弊）。
 * 永不抛错：内部 try/catch，兜底返回合法动作。
 */

function pick<T>(arr: T[], rng: () => number): T | null {
  if (arr.length === 0) return null;
  const i = Math.floor(rng() * arr.length);
  if (i < 0 || i >= arr.length) return arr[0];
  return arr[i];
}

function aliveSeats(state: GameState): string[] {
  return state.players.filter((p) => p.alive).map((p) => p.seat);
}

function otherAliveSeats(state: GameState, self: string): string[] {
  return aliveSeats(state).filter((s) => s !== self);
}

// AI 只知道自己的 seat，但不知道自己是好人还是狼人（不作弊）。
// 用已知的公开信息（例如 night.wolfTarget 不可读）来决定策略。
// 为了让 AI 策略“合理”，我们在外部传入 seat 时约定：
//   seat 以 "ai:" 开头，具体身份信息不由 AI 读取。
// 这里采取：狼人会用 AI 自己的 seat 在 wolfSeats 里（不可读），
// 因此 AI 不区分身份，用通用策略。

function nightSkip(): unknown {
  return { kind: "night", target: null, potion: null };
}

function daySkip(phase: Phase): unknown {
  if (phase === "announce") return { kind: "announce_done" };
  if (phase === "lastwords") return { kind: "lastwords_done" };
  if (phase === "speak") return { kind: "speak_done" };
  if (phase === "pk_speak") return { kind: "speak_done" };
  return { kind: "announce_done" };
}

export function chooseNightAction(
  state: GameState,
  seat: string,
  rng: () => number,
): unknown {
  try {
    if (state.phase !== "night") return nightSkip();
    const step = state.night.step;
    const others = otherAliveSeats(state, seat);

    if (step === "guard") {
      // 守卫守随机存活非自己；尽量不连守（AI 读不到 lastGuardTarget，因此只能靠随机）
      const target = pick(others, rng);
      if (target === null) return nightSkip();
      return { kind: "night", target };
    }

    if (step === "wolves") {
      // 狼人刀随机存活玩家（AI 不读 role，无法判断谁是狼）
      // 为了不刀到自己，排除 self
      const target = pick(others, rng);
      if (target === null) return { kind: "night", target: null };
      return { kind: "night", target };
    }

    if (step === "seer") {
      // 预言家验随机存活其他人
      const target = pick(others, rng);
      if (target === null) return nightSkip();
      return { kind: "night", target };
    }

    if (step === "witch") {
      // 女巫：不知道谁被刀，保守不用药
      return { kind: "night", potion: null };
    }

    return nightSkip();
  } catch {
    return nightSkip();
  }
}

export function chooseDayAction(
  state: GameState,
  seat: string,
  rng: () => number,
): unknown {
  try {
    const phase = state.phase;

    if (phase === "announce") {
      // 如果是猎人需要开枪
      if (state.hunterShootPending === seat) {
        const others = otherAliveSeats(state, seat);
        const target = pick(others, rng);
        if (target === null) {
          // 没有目标可打，返回一个合法的空动作会被拒；这里只能打自己？不允许。
          // 兜底返回 target 为自己（会被拒），但流程里如果只剩自己，游戏应已结束。
          return { kind: "hunter_shoot", target: seat };
        }
        return { kind: "hunter_shoot", target };
      }
      return { kind: "announce_done" };
    }

    if (phase === "lastwords") {
      return { kind: "lastwords_done" };
    }

    if (phase === "sheriff") {
      // 50% 上警
      if (rng() < 0.5) {
        return { kind: "sheriff" };
      }
      return { kind: "sheriff_pass" };
    }

    if (phase === "speak" || phase === "pk_speak") {
      return { kind: "speak_done" };
    }

    if (phase === "vote" || phase === "pk_vote") {
      const pool =
        phase === "pk_vote"
          ? state.pkSeats.filter((s) => s !== seat)
          : otherAliveSeats(state, seat);
      if (pool.length === 0) {
        return { kind: "vote", target: null };
      }
      const target = pick(pool, rng);
      return { kind: "vote", target };
    }

    return daySkip(phase);
  } catch {
    return daySkip(state.phase);
  }
}
