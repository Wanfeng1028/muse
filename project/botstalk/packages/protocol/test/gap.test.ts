// gap 单元测试：GapRateLimiter 频率限制与 makeGap 构造字段。
import { describe, it, expect } from "vitest";
import { GapRateLimiter, makeGap } from "../src/index.js";

describe("GapRateLimiter.shouldSend", () => {
  it("同缺口 5s 内只 true 一次，超时后再 true，不同缺口独立", () => {
    const r = new GapRateLimiter();
    expect(r.shouldSend(2, 5, 1000)).toBe(true);
    expect(r.shouldSend(2, 5, 5999)).toBe(false);
    expect(r.shouldSend(2, 5, 6000)).toBe(true);
    expect(r.shouldSend(3, 5, 2000)).toBe(true);
  });
});

describe("makeGap", () => {
  it("构造的帧 type/payload 正确", () => {
    const env = makeGap("alice", "room1", 10, 3, 2, 5);
    expect(env.type).toBe("gap");
    expect(env.payload.from_seq).toBe(2);
    expect(env.payload.to_seq).toBe(5);
    expect(env.sender).toBe("alice");
    expect(env.room).toBe("room1");
    expect(env.seq).toBe(10);
    expect(env.ack).toBe(3);
  });
});
