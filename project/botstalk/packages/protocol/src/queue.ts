// 职责：服务端 per-adapter 补发队列（FIFO，双上限 200 条 / 64KB）。
// 逐出最旧帧并记录 firstEvictedSeq；按 seq 区间取帧用于 gap 重发。

import type { Envelope } from "./types.js";
import { RESEND_MAX_BYTES, RESEND_MAX_MSGS } from "./constants.js";

export interface PushResult {
  evicted: Envelope[];
}

export class ResendQueue {
  private readonly maxMsgs: number;
  private readonly maxBytes: number;
  private readonly frames: Envelope[] = [];
  private bytes = 0;
  private firstEvictedSeq: number | null = null;

  constructor(maxMsgs: number = RESEND_MAX_MSGS, maxBytes: number = RESEND_MAX_BYTES) {
    this.maxMsgs = maxMsgs;
    this.maxBytes = maxBytes;
  }

  push(env: Envelope): PushResult {
    const frameBytes = byteLengthOf(env);
    this.frames.push(env);
    this.bytes += frameBytes;

    const evicted: Envelope[] = [];

    while (this.frames.length > this.maxMsgs || this.bytes > this.maxBytes) {
      const dropped = this.frames.shift();
      if (dropped === undefined) {
        break;
      }
      this.bytes -= byteLengthOf(dropped);
      if (this.firstEvictedSeq === null) {
        this.firstEvictedSeq = dropped.seq;
      }
      evicted.push(dropped);
    }

    return { evicted };
  }

  getMissing(fromSeq: number, toSeq: number): Envelope[] {
    const result: Envelope[] = [];
    for (const frame of this.frames) {
      const g = frame.gseq ?? 0;
      if (g >= fromSeq && g <= toSeq) {
        result.push(frame);
      }
    }
    return result;
  }

  /**
   * 按 per-sender seq 区间取帧。供客户端响应网关 gap 请求时使用：
   * 客户端重发队列里是自己发出的帧（无 gseq），gap 的 from_seq/to_seq
   * 是客户端 per-sender seq 空间，不能用按 gseq 查的 getMissing。
   */
  getMissingBySeq(fromSeq: number, toSeq: number): Envelope[] {
    const result: Envelope[] = [];
    for (const frame of this.frames) {
      if (frame.seq >= fromSeq && frame.seq <= toSeq) {
        result.push(frame);
      }
    }
    return result;
  }

  sizeBytes(): number {
    return this.bytes;
  }

  getFirstEvictedSeq(): number | null {
    return this.firstEvictedSeq;
  }

  size(): number {
    return this.frames.length;
  }
}

function byteLengthOf(env: Envelope): number {
  return utf8ByteLength(JSON.stringify(env));
}

function utf8ByteLength(input: string): number {
  let bytes = 0;
  for (let i = 0; i < input.length; i += 1) {
    const code = input.charCodeAt(i);
    if (code < 0x80) {
      bytes += 1;
    } else if (code < 0x800) {
      bytes += 2;
    } else if (code >= 0xd800 && code <= 0xdbff) {
      // 高代理项，与低位组成 4 字节码点。
      const next = input.charCodeAt(i + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        bytes += 4;
        i += 1;
      } else {
        bytes += 3;
      }
    } else {
      bytes += 3;
    }
  }
  return bytes;
}
