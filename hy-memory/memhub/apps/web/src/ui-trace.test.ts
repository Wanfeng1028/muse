import { afterEach, describe, expect, it, vi } from "vitest";
import { traceUiAction, traceUiOperation } from "./ui-trace";

type Emitted = {
  action: string;
  page: string;
  phase: "action" | "result";
  status?: string;
  reason?: string;
  count?: number;
  trace_id?: string;
};

function capture() {
  const events: Emitted[] = [];
  vi.stubGlobal("window", {
    oneMemory: {
      logUiTrace: (input: Emitted) => {
        events.push(input);
        return Promise.resolve({ state: "logged" });
      },
    },
  });
  return events;
}

afterEach(() => vi.unstubAllGlobals());

describe("traceUiAction", () => {
  it("emits ui-action then ui-result carrying the same trace id", () => {
    const events = capture();
    const trace = traceUiAction("sources", "toggle");
    trace.done("succeeded");
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({
      page: "sources",
      action: "toggle",
      phase: "action",
      trace_id: trace.traceId,
    });
    expect(events[1]).toMatchObject({
      page: "sources",
      action: "toggle",
      phase: "result",
      status: "succeeded",
      trace_id: trace.traceId,
    });
  });

  it("ignores a second close so one action yields exactly one result line", () => {
    const events = capture();
    const trace = traceUiAction("sources", "toggle");
    trace.done("succeeded");
    trace.done("failed", { reason: "late" });
    expect(events.filter((event) => event.phase === "result")).toHaveLength(1);
    expect(events.at(-1)?.status).toBe("succeeded");
  });

  it("records only the closed vocabularies and a code, never free text", () => {
    const events = capture();
    const trace = traceUiAction("memory", "submit");
    trace.done("failed", { reason: "model_content_conflict" });
    // The emitted event has no slot that could carry a user's words: every
    // field is an enum, an id-shaped code, or a count.
    const keys = new Set(events.flatMap((event) => Object.keys(event)));
    expect([...keys].sort()).toEqual([
      "action",
      "page",
      "phase",
      "reason",
      "status",
      "trace_id",
    ]);
  });

  it("does not fail the interaction when the bridge is absent", () => {
    vi.stubGlobal("window", {});
    expect(() =>
      traceUiAction("sources", "toggle").done("succeeded"),
    ).not.toThrow();
  });

  it("does not fail when the bridge throws", () => {
    vi.stubGlobal("window", {
      oneMemory: {
        logUiTrace: () => {
          throw new Error("bridge down");
        },
      },
    });
    expect(() => traceUiAction("sources", "toggle")).not.toThrow();
  });
});

describe("traceUiOperation", () => {
  it("passes the trace id into the operation and keeps the resolved value", async () => {
    const events = capture();
    const value = await traceUiOperation(
      "sources",
      "submit",
      async (traceId) => ({ traceId, count: 2 }),
      { countOf: (result) => result.count },
    );
    expect(value.traceId).toBe(events[0].trace_id);
    expect(events[1]).toMatchObject({ status: "succeeded", count: 2 });
  });

  it("rethrows the original error after recording a failed result", async () => {
    const events = capture();
    await expect(
      traceUiOperation(
        "sources",
        "submit",
        async () => {
          throw new Error("core down");
        },
        { reasonOf: () => "transport_result_unknown" },
      ),
    ).rejects.toThrow("core down");
    expect(events[1]).toMatchObject({
      status: "failed",
      reason: "transport_result_unknown",
    });
  });
});

describe("emit tolerates a rejecting async bridge", () => {
  // The desktop bridge is `ipcRenderer.invoke`, which returns a promise. A
  // rejection (window closed, validator refused the input) used to become an
  // unhandled rejection because `emit` only wrapped the *call* in try/catch.
  // Tracing must never become a new failure mode for the interaction it
  // observes, so the rejection is swallowed and the interaction is unaffected.
  it("does not surface an unhandled rejection when the bridge rejects", async () => {
    vi.stubGlobal("window", {
      oneMemory: {
        logUiTrace: () => Promise.reject(new Error("ui_trace_reason_rejected")),
      },
    });
    const rejections: unknown[] = [];
    const onRejection = (reason: unknown) => rejections.push(reason);
    process.on("unhandledRejection", onRejection);
    try {
      const trace = traceUiAction("memory", "submit");
      expect(() => trace.done("failed", { reason: "x" })).not.toThrow();
      // Give the microtask queue a chance to surface a stray rejection.
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(rejections).toEqual([]);
    } finally {
      process.off("unhandledRejection", onRejection);
    }
  });

  it("still emits the result line when the bridge rejects", async () => {
    const events: Emitted[] = [];
    vi.stubGlobal("window", {
      oneMemory: {
        logUiTrace: (input: Emitted) => {
          events.push(input);
          return input.phase === "result"
            ? Promise.reject(new Error("ui_trace_reason_rejected"))
            : Promise.resolve({ state: "logged" });
        },
      },
    });
    const trace = traceUiAction("memory", "submit");
    trace.done("failed", { reason: "x" });
    // The renderer still *attempted* the result line; the rejection belongs to
    // the validator, not to the interaction.
    expect(events.map((item) => item.phase)).toEqual(["action", "result"]);
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
});
