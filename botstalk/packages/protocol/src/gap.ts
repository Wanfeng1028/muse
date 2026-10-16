// 职责：缺口信号限速（同一 [from,to] 5000ms 内只发一次）与 gap 帧构造。
// 纯状态类，时间由参数传入。

import type { Envelope, GapPayload } from "./types.js";
import { GAP_RESEND_MS, PROTOCOL_VERSION } from "./constants.js";

export class GapRateLimiter {
  private readonly lastSent: Map<string, number> = new Map();

  shouldSend(fromSeq: number, toSeq: number, nowMs: number): boolean {
    const key = `${fromSeq}:${toSeq}`;
    const last = this.lastSent.get(key);
    if (last !== undefined && nowMs - last < GAP_RESEND_MS) {
      return false;
    }
    this.lastSent.set(key, nowMs);
    return true;
  }
}

/** 构造 gap 帧。 */
export function makeGap(
  sender: string,
  room: string,
  seq: number,
  ack: number,
  fromSeq: number,
  toSeq: number,
): Envelope<GapPayload> {
  return {
    v: PROTOCOL_VERSION,
    type: "gap",
    seq,
    ack,
    sender,
    room,
    ts: Date.now(),
    payload: { from_seq: fromSeq, to_seq: toSeq },
  };
}
