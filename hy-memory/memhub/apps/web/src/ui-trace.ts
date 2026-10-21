/** Four-step trace for one user interaction.
 *
 * The chain is:
 *   `[ui-action]`  what the user did          (page + control, never content)
 *   `[kernel-call]` which Core call it made   (already logged by Core)
 *   `[kernel-return]` what Core answered      (already logged by Core)
 *   `[ui-result]`  what the UI rendered       (page + outcome + optional code)
 *
 * Core already writes the middle two for every request and stamps them with
 * `X-One-Memory-Trace-Id`. The renderer therefore only has to emit the two ends
 * **carrying the same trace id**, and the four lines fall in order in the same
 * log file. That is what makes "open one log and see whether the bug is UI or
 * kernel" true rather than aspirational.
 *
 * Everything goes through one helper on purpose: scattering calls across 400+
 * interaction points is how a trace becomes partial without anyone noticing.
 */

/** One page identifier, matching the navigation view names. */
export type UiTracePage =
  | "sources"
  | "memory"
  | "applications"
  | "calls"
  | "settings"
  | "health"
  | "matters"
  | "onboarding";

/** What the user did. A closed set keeps the log queryable. */
export type UiTraceAction =
  | "click"
  | "toggle"
  | "submit"
  | "type"
  | "expand"
  | "navigate"
  | "retry"
  | "cancel"
  | "confirm"
  | "open"
  | "close";

export type UiTraceOutcome = "succeeded" | "failed" | "rejected" | "unknown";

export interface UiTraceBridge {
  logUiTrace?(input: {
    action: UiTraceAction;
    page: UiTracePage;
    phase: "action" | "result";
    status?: UiTraceOutcome;
    reason?: string;
    count?: number;
    trace_id?: string;
  }): Promise<unknown> | unknown;
}

/** A started trace. `traceId` is what the caller passes to the api call. */
export interface UiTrace {
  traceId: string;
  done(
    outcome: UiTraceOutcome,
    options?: { reason?: string; count?: number },
  ): void;
}

/**
 * Starts one traced interaction.
 *
 * The returned `traceId` must be handed to the api call the interaction makes,
 * so `X-One-Memory-Trace-Id` reaches Core unchanged and all four lines carry
 * the same id. Passing it explicitly (rather than through a module-level slot)
 * keeps two concurrent interactions from stealing each other's id.
 *
 * ```ts
 * const trace = traceUiAction("sources", "toggle");
 * try {
 *   await imports.setSync(source, enabled, trace.traceId);
 *   trace.done("succeeded");
 * } catch (error) {
 *   trace.done("failed", { reason: codeOf(error) });
 * }
 * ```
 */
export function traceUiAction(
  page: UiTracePage,
  action: UiTraceAction,
): UiTrace {
  const traceId = newTraceId();
  emit({ page, action, phase: "action", trace_id: traceId });
  let closed = false;
  return {
    traceId,
    done(outcome, options = {}) {
      // A double-close would produce a second `ui-result` for one action and
      // make the chain ambiguous; the first verdict is the one that happened.
      if (closed) return;
      closed = true;
      emit({
        page,
        action,
        phase: "result",
        status: outcome,
        trace_id: traceId,
        ...(options.reason ? { reason: options.reason } : {}),
        ...(options.count === undefined ? {} : { count: options.count }),
      });
    },
  };
}

/** Trace a promise without swallowing it: the value and error pass through. */
export async function traceUiOperation<T>(
  page: UiTracePage,
  action: UiTraceAction,
  run: (traceId: string) => Promise<T>,
  options: {
    reasonOf?: (error: unknown) => string | undefined;
    countOf?: (value: T) => number | undefined;
  } = {},
): Promise<T> {
  const trace = traceUiAction(page, action);
  try {
    const value = await run(trace.traceId);
    trace.done("succeeded", {
      ...(options.countOf ? { count: options.countOf(value) } : {}),
    });
    return value;
  } catch (error) {
    trace.done("failed", {
      ...(options.reasonOf ? { reason: options.reasonOf(error) } : {}),
    });
    throw error;
  }
}

function newTraceId(): string {
  const native = globalThis.crypto?.randomUUID;
  if (typeof native === "function") return native.call(globalThis.crypto);
  const bytes = Array.from({ length: 16 }, () =>
    Math.floor(Math.random() * 256),
  );
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function emit(input: {
  action: UiTraceAction;
  page: UiTracePage;
  phase: "action" | "result";
  status?: UiTraceOutcome;
  reason?: string;
  count?: number;
  trace_id?: string;
}): void {
  if (typeof window === "undefined") return;
  const bridge = window as unknown as { oneMemory?: UiTraceBridge };
  // Tracing must never become a new failure mode for the interaction it
  // observes: a missing bridge (browser console) or a rejected write is
  // swallowed, exactly like the diagnostic writers in Core.
  //
  // The bridge is `ipcRenderer.invoke`, so it returns a *promise*: awaiting it
  // (rather than only try/catching the call) is what keeps a rejection from
  // surfacing as an unhandled rejection — e.g. the window closed, or the
  // desktop validator refused a reason. Without this the renderer could both
  // log a scary error and, in the `done` path, lose nothing but crash the turn.
  try {
    const result = bridge.oneMemory?.logUiTrace?.(input);
    if (result && typeof (result as PromiseLike<unknown>).then === "function")
      Promise.resolve(result).catch(() => {});
  } catch {
    // A synchronous throw from a stub bridge is swallowed the same way.
  }
}
