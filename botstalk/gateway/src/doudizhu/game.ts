import { parseCombo, canBeat, sortCards } from "./cards.js";
import type { Combo } from "./cards.js";

/**
 * 斗地主对局状态机。
 * 职责：发牌、叫分、出牌轮转、炸弹翻倍、春天判定、按座位脱敏。
 * 纯函数式：所有导出函数返回新的 GameState，不修改入参。
 */

export interface PlayerState {
  seat: string;
  hand: number[];
  isLandlord: boolean;
}

export interface GameState {
  phase: "bidding" | "playing" | "finished";
  players: PlayerState[]; // 固定顺序 [s0,s1,s2]
  landlordSeat?: string;
  currentSeat: string; // 当前该谁行动（叫分期=该谁叫分，出牌期=该谁出牌）
  lastPlay: { seat: string; combo: Combo } | null;
  baseScore: number;
  bombs: number; // 本局已出的炸弹+王炸总数（翻倍计数）
  spring?: "landlord" | "farmers";
  winner?: string; // 获胜者的 seat

  // —— 以下为内部字段（契约未列，加注释说明）——
  bottomCards: number[]; // 三张底牌，地主确定后并入其手牌
  bids: (0 | 1 | 2 | 3 | null)[]; // 各玩家叫分记录，null 表示尚未叫
  bidTurn: number; // 叫分轮转指针（0..3）
  redeals: number; // 全不叫导致的重发次数
  landlordPlays: number; // 地主非“不出”出牌次数
  farmerPlays: number; // 农民非“不出”出牌次数
  rng: () => number; // 随机数源（createGame 传入，用于重发/随机定地主，保证可测试）
}

// 构造 54 张牌：3..15 各 4 张，16、17 各 1 张
function buildDeck(): number[] {
  const deck: number[] = [];
  for (let rank = 3; rank <= 15; rank++) {
    for (let i = 0; i < 4; i++) deck.push(rank);
  }
  deck.push(16);
  deck.push(17);
  return deck;
}

// Fisher-Yates 洗牌（返回新数组，不修改入参）
function shuffle(cards: number[], rng: () => number): number[] {
  const arr = cards.slice();
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
  return arr;
}

// 深拷贝玩家数组
function clonePlayers(players: PlayerState[]): PlayerState[] {
  return players.map((p) => ({
    seat: p.seat,
    hand: p.hand.slice(),
    isLandlord: p.isLandlord,
  }));
}

// 整体深拷贝一份状态（用于不可变更新）
function cloneState(state: GameState): GameState {
  const next: GameState = {
    phase: state.phase,
    players: clonePlayers(state.players),
    currentSeat: state.currentSeat,
    lastPlay: state.lastPlay
      ? { seat: state.lastPlay.seat, combo: { ...state.lastPlay.combo, cards: state.lastPlay.combo.cards.slice() } }
      : null,
    baseScore: state.baseScore,
    bombs: state.bombs,
    bottomCards: state.bottomCards.slice(),
    bids: state.bids.slice(),
    bidTurn: state.bidTurn,
    redeals: state.redeals,
    landlordPlays: state.landlordPlays,
    farmerPlays: state.farmerPlays,
    rng: state.rng,
  };
  if (state.landlordSeat !== undefined) next.landlordSeat = state.landlordSeat;
  if (state.spring !== undefined) next.spring = state.spring;
  if (state.winner !== undefined) next.winner = state.winner;
  return next;
}

// 按 players 固定顺序找下一个手牌非空的座位索引（从 from+1 开始循环）
function nextNonEmptyIndex(players: PlayerState[], from: number): number {
  const n = players.length;
  for (let step = 1; step <= n; step++) {
    const idx = (from + step) % n;
    if (players[idx].hand.length > 0) return idx;
  }
  return -1; // 理论上不会发生
}

// 从手牌中按值移除指定牌（多重集）
function removeCards(hand: number[], cards: number[]): number[] {
  const rest = hand.slice();
  for (const c of cards) {
    const idx = rest.indexOf(c);
    if (idx >= 0) rest.splice(idx, 1);
  }
  return rest;
}

// 多重集包含检查
function handContains(hand: number[], cards: number[]): boolean {
  const pool = hand.slice();
  for (const c of cards) {
    const idx = pool.indexOf(c);
    if (idx < 0) return false;
    pool.splice(idx, 1);
  }
  return true;
}

// 一局全新发牌，返回 players / bottomCards
function dealFresh(
  seats: [string, string, string],
  rng: () => number
): { players: PlayerState[]; bottomCards: number[] } {
  const deck = shuffle(buildDeck(), rng);
  const hands: number[][] = [[], [], []];
  for (let i = 0; i < 51; i++) {
    hands[i % 3].push(deck[i]);
  }
  const bottomCards = deck.slice(51, 54);
  const players: PlayerState[] = seats.map((seat, i) => ({
    seat,
    hand: sortCards(hands[i]),
    isLandlord: false,
  }));
  return { players, bottomCards };
}

export function createGame(seats: [string, string, string], rng: () => number = Math.random): GameState {
  const { players, bottomCards } = dealFresh(seats, rng);
  return {
    phase: "bidding",
    players,
    currentSeat: seats[0],
    lastPlay: null,
    baseScore: 0,
    bombs: 0,
    bottomCards,
    bids: [null, null, null],
    bidTurn: 0,
    redeals: 0,
    landlordPlays: 0,
    farmerPlays: 0,
    rng,
  };
}

export function bid(state: GameState, seat: string, score: 0 | 1 | 2 | 3): GameState {
  if (state.phase !== "bidding") throw Error("当前不在叫分阶段");
  if (state.players[state.bidTurn].seat !== seat) throw Error("还没轮到你叫分");
  if (state.bids[state.bidTurn] !== null) throw Error("本轮已经叫过分了");
  if (score !== 0 && score !== 1 && score !== 2 && score !== 3) throw Error("叫分不合法");

  const next = cloneState(state);
  next.bids[next.bidTurn] = score;
  next.bidTurn++;

  if (next.bidTurn < 3) {
    next.currentSeat = next.players[next.bidTurn].seat;
    return next;
  }

  // 三人都已叫完
  let maxScore: 0 | 1 | 2 | 3 = 0;
  let maxIdx = -1;
  for (let i = 0; i < 3; i++) {
    const v = next.bids[i] as 0 | 1 | 2 | 3;
    if (v > maxScore) {
      maxScore = v;
      maxIdx = i;
    }
  }

  if (maxScore > 0) {
    // 最高分者当地主（并列时取顺序在前者，上面的循环已保证 > 才更新）
    const landlordIdx = maxIdx;
    const landlord = next.players[landlordIdx];
    landlord.isLandlord = true;
    landlord.hand = sortCards(landlord.hand.concat(next.bottomCards));
    next.landlordSeat = landlord.seat;
    next.baseScore = maxScore;
    next.phase = "playing";
    next.currentSeat = landlord.seat;
    next.lastPlay = null;
    return next;
  }

  // 全不叫
  next.redeals++;
  if (next.redeals > 3) {
    // 随机定地主（用状态自带的随机数源，保证可测试）
    const idx = Math.floor(next.rng() * 3);
    const landlord = next.players[idx];
    landlord.isLandlord = true;
    landlord.hand = sortCards(landlord.hand.concat(next.bottomCards));
    next.landlordSeat = landlord.seat;
    next.baseScore = 1;
    next.phase = "playing";
    next.currentSeat = landlord.seat;
    next.lastPlay = null;
    return next;
  }

  // 重新洗牌发牌，保留 redeals
  const seatsTuple: [string, string, string] = [
    next.players[0].seat,
    next.players[1].seat,
    next.players[2].seat,
  ];
  const { players, bottomCards } = dealFresh(seatsTuple, next.rng);
  next.players = players;
  next.bottomCards = bottomCards;
  next.bids = [null, null, null];
  next.bidTurn = 0;
  next.currentSeat = seatsTuple[0];
  next.phase = "bidding";
  next.lastPlay = null;
  next.landlordPlays = 0;
  next.farmerPlays = 0;
  return next;
}

export function play(state: GameState, seat: string, cards: number[]): GameState {
  if (state.phase !== "playing") throw Error("当前不在出牌阶段");
  if (state.currentSeat !== seat) throw Error("还没轮到你出牌");

  const curIdx = state.players.findIndex((p) => p.seat === seat);
  if (curIdx < 0) throw Error("座位不存在");
  if (state.players[curIdx].hand.length === 0) throw Error("该玩家已出完牌");

  const next = cloneState(state);
  const player = next.players[curIdx];

  if (cards.length === 0) {
    // 不出
    if (next.lastPlay === null || next.lastPlay.seat === seat) {
      throw Error("你必须出牌，不能不出");
    }
    const nIdx = nextNonEmptyIndex(next.players, curIdx);
    if (nIdx < 0) throw Error("内部错误：找不到下一个可出牌玩家");
    next.currentSeat = next.players[nIdx].seat;
    if (next.currentSeat === next.lastPlay.seat) {
      // 其余两家都不出，本轮结束，由 lastPlay.seat 自由领出
      next.lastPlay = null;
    }
    return next;
  }

  // 出牌
  const combo = parseCombo(cards);
  if (combo.type === "invalid") throw Error("牌型不合法");
  if (!handContains(player.hand, cards)) throw Error("手牌中没有这些牌");

  if (next.lastPlay !== null && next.lastPlay.seat !== seat) {
    if (!canBeat(combo, next.lastPlay.combo)) throw Error("压不住上家的牌");
  }

  player.hand = sortCards(removeCards(player.hand, cards));

  if (combo.type === "bomb" || combo.type === "rocket") {
    next.bombs++;
  }

  // 非“不出”出牌计数
  if (player.isLandlord) next.landlordPlays++;
  else next.farmerPlays++;

  next.lastPlay = { seat, combo };

  if (player.hand.length === 0) {
    // 对局结束
    next.phase = "finished";
    next.winner = seat;
    if (player.isLandlord) {
      if (next.farmerPlays === 0) next.spring = "landlord";
    } else {
      if (next.landlordPlays === 1) next.spring = "farmers";
    }
    return next;
  }

  const nIdx = nextNonEmptyIndex(next.players, curIdx);
  if (nIdx < 0) throw Error("内部错误：找不到下一个可出牌玩家");
  next.currentSeat = next.players[nIdx].seat;
  return next;
}

export function serializeForSeat(state: GameState, seat: string): unknown {
  const inBidding = state.phase === "bidding";

  const players = state.players.map((p) => {
    const view: { seat: string; handCount: number; isLandlord: boolean; hand?: number[] } = {
      seat: p.seat,
      handCount: p.hand.length,
      isLandlord: inBidding ? false : p.isLandlord,
    };
    if (p.seat === seat) {
      view.hand = sortCards(p.hand);
    }
    return view;
  });

  const bids = state.players.map((p, i) => ({
    seat: p.seat,
    score: state.bids[i],
  }));

  const out: {
    phase: GameState["phase"];
    currentSeat: string;
    lastPlay: { seat: string; combo: Combo } | null;
    baseScore: number;
    bombs: number;
    spring?: "landlord" | "farmers";
    winner?: string;
    landlordSeat?: string;
    players: typeof players;
    bids: typeof bids;
    bottomCards?: number[];
  } = {
    phase: state.phase,
    currentSeat: state.currentSeat,
    lastPlay: state.lastPlay
      ? { seat: state.lastPlay.seat, combo: { ...state.lastPlay.combo, cards: state.lastPlay.combo.cards.slice() } }
      : null,
    baseScore: state.baseScore,
    bombs: state.bombs,
    players,
    bids,
  };

  if (!inBidding) {
    if (state.landlordSeat !== undefined) out.landlordSeat = state.landlordSeat;
    out.bottomCards = state.bottomCards.slice();
  }
  if (state.spring !== undefined) out.spring = state.spring;
  if (state.winner !== undefined) out.winner = state.winner;

  return out;
}
