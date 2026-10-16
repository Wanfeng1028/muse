// queue 单元测试：ResendQueue 条数/字节逐出、getMissing 排序、先到上限者先逐出。
import { describe, it, expect } from "vitest";
import { ResendQueue } from "../src/index.js";
import type { Envelope, MessagePayload } from "../src/index.js";

const TS = 1700000000000;

function msgFrame(seq: number, text: string): Envelope<MessagePayload> {
  return {
    v: 1,
    type: "message",
    seq,
    ack: 0,
    sender: "alice",
    room: "room1",
    ts: TS,
    payload: {
      msg_id: "m" + seq,
      text,
      mentions: [],
      intent: "chat",
    },
  };
}

describe("ResendQueue 条数上限", () => {
  it("超出 maxMsgs 逐出最旧帧并记录 firstEvictedSeq", () => {
    const q = new ResendQueue(3, 1_000_000);
    expect(q.push(msgFrame(1, "a")).evicted).toEqual([]);
    expect(q.push(msgFrame(2, "b")).evicted).toEqual([]);
    expect(q.push(msgFrame(3, "c")).evicted).toEqual([]);
    const r = q.push(msgFrame(4, "d"));
    expect(r.evicted.length).toBe(1);
    expect(r.evicted[0].seq).toBe(1);
    expect(q.getFirstEvictedSeq()).toBe(1);
  });
});

describe("ResendQueue 字节上限", () => {
  it("超字节上限发生逐出且 sizeBytes<=上限", () => {
    const q = new ResendQueue(1000, 300);
    const text = "x".repeat(200);
    q.push(msgFrame(1, text));
    q.push(msgFrame(2, text));
    q.push(msgFrame(3, text));
    expect(q.getFirstEvictedSeq()).not.toBeNull();
    expect(q.sizeBytes()).toBeLessThanOrEqual(300);
  });
});

describe("ResendQueue.getMissing", () => {
  it("v1.1: 按 gseq 区间返回且保持入队顺序", () => {
    const q = new ResendQueue();
    const f1 = msgFrame(1, "a"); f1.gseq = 10;
    const f2 = msgFrame(2, "b"); f2.gseq = 11;
    const f3 = msgFrame(3, "c"); f3.gseq = 12;
    const f4 = msgFrame(4, "d"); // 无 gseq，视为 gseq=0
    q.push(f1);
    q.push(f2);
    q.push(f3);
    q.push(f4);
    const got = q.getMissing(11, 12);
    expect(got.length).toBe(2);
    expect(got.map((e) => e.gseq)).toEqual([11, 12]);
  });

  it("v1.1: 无 gseq 的帧不命中正区间", () => {
    const q = new ResendQueue();
    q.push(msgFrame(1, "a"));
    expect(q.getMissing(1, 100)).toEqual([]);
  });
});

describe("ResendQueue 先到上限者先逐出", () => {
  it("只超条数不超字节时按条数逐出", () => {
    const q = new ResendQueue(2, 1_000_000);
    q.push(msgFrame(1, "a"));
    q.push(msgFrame(2, "b"));
    const r = q.push(msgFrame(3, "c"));
    expect(r.evicted.length).toBe(1);
    expect(r.evicted[0].seq).toBe(1);
    expect(q.size()).toBe(2);
    expect(q.getFirstEvictedSeq()).toBe(1);
  });
});
