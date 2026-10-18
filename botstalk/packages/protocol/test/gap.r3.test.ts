import { describe, it, expect } from "vitest";
import { GapRateLimiter, makeGap } from "../src/index.js";

describe("gap.r3 未覆盖分支", () => {
  it("恰好间隔 5000ms 时严格小于不成立，应放行再次发送", () => {
    const l = new GapRateLimiter();
    expect(l.shouldSend(1, 5, 0)).toBe(true);
    expect(l.shouldSend(1, 5, 4999)).toBe(false);
    expect(l.shouldSend(1, 5, 5000)).toBe(true);
  });

  it("不同 from:to 区间各自独立计时互不影响", () => {
    const l = new GapRateLimiter();
    expect(l.shouldSend(1, 5, 0)).toBe(true);
    expect(l.shouldSend(6, 10, 0)).toBe(true);
    expect(l.shouldSend(1, 5, 1000)).toBe(false);
    expect(l.shouldSend(6, 10, 1000)).toBe(false);
  });

  it("时钟倒流时差为负仍小于阈值，应返回 false 锁定现有行为", () => {
    const l = new GapRateLimiter();
    expect(l.shouldSend(1, 5, 10000)).toBe(true);
    expect(l.shouldSend(1, 5, 5000)).toBe(false);
  });

  it("发送成功后水位更新为最新时间，后续按新水位判定", () => {
    const l = new GapRateLimiter();
    expect(l.shouldSend(1, 5, 0)).toBe(true);
    expect(l.shouldSend(1, 5, 6000)).toBe(true);
    expect(l.shouldSend(1, 5, 9000)).toBe(false);
  });

  it("makeGap 返回字段完整且类型正确", () => {
    const g = makeGap("alice", "room1", 7, 3, 10, 20);
    expect(g.v).toBe(1);
    expect(g.type).toBe("gap");
    expect(g.seq).toBe(7);
    expect(g.ack).toBe(3);
    expect(g.sender).toBe("alice");
    expect(g.room).toBe("room1");
    expect(g.payload).toEqual({ from_seq: 10, to_seq: 20 });
    expect(typeof g.ts).toBe("number");
  });

  it("key 由 from:to 顺序构成，反向区间视为不同 key 独立放行", () => {
    const l = new GapRateLimiter();
    expect(l.shouldSend(1, 5, 0)).toBe(true);
    expect(l.shouldSend(5, 1, 0)).toBe(true);
  });
});