import { describe, expect, it, vi } from "vitest";

import { runWatchLoop, type WatchEvent } from "./watch-loop.js";

describe("bounded watch loop", () => {
  it("keeps the observed timestamp as ISO UTC when no clock is injected", async () => {
    const events: WatchEvent[] = [];
    const result = await runWatchLoop({
      kind: "progress",
      intervalMs: 1,
      maxEvents: 1,
      signal: new AbortController().signal,
      read: async () => ({ instanceId: "instance-1", value: {} }),
      emit: (event) => events.push(event),
      wait: async () => undefined,
    });
    expect(result).toEqual({ state: "complete", events: 1 });
    expect(events).toHaveLength(1);
    expect(() => new Date(events[0].observed_at)).not.toThrow();
    expect(events[0].observed_at).toMatch(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/,
    );
  });

  it("waits for each read before starting the next one", async () => {
    let active = 0;
    let maximum = 0;
    let reads = 0;
    const events: unknown[] = [];
    const result = await runWatchLoop({
      kind: "status",
      intervalMs: 1,
      maxEvents: 3,
      signal: new AbortController().signal,
      read: async () => {
        active += 1;
        maximum = Math.max(maximum, active);
        await Promise.resolve();
        reads += 1;
        active -= 1;
        return {
          instanceId: "instance-1",
          value: { state: "ok", read: reads },
        };
      },
      emit: (event) => events.push(event),
      wait: async () => undefined,
      now: () => "T",
    });
    expect(result).toEqual({ state: "complete", events: 3 });
    expect(maximum).toBe(1);
    expect(events).toEqual([
      expect.objectContaining({ sequence: 1, observed_at: "T" }),
      expect.objectContaining({ sequence: 2, observed_at: "T" }),
      expect.objectContaining({ sequence: 3, observed_at: "T" }),
    ]);
  });

  it("aborts an in-flight read and exits without another request", async () => {
    const controller = new AbortController();
    let reads = 0;
    const read = vi.fn(
      (signal: AbortSignal) =>
        new Promise<never>((_resolve, reject) => {
          reads += 1;
          signal.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true },
          );
          controller.abort();
        }),
    );
    const result = await runWatchLoop({
      kind: "progress",
      intervalMs: 1,
      signal: controller.signal,
      read,
      emit: () => {
        throw new Error("an aborted read must not emit");
      },
    });
    expect(result).toEqual({ state: "cancelled", events: 0 });
    expect(reads).toBe(1);
  });

  it("stops on data-instance identity change instead of mixing snapshots", async () => {
    const events: WatchEvent[] = [];
    let read = 0;
    const result = await runWatchLoop({
      kind: "status",
      intervalMs: 1,
      maxEvents: 3,
      signal: new AbortController().signal,
      read: async () => {
        read += 1;
        return {
          instanceId: read === 1 ? "instance-a" : "instance-b",
          value: { state: "ok", marker: `snapshot-${read}` },
        };
      },
      emit: (event) => events.push(event),
      wait: async () => undefined,
      now: () => "T",
    });
    expect(result).toEqual({
      state: "failed",
      code: "watch_instance_changed",
      events: 2,
    });
    expect(events[0].data).toMatchObject({ marker: "snapshot-1" });
    expect(events[1]).toMatchObject({
      state: "untrusted",
      code: "watch_instance_changed",
      expected_instance_id: "instance-a",
      actual_instance_id: "instance-b",
    });
    expect(events[1]).not.toHaveProperty("data");
  });

  it("emits a current failure rather than repeating the previous success", async () => {
    const events: WatchEvent[] = [];
    let read = 0;
    await runWatchLoop({
      kind: "progress",
      intervalMs: 1,
      maxEvents: 2,
      signal: new AbortController().signal,
      read: async () => {
        read += 1;
        if (read === 2) throw new Error("transport failed");
        return {
          instanceId: "instance-1",
          value: { state: "ok", marker: "only-current-once" },
        };
      },
      emit: (event) => events.push(event),
      wait: async () => undefined,
      now: () => "T",
    });
    expect(events[0].data).toMatchObject({ marker: "only-current-once" });
    expect(events[1]).toMatchObject({
      state: "unavailable",
      code: "watch_read_failed",
    });
    expect(events[1]).not.toHaveProperty("data");
  });

  it("refuses an event that exceeds the NDJSON byte budget", async () => {
    const events: WatchEvent[] = [];
    const result = await runWatchLoop({
      kind: "status",
      intervalMs: 1,
      maxEvents: 1,
      maxEventBytes: 128,
      signal: new AbortController().signal,
      read: async () => ({
        instanceId: "instance-1",
        value: { text: "x".repeat(1_000) },
      }),
      emit: (event) => events.push(event),
      now: () => "T",
    });
    expect(result).toMatchObject({
      state: "failed",
      code: "watch_event_too_large",
    });
    expect(events).toEqual([
      expect.objectContaining({
        state: "unavailable",
        code: "watch_event_too_large",
      }),
    ]);
  });
});
