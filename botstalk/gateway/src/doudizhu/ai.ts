import { parseCombo, canBeat, sortCards } from "./cards.js";
import type { Combo } from "./cards.js";
import type { GameState } from "./game.js";

/**
 * 斗地主简单 AI。
 * 纯函数，无副作用。返回要出的牌数组（升序），[] 表示不出。
 */

/** 找出与 target 同 type 同 length 的候选组合。暴力枚举子集并剪枝。 */
function findSameTypeCandidates(
  hand: number[],
  target: Combo
): number[] | null {
  // 优先用结构化搜索（对小 length 高效），否则暴力枚举
  const n = hand.length;
  const k = target.length;
  if (k <= 0 || k > n) return null;

  // 当手牌较多且目标较长时，退化为只找简单牌型
  if (n > 12 && k > 5) {
    return null;
  }

  // 暴力枚举所有长度为 k 的子集，剪枝：必须含至少一张点数 > target.mainRank 的牌
  // 为控制规模，先按牌点数分组，从候选位置组合枚举
  const indices = hand.map((_, i) => i);
  const chosen: number[] = [];
  const visited = new Set<string>();
  let best: number[] | null = null;
  let bestCombo: Combo | null = null;

  // 为限制规模，按点数从小到大枚举
  // 将手牌索引按牌面值排序，优先选小牌
  const order = indices.slice().sort((a, b) => hand[a] - hand[b]);
  const orderedRecurse = (pos: number): void => {
    if (chosen.length === k) {
      const cards = chosen.map((i) => hand[i]);
      let hasGreater = false;
      for (const c of cards) {
        if (c > target.mainRank) {
          hasGreater = true;
          break;
        }
      }
      if (!hasGreater) return;
      const key = cards.slice().sort((a, b) => a - b).join(",");
      if (visited.has(key)) return;
      visited.add(key);
      const combo = parseCombo(cards);
      if (combo.type === "invalid") return;
      if (combo.type === "bomb" || combo.type === "rocket") return;
      if (!canBeat(combo, target)) return;
      if (
        bestCombo === null ||
        combo.mainRank < bestCombo.mainRank ||
        (combo.mainRank === bestCombo.mainRank && combo.length < bestCombo.length)
      ) {
        bestCombo = combo;
        best = cards.slice();
      }
      return;
    }
    if (pos >= order.length) return;
    // 剩余数量不足则剪枝
    if (order.length - pos < k - chosen.length) return;
    // 选
    chosen.push(order[pos]);
    orderedRecurse(pos + 1);
    chosen.pop();
    // 不选
    orderedRecurse(pos + 1);
  };

  orderedRecurse(0);

  return best;
}

/** 找最小炸弹（含王炸） */
function findBomb(hand: number[]): number[] | null {
  // 王炸优先？这里返回最小炸弹（点数最小），王炸单独处理
  const counts = new Map<number, number>();
  for (const c of hand) {
    counts.set(c, (counts.get(c) ?? 0) + 1);
  }
  let bestRank = Infinity;
  let best: number[] | null = null;
  for (const [r, c] of counts) {
    if (c >= 4 && r < bestRank) {
      bestRank = r;
      best = [r, r, r, r];
    }
  }
  return best;
}

/** 找王炸 */
function findRocket(hand: number[]): number[] | null {
  if (hand.includes(16) && hand.includes(17)) {
    return [16, 17];
  }
  return null;
}

/** 手牌中最小的单张 */
function smallestSingle(hand: number[]): number[] {
  if (hand.length === 0) return [];
  const sorted = sortCards(hand);
  return [sorted[0]];
}

/** 判断出这些牌后手牌是否为空 */
function emptiesHand(hand: number[], cards: number[]): boolean {
  if (cards.length !== hand.length) return false;
  const pool = hand.slice();
  for (const c of cards) {
    const idx = pool.indexOf(c);
    if (idx < 0) return false;
    pool.splice(idx, 1);
  }
  return pool.length === 0;
}

/** 判断是否是队友 */
function isTeammate(state: GameState, seat: string, otherSeat: string): boolean {
  const me = state.players.find((p) => p.seat === seat);
  const other = state.players.find((p) => p.seat === otherSeat);
  if (!me || !other) return false;
  // 都是农民则为队友
  return !me.isLandlord && !other.isLandlord;
}

/** 获取手牌数最少的对手的手牌数（非队友） */
function minOpponentHandCount(state: GameState, seat: string): number {
  let min = Infinity;
  for (const p of state.players) {
    if (p.seat === seat) continue;
    if (isTeammate(state, seat, p.seat)) continue;
    if (p.hand.length < min) min = p.hand.length;
  }
  return min === Infinity ? 0 : min;
}

/** 获取队友（另一农民） */
function getTeammate(state: GameState, seat: string): { seat: string; hand: number[] } | null {
  const me = state.players.find((p) => p.seat === seat);
  if (!me || me.isLandlord) return null;
  for (const p of state.players) {
    if (p.seat === seat) continue;
    if (!p.isLandlord) {
      return { seat: p.seat, hand: p.hand };
    }
  }
  return null;
}

export function choosePlay(state: GameState, seat: string): number[] {
  // 前置校验
  if (state.phase !== "playing") {
    throw Error("AI 只能在轮到自己出牌时决策");
  }
  if (state.currentSeat !== seat) {
    throw Error("AI 只能在轮到自己出牌时决策");
  }

  const me = state.players.find((p) => p.seat === seat);
  if (!me) {
    throw Error("AI 只能在轮到自己出牌时决策");
  }
  const hand = me.hand;

  // 空手牌：理论上不会走到这里
  if (hand.length === 0) return [];

  const lastPlay = state.lastPlay;

  // 规则 1：自由领出
  if (lastPlay === null || lastPlay.seat === seat) {
    // 特殊情况：只剩一手牌，直接出
    if (hand.length === 1) return sortCards(hand);
    // 王炸
    const rocket = findRocket(hand);
    if (rocket && hand.length === 2) return rocket;
    // 只剩炸弹
    if (hand.length === 4) {
      const combo = parseCombo(hand);
      if (combo.type === "bomb") return sortCards(hand);
    }
    // 否则出最小单张
    return smallestSingle(hand);
  }

  const target = lastPlay.combo;

  // 规则 4：我是农民且上家是队友出的牌 → 直接不出
  // 但特殊情况：队友出的牌我不管，让队友跑
  if (isTeammate(state, seat, lastPlay.seat)) {
    // 队友出的牌一律不出
    return [];
  }

  // 特殊情况：手牌只剩一手牌且需要压牌
  if (hand.length >= 1) {
    // 手牌能一次出完且能压过 target
    if (hand.length <= 2) {
      const combo = parseCombo(hand);
      if (combo.type !== "invalid" && canBeat(combo, target)) {
        return sortCards(hand);
      }
      // 王炸
      const rocket = findRocket(hand);
      if (rocket && canBeat(parseCombo(rocket), target)) {
        return rocket;
      }
    }
    // 只剩炸弹
    if (hand.length === 4) {
      const combo = parseCombo(hand);
      if (combo.type === "bomb" && canBeat(combo, target)) {
        return sortCards(hand);
      }
    }
    // 只剩王炸
    if (hand.length === 2 && hand.includes(16) && hand.includes(17)) {
      const rocket = parseCombo([16, 17]);
      if (canBeat(rocket, target)) {
        return [16, 17];
      }
    }
  }

  // 规则 3：队友剩 1 张保护
  const teammate = getTeammate(state, seat);
  const teammateOneLeft = teammate !== null && teammate.hand.length === 1;

  // 规则 2a：找非炸弹解
  const nonBomb = findSameTypeCandidates(hand, target);
  if (nonBomb !== null && nonBomb.length > 0) {
    // 如果能出完直接出
    if (emptiesHand(hand, nonBomb)) {
      return sortCards(nonBomb);
    }
    // 队友剩 1 张且能压 → 优先压
    if (teammateOneLeft) {
      return sortCards(nonBomb);
    }
    // 地主身份：我是地主有牌就压
    if (me.isLandlord) {
      return sortCards(nonBomb);
    }
    // 我是农民，上家是地主
    // 检查对手中是否有人剩 1 张
    const oppMin = minOpponentHandCount(state, seat);
    if (oppMin <= 1) {
      // 对手快跑完，必须压
      return sortCards(nonBomb);
    }
    // 一般情况下农民也压（简单 AI 不放水）
    return sortCards(nonBomb);
  }

  // 规则 2c：炸弹
  const bomb = findBomb(hand);
  const rocket = findRocket(hand);

  // 出炸弹后能出完
  if (bomb !== null && emptiesHand(hand, bomb)) {
    return sortCards(bomb);
  }
  if (rocket !== null && emptiesHand(hand, rocket)) {
    return rocket;
  }

  // 对手有人剩 1 张且我无非炸弹可压 → 出最小炸弹拦截
  const oppMin = minOpponentHandCount(state, seat);
  if (oppMin <= 1) {
    if (bomb !== null) {
      return sortCards(bomb);
    }
    if (rocket !== null) {
      return rocket;
    }
  }

  // 队友剩 1 张且我有炸弹能压 → 不出，保留炸弹（因为队友要跑）
  // 但如果对手也快跑完则已在上一步处理

  // 否则不出
  return [];
}
