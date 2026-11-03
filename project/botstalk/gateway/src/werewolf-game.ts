/**
 * 狼人杀网关适配层。
 *
 * 依赖（唯一事实来源）：
 *   gateway/src/werewolf/game.js:
 *     createGame(seats, config?, rng?): GameState
 *     nightAction(state, seat, action): GameState
 *     dayAction(state, seat, action): GameState
 *     serializeForSeat(state, seat): unknown
 *     WerewolfError
 *   gateway/src/werewolf/ai.js:
 *     chooseNightAction(state, seat, rng): unknown
 *     chooseDayAction(state, seat, rng): unknown
 *
 * AI 座位约定：seat 以 "ai:" 开头。
 * applyAction 永不抛错：所有异常在内部 catch，转成 {code,message,seat,at} 的 error 对象。
 */

import { createHash } from "node:crypto";

import type { GameActionPayload, GameStatePayload } from "@botstalk/protocol";
import type { GameEngine } from "./hub.js";
import {
  createGame,
  nightAction,
  dayAction,
  serializeForSeat,
  WerewolfError,
} from "./werewolf/game.js";
import type { GameState, WerewolfConfig } from "./werewolf/game.js";
import { chooseNightAction, chooseDayAction } from "./werewolf/ai.js";

export class WerewolfGameError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "WerewolfGameError";
  }
}

// 直接复用引擎类型（唯一事实来源）
export type WerewolfGameState = GameState;

export type WerewolfAction =
  | { kind: "start"; seats: string[]; config?: WerewolfConfig }
  | Record<string, unknown> & { kind: string };

export interface WerewolfSessionData {
  v: 1;
  state: WerewolfGameState | null;
  error?: { code: string; message: string; seat?: string; at: number };
}

export const SUPPORTED_COUNTS: readonly number[] = [6, 7, 8, 9, 10, 11, 12];

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

export function isAiSeat(seat: string): boolean {
  return seat.startsWith("ai:");
}

function isValidPhase(value: unknown): value is WerewolfGameState["phase"] {
  return (
    value === "night" ||
    value === "announce" ||
    value === "lastwords" ||
    value === "sheriff" ||
    value === "speak" ||
    value === "vote" ||
    value === "pk_speak" ||
    value === "pk_vote" ||
    value === "finished"
  );
}

function isValidGameState(value: unknown): value is WerewolfGameState {
  if (typeof value !== "object" || value === null) return false;
  const s = value as Record<string, unknown>;
  if (!isValidPhase(s["phase"])) return false;
  if (!Array.isArray(s["players"])) return false;
  if (typeof s["currentSeat"] !== "string") return false;
  if (typeof s["day"] !== "number") return false;
  if (typeof s["night"] !== "object" || s["night"] === null) return false;
  return true;
}

function errMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return "未知错误";
}

function isSeatsValid(seats: unknown): seats is string[] {
  if (!Array.isArray(seats)) return false;
  if (!SUPPORTED_COUNTS.includes(seats.length)) return false;
  for (const s of seats) {
    if (typeof s !== "string" || s.length === 0) return false;
  }
  return new Set(seats).size === seats.length;
}

// ---------------------------------------------------------------------------
// WerewolfRoom
// ---------------------------------------------------------------------------

export class WerewolfRoom {
  private constructor(
    readonly roomId: string,
    readonly sessionId: string,
    private gameState: WerewolfGameState,
  ) {}

  static create(
    roomId: string,
    sessionId: string,
    seats: string[],
    config?: WerewolfConfig,
  ): WerewolfRoom {
    if (!isSeatsValid(seats)) {
      throw new WerewolfGameError(
        "BAD_SEATS",
        `狼人杀需要 ${SUPPORTED_COUNTS.join("/")} 个互不相同的非空座位`,
      );
    }
    let state: WerewolfGameState;
    try {
      state = createGame(seats, config ?? {});
    } catch (e) {
      throw new WerewolfGameError("ENGINE_ERROR", errMessage(e));
    }
    return new WerewolfRoom(roomId, sessionId, state);
  }

  static fromJSON(roomId: string, sessionId: string, json: string): WerewolfRoom {
    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch (e) {
      throw new WerewolfGameError("BAD_STATE", `JSON 解析失败: ${errMessage(e)}`);
    }
    // toJSON 落盘的是 {v:1, state} 包裹；同时兼容裸 GameState
    const inner =
      typeof parsed === "object" &&
      parsed !== null &&
      "state" in parsed &&
      isValidGameState((parsed as { state: unknown }).state)
        ? (parsed as { state: WerewolfGameState }).state
        : parsed;
    if (!isValidGameState(inner)) {
      throw new WerewolfGameError("BAD_STATE", "状态缺少合法 phase/players/currentSeat");
    }
    if (typeof inner.rng !== "function") {
      inner.rng = Math.random;
    }
    return new WerewolfRoom(roomId, sessionId, inner);
  }

  static fromState(
    roomId: string,
    sessionId: string,
    state: WerewolfGameState,
  ): WerewolfRoom {
    if (typeof state.rng !== "function") {
      state.rng = Math.random;
    }
    return new WerewolfRoom(roomId, sessionId, state);
  }

  toJSON(): string {
    const data: WerewolfSessionData = { v: 1, state: this.gameState };
    return JSON.stringify(data);
  }

  getState(): WerewolfGameState {
    return this.gameState;
  }

  handleAction(seat: string, action: unknown): void {
    if (typeof seat !== "string" || seat.length === 0) {
      throw new WerewolfGameError("UNKNOWN_SEAT", "座位标识非法");
    }
    if (!this.gameState.players.some((p) => p.seat === seat)) {
      throw new WerewolfGameError("UNKNOWN_SEAT", `未知座位: ${seat}`);
    }
    if (typeof action !== "object" || action === null) {
      throw new WerewolfGameError("BAD_ACTION", "动作必须是对象");
    }
    const act = action as Record<string, unknown>;
    const kind = act["kind"];
    if (typeof kind !== "string") {
      throw new WerewolfGameError("BAD_ACTION", "动作缺少 kind");
    }

    if (this.gameState.phase === "finished") {
      throw new WerewolfGameError("GAME_FINISHED", "对局已结束");
    }

    if (this.gameState.phase === "night") {
      try {
        this.gameState = nightAction(this.gameState, seat, action);
      } catch (e) {
        if (e instanceof WerewolfError) {
          throw new WerewolfGameError(e.code, e.message);
        }
        throw new WerewolfGameError("ENGINE_ERROR", errMessage(e));
      }
      return;
    }

    try {
      this.gameState = dayAction(this.gameState, seat, action);
    } catch (e) {
      if (e instanceof WerewolfError) {
        throw new WerewolfGameError(e.code, e.message);
      }
      throw new WerewolfGameError("ENGINE_ERROR", errMessage(e));
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
      game: "werewolf",
      seat,
      state: payloadState,
      state_hash,
    };
  }

  runAiTurns(maxSteps = 200): number {
    let steps = 0;
    while (steps < maxSteps) {
      const s = this.gameState;
      if (s.phase === "finished") break;
      let current = s.currentSeat;
      // announce 阶段 currentSeat 为空：任选一个存活 AI 座位代为确认进入白天
      if (s.phase === "announce" && !isAiSeat(current)) {
        const driver = s.players.find((pl) => pl.alive && isAiSeat(pl.seat))?.seat;
        if (!driver) break;
        current = driver;
      }
      if (!isAiSeat(current)) break;
      let action: unknown;
      try {
        if (s.phase === "night") {
          action = chooseNightAction(s, current, s.rng);
        } else {
          action = chooseDayAction(s, current, s.rng);
        }
      } catch {
        break;
      }
      try {
        if (s.phase === "night") {
          this.gameState = nightAction(this.gameState, current, action);
        } else {
          this.gameState = dayAction(this.gameState, current, action);
        }
      } catch {
        break;
      }
      steps += 1;
    }
    return steps;
  }
}

// ---------------------------------------------------------------------------
// WerewolfGameEngine
// ---------------------------------------------------------------------------

export class WerewolfGameEngine implements GameEngine {
  applyAction(prevState: unknown, action: GameActionPayload): unknown {
    // 开局分支
    if (typeof action.action === "object" && action.action !== null) {
      const act = action.action as {
        kind?: unknown;
        seats?: unknown;
        config?: unknown;
      };
      if (act.kind === "start") {
        if (!isSeatsValid(act.seats)) {
          return {
            v: 1,
            state: null,
            error: {
              code: "BAD_SEATS",
              message: `开局需要 ${SUPPORTED_COUNTS.join("/")} 个互不相同的非空座位`,
              at: Date.now(),
            },
          };
        }
        try {
          const room = WerewolfRoom.create(
            "",
            "",
            act.seats,
            (act.config ?? undefined) as WerewolfConfig | undefined,
          );
          room.runAiTurns();
          return { v: 1, state: room.getState() };
        } catch (e) {
          const err: {
            code: string;
            message: string;
            seat?: string;
            at: number;
          } = {
            code: e instanceof WerewolfGameError ? e.code : "INTERNAL",
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
    let inner: WerewolfGameState | null = null;
    if (typeof prevState === "object" && prevState !== null) {
      const data = prevState as Partial<WerewolfSessionData>;
      if (isValidGameState(data.state)) {
        inner = data.state;
      } else if (isValidGameState(prevState)) {
        inner = prevState;
      }
    }

    if (inner === null) {
      const out: WerewolfSessionData = {
        v: 1,
        state: null,
        error: {
          code: "BAD_STATE",
          message: "狼人杀局面数据损坏或未初始化",
          at: Date.now(),
        },
      };
      return out;
    }

    const seat = typeof action.seat === "string" ? action.seat : "";

    try {
      const room = WerewolfRoom.fromState("", "", inner);
      room.handleAction(seat, action.action);
      room.runAiTurns();
      const out: WerewolfSessionData = { v: 1, state: room.getState() };
      return out;
    } catch (e) {
      const code = e instanceof WerewolfGameError ? e.code : "INTERNAL";
      const message = e instanceof Error ? e.message : "未知错误";
      const out: WerewolfSessionData = {
        v: 1,
        state: inner,
        error: { code, message, seat, at: Date.now() },
      };
      return out;
    }
  }
}
