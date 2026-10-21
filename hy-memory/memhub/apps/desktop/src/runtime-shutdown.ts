import { stopRuntimeProcess } from "@one-memory/runtime-control";

export interface RuntimeShutdownOptions {
  dataDir: string;
  /** Packaged builds run the Runtime as their own process; a dev build's Core
   * is this process's child and is stopped by the supervisor. */
  standalone: boolean;
  /** A managed OS service outlives Electron; a transient App-spawned Runtime
   * is still stopped on quit. */
  preserveManagedRuntime?: boolean;
  /** Tear down this process's supervisor state (Core child, broker). */
  stopSupervisor?: () => Promise<void>;
  onDiagnostic?: (event: {
    outcome: "succeeded" | "degraded";
    detail: string;
  }) => Promise<void> | void;
}

export type RuntimeShutdownResult =
  | { runtime: "stopped" }
  | { runtime: "not-running" }
  | { runtime: "unchanged" }
  | { runtime: "failed"; detail: string };

/** Stop everything a full quit has to stop.
 *
 * Quitting used to tear down this process's own handles and nothing else. In a
 * packaged build the Runtime is a separate process, so it outlived the app: the
 * window and the tray were gone and the Runtime was still there, and its
 * receipt still named a pid, so the next launch concluded it was already
 * running and attached to a process that no longer answered.
 *
 * A failure here is reported, never thrown. By the time this runs the app is
 * already quitting, and throwing would only turn a failure someone could see
 * into one nobody could.
 */
export async function shutdownRuntime(
  options: RuntimeShutdownOptions,
): Promise<RuntimeShutdownResult> {
  const stopSupervisor = options.stopSupervisor ?? (async () => {});
  const supervisorFailure = await settle(stopSupervisor);
  if (options.preserveManagedRuntime) {
    await options.onDiagnostic?.({
      outcome: supervisorFailure ? "degraded" : "succeeded",
      detail: supervisorFailure ?? "managed-runtime-preserved",
    });
    return supervisorFailure
      ? { runtime: "failed", detail: supervisorFailure }
      : { runtime: "unchanged" };
  }
  if (!options.standalone) {
    if (supervisorFailure) {
      await options.onDiagnostic?.({
        outcome: "degraded",
        detail: supervisorFailure,
      });
      return { runtime: "failed", detail: supervisorFailure };
    }
    return { runtime: "unchanged" };
  }
  try {
    const result = await stopRuntimeProcess({ dataDir: options.dataDir });
    await options.onDiagnostic?.({
      outcome: supervisorFailure ? "degraded" : "succeeded",
      detail: supervisorFailure ?? result,
    });
    if (supervisorFailure) {
      return { runtime: "failed", detail: supervisorFailure };
    }
    return { runtime: result };
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown";
    await options.onDiagnostic?.({ outcome: "degraded", detail });
    return { runtime: "failed", detail };
  }
}

/** Run an action and hand back why it failed, instead of throwing. */
async function settle(action: () => Promise<void>): Promise<string | null> {
  try {
    await action();
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : "unknown";
  }
}
