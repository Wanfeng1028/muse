import { describe, it, expect } from "vitest";
import { ResendQueue } from "../src/index.js";
import type { Envelope, MessagePayload } from "../src/index.js";

const TS = 1700000000000;
function msgFrame(seq: number, text: string, gseq?: number): Envelope<MessagePayload> {
  const e: Envelope<MessagePayload> = {
    v: 1, type: "message", seq, ack: 0, sender: "alice", room: "room1", ts: TS,
    payload: { msg_id: "m" + seq, text, mentions: [], intent: "chat" },
  };
  if (gseq !== undefined) (e as unknown as { gseq: number }).gseq = gseq;
  return e;
}

// 语义说明：getMissing 按网关 gseq 查（服务端补发用）；
// getMissingBySeq 按 per-sender seq 查（客户端重发队列里是自发帧、无 gseq，响应网关 gap 请求用）。

describe("queue.r3 getMissingBySeq", () => {
  it("基本区间：入队 seq 1..5，查 [2,4] 返回 seq 为 [2,3,4] 的三帧且保持入队顺序", () => {
    const q = new ResendQueue();
    for (let i = 1; i <= 5; i++) q.push(msgFrame(i, "t" + i));
    const got = q.getMissingBySeq(2, 4);
    expect(got.length).toBe(3);
    expect(got.map((f) => f.seq)).toEqual([2, 3, 4]);
  });

  it("与 getMissing 语义不同：帧 seq 1..3 且 gseq 10..12，getMissing(10,12) 命中三帧而 getMissingBySeq(10,12) 为空", () => {
    const q = new ResendQueue();
    for (let i = 1; i <= 3; i++) q.push(msgFrame(i, "t" + i, 9 + i));
    expect(q.getMissing(10, 12).length).toBe(3);
    expect(q.getMissingBySeq(10, 12)).toEqual([]);
  });

  it("空区间 fromSeq 大于 toSeq：getMissingBySeq(5,3) 返回空数组", () => {
    const q = new ResendQueue();
    for (let i = 1; i <= 5; i++) q.push(msgFrame(i, "t" + i));
    expect(q.getMissingBySeq(5, 3)).toEqual([]);
  });

  it("区间与已有 seq 无交集：getMissingBySeq(100,200) 返回空数组", () => {
    const q = new ResendQueue();
    for (let i = 1; i <= 5; i++) q.push(msgFrame(i, "t" + i));
    expect(q.getMissingBySeq(100, 200)).toEqual([]);
  });

  it("区间含端点：getMissingBySeq(3,3) 返回一帧且 seq 为 3", () => {
    const q = new ResendQueue();
    for (let i = 1; i <= 5; i++) q.push(msgFrame(i, "t" + i));
    const got = q.getMissingBySeq(3, 3);
    expect(got.length).toBe(1);
    expect(got[0].seq).toBe(3);
  });

  it("push 返回的 evicted 是被逐出的帧本身：maxMsgs=2 时第三次 push 逐出 seq 1 且 size 为 2", () => {
    const q = new ResendQueue(2, 1_000_000);
    expect(q.push(msgFrame(1, "a")).evicted).toEqual([]);
    expect(q.push(msgFrame(2, "b")).evicted).toEqual([]);
    const third = q.push(msgFrame(3, "c"));
    expect(third.evicted.length).toBe(1);
    expect(third.evicted[0].seq).toBe(1);
    expect(q.size()).toBe(2);
  });

  it("多次逐出后 firstEvictedSeq 保持首次值：maxMsgs=2 连续 push 1..4 后仍为 1", () => {
    const q = new ResendQueue(2, 1_000_000);
    for (let i = 1; i <= 4; i++) q.push(msgFrame(i, "t" + i));
    expect(q.getFirstEvictedSeq()).toBe(1);
  });

  it("未发生逐出时 getFirstEvictedSeq 为 null：容量充足下 push 一帧后返回 null", () => {
    const q = new ResendQueue(10, 1_000_000);
    q.push(msgFrame(1, "a"));
    expect(q.getFirstEvictedSeq()).toBeNull();
  });
});
