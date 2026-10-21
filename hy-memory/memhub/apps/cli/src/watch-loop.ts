import { Buffer } from "node:buffer";

const DEFAULT_EVENT_BUDGET = 1024 * 1024;

export interface WatchRead<T> {
  instanceId?: string;
  value: T;
}

export interface WatchEvent<T = unknown> {
  schema_version: 1;
  event: "status" | "progress";
  sequence: number;
  observed_at: string;
  instance_id?: string;
  state?: "unavailable" | "untrusted";
  code?: string;
  data?: T;
  expected_instance_id?: string;
  actual_instance_id?: string;
}

export type WatchResult =
  | { state: "complete" | "cancelled"; events: number }
  | { state: "failed"; code: string; events: number };

/**
 * Serial polling only: the next read starts after the current read and the
 * interval have both completed. A failed read emits a current failure event,
 * never the previous value. Identity drift is terminal because snapshots from
 * two data instances cannot be one timeline.
 */
export async function runWatchLoop<T>(options: {
  kind: "status" | "progress";
  intervalMs: number;
  signal: AbortSignal;
  read(signal: AbortSignal): Promise<WatchRead<T>>;
  emit(event: WatchEvent<T>): void;
  maxEvents?: number;
  maxEventBytes?: number;
  wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
  now?: () => string;
}): Promise<WatchResult> {
  const maxEvents = options.maxEvents ?? Number.POSITIVE_INFINITY;
  const maxEventBytes = options.maxEventBytes ?? DEFAULT_EVENT_BUDGET;
  const wait = options.wait ?? abortableWait;
  const now = options.now ?? (() => new Date().toISOString());
  let emitted = 0;
  let expectedInstanceId: string | undefined;

  while (emitted < maxEvents) {
    if (options.signal.aborted) return { state: "cancelled", events: emitted };
    const sequence = emitted + 1;
    let snapshot: WatchRead<T>;
    try {
      snapshot = await options.read(options.signal);
    } catch {
      if (options.signal.aborted)
        return { state: "cancelled", events: emitted };
      const event: WatchEvent<T> = {
        schema_version: 1,
        event: options.kind,
        sequence,
        observed_at: now(),
        state: "unavailable",
        code: "watch_read_failed",
      };
      options.emit(event);
      emitted += 1;
      if (emitted >= maxEvents) break;
      if (!(await waitForNext(wait, options.intervalMs, options.signal))) {
        return { state: "cancelled", events: emitted };
      }
      continue;
    }

    if (
      expectedInstanceId !== undefined &&
      snapshot.instanceId !== undefined &&
      snapshot.instanceId !== expectedInstanceId
    ) {
      options.emit({
        schema_version: 1,
        event: options.kind,
        sequence,
        observed_at: now(),
        state: "untrusted",
        code: "watch_instance_changed",
        expected_instance_id: expectedInstanceId,
        actual_instance_id: snapshot.instanceId,
      });
      return {
        state: "failed",
        code: "watch_instance_changed",
        events: emitted + 1,
      };
    }
    expectedInstanceId ??= snapshot.instanceId;
    const event: WatchEvent<T> = {
      schema_version: 1,
      event: options.kind,
      sequence,
      observed_at: now(),
      ...(snapshot.instanceId ? { instance_id: snapshot.instanceId } : {}),
      data: snapshot.value,
    };
    if (Buffer.byteLength(JSON.stringify(event), "utf8") > maxEventBytes) {
      options.emit({
        schema_version: 1,
        event: options.kind,
        sequence,
        observed_at: now(),
        state: "unavailable",
        code: "watch_event_too_large",
      });
      return {
        state: "failed",
        code: "watch_event_too_large",
        events: emitted + 1,
      };
    }
    options.emit(event);
    emitted += 1;
    if (emitted >= maxEvents) break;
    if (!(await waitForNext(wait, options.intervalMs, options.signal))) {
      return { state: "cancelled", events: emitted };
    }
  }
  return { state: "complete", events: emitted };
}

async function waitForNext(
  wait: (milliseconds: number, signal: AbortSignal) => Promise<void>,
  milliseconds: number,
  signal: AbortSignal,
): Promise<boolean> {
  try {
    await wait(milliseconds, signal);
    return !signal.aborted;
  } catch {
    return false;
  }
}

function abortableWait(
  milliseconds: number,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
