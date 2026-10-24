import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { createInitialRuntimeState, buildRuntimeStateArtifactsFromSnapshot, saveRuntimeStateSnapshot, loadRuntimeStateSnapshot } from "../state/runtime-state-store.js";
import { retrieveMemorySelection } from "../utils/memory-retrieval.js";
import type { HookRecord, RuntimeStateDelta } from "../models/runtime-state.js";
import { createSettlementToolSchema } from "../agents/settler-tool.js";
import { Value } from "@sinclair/typebox/value";

it("archives explicitly withdrawn premises, excludes them from future retrieval and preserves resolved history", async () => {
  const bookDir = await mkdtemp(join(tmpdir(), "inkos-withdrawn-hooks-"));
  const planned: HookRecord = { hookId: "plan", startChapter: 0, type: "promise", status: "deferred", lastAdvancedChapter: 0, expectedPayoff: "Discover the workshop prohibition", notes: "Original plan" };
  const resolved: HookRecord = { ...planned, hookId: "past", status: "resolved" };
  const active: HookRecord = { ...planned, hookId: "active", status: "open" };
  const delta: RuntimeStateDelta = { chapter: 1, factOps: { upsert: [], expire: [] }, hookOps: { upsert: [{ ...planned, status: "superseded", notes: "Current book rules explicitly withdraw the workshop prohibition" }], mention: [], resolve: [], defer: [] }, newHookCandidates: [] };
  try {
    const candidatesSchema = createSettlementToolSchema(false).properties.newHookCandidates;
    expect(Value.Check(candidatesSchema, [])).toBe(true);
    expect(Value.Check(candidatesSchema, [{ type: "promise", expectedPayoff: "New event", notes: "New plan" }])).toBe(false);
    const before = await createInitialRuntimeState({ bookDir, language: "en", hooks: [planned, resolved, active] });
    const result = buildRuntimeStateArtifactsFromSnapshot({ snapshot: before, delta, language: "en" });
    await saveRuntimeStateSnapshot(bookDir, result.snapshot);
    const saved = await loadRuntimeStateSnapshot(bookDir);
    expect(saved.hooks.hooks.find(hook => hook.hookId === "plan")).toMatchObject({ ...planned, status: "superseded", notes: planned.notes + "\n" + delta.hookOps.upsert[0]!.notes });
    expect(saved.hooks.hooks.find(hook => hook.hookId === "past")).toEqual(resolved);
    const selection = await retrieveMemorySelection({ bookDir, chapterNumber: 2, goal: "workshop prohibition", semanticSelector: async request => request.candidates.map(candidate => candidate.id) });
    expect(new Set([...selection.hooks, ...selection.lookupHooks].map(hook => hook.hookId))).toEqual(new Set(["active"]));
    const reactivated = buildRuntimeStateArtifactsFromSnapshot({ snapshot: saved, delta: { ...delta, chapter: 2, hookOps: { ...delta.hookOps, upsert: [planned] } }, language: "en" });
    expect(reactivated.snapshot.hooks.hooks.find(hook => hook.hookId === "plan")?.status).toBe("superseded");
    expect(() => buildRuntimeStateArtifactsFromSnapshot({ snapshot: saved, delta: { ...delta, chapter: 2, hookOps: { ...delta.hookOps, upsert: [{ ...resolved, status: "superseded", notes: "Replace the plan" }] } }, language: "en" })).toThrowError(expect.objectContaining({ code: "HOOK_RESOLVED_HISTORY" }));
    expect((await loadRuntimeStateSnapshot(bookDir)).hooks).toEqual(saved.hooks);
  } finally {
    await rm(bookDir, { recursive: true, force: true });
  }
});
