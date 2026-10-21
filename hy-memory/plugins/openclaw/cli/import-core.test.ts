import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtemp, mkdir, writeFile, rm, stat } from "node:fs/promises";
import { tmpdir, homedir } from "node:os";
import { join } from "node:path";
import {
  scanUnits,
  parseSessionMessages,
  splitText,
  runImport,
  loadLedger,
  ledgerPath,
  resolveSourcesFromConfig,
  defaultStateDir,
  isTransientError,
  type ImportProvider,
} from "./import-core.js";

// ── Fake provider that records every add call ───────────────────────────────
function makeFakeProvider() {
  const calls: Array<{
    data: string | Array<{ role: string; content: string }>;
    options: Record<string, unknown>;
  }> = [];
  let counter = 0;
  const provider: ImportProvider = {
    async add(data, options) {
      calls.push({ data, options });
      counter += 1;
      return { success: true, memory_id: `mem-${counter}` };
    },
  };
  return { provider, calls };
}

function sessionJsonl(ts: string): string {
  return [
    `{"type":"session","version":3,"id":"s","timestamp":"${ts}","cwd":"/ws"}`,
    `{"type":"model_change","id":"m1","timestamp":"t"}`,
    `{"type":"message","id":"a1","timestamp":"t","message":{"role":"user","content":[{"type":"text","text":"hi there"}]}}`,
    `{"type":"message","id":"a2","timestamp":"t","message":{"role":"assistant","content":[{"type":"text","text":"hello back"}]}}`,
    `{"type":"custom","customType":"tool","data":{},"id":"c1","timestamp":"t"}`,
    `{"type":"message","id":"a3","timestamp":"t","message":{"role":"assistant","content":[]}}`,
  ].join("\n");
}

let workspaceDir: string;
let sessionsDir: string;

// Fixture covers: MEMORY.md, two dated daily notes, an empty note, an excluded
// dreaming report, a session on a day that HAS a note (should be skipped), a
// session on a day WITHOUT a note (should be imported), and an archived reset.
async function buildFixture() {
  const dir = await mkdtemp(join(tmpdir(), "hy-import-"));
  await mkdir(join(dir, "memory", "dreaming"), { recursive: true });
  await writeFile(join(dir, "MEMORY.md"), "# MEMORY\n\n- likes Rust\n");
  await writeFile(join(dir, "memory", "2026-04-01.md"), "# Daily\n\n- did X\n");
  await writeFile(join(dir, "memory", "2026-04-15.md"), "# Daily\n\n- did Y\n");
  await writeFile(join(dir, "memory", "blank.md"), "   \n\n  \n"); // empty → skipped at import
  await writeFile(join(dir, "memory", "dreaming", "DREAMS.md"), "# Dreams\n\n- reflection\n"); // excluded

  const sessions = join(dir, "sessions");
  await mkdir(sessions, { recursive: true });
  await writeFile(join(sessions, "covered.jsonl"), sessionJsonl("2026-04-01T03:00:00.000Z")); // day has a note → skip
  await writeFile(join(sessions, "gap.jsonl"), sessionJsonl("2026-05-10T02:11:00.000Z")); // no note that day → import
  await writeFile(
    join(sessions, "old.jsonl.reset.2026-05-11T00-00-00.000Z"),
    sessionJsonl("2026-05-11T00:00:00.000Z"),
  ); // archived → ignored
  return { dir, sessions };
}

beforeEach(async () => {
  const fx = await buildFixture();
  workspaceDir = fx.dir;
  sessionsDir = fx.sessions;
});

afterEach(async () => {
  await rm(workspaceDir, { recursive: true, force: true });
});

describe("splitText", () => {
  it("keeps short text as a single chunk", () => {
    expect(splitText("hello world", 100)).toEqual(["hello world"]);
  });
  it("splits oversized text into pieces under the cap", () => {
    const big = Array.from({ length: 50 }, (_, i) => `para ${i} ${"x".repeat(40)}`).join("\n\n");
    const chunks = splitText(big, 200);
    expect(chunks.length).toBeGreaterThan(1);
    for (const c of chunks) expect(c.length).toBeLessThanOrEqual(200);
  });
  it("hard-slices a single paragraph longer than the cap", () => {
    expect(splitText("y".repeat(500), 100).length).toBe(5);
  });
});

describe("isTransientError", () => {
  it("flags 429 / rate-limit / 5xx as transient, others not", () => {
    expect(isTransientError("Error code: 429 - all keys busy")).toBe(true);
    expect(isTransientError("rate_limit_exceeded")).toBe(true);
    expect(isTransientError("HTTP 503")).toBe(true);
    expect(isTransientError("HTTP 400: invalid request")).toBe(false);
  });
});

describe("parseSessionMessages", () => {
  it("extracts user/assistant text and skips empty/non-message lines", () => {
    expect(parseSessionMessages(sessionJsonl("2026-05-10T02:11:00.000Z"))).toEqual([
      { role: "user", content: "hi there" },
      { role: "assistant", content: "hello back" },
    ]);
  });
});

describe("scanUnits", () => {
  it("MEMORY.md + daily notes; dreaming excluded; sessions only for note-less days", async () => {
    const units = await scanUnits({ workspaceDir, sessionsDirs: [sessionsDir] });
    expect(units.filter((u) => u.kind === "memory-root").length).toBe(1);
    expect(units.filter((u) => u.kind === "daily-note").length).toBe(3); // 2 dated + blank
    expect(units.filter((u) => u.kind === "session").length).toBe(1);
    expect(units.some((u) => u.relPath.includes("dreaming"))).toBe(false); // dreaming not imported
    expect(units.some((u) => u.relPath.includes("covered.jsonl"))).toBe(false); // day 2026-04-01 has a note
    const session = units.find((u) => u.kind === "session");
    expect(session?.relPath).toContain("gap.jsonl");
    expect(session?.memoryAt).toBe("2026-05-10T02:11:00.000Z");
  });

  it("orders units chronologically by memory_at (oldest first)", async () => {
    const units = await scanUnits({ workspaceDir, sessionsDirs: [sessionsDir] });
    const ats = units.map((u) => u.memoryAt ?? "");
    expect(ats).toEqual([...ats].sort());
    expect(units[0]?.relPath).toContain("2026-04-01.md"); // earliest memory_at
  });
});

describe("runImport", () => {
  it("dry-run: counts would-imports, writes no ledger, calls no provider", async () => {
    const { provider, calls } = makeFakeProvider();
    const s = await runImport(
      { workspaceDir, sessionsDirs: [sessionsDir], userId: "u1", dryRun: true, rateDelayMs: 0 },
      provider,
    );
    expect(s.total).toBe(5); // MEMORY + 2 dated daily + blank + gap-session
    expect(s.ok).toBe(4); // blank is empty → skipped
    expect(s.skipped).toBe(1);
    expect(calls.length).toBe(0);
    await expect(stat(ledgerPath(workspaceDir))).rejects.toBeTruthy();
  });

  it("real run: imports, records ledger, preserves memory_at + tags, session as messages", async () => {
    const { provider, calls } = makeFakeProvider();
    const s = await runImport(
      { workspaceDir, sessionsDirs: [sessionsDir], userId: "u1", agentId: "default_agent", rateDelayMs: 0 },
      provider,
    );
    expect(s.ok).toBe(4);
    expect(s.failed).toBe(0);
    expect(calls.length).toBe(4);
    for (const c of calls) {
      expect(c.options.user_id).toBe("u1");
      expect(c.options.agent_id).toBe("default_agent");
      expect(c.options.session_id).toBe("imported-from-openclaw");
      expect(c.options.memory_at).toBeTruthy();
    }
    expect(calls.some((c) => Array.isArray(c.data))).toBe(true); // gap session imported as messages
    const ledger = await loadLedger(ledgerPath(workspaceDir), "u1");
    expect(Object.keys(ledger.entries).length).toBe(4);
  });

  it("writes in chronological order (memory_at ascending)", async () => {
    const { provider, calls } = makeFakeProvider();
    await runImport({ workspaceDir, sessionsDirs: [sessionsDir], userId: "u1", rateDelayMs: 0 }, provider);
    const ats = calls.map((c) => String(c.options.memory_at ?? ""));
    expect(ats).toEqual([...ats].sort());
  });

  it("is idempotent: a second run skips everything unchanged", async () => {
    const first = makeFakeProvider();
    await runImport({ workspaceDir, sessionsDirs: [sessionsDir], userId: "u1", rateDelayMs: 0 }, first.provider);
    const second = makeFakeProvider();
    const s = await runImport(
      { workspaceDir, sessionsDirs: [sessionsDir], userId: "u1", rateDelayMs: 0 },
      second.provider,
    );
    expect(s.ok).toBe(0);
    expect(s.skipped).toBe(5);
    expect(second.calls.length).toBe(0);
  });

  it("re-imports a file whose content changed", async () => {
    const first = makeFakeProvider();
    await runImport({ workspaceDir, userId: "u1", rateDelayMs: 0 }, first.provider);
    await writeFile(join(workspaceDir, "MEMORY.md"), "# MEMORY\n\n- now likes Go\n");
    const second = makeFakeProvider();
    const s = await runImport({ workspaceDir, userId: "u1", rateDelayMs: 0 }, second.provider);
    expect(s.ok).toBe(1); // only the changed MEMORY.md
  });

  it("--force re-imports everything", async () => {
    const first = makeFakeProvider();
    await runImport({ workspaceDir, userId: "u1", rateDelayMs: 0 }, first.provider);
    const second = makeFakeProvider();
    const s = await runImport({ workspaceDir, userId: "u1", force: true, rateDelayMs: 0 }, second.provider);
    expect(s.ok).toBe(3); // MEMORY + 2 dated daily (no sessions passed; blank skipped)
    expect(second.calls.length).toBe(3);
  });

  it("retries transient 429 then succeeds", async () => {
    let n = 0;
    const provider: ImportProvider = {
      async add() {
        n += 1;
        if (n <= 2) return { success: false, memory_id: "", error_message: "Error code: 429 - all keys busy" };
        return { success: true, memory_id: `m${n}` };
      },
    };
    const s = await runImport({ workspaceDir, userId: "u1", retryBaseMs: 1, rateDelayMs: 0 }, provider);
    expect(s.ok).toBe(3); // MEMORY + 2 daily; first add retried twice then ok
    expect(s.failed).toBe(0);
  });

  it("does NOT retry a non-transient error", async () => {
    let calls = 0;
    const provider: ImportProvider = {
      async add() {
        calls += 1;
        return { success: false, memory_id: "", error_message: "HTTP 400: invalid request" };
      },
    };
    const s = await runImport({ workspaceDir, userId: "u1", retryBaseMs: 1, rateDelayMs: 0 }, provider);
    expect(s.failed).toBe(3);
    expect(calls).toBe(3); // one attempt per unit, no retries
  });

  it("records failures without aborting the whole run", async () => {
    let n = 0;
    const provider: ImportProvider = {
      async add() {
        n += 1;
        if (n === 1) return { success: false, memory_id: "", error_message: "boom" };
        return { success: true, memory_id: `mem-${n}` };
      },
    };
    const s = await runImport({ workspaceDir, userId: "u1", retryBaseMs: 1, rateDelayMs: 0 }, provider);
    expect(s.failed).toBe(1);
    expect(s.ok).toBe(2);
    expect(s.failures[0]?.error).toContain("boom");
  });
});

describe("defaultStateDir", () => {
  it("honours OPENCLAW_STATE_DIR (highest priority)", () => {
    expect(defaultStateDir({ OPENCLAW_STATE_DIR: "/custom/state" })).toBe("/custom/state");
  });
  it("honours OPENCLAW_HOME when no state-dir override", () => {
    expect(defaultStateDir({ OPENCLAW_HOME: "/home/box" })).toBe(join("/home/box", ".openclaw"));
  });
  it("falls back to ~/.openclaw", () => {
    expect(defaultStateDir({})).toBe(join(homedir(), ".openclaw"));
  });
});

describe("resolveSourcesFromConfig", () => {
  let stateDir: string;
  beforeEach(async () => {
    stateDir = await mkdtemp(join(tmpdir(), "hy-state-"));
    await mkdir(join(stateDir, "agents", "main", "sessions"), { recursive: true });
    await writeFile(
      join(stateDir, "openclaw.json"),
      JSON.stringify({ agents: { defaults: { workspace: "./workspace" }, list: [{ id: "main" }] } }),
    );
  });
  afterEach(async () => {
    await rm(stateDir, { recursive: true, force: true });
  });

  it("resolves a relative workspace against the state dir + locates sessions", async () => {
    const res = await resolveSourcesFromConfig({ stateDir, agentId: "main" });
    expect(res.workspaceDir).toBe(join(stateDir, "workspace"));
    expect(res.sessionsDirs).toEqual([join(stateDir, "agents", "main", "sessions")]);
  });

  it("falls back to <stateDir>/workspace when config is missing", async () => {
    const empty = await mkdtemp(join(tmpdir(), "hy-empty-"));
    const res = await resolveSourcesFromConfig({ stateDir: empty });
    expect(res.workspaceDir).toBe(join(empty, "workspace"));
    await rm(empty, { recursive: true, force: true });
  });
});
