// stream 单元测试：StreamTracker 顺序/去重/终帧/错误终帧/isDangling/getText。
import { describe, it, expect } from "vitest";
import { StreamTracker, makeErrorFinal } from "../src/index.js";
import type { Envelope, StreamPayload } from "../src/index.js";

const TS = 1700000000000;

function frame(
  streamId: string,
  chunkIndex: number,
  final: boolean,
  delta: string,
  seq: number,
): Envelope<StreamPayload> {
  return {
    v: 1,
    type: "stream",
    seq,
    ack: 0,
    sender: "alice",
    room: "room1",
    ts: TS,
    payload: {
      stream_id: streamId,
      chunk_index: chunkIndex,
      final,
      delta,
    },
  };
}

describe("StreamTracker.ingest/getText", () => {
  it("按序 ingest 返回 accepted，getText 拼接正确", () => {
    const t = new StreamTracker();
    expect(t.ingest(frame("s1", 0, false, "a", 1))).toBe("accepted");
    expect(t.ingest(frame("s1", 1, false, "b", 2))).toBe("accepted");
    expect(t.ingest(frame("s1", 2, false, "c", 3))).toBe("accepted");
    expect(t.getText("s1")).toBe("abc");
  });

  it("重放 chunk 1 返回 duplicate-chunk", () => {
    const t = new StreamTracker();
    t.ingest(frame("s1", 0, false, "a", 1));
    t.ingest(frame("s1", 1, false, "b", 2));
    expect(t.ingest(frame("s1", 1, false, "b", 2))).toBe("duplicate-chunk");
  });

  it("final=true 的 chunk 返回 completed", () => {
    const t = new StreamTracker();
    t.ingest(frame("s1", 0, false, "a", 1));
    t.ingest(frame("s1", 1, false, "b", 2));
    t.ingest(frame("s1", 2, false, "c", 3));
    expect(t.ingest(frame("s1", 3, true, "d", 4))).toBe("completed");
  });

  it("中断后 makeErrorFinal 帧 ingest 返回 completed 且字段正确", () => {
    const t = new StreamTracker();
    t.ingest(frame("s1", 0, false, "a", 1));
    t.ingest(frame("s1", 1, false, "b", 2));
    const errFrame = makeErrorFinal("s1", "timeout", "alice", "room1", 3, 2, TS);
    expect(t.ingest(errFrame)).toBe("completed");
    expect(errFrame.payload.final).toBe(true);
    expect(errFrame.payload.delta).toBe("");
    expect(errFrame.payload.error).toBe(true);
    expect(errFrame.payload.reason).toBe("timeout");
  });
});

describe("StreamTracker.isDangling", () => {
  it("59999ms 未悬挂，60000ms 悬挂，completed 不悬挂", () => {
    const t = new StreamTracker();
    t.ingest(frame("s1", 0, false, "a", 1));
    expect(t.isDangling("s1", TS + 59999)).toBe(false);
    expect(t.isDangling("s1", TS + 60000)).toBe(true);

    const t2 = new StreamTracker();
    t2.ingest(frame("s2", 0, false, "a", 1));
    t2.ingest(frame("s2", 1, true, "b", 2));
    expect(t2.isDangling("s2", TS + 60000)).toBe(false);
  });
});
