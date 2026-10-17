/**
 * 斗地主网关适配层（B1 批次）
 *
 * 依赖（A 线，逐字）：
 *   gateway/src/doudizhu/game.js 的 4 个具名导出 + ai.js 的 1 个：
 *     createGame(seats:[string,string,string], rng?): GameState
 *     bid(state, seat, score:0|1|2|3): GameState
 *     play(state, seat, cards:number[]): GameState
 *     serializeForSeat(state, seat): unknown
 *     choosePlay(state, seat): number[]
 *
 * AI 座位约定：seat 以 "ai:" 开头（isAiSeat 判断）。
 *
 * applyAction 永不抛错的原因：hub.ts 的 handleGameAction 调用 applyAction
 * 时没有任何 try/catch，异常会沿 ws 回调上抛导致网关进程 crash。
 * 因此所有 GameError 必须在 applyAction 内部 catch，转成随状态返回的 error 对象。
 *
 * 牌数字：3=3 … 13=K, 14=A, 15=2, 16=小王, 17=大王。
 */

import { createHash } from "node:crypto";

import type { GameActionPayload, GameStatePayload } from "@botstalk/protocol";
import type { GameEngine } from "./hub.js";
import { createGame, bid, play, serializeForSeat } from "./doudizhu/game.js";
import { choosePlay } from "./doudizhu/ai.js";

export class GameError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "GameError";
  }
}

// ---------------------------------------------------------------------------
// 本地类型（按 GameState 形状逐字声明，不 import 引擎类型）
// ---------------------------------------------------------------------------

import type { GameState } from "./doudizhu/game.js";

// 网关侧直接复用引擎的 GameState（唯一事实来源），不再另定义一套简化接口——
// 之前的手写 DoudizhuGameState 漏了 bottomCards/bids/bidTurn/redeals 等内部字段，
// 还把 spring 的类型写错（boolean vs "landlord"|"farmers"），已被 tsc 抓现行。
export type DoudizhuGameState = GameState;

export type DoudizhuAction =
  | { kind: "bid"; score: 0 | 1 | 2 | 3 }
  | { kind: "play"; cards: number[] }
  | { kind: "start"; seats: [string, string, string] };

export interface DoudizhuSessionData {
  v: 1;
  state: DoudizhuGameState | null;
  error?: { code: string; message: string; seat?: string; at: number };
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

export function isAiSeat(seat: string): boolean {
  return seat.startsWith("ai:");
}

function isValidPhase(value: unknown): value is DoudizhuGameState["phase"] {
  return value === "bidding" || value === "playing" || value === "finished";
}

function isValidGameState(value: unknown): value is DoudizhuGameState {
  if (typeof value !== "object" || value === null) return false;
  const s = value as Record<string, unknown>;
  if (!isValidPhase(s["phase"])) return false;
  if (!Array.isArray(s["players"])) return false;
  if (typeof s["currentSeat"] !== "string") return false;
  return true;
}

function errMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return "未知错误";
}

// ---------------------------------------------------------------------------
// DoudizhuRoom
// ---------------------------------------------------------------------------

export class DoudizhuRoom {
  private constructor(
    readonly roomId: string,
    readonly sessionId: string,
    private gameState: DoudizhuGameState,
  ) {}

  static create(roomId: string, sessionId: string, seats: string[]): DoudizhuRoom {
    if (!Array.isArray(seats) || seats.length !== 3) {
      throw new GameError("BAD_SEATS", "斗地主需要恰好 3 个座位");
    }
    for (const s of seats) {
      if (typeof s !== "string" || s.length === 0) {
        throw new GameError("BAD_SEATS", "座位必须是非空字符串");
      }
    }
    const unique = new Set(seats);
    if (unique.size !== 3) {
      throw new GameError("BAD_SEATS", "座位必须互不相同");
    }
    let state: DoudizhuGameState;
    try {
      state = createGame(seats as [string, string, string]);
    } catch (e) {
      throw new GameError("ENGINE_ERROR", errMessage(e));
    }
    return new DoudizhuRoom(roomId, sessionId, state);
  }

  static fromJSON(roomId: string, sessionId: string, json: string): DoudizhuRoom {
    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch (e) {
      throw new GameError("BAD_STATE", `JSON 解析失败: ${errMessage(e)}`);
    }
    if (!isValidGameState(parsed)) {
      throw new GameError("BAD_STATE", "状态缺少合法 phase/players/currentSeat");
    }
    // JSON 落盘会丢掉 rng 函数（engine 的 bid 重发/随机定地主需要它），读回时补默认随机源
    if (typeof parsed.rng !== "function") {
      parsed.rng = Math.random;
    }
    return new DoudizhuRoom(roomId, sessionId, parsed);
  }

  static fromState(
    roomId: string,
    sessionId: string,
    state: DoudizhuGameState,
  ): DoudizhuRoom {
    // 同上：从 DB/网络读回的 state 可能丢了 rng，补上避免 bid 内重发时崩溃
    if (typeof state.rng !== "function") {
      state.rng = Math.random;
    }
    return new DoudizhuRoom(roomId, sessionId, state);
  }

  toJSON(): string {
    const data: DoudizhuSessionData = { v: 1, state: this.gameState };
    return JSON.stringify(data);
  }

  getState(): DoudizhuGameState {
    return this.gameState;
  }

  handleAction(seat: string, action: unknown): void {
    // a) seat 校验
    if (typeof seat !== "string" || seat.length === 0) {
      throw new GameError("UNKNOWN_SEAT", "座位标识非法");
    }
    if (!this.gameState.players.some((p) => p.seat === seat)) {
      throw new GameError("UNKNOWN_SEAT", `未知座位: ${seat}`);
    }

    // b) action 形状
    if (typeof action !== "object" || action === null) {
      throw new GameError("BAD_ACTION", "动作必须是对象");
    }
    const act = action as Record<string, unknown>;
    const kind = act["kind"];
    if (kind !== "bid" && kind !== "play") {
      throw new GameError("BAD_ACTION", `未知动作类型: ${String(kind)}`);
    }

    // c) 终局
    if (this.gameState.phase === "finished") {
      throw new GameError("GAME_FINISHED", "牌局已结束");
    }

    if (kind === "bid") {
      // d) 叫分
      if (this.gameState.phase !== "bidding") {
        throw new GameError("WRONG_PHASE", "当前不是叫分阶段");
      }
      const score = act["score"];
      if (
        typeof score !== "number" ||
        !Number.isInteger(score) ||
        (score !== 0 && score !== 1 && score !== 2 && score !== 3)
      ) {
        throw new GameError("BAD_SCORE", `非法叫分: ${String(score)}`);
      }
      if (this.gameState.currentSeat !== seat) {
        throw new GameError("NOT_YOUR_TURN", `当前轮到 ${this.gameState.currentSeat}`);
      }
      try {
        this.gameState = bid(
          this.gameState,
          seat,
          score as 0 | 1 | 2 | 3,
        );
      } catch (e) {
        throw new GameError("ILLEGAL_BID", errMessage(e));
      }
      return;
    }

    // e) 出牌
    if (this.gameState.phase !== "playing") {
      throw new GameError("WRONG_PHASE", "当前不是出牌阶段");
    }
    const cards = act["cards"];
    if (!Array.isArray(cards)) {
      throw new GameError("BAD_ACTION", "cards 必须是数组");
    }
    for (const c of cards) {
      if (typeof c !== "number") {
        throw new GameError("BAD_ACTION", "cards 每项必须是 number");
      }
    }
    if (this.gameState.currentSeat !== seat) {
      throw new GameError("NOT_YOUR_TURN", `当前轮到 ${this.gameState.currentSeat}`);
    }
    try {
      this.gameState = play(
        this.gameState,
        seat,
        cards as number[],
      );
    } catch (e) {
      throw new GameError("ILLEGAL_PLAY", errMessage(e));
    }
  }

  toStateFrame(seat?: string): GameStatePayload {
    let view: unknown;
    if (seat) {
      try {
        view = serializeForSeat(this.gameState, seat);
      } catch {
        view = this.gameState;
      }
    } else {
      view = this.gameState;
    }
    const payloadState = view ?? null;
    const stateStr = JSON.stringify(payloadState);
    const state_hash = createHash("sha256").update(stateStr).digest("hex");
    return {
      game: "doudizhu",
      seat,
      state: payloadState,
      state_hash,
    };
  }

  runAiTurns(maxSteps = 200): number {
    let steps = 0;
    while (steps < maxSteps) {
      if (this.gameState.phase !== "playing") break;
      const current = this.gameState.currentSeat;
      if (!isAiSeat(current)) break;
      let cards: number[];
      try {
        cards = choosePlay(this.gameState, current) as number[];
      } catch {
        break;
      }
      try {
        this.gameState = play(
          this.gameState,
          current,
          cards,
        );
      } catch {
        break;
      }
      steps += 1;
    }
    return steps;
  }
}

// ---------------------------------------------------------------------------
// DoudizhuGameEngine
// ---------------------------------------------------------------------------

export class DoudizhuGameEngine implements GameEngine {
  applyAction(prevState: unknown, action: GameActionPayload): unknown {
    // 开局分支：不依赖 prevState，空 session 也能把牌局开起来
    if (typeof action.action === "object" && action.action !== null) {
      const act = action.action as { kind?: unknown; seats?: unknown };
      if (act.kind === "start") {
        const seats = act.seats;
        const seatsOk =
          Array.isArray(seats) &&
          seats.length === 3 &&
          seats.every((s) => typeof s === "string" && s.length > 0) &&
          new Set(seats).size === 3;
        if (!seatsOk) {
          return {
            v: 1,
            state: null,
            error: {
              code: "BAD_SEATS",
              message: "开局需要 3 个互不相同的非空座位",
              at: Date.now(),
            },
          };
        }
        try {
          const room = DoudizhuRoom.create(
            "",
            "",
            seats as [string, string, string],
          );
          return { v: 1, state: room.getState() };
        } catch (e) {
          const err: {
            code: string;
            message: string;
            seat?: string;
            at: number;
          } = {
            code: e instanceof GameError ? e.code : "INTERNAL",
            message: e instanceof Error ? e.message : "未知错误",
            at: Date.now(),
          };
          if (typeof action.seat === "string") {
            err.seat = action.seat;
          }
          return { v: 1, state: null, error: err };
        }
      }
    }

    // 解析：优先 data.state，其次 prevState 本身
    let inner: DoudizhuGameState | null = null;
    if (typeof prevState === "object" && prevState !== null) {
      const data = prevState as Partial<DoudizhuSessionData>;
      if (isValidGameState(data.state)) {
        inner = data.state;
      } else if (isValidGameState(prevState)) {
        inner = prevState;
      }
    }

    if (inner === null) {
      const out: DoudizhuSessionData = {
        v: 1,
        state: null,
        error: {
          code: "BAD_STATE",
          message: "斗地主局面数据损坏或未初始化",
          at: Date.now(),
        },
      };
      return out;
    }

    const seat = typeof action.seat === "string" ? action.seat : "";

    try {
      const room = DoudizhuRoom.fromState("", "", inner);
      room.handleAction(seat, action.action);
      room.runAiTurns();
      const out: DoudizhuSessionData = { v: 1, state: room.getState() };
      return out;
    } catch (e) {
      const code = e instanceof GameError ? e.code : "INTERNAL";
      const message = e instanceof Error ? e.message : "未知错误";
      const out: DoudizhuSessionData = {
        v: 1,
        state: inner,
        error: { code, message, seat, at: Date.now() },
      };
      return out;
    }
  }
}