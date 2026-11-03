import path from "node:path";

/**
 * Decide whether the CLI entry should write its own diagnostic file.
 *
 * The entry logger resolves the data dir the same way `run()` does. When the
 * caller names neither `--data-dir` nor `ONE_MEMORY_DATA_DIR`, that resolution
 * falls back to `<HOME>/.one-memory` -- the real account-home default. Under an
 * isolated HOME used only as an isolation root, writing there adds
 * `.one-memory/logs/diagnostic-cli.jsonl` to a directory the caller did not
 * mean as a user home (C8 P1 isolated-cli-session-writes-home). This decides
 * that case without touching the filesystem, so it is a pure, testable rule.
 */
export type EntryDiagnosticsDecision =
  | { kind: "log" }
  | { kind: "skip"; reason: "isolated_home" };

export function resolveEntryDiagnostics(input: {
  arguments_: readonly string[];
  home: string | undefined;
  accountHome: string | undefined;
  environmentDataDir: string | undefined;
}): EntryDiagnosticsDecision {
  if (input.arguments_.includes("--data-dir")) return { kind: "log" };
  if (input.environmentDataDir !== undefined) return { kind: "log" };
  // Compare resolved paths: `HOME` can carry a trailing slash or `.`/`..`
  // segments while still naming the real account home, and a string-only
  // comparison would misread that as isolated and silently drop diagnostics.
  const home = resolve(input.home);
  const accountHome = resolve(input.accountHome);
  if (home === undefined || accountHome === undefined || home === accountHome) {
    return { kind: "log" };
  }
  // Isolated HOME with no explicit data dir: the fallback path would write
  // into the isolation root, so skip entry diagnostics.
  return { kind: "skip", reason: "isolated_home" };
}

function resolve(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  return path.resolve(value);
}
