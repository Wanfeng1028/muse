/**
 * import-from-openclaw — CLI orchestration.
 *
 * Wires the dependency-free core (import-core.ts) to the interactive prompt
 * (@clack/prompts), a zero-dependency progress bar, server pre-flight checks
 * and workspace resolution. Dynamically imported by index.ts so the main
 * plugin bundle stays lean.
 */

import { homedir } from "node:os";
import { isAbsolute, resolve } from "node:path";
import { intro, outro, confirm, isCancel, cancel, note } from "@clack/prompts";
import type { ImportProvider, ImportSummary, ProgressState } from "./import-core.js";
import {
  DEFAULT_IMPORT_SESSION_ID,
  expandHome,
  resolveSourcesFromConfig,
  runImport,
  scanUnits,
} from "./import-core.js";

export interface ImportCliOptions {
  /** Explicit OpenClaw agent workspace dir (auto-detected from config if omitted). */
  workspace?: string;
  /** OpenClaw agent id (used to locate workspace + sessions). */
  agent: string;
  /** OpenClaw state dir holding openclaw.json (default: ~/.openclaw). */
  stateDir?: string;
  /** Target HY Memory user id (default: cfg.userId). */
  userId?: string;
  dryRun?: boolean;
  force?: boolean;
  /** Retries for transient errors (429 / rate-limit / 5xx). */
  maxRetries?: number;
  /** Base backoff in ms (exponential + jitter). */
  retryBaseMs?: number;
  /** Skip the confirmation prompt. */
  yes?: boolean;
}

export interface ImportCliDeps {
  provider: ImportProvider & { healthCheck(): Promise<boolean> };
  cfg: { userId: string; agentId: string; serverUrl: string; serverPort: number; pythonPath: string };
}

// ============================================================================
// Zero-dependency progress bar
// ============================================================================

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

function fmtSecs(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m${String(s % 60).padStart(2, "0")}s`;
}

function createProgressBar(total: number, stream: NodeJS.WriteStream = process.stderr) {
  const isTTY = Boolean(stream.isTTY);
  let lastLen = 0;
  let lastDone = -1;

  const render = (s: ProgressState) => {
    const pct = s.total ? Math.floor((s.done / s.total) * 100) : 100;
    const width = 24;
    const ratio = s.total ? s.done / s.total : 1;
    const filled = Math.min(width, Math.round(width * ratio));
    const bar = "█".repeat(filled) + "░".repeat(width - filled);
    const elapsed = (Date.now() - s.startedAt) / 1000;
    const eta =
      s.done > 0 && s.done < s.total ? Math.round((elapsed / s.done) * (s.total - s.done)) : 0;
    const tail = s.current ? truncate(s.current, 34) : "";
    return `  [${bar}] ${s.done}/${s.total} ${pct}% | ok:${s.ok} skip:${s.skipped} err:${s.failed} | ETA ${fmtSecs(eta)} | ${tail}`;
  };

  return {
    update(s: ProgressState) {
      if (isTTY) {
        const line = render(s);
        const pad = line.length < lastLen ? " ".repeat(lastLen - line.length) : "";
        stream.write("\r" + line + pad);
        lastLen = line.length;
      } else if (s.done !== lastDone) {
        // Non-interactive: one concise line per completed unit.
        lastDone = s.done;
        if (s.done > 0) stream.write(render(s).trim() + "\n");
      }
    },
    finish(s: ProgressState) {
      if (isTTY) {
        const line = render(s);
        const pad = line.length < lastLen ? " ".repeat(lastLen - line.length) : "";
        stream.write("\r" + line + pad + "\n");
      }
    },
  };
}

// ============================================================================
// Source resolution
// ============================================================================

async function resolveSources(opts: ImportCliOptions): Promise<{
  workspaceDir: string;
  sessionsDirs: string[];
}> {
  const stateDir = opts.stateDir ? expandHome(opts.stateDir) : undefined;
  const fromCfg = await resolveSourcesFromConfig({ stateDir, agentId: opts.agent });

  let workspaceDir = fromCfg.workspaceDir;
  if (opts.workspace) {
    const expanded = expandHome(opts.workspace);
    workspaceDir = isAbsolute(expanded) ? expanded : resolve(process.cwd(), expanded);
  }
  return { workspaceDir, sessionsDirs: fromCfg.sessionsDirs };
}

// ============================================================================
// Command entry
// ============================================================================

export async function runImportFromOpenclaw(
  opts: ImportCliOptions,
  deps: ImportCliDeps,
): Promise<ImportSummary | null> {
  intro("🧠 HY Memory — Import from OpenClaw memory-core");

  const userId = opts.userId || deps.cfg.userId;
  const { workspaceDir, sessionsDirs } = await resolveSources(opts);

  note(
    `Workspace: ${workspaceDir}\n` +
      `Sessions:  ${sessionsDirs.join(", ") || "(none)"}\n` +
      `User ID:   ${userId}`,
    "Source",
  );

  // ── Pre-flight: server must be reachable (unless dry-run) ────────────────
  if (!opts.dryRun) {
    const healthy = await deps.provider.healthCheck();
    if (!healthy) {
      cancel(
        `HY Memory server not reachable at ${deps.cfg.serverUrl}.\n` +
          `  Start it first (e.g. \`openclaw gateway restart\`), or run with --dry-run to preview.`,
      );
      return null;
    }
  }

  // ── Plan ─────────────────────────────────────────────────────────────────
  // Scope is automatic: MEMORY.md + daily notes; sessions only fill days that
  // have no daily note; dreaming is not imported. (No user-facing "mode".)
  const units = await scanUnits({ workspaceDir, sessionsDirs });
  if (units.length === 0) {
    outro("No memory files found — nothing to import.");
    return {
      total: 0,
      ok: 0,
      skipped: 0,
      failed: 0,
      failures: [],
      elapsedMs: 0,
      dryRun: Boolean(opts.dryRun),
    };
  }

  const byKind = units.reduce<Record<string, number>>((acc, u) => {
    acc[u.kind] = (acc[u.kind] ?? 0) + 1;
    return acc;
  }, {});
  note(
    Object.entries(byKind)
      .map(([k, n]) => `${k}: ${n}`)
      .join("\n") + `\n\nTotal units: ${units.length}`,
    "Plan",
  );

  if (!opts.dryRun && !opts.yes) {
    const ok = await confirm({ message: `Import ${units.length} unit(s) into HY Memory (user: ${userId})?` });
    if (isCancel(ok) || !ok) {
      cancel("Cancelled.");
      return null;
    }
  }

  // ── Run with progress bar ────────────────────────────────────────────────
  const bar = createProgressBar(units.length);
  let lastState: ProgressState | null = null;
  const summary = await runImport(
    {
      workspaceDir,
      sessionsDirs,
      userId,
      agentId: deps.cfg.agentId,
      sessionId: DEFAULT_IMPORT_SESSION_ID,
      dryRun: opts.dryRun,
      force: opts.force,
      maxRetries: opts.maxRetries,
      retryBaseMs: opts.retryBaseMs,
      onProgress: (s) => {
        lastState = s;
        bar.update(s);
      },
    },
    opts.dryRun ? null : deps.provider,
  );
  if (lastState) bar.finish(lastState);

  // ── Summary ──────────────────────────────────────────────────────────────
  const verb = opts.dryRun ? "Would import" : "Imported";
  const lines = [
    `${verb}: ${summary.ok}`,
    `Skipped (unchanged/empty): ${summary.skipped}`,
    `Failed: ${summary.failed}`,
    `Elapsed: ${fmtSecs(Math.round(summary.elapsedMs / 1000))}`,
  ];
  if (summary.failures.length > 0) {
    lines.push("", "Failures:");
    for (const f of summary.failures.slice(0, 10)) lines.push(`  - ${f.key}: ${f.error}`);
    if (summary.failures.length > 10) lines.push(`  … and ${summary.failures.length - 10} more`);
  }
  note(lines.join("\n"), opts.dryRun ? "Dry-run result" : "Import complete");

  outro(
    summary.failed > 0
      ? "Done with errors. Re-run to retry failed units (idempotent)."
      : opts.dryRun
        ? "Dry-run only — no memories written. Re-run without --dry-run to import."
        : "All done. ✓",
  );

  return summary;
}
