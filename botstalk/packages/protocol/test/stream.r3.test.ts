import { describe, it, expect } from "vitest";
import { StreamTracker } from "../src/index.js";
import type { Envelope, StreamPayload } from "../src/index.js";

const TS = 1700000000000;
function chunk(streamId: string, index: number, delta: string, final = false, ts = TS): Envelope<StreamPayload> {
  return { v: 1, type: "stream", seq: index + 1, ack: 0, sender: "a", room: "r", ts, payload: { stream_id: streamId, chunk_index: index, final, delta } };
}

describe("stream.r3 未覆盖分支", () => {
  it("已完成流继续 ingest 未见过的更大 chunk_index 时仍返回 completed", () => {
    const t = new StreamTracker();
    expect(t.ingest(chunk("s", 0, "a"))).toBe("accepted");
    expect(t.ingest(chunk("s", 1, "b", true))).toBe("completed");
    expect(t.ingest(chunk("s", 2, "c"))).toBe("completed");
  });

  it("已完成流重放已见过的旧 chunk_index 时 chunks.has 先命中返回 duplicate-chunk", () => {
    const t = new StreamTracker();
    t.ingest(chunk("s", 0, "a"));
    t.ingest(chunk("s", 1, "b", true));
    expect(t.ingest(chunk("s", 0, "a"))).toBe("duplicate-chunk");
  });

  it("isDangling 对未知 stream 即便 nowMs 远超阈值也返回 false", () => {
    const t = new StreamTracker();
    expect(t.isDangling("ghost", TS + 999999)).toBe(false);
  });

  it("getText 对未知 stream 返回空串", () => {
    const t = new StreamTracker();
    expect(t.getText("ghost")).toBe("");
  });

  it("乱序到达的 chunk 按到达顺序拼接而非按 chunk_index 排序", () => {
    const t = new StreamTracker();
    t.ingest(chunk("s", 1, "b"));
    t.ingest(chunk("s", 0, "a"));
    expect(t.getText("s")).toBe("ba");
  });

  it("final 为 true 的帧其 delta 不拼入文本", () => {
    const t = new StreamTracker();
    t.ingest(chunk("s", 0, "a"));
    t.ingest(chunk("s", 1, "B", true));
    expect(t.getText("s")).toBe("a");
  });

  it("不同 stream_id 的状态互相隔离且刚 ingest 的流不悬挂", () => {
    const t = new StreamTracker();
    t.ingest(chunk("s1", 0, "x"));
    t.ingest(chunk("s2", 0, "y"));
    expect(t.getText("s1")).toBe("x");
    expect(t.getText("s2")).toBe("y");
    expect(t.isDangling("s1", TS)).toBe(false);
  });
});
