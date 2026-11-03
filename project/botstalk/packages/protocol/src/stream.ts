// 职责：流式帧追踪（按 stream_id + chunk_index 防重放、拼接 delta、判定悬空流）。
// 提供 error 终帧构造。时间一律由参数传入，无副作用。

import type { Envelope, StreamPayload } from "./types.js";
import { STREAM_DANGLING_MS } from "./constants.js";

export type IngestResult = "accepted" | "duplicate-chunk" | "completed";

interface StreamState {
  /** 已见的 chunk_index 集合。 */
  chunks: Set<number>;
  /** 拼接的文本。 */
  text: string;
  /** 最近一次收到帧的时间戳（ms）。 */
  lastAtMs: number;
  /** 是否已收到 final 帧。 */
  finished: boolean;
}

export class StreamTracker {
  private readonly streams: Map<string, StreamState> = new Map();

  ingest(frame: Envelope<StreamPayload>): IngestResult {
    const payload = frame.payload;
    let state = this.streams.get(payload.stream_id);
    if (state === undefined) {
      state = { chunks: new Set<number>(), text: "", lastAtMs: frame.ts, finished: false };
      this.streams.set(payload.stream_id, state);
    }

    state.lastAtMs = frame.ts;

    if (state.chunks.has(payload.chunk_index)) {
      return "duplicate-chunk";
    }
    state.chunks.add(payload.chunk_index);

    if (payload.final !== true) {
      state.text += payload.delta;
    } else {
      state.finished = true;
    }

    if (state.finished) {
      return "completed";
    }
    return "accepted";
  }

  isDangling(streamId: string, nowMs: number): boolean {
    const state = this.streams.get(streamId);
    if (state === undefined) {
      return false;
    }
    if (state.finished) {
      return false;
    }
    return nowMs - state.lastAtMs >= STREAM_DANGLING_MS;
  }

  getText(streamId: string): string {
    const state = this.streams.get(streamId);
    if (state === undefined) {
      return "";
    }
    return state.text;
  }
}

/** 构造 error 终帧（final=true, delta="", error=true）。 */
export function makeErrorFinal(
  streamId: string,
  reason: string,
  sender: string,
  room: string,
  seq: number,
  chunkIndex: number,
  ts: number,
): Envelope<StreamPayload> {
  const payload: StreamPayload = {
    stream_id: streamId,
    chunk_index: chunkIndex,
    final: true,
    delta: "",
    error: true,
    reason,
  };
  return {
    v: 1,
    type: "stream",
    seq,
    ack: 0,
    sender,
    room,
    ts,
    payload,
  };
}
