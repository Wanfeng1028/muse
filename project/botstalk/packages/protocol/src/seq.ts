// 职责：per-sender 的 seq 去重与缺口检测（滑动窗口 500）。
// seen 判定 ok / duplicate / stale；nextSeq 提供本地发送序列号。
// hasGap 报告窗口内的缺失区间。纯状态类，无时钟依赖。

import { DEDUP_WINDOW } from "./constants.js";

export type SeenResult = "ok" | "duplicate" | "stale";

export interface GapRange {
  missing: [number, number][];
}

interface SenderState {
  /** 已见最大 seq。 */
  max: number;
  /** 窗口内的已见 seq 集合。 */
  seen: Set<number>;
}

export class SeqTracker {
  private readonly windowSize: number;
  private readonly states: Map<string, SenderState> = new Map();
  private localSeq = 0;

  constructor(windowSize: number = DEDUP_WINDOW) {
    this.windowSize = windowSize;
  }

  seen(sender: string, seq: number): SeenResult {
    let state = this.states.get(sender);
    if (state === undefined) {
      state = { max: 0, seen: new Set<number>() };
      this.states.set(sender, state);
    }

    if (seq <= state.max - this.windowSize) {
      return "stale";
    }

    if (state.seen.has(seq)) {
      return "duplicate";
    }

    state.seen.add(seq);
    if (seq > state.max) {
      state.max = seq;
    }

    // 清理窗口外的 seq，保持集合有界。
    const lowerBound = state.max - this.windowSize;
    for (const s of state.seen) {
      if (s <= lowerBound) {
        state.seen.delete(s);
      }
    }

    return "ok";
  }

  nextSeq(): number {
    this.localSeq += 1;
    return this.localSeq;
  }

  hasGap(sender: string): GapRange | null {
    const state = this.states.get(sender);
    if (state === undefined) {
      return null;
    }

    const lowerBound = Math.max(1, state.max - this.windowSize + 1);
    const missing: [number, number][] = [];
    let runStart: number | null = null;

    for (let s = lowerBound; s <= state.max; s += 1) {
      if (!state.seen.has(s)) {
        if (runStart === null) {
          runStart = s;
        }
      } else if (runStart !== null) {
        missing.push([runStart, s - 1]);
        runStart = null;
      }
    }
    if (runStart !== null) {
      missing.push([runStart, state.max]);
    }

    if (missing.length === 0) {
      return null;
    }
    return { missing };
  }
}
