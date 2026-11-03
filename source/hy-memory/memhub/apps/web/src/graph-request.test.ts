import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getMemoryGraphWith, resetMemoryGraphCoalescingForTest } from "./api";

describe("the memory map request", () => {
  beforeEach(() => {
    resetMemoryGraphCoalescingForTest();
  });

  afterEach(() => {
    resetMemoryGraphCoalescingForTest();
  });

  it("is issued once when several callers ask at once", async () => {
    let release: (() => void) | undefined;
    const pending = new Promise<{ data: unknown }>((resolve) => {
      release = () => resolve({ data: { nodes: [], edges: [] } });
    });
    const transport = { get: vi.fn(() => pending) };

    const first = getMemoryGraphWith(transport as never);
    const second = getMemoryGraphWith(transport as never);
    const third = getMemoryGraphWith(transport as never);
    release?.();

    const [one, two, three] = await Promise.all([first, second, third]);

    // D91: three overlapping map requests all timed out on Kristin's machine
    // and dragged the memory list from 0.4 s to 4.3 s. The map is the slowest
    // read in the app, so it never runs twice at once.
    expect(transport.get).toHaveBeenCalledTimes(1);
    // And every caller still gets the answer.
    expect(one).toBe(two);
    expect(two).toBe(three);
  });

  it("asks again after the previous one settled", async () => {
    const transport = {
      get: vi.fn(async () => ({ data: { nodes: [], edges: [] } })),
    };

    await getMemoryGraphWith(transport as never);
    await getMemoryGraphWith(transport as never);

    // Coalescing is not caching: a later caller gets its own read.
    expect(transport.get).toHaveBeenCalledTimes(2);
  });
});
