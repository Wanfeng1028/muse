import { describe, it, expect } from "vitest";
import { SeqTracker } from "../src/index.js";

describe("seq.r3 未覆盖分支", () => {
  it("未知 sender 没有状态时 hasGap 应返回 null", () => {
    const tracker = new SeqTracker();
    expect(tracker.hasGap("ghost")).toBeNull();
  });

  it("连续已见无缺口时 hasGap 应返回 null", () => {
    const tracker = new SeqTracker();
    tracker.seen("a", 1);
    tracker.seen("a", 2);
    tracker.seen("a", 3);
    expect(tracker.hasGap("a")).toBeNull();
  });

  it("存在多个不连续缺口时应返回多个缺口区间", () => {
    const tracker = new SeqTracker();
    tracker.seen("a", 1);
    tracker.seen("a", 2);
    tracker.seen("a", 5);
    tracker.seen("a", 8);
    expect(tracker.hasGap("a")).toEqual({ missing: [[3, 4], [6, 7]] });
  });

  it("缺口延伸到 max 之前的空档时区间不应包含已见的 max", () => {
    const tracker = new SeqTracker();
    tracker.seen("a", 1);
    tracker.seen("a", 2);
    tracker.seen("a", 5);
    expect(tracker.hasGap("a")).toEqual({ missing: [[3, 4]] });
  });

  it("首个 seq 缺失时 lowerBound 为 1 应报告缺失区间", () => {
    const tracker = new SeqTracker();
    tracker.seen("a", 2);
    tracker.seen("a", 3);
    expect(tracker.hasGap("a")).toEqual({ missing: [[1, 1]] });
  });

  it("窗口滑动后旧缺口落入窗口外时 hasGap 应返回 null", () => {
    const tracker = new SeqTracker(5);
    tracker.seen("a", 1);
    tracker.seen("a", 2);
    tracker.seen("a", 3);
    tracker.seen("a", 4);
    tracker.seen("a", 5);
    tracker.seen("a", 6);
    tracker.seen("a", 7);
    expect(tracker.hasGap("a")).toBeNull();
  });

  it("补齐缺口后 hasGap 应从报告缺口变为 null", () => {
    const tracker = new SeqTracker();
    tracker.seen("a", 1);
    tracker.seen("a", 3);
    expect(tracker.hasGap("a")).toEqual({ missing: [[2, 2]] });
    tracker.seen("a", 2);
    expect(tracker.hasGap("a")).toBeNull();
  });

  it("nextSeq 独立于 seen 计数不受影响", () => {
    const tracker = new SeqTracker();
    tracker.seen("a", 100);
    expect(tracker.nextSeq()).toBe(1);
  });
});