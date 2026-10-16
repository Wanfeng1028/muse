// seq 单元测试：SeqTracker 去重/乱序/缺口/隔离/窗口，及 nextSeq 单调递增。
import { describe, it, expect } from "vitest";
import { SeqTracker } from "../src/index.js";

describe("SeqTracker.seen", () => {
  it("单调递增返回 ok，重复返回 duplicate，超窗口返回 stale", () => {
    const t = new SeqTracker();
    expect(t.seen("alice", 1)).toBe("ok");
    expect(t.seen("alice", 2)).toBe("ok");
    expect(t.seen("alice", 3)).toBe("ok");
    expect(t.seen("alice", 3)).toBe("duplicate");
    expect(t.seen("alice", 4)).toBe("ok");
    // max=4, window=500 -> seq <= -496 为 stale；用 max-600
    expect(t.seen("alice", 4 - 600)).toBe("stale");
  });

  it("乱序后 hasGap 返回缺口，补齐后返回 null", () => {
    const t = new SeqTracker();
    t.seen("alice", 1);
    t.seen("alice", 3);
    const gap = t.hasGap("alice");
    expect(gap).not.toBeNull();
    expect(gap!.missing).toContainEqual([2, 2]);
    t.seen("alice", 2);
    expect(t.hasGap("alice")).toBeNull();
  });

  it("per-sender 隔离：A 的 seq=5 不影响 B 的 seq=1", () => {
    const t = new SeqTracker();
    expect(t.seen("A", 5)).toBe("ok");
    expect(t.seen("B", 1)).toBe("ok");
  });

  it("小窗口 new SeqTracker(3)：seen 1,2,3,4 后 seen 1 返回 stale", () => {
    const t = new SeqTracker(3);
    expect(t.seen("alice", 1)).toBe("ok");
    expect(t.seen("alice", 2)).toBe("ok");
    expect(t.seen("alice", 3)).toBe("ok");
    expect(t.seen("alice", 4)).toBe("ok");
    expect(t.seen("alice", 1)).toBe("stale");
  });
});

describe("SeqTracker.nextSeq", () => {
  it("连续调用返回 1,2,3", () => {
    const t = new SeqTracker();
    expect(t.nextSeq()).toBe(1);
    expect(t.nextSeq()).toBe(2);
    expect(t.nextSeq()).toBe(3);
  });
});
