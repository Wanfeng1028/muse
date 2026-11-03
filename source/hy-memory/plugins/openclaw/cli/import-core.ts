/**
 * import-from-openclaw — core logic (dependency-free, unit-testable).
 *
 * Migrates legacy OpenClaw `memory-core` memories (file-backed markdown +
 * session transcripts) into HY Memory via the `add` API.
 *
 * This module deliberately avoids any `@clack/prompts` / commander / network
 * coupling so it can be tested in isolation. The interactive prompt, progress
 * bar rendering and provider wiring live in index.ts.
 */

import { createHash } from "node:crypto";
import { readFile, readdir, stat, writeFile, rename, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";

// ============================================================================
// Types
// ============================================================================

export type ImportUnitKind = "memory-root" | "daily-note" | "session";

export interface ImportUnit {
  /** Stable ledger key, unique across all units. */
  key: string;
  /** Absolute path on disk. */
  absPath: string;
  /** Human-friendly path for display/logging. */
  relPath: string;
  kind: ImportUnitKind;
  /** ISO timestamp used as `memory_at` to preserve the original memory time. */
  memoryAt?: string;
}

export interface TextPayload {
  kind: "text";
  /** One or more text chunks (>1 only when a single file exceeds maxChars). */
  chunks: string[];
}

export interface MessagesPayload {
  kind: "messages";
  messages: Array<{ role: string; content: string }>;
}

export type UnitPayload = TextPayload | MessagesPayload;

export interface LedgerEntry {
  hash: string;
  memoryIds: string[];
  importedAt: string;
  kind: ImportUnitKind;
}

export interface Ledger {
  version: number;
  userId: string;
  entries: Record<string, LedgerEntry>;
}

/** Minimal provider surface — satisfied by HttpProvider. */
export interface ImportProvider {
  add(
    data: string | Array<{ role: string; content: string }>,
    options: {
      user_id: string;
      agent_id?: string;
      session_id?: string;
      enable_agent?: boolean;
      memory_at?: string;
    },
  ): Promise<{ success: boolean; memory_id: string; error_message?: string | null }>;
}

export interface ProgressState {
  total: number;
  done: number;
  ok: number;
  skipped: number;
  failed: number;
  current?: string;
  startedAt: number;
}

export interface RunImportOptions {
  workspaceDir: string;
  /** Directories containing session `*.jsonl` transcripts (per-day fallback). */
  sessionsDirs?: string[];
  userId: string;
  /** agent_id stored on each memory (default: keep plugin's configured agent). */
  agentId?: string;
  /** session_id tag used for traceability / rollback (default below). */
  sessionId?: string;
  dryRun?: boolean;
  /** Ignore ledger and re-import everything. */
  force?: boolean;
  /** Soft cap; files longer than this are split on blank lines. */
  maxChars?: number;
  /** Gentle rate-limit: delay (ms) between sequential writes. */
  rateDelayMs?: number;
  /** Retries for transient errors (429 / rate-limit / timeout / 5xx). */
  maxRetries?: number;
  /** Base backoff in ms (exponential + jitter). */
  retryBaseMs?: number;
  onProgress?: (state: ProgressState) => void;
  onLog?: (msg: string) => void;
}

export interface ImportSummary {
  total: number;
  ok: number;
  skipped: number;
  failed: number;
  failures: Array<{ key: string; error: string }>;
  elapsedMs: number;
  dryRun: boolean;
}

export const LEDGER_FILE = ".hy-memory-import.json";
export const LEDGER_VERSION = 1;
export const DEFAULT_IMPORT_SESSION_ID = "imported-from-openclaw";
export const DEFAULT_MAX_CHARS = 24_000;
export const DEFAULT_MAX_RETRIES = 4;
export const DEFAULT_RETRY_BASE_MS = 1_500;
export const DEFAULT_RATE_DELAY_MS = 500;

const TRANSIENT_RE =
  /\b429\b|rate.?limit|all keys busy|busy|timeout|timed out|temporarily|ECONNRESET|ETIMEDOUT|EAI_AGAIN|\b5\d\d\b/i;

/** Whether an error message looks like a transient/retryable failure. */
export function isTransientError(message: string): boolean {
  return TRANSIENT_RE.test(message);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ============================================================================
// Small helpers
// ============================================================================

const DATE_RE = /(\d{4})-(\d{2})-(\d{2})/;

export function hashContent(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

/** Expand a leading `~` to the user's home directory. */
export function expandHome(p: string): string {
  if (p === "~") return homedir();
  if (p.startsWith("~/")) return join(homedir(), p.slice(2));
  return p;
}

function isoFromDateName(name: string): string | undefined {
  const m = name.match(DATE_RE);
  if (!m) return undefined;
  const iso = `${m[1]}-${m[2]}-${m[3]}T00:00:00.000Z`;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

async function mtimeIso(absPath: string): Promise<string | undefined> {
  try {
    return (await stat(absPath)).mtime.toISOString();
  } catch {
    return undefined;
  }
}

async function pathExists(p: string): Promise<boolean> {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

async function listMarkdownRecursive(dir: string, opts: { skipDirName?: string } = {}): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true }).catch(() => []);
  const out: string[] = [];
  for (const entry of entries) {
    if (entry.isSymbolicLink()) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (opts.skipDirName && entry.name === opts.skipDirName) continue;
      out.push(...(await listMarkdownRecursive(full, opts)));
      continue;
    }
    if (entry.isFile() && entry.name.toLowerCase().endsWith(".md")) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Split text on blank-line boundaries so each piece stays <= maxChars.
 * A single oversized paragraph is hard-sliced as a last resort.
 */
export function splitText(text: string, maxChars: number): string[] {
  if (text.length <= maxChars) return [text];
  const paragraphs = text.split(/\n\s*\n/);
  const chunks: string[] = [];
  let buf = "";
  const flush = () => {
    if (buf.trim()) chunks.push(buf.trim());
    buf = "";
  };
  for (const para of paragraphs) {
    if (para.length > maxChars) {
      flush();
      for (let i = 0; i < para.length; i += maxChars) {
        chunks.push(para.slice(i, i + maxChars));
      }
      continue;
    }
    if (buf.length + para.length + 2 > maxChars) flush();
    buf += (buf ? "\n\n" : "") + para;
  }
  flush();
  return chunks.length > 0 ? chunks : [text.slice(0, maxChars)];
}

// ============================================================================
// Workspace / sessions resolution from openclaw.json
// ============================================================================

export interface ResolvedSources {
  workspaceDir: string;
  sessionsDirs: string[];
  configPath?: string;
}

/**
 * Default OpenClaw state dir, mirroring OpenClaw's own resolution:
 * honour OPENCLAW_STATE_DIR, then OPENCLAW_HOME, else ~/.openclaw.
 * This matters on lighthouse deployments that relocate the state dir.
 */
export function defaultStateDir(env: NodeJS.ProcessEnv = process.env): string {
  const override = env.OPENCLAW_STATE_DIR?.trim();
  if (override) return expandHome(override);
  const homeOverride = env.OPENCLAW_HOME?.trim();
  const home = homeOverride ? expandHome(homeOverride) : homedir();
  return join(home, ".openclaw");
}

/**
 * Resolve the agent workspace dir and session dirs from an openclaw config dir
 * (e.g. ~/.openclaw). Honours `agents.list[id].workspace` then
 * `agents.defaults.workspace`, falling back to `<stateDir>/workspace`.
 */
export async function resolveSourcesFromConfig(params: {
  stateDir?: string;
  agentId?: string;
}): Promise<ResolvedSources> {
  const stateDir = params.stateDir ?? defaultStateDir();
  const agentId = params.agentId ?? "main";
  const configPath = join(stateDir, "openclaw.json");

  let workspace: string | undefined;
  let cfg: any;
  if (await pathExists(configPath)) {
    try {
      cfg = JSON.parse(await readFile(configPath, "utf-8"));
    } catch {
      cfg = undefined;
    }
  }
  if (cfg?.agents) {
    const entry = Array.isArray(cfg.agents.list)
      ? cfg.agents.list.find((e: any) => (e?.id ?? "main") === agentId)
      : undefined;
    workspace = entry?.workspace ?? cfg.agents.defaults?.workspace;
  }

  // Resolve workspace: ~ expansion + relative to the config dir.
  let workspaceDir: string;
  if (workspace) {
    const expanded = expandHome(workspace);
    workspaceDir = isAbsolute(expanded) ? expanded : resolve(stateDir, expanded);
  } else {
    workspaceDir = join(stateDir, "workspace");
  }

  const sessionsDirs = [join(stateDir, "agents", agentId, "sessions")].filter(Boolean);
  return { workspaceDir, sessionsDirs, configPath };
}

// ============================================================================
// Scan
// ============================================================================

export async function scanUnits(input: {
  workspaceDir: string;
  sessionsDirs?: string[];
}): Promise<ImportUnit[]> {
  const { workspaceDir } = input;
  const units: ImportUnit[] = [];

  // 1) Long-term root memory: MEMORY.md (preferred) or memory.md — always imported.
  for (const name of ["MEMORY.md", "memory.md"]) {
    const abs = join(workspaceDir, name);
    if (await pathExists(abs)) {
      units.push({
        key: name,
        absPath: abs,
        relPath: name,
        kind: "memory-root",
        memoryAt: await mtimeIso(abs),
      });
      break;
    }
  }

  // 2) Daily notes: memory/**/*.md (excluding memory/dreaming/** — dreaming is NOT
  //    imported). Track which calendar days already have a daily note.
  const noteDays = new Set<string>();
  const memoryDir = join(workspaceDir, "memory");
  if (await pathExists(memoryDir)) {
    const daily = await listMarkdownRecursive(memoryDir, { skipDirName: "dreaming" });
    for (const abs of daily) {
      const rel = relative(workspaceDir, abs).replace(/\\/g, "/");
      const dayIso = isoFromDateName(basename(abs));
      if (dayIso) noteDays.add(dayIso.slice(0, 10));
      units.push({
        key: rel,
        absPath: abs,
        relPath: rel,
        kind: "daily-note",
        memoryAt: dayIso ?? (await mtimeIso(abs)),
      });
    }
  }

  // 3) Sessions — per-day fallback: import a session ONLY if its day has no daily
  //    note (daily notes already digest that day's sessions, so importing both
  //    would double-count). Archived `*.jsonl.reset.<ts>` files are excluded by the
  //    exact-suffix check.
  for (const dir of input.sessionsDirs ?? []) {
    if (!(await pathExists(dir))) continue;
    const entries = await readdir(dir, { withFileTypes: true }).catch(() => []);
    const files = entries
      .filter((e) => e.isFile() && e.name.endsWith(".jsonl"))
      .map((e) => join(dir, e.name))
      .sort();
    for (const abs of files) {
      const memoryAt = (await sessionStartIso(abs)) ?? (await mtimeIso(abs));
      const day = (memoryAt ?? "").slice(0, 10);
      if (day && noteDays.has(day)) continue; // that day is already covered by a daily note
      units.push({
        key: `session:${basename(abs)}`,
        absPath: abs,
        relPath: `sessions/${basename(abs)}`,
        kind: "session",
        memoryAt,
      });
    }
  }

  // 4) Global chronological order by memory_at (older first) so the server's
  //    evolution / dedup / recency logic sees memories in the right time order.
  units.sort((a, b) => (a.memoryAt ?? "").localeCompare(b.memoryAt ?? ""));
  return units;
}

async function sessionStartIso(absPath: string): Promise<string | undefined> {
  try {
    const raw = await readFile(absPath, "utf-8");
    for (const line of raw.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      const obj = JSON.parse(t);
      if (obj?.type === "session" && typeof obj.timestamp === "string") {
        const d = new Date(obj.timestamp);
        return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
      }
      // First line wasn't a session header — stop probing.
      break;
    }
  } catch {
    /* ignore */
  }
  return undefined;
}

// ============================================================================
// Payload extraction
// ============================================================================

/** Extract {role, content} pairs from an OpenClaw session JSONL transcript. */
export function parseSessionMessages(raw: string): Array<{ role: string; content: string }> {
  const out: Array<{ role: string; content: string }> = [];
  for (const line of raw.split("\n")) {
    const t = line.trim();
    if (!t) continue;
    let obj: any;
    try {
      obj = JSON.parse(t);
    } catch {
      continue;
    }
    if (obj?.type !== "message") continue;
    const msg = obj.message;
    if (!msg || typeof msg !== "object") continue;
    const role = msg.role;
    if (role !== "user" && role !== "assistant") continue;

    let text = "";
    if (typeof msg.content === "string") {
      text = msg.content;
    } else if (Array.isArray(msg.content)) {
      for (const block of msg.content) {
        if (block?.type === "text" && typeof block.text === "string") {
          text += (text ? "\n" : "") + block.text;
        }
      }
    }
    text = text.trim();
    if (text.length > 0) out.push({ role, content: text });
  }
  return out;
}

/**
 * Read a unit and produce its add-payload + content hash.
 * Returns null when there is nothing worth importing (empty file / no messages).
 */
export async function readUnitPayload(
  unit: ImportUnit,
  opts: { maxChars: number },
): Promise<{ payload: UnitPayload; hash: string } | null> {
  const raw = await readFile(unit.absPath, "utf-8");
  const hash = hashContent(raw);

  if (unit.kind === "session") {
    const messages = parseSessionMessages(raw);
    if (messages.length === 0 || !messages.some((m) => m.role === "user")) return null;
    return { payload: { kind: "messages", messages }, hash };
  }

  const text = raw.trim();
  if (text.length === 0) return null;
  return { payload: { kind: "text", chunks: splitText(text, opts.maxChars) }, hash };
}

// ============================================================================
// Ledger (idempotency / resume)
// ============================================================================

export function ledgerPath(workspaceDir: string): string {
  return join(workspaceDir, LEDGER_FILE);
}

export async function loadLedger(path: string, userId: string): Promise<Ledger> {
  try {
    const parsed = JSON.parse(await readFile(path, "utf-8")) as Ledger;
    if (parsed && typeof parsed === "object" && parsed.entries) {
      // A ledger written for a different user is ignored (fresh import).
      if (parsed.userId === userId) return parsed;
    }
  } catch {
    /* no ledger yet */
  }
  return { version: LEDGER_VERSION, userId, entries: {} };
}

export async function saveLedger(path: string, ledger: Ledger): Promise<void> {
  await mkdir(dirname(path), { recursive: true }).catch(() => {});
  const tmp = `${path}.tmp`;
  await writeFile(tmp, JSON.stringify(ledger, null, 2) + "\n", "utf-8");
  await rename(tmp, path);
}

// ============================================================================
// Run
// ============================================================================

export async function runImport(
  options: RunImportOptions,
  provider: ImportProvider | null,
): Promise<ImportSummary> {
  const {
    workspaceDir,
    userId,
    agentId,
    sessionId = DEFAULT_IMPORT_SESSION_ID,
    dryRun = false,
    force = false,
    maxChars = DEFAULT_MAX_CHARS,
    maxRetries = DEFAULT_MAX_RETRIES,
    retryBaseMs = DEFAULT_RETRY_BASE_MS,
    rateDelayMs = DEFAULT_RATE_DELAY_MS,
    onProgress,
    onLog,
  } = options;

  if (!dryRun && !provider) {
    throw new Error("runImport: provider is required unless dryRun is true");
  }

  // Add one payload with exponential-backoff retry on transient errors.
  const addWithRetry = async (
    data: string | Array<{ role: string; content: string }>,
    addOpts: Parameters<ImportProvider["add"]>[1],
    label: string,
  ): Promise<string> => {
    let lastErr = "add failed";
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      let transient = false;
      try {
        const res = await provider!.add(data, addOpts);
        if (res.success) return res.memory_id;
        lastErr = res.error_message || "add failed";
        transient = isTransientError(lastErr);
      } catch (err) {
        lastErr = err instanceof Error ? err.message : String(err);
        transient = isTransientError(lastErr);
      }
      if (!transient || attempt === maxRetries) break;
      const delay = Math.round(retryBaseMs * 2 ** attempt + Math.random() * 300);
      onLog?.(`retry ${attempt + 1}/${maxRetries} in ${delay}ms (${label}): ${lastErr}`);
      await sleep(delay);
    }
    throw new Error(lastErr);
  };

  const startedAt = Date.now();
  const units = await scanUnits({ workspaceDir, sessionsDirs: options.sessionsDirs });

  const lPath = ledgerPath(workspaceDir);
  const ledger = await loadLedger(lPath, userId);

  const state: ProgressState = {
    total: units.length,
    done: 0,
    ok: 0,
    skipped: 0,
    failed: 0,
    startedAt,
  };
  const failures: Array<{ key: string; error: string }> = [];
  onProgress?.({ ...state });

  // Serialize ledger writes.
  let ledgerWrite: Promise<void> = Promise.resolve();
  const flushLedger = () => {
    if (dryRun) return Promise.resolve();
    ledgerWrite = ledgerWrite.then(() => saveLedger(lPath, ledger)).catch(() => {});
    return ledgerWrite;
  };

  const processUnit = async (unit: ImportUnit): Promise<void> => {
    state.current = unit.relPath;
    onProgress?.({ ...state });
    try {
      const read = await readUnitPayload(unit, { maxChars });
      if (!read) {
        state.skipped += 1;
        onLog?.(`skip (empty): ${unit.relPath}`);
        return;
      }

      const prev = ledger.entries[unit.key];
      if (!force && prev && prev.hash === read.hash) {
        state.skipped += 1;
        onLog?.(`skip (unchanged): ${unit.relPath}`);
        return;
      }

      if (dryRun) {
        state.ok += 1;
        onLog?.(`would import: ${unit.relPath} (${unit.kind}, memory_at=${unit.memoryAt ?? "-"})`);
        return;
      }

      const addOpts = {
        user_id: userId,
        agent_id: agentId,
        session_id: sessionId,
        enable_agent: true,
        memory_at: unit.memoryAt,
      };
      const memoryIds: string[] = [];
      if (read.payload.kind === "text") {
        const chunks = read.payload.chunks;
        for (let i = 0; i < chunks.length; i++) {
          const label = chunks.length > 1 ? `${unit.relPath}#${i + 1}` : unit.relPath;
          memoryIds.push(await addWithRetry(chunks[i]!, addOpts, label));
        }
      } else {
        memoryIds.push(await addWithRetry(read.payload.messages, addOpts, unit.relPath));
      }

      ledger.entries[unit.key] = {
        hash: read.hash,
        memoryIds,
        importedAt: new Date().toISOString(),
        kind: unit.kind,
      };
      await flushLedger();
      state.ok += 1;
      onLog?.(`imported: ${unit.relPath} -> ${memoryIds.join(", ")}`);
    } catch (err) {
      state.failed += 1;
      const msg = err instanceof Error ? err.message : String(err);
      failures.push({ key: unit.key, error: msg });
      onLog?.(`FAILED: ${unit.relPath}: ${msg}`);
    } finally {
      state.done += 1;
      onProgress?.({ ...state });
    }
  };

  // Strictly sequential writes: preserve chronological order (so the server's
  // evolution/dedup sees memories oldest→newest) and stay gentle on rate-limited
  // backends. A small delay between writes further smooths load.
  for (let i = 0; i < units.length; i++) {
    await processUnit(units[i]!);
    if (!dryRun && rateDelayMs > 0 && i < units.length - 1) {
      await sleep(rateDelayMs);
    }
  }
  await ledgerWrite;

  return {
    total: units.length,
    ok: state.ok,
    skipped: state.skipped,
    failed: state.failed,
    failures,
    elapsedMs: Date.now() - startedAt,
    dryRun,
  };
}
