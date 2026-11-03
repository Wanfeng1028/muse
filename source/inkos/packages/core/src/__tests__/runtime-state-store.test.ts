import { afterEach, describe, expect, it } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  buildRuntimeStateArtifacts,
  createInitialRuntimeState,
  loadRuntimeStateSnapshot,
  saveRuntimeStateSnapshot,
} from "../state/runtime-state-store.js";

describe("runtime state mini-flow", () => {
  const roots: string[] = [];

  afterEach(async () => {
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it("initializes, applies, atomically projects, and reloads typed story state", async () => {
    const bookDir = await tempBook();
    await createInitialRuntimeState({
      bookDir,
      language: "en",
      hooks: [{
        hookId: "ledger-origin",
        startChapter: 0,
        type: "mystery",
        status: "deferred",
        lastAdvancedChapter: 0,
        expectedPayoff: "Reveal where the ledger came from.",
        notes: "Seeded before chapter one.",
      }],
    });
    const artifacts = await buildRuntimeStateArtifacts({
      bookDir,
      language: "en",
      delta: {
        chapter: 1,
        factOps: { upsert: [{ subject: "Lin", predicate: "location", object: "archive" }], expire: [] },
        hookOps: { upsert: [], mention: ["ledger-origin"], resolve: [], defer: [] },
        newHookCandidates: [],
        chapterSummary: {
          chapter: 1,
          title: "The Archive",
          characters: "Lin",
          events: "Lin enters the archive.",
          stateChanges: "Lin reaches the archive.",
          hookActivity: "ledger-origin mentioned",
          mood: "tense",
          chapterType: "investigation",
        },
      },
    });
    await saveRuntimeStateSnapshot(bookDir, artifacts.snapshot);

    const [loaded, projection] = await Promise.all([
      loadRuntimeStateSnapshot(bookDir),
      readFile(join(bookDir, "story", "current_state.md"), "utf-8"),
    ]);
    expect({
      chapter: loaded.manifest.lastAppliedChapter,
      fact: loaded.currentState.facts[0]?.object,
      hooks: loaded.hooks.hooks.map((hook) => hook.hookId),
      summaries: loaded.chapterSummaries.rows.map((summary) => summary.chapter),
      projectionHasFact: projection.includes("archive"),
    }).toEqual({
      chapter: 1,
      fact: "archive",
      hooks: ["ledger-origin"],
      summaries: [1],
      projectionHasFact: true,
    });
  });

  it("fails loudly when a canonical state artifact is corrupt", async () => {
    const bookDir = await tempBook();
    await createInitialRuntimeState({ bookDir, language: "zh" });
    await writeFile(join(bookDir, "story", "state", "hooks.json"), "{broken");
    await expect(loadRuntimeStateSnapshot(bookDir)).rejects.toThrow();
  });

  async function tempBook(): Promise<string> {
    const root = await mkdtemp(join(tmpdir(), "inkos-runtime-state-flow-"));
    roots.push(root);
    return root;
  }
});
