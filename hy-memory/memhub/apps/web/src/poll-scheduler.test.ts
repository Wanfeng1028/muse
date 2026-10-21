import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  pollNow,
  resetPollScheduler,
  scheduledPollCount,
  subscribePoll,
} from "./poll-scheduler";

describe("poll-scheduler", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // The scheduler is a browser module; give it both globals it touches.
    vi.stubGlobal("window", {});
    vi.stubGlobal("document", { hidden: false });
    resetPollScheduler();
  });
  afterEach(() => {
    resetPollScheduler();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("runs exactly one timer for two subscribers of the same surface", () => {
    subscribePoll({ key: "sources", intervalMs: 5_000, run: vi.fn() });
    subscribePoll({ key: "sources", intervalMs: 5_000, run: vi.fn() });
    expect(scheduledPollCount()).toBe(1);
  });

  it("runs one timer per distinct surface", () => {
    subscribePoll({ key: "sources", intervalMs: 1_000, run: vi.fn() });
    subscribePoll({ key: "processing", intervalMs: 3_000, run: vi.fn() });
    expect(scheduledPollCount()).toBe(2);
  });

  it("paces a shared surface at the fastest interval requested", async () => {
    const slow = vi.fn();
    const fast = vi.fn();
    subscribePoll({ key: "processing", intervalMs: 12_000, run: slow });
    subscribePoll({ key: "processing", intervalMs: 3_000, run: fast });
    await vi.advanceTimersByTimeAsync(3_000);
    expect(fast).toHaveBeenCalledTimes(1);
    expect(slow).toHaveBeenCalledTimes(1);
  });

  it("recomputes the interval when the fastest subscriber leaves", async () => {
    const slow = vi.fn();
    const fast = vi.fn();
    subscribePoll({ key: "processing", intervalMs: 12_000, run: slow });
    const off = subscribePoll({
      key: "processing",
      intervalMs: 3_000,
      run: fast,
    });
    off();
    await vi.advanceTimersByTimeAsync(3_000);
    // The 3s caller is gone, so the surface is back to 12s.
    expect(fast).not.toHaveBeenCalled();
    expect(slow).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(9_000);
    expect(slow).toHaveBeenCalledTimes(1);
  });

  it("stops the timer when the last subscriber leaves", () => {
    const off = subscribePoll({
      key: "health",
      intervalMs: 1_000,
      run: vi.fn(),
    });
    expect(scheduledPollCount()).toBe(1);
    off();
    expect(scheduledPollCount()).toBe(0);
  });

  it("pauses every subscriber while the document is hidden", async () => {
    const run = vi.fn();
    subscribePoll({ key: "sources", intervalMs: 1_000, run });
    vi.stubGlobal("document", { hidden: true });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(run).not.toHaveBeenCalled();
  });

  it("honours a subscriber that asked to keep running while hidden", async () => {
    const run = vi.fn();
    subscribePoll({
      key: "imports",
      intervalMs: 1_000,
      run,
      pauseWhenHidden: false,
    });
    vi.stubGlobal("document", { hidden: true });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("keeps other subscribers running when one throws", async () => {
    const good = vi.fn();
    subscribePoll({
      key: "sources",
      intervalMs: 1_000,
      run: () => {
        throw new Error("bad read");
      },
    });
    subscribePoll({ key: "sources", intervalMs: 1_000, run: good });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(good).toHaveBeenCalledTimes(1);
  });

  it("does not stack ticks on a subscriber that is still running", async () => {
    let resolve!: () => void;
    const run = vi.fn(
      () =>
        new Promise<void>((done) => {
          resolve = done;
        }),
    );
    subscribePoll({ key: "sources", intervalMs: 1_000, run });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(run).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(run).toHaveBeenCalledTimes(1);
    resolve();
  });

  it("pollNow runs every subscriber of one surface once", async () => {
    const a = vi.fn();
    const b = vi.fn();
    subscribePoll({ key: "sources", intervalMs: 9_000, run: a });
    subscribePoll({ key: "sources", intervalMs: 9_000, run: b });
    await pollNow("sources");
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });

  it("runs a shared fetch once per tick and feeds every subscriber", async () => {
    const fetchOnce = vi.fn(async () => 41);
    const a = vi.fn();
    const b = vi.fn();
    subscribePoll({
      key: "processing",
      intervalMs: 3_000,
      fetch: fetchOnce,
      onValue: a,
    });
    subscribePoll({
      key: "processing",
      intervalMs: 10_000,
      fetch: fetchOnce,
      onValue: b,
    });
    await vi.advanceTimersByTimeAsync(3_000);
    // Two pages read the same endpoint; one tick must produce one request.
    expect(fetchOnce).toHaveBeenCalledTimes(1);
    expect(a).toHaveBeenCalledWith(41);
    expect(b).toHaveBeenCalledWith(41);
  });

  it("does not start a second shared fetch while one is still in flight", async () => {
    let release!: (value: number) => void;
    const fetchOnce = vi.fn(
      () => new Promise<number>((done) => (release = done)),
    );
    subscribePoll({
      key: "processing",
      intervalMs: 1_000,
      fetch: fetchOnce,
      onValue: vi.fn(),
    });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(fetchOnce).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(4_000);
    expect(fetchOnce).toHaveBeenCalledTimes(1);
    release(1);
  });

  it("serves two same-surface subscribers at different intervals with one read per tick", async () => {
    // The real app does exactly this: MemorySpace subscribes `processing` at
    // 12s for the summary panel and again at 3s for the arrival prompt. Both
    // read `getMemoryProcessing`. The scheduler must fire one request per tick
    // at the fastest cadence and hand the same value to both — not one request
    // per subscriber, and not two timers.
    let calls = 0;
    const fetch = vi.fn(async () => {
      calls += 1;
      return { extraction_window_preset: "3m", counts: calls };
    });
    const slow = vi.fn();
    const fast = vi.fn();
    const stopSlow = subscribePoll({
      key: "processing",
      intervalMs: 12_000,
      fetch,
      onValue: slow,
    });
    const stopFast = subscribePoll({
      key: "processing",
      intervalMs: 3_000,
      fetch,
      onValue: fast,
    });
    expect(scheduledPollCount()).toBe(1);
    // The fastest subscriber (3s) sets the cadence, so one 3s tick is enough.
    await vi.advanceTimersByTimeAsync(3_000);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(slow).toHaveBeenCalledTimes(1);
    expect(fast).toHaveBeenCalledTimes(1);
    // One read, one value object shared by both subscribers.
    expect(slow.mock.calls[0][0]).toBe(fast.mock.calls[0][0]);
    stopSlow();
    stopFast();
    expect(scheduledPollCount()).toBe(0);
  });
});
