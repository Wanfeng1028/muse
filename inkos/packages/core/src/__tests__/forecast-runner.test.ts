import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AgentContext } from "../agents/base.js";
import { NarrativeForecastAgent } from "../forecast/agent.js";
import {
  createNarrativeForecast,
  getNarrativeForecast,
  selectNarrativeBranch,
} from "../forecast/runner.js";
import {
  makeModelBranch,
  snapshotCanonicalFiles,
  writeForecastFixtureBook,
} from "./helpers/forecast-fixture.js";
import { buildRuntimeStateArtifacts, saveRuntimeStateSnapshot } from "../state/runtime-state-store.js";

describe("narrative forecast mini-flow", () => {
  const roots: string[] = [];

  afterEach(async () => {
    vi.restoreAllMocks();
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it("creates, reads, selects, and traces a non-canonical branch without mutating canon", async () => {
    const { root, bookDir } = await fixture();
    stubForecastAgent();
    const before = await snapshotCanonicalFiles(bookDir);

    const created = await createNarrativeForecast({
      projectRoot: root,
      bookId: "demo-book",
      divergence: "主角接受还是拒绝合作",
      branchCount: 2,
      horizon: 5,
      runtime: runtime(root),
      determinism: { now: () => new Date("2026-07-15T00:00:00.000Z") },
    });
    const loaded = await getNarrativeForecast({
      projectRoot: root,
      bookId: "demo-book",
      forecastId: created.forecast.forecastId,
    });
    const selected = await selectNarrativeBranch({
      projectRoot: root,
      bookId: "demo-book",
      forecastId: created.forecast.forecastId,
      branchId: "branch-2",
    });

    expect({
      ids: loaded.forecast.branches.map((branch) => branch.branchId),
      stale: loaded.stale,
      selected: selected.branch.branchId,
      planMentionsSelection: (await readFile(selected.planPath, "utf-8")).includes("拒绝提议"),
      canonUnchanged: await snapshotCanonicalFiles(bookDir),
    }).toEqual({
      ids: ["branch-1", "branch-2"],
      stale: false,
      selected: "branch-2",
      planMentionsSelection: true,
      canonUnchanged: before,
    });
  });

  it("marks an existing forecast stale after canonical state advances", async () => {
    const { root, bookDir } = await fixture();
    stubForecastAgent();
    const created = await createNarrativeForecast({
      projectRoot: root,
      bookId: "demo-book",
      divergence: "主角接受还是拒绝合作",
      branchCount: 2,
      runtime: runtime(root),
    });
    await writeFile(join(bookDir, "chapters", "0003_后果.md"), "第三章正文", "utf-8");
    const index = JSON.parse(await readFile(join(bookDir, "chapters", "index.json"), "utf-8"));
    index.push({ ...index[1], number: 3, title: "后果" });
    await writeFile(join(bookDir, "chapters", "index.json"), JSON.stringify(index), "utf-8");
    const state = await buildRuntimeStateArtifacts({
      bookDir,
      language: "zh",
      delta: {
        chapter: 3,
        factOps: { upsert: [{ subject: "主角", predicate: "选择", object: "拒绝合作" }], expire: [] },
        hookOps: { upsert: [], mention: [], resolve: [], defer: [] },
        newHookCandidates: [],
      },
    });
    await saveRuntimeStateSnapshot(bookDir, state.snapshot);

    const loaded = await getNarrativeForecast({
      projectRoot: root,
      bookId: "demo-book",
      forecastId: created.forecast.forecastId,
    });
    expect({ stale: loaded.stale, status: loaded.forecast.status }).toEqual({ stale: true, status: "stale" });
  });

  it("does not write a selection artifact for an unknown branch", async () => {
    const { root } = await fixture();
    stubForecastAgent();
    const created = await createNarrativeForecast({
      projectRoot: root,
      bookId: "demo-book",
      divergence: "主角接受还是拒绝合作",
      branchCount: 2,
      runtime: runtime(root),
    });
    await expect(selectNarrativeBranch({
      projectRoot: root,
      bookId: "demo-book",
      forecastId: created.forecast.forecastId,
      branchId: "branch-9",
    })).rejects.toThrow("branch-9");
  });

  function stubForecastAgent(): void {
    vi.spyOn(NarrativeForecastAgent.prototype, "generateBranches").mockResolvedValue({
      branches: [
        makeModelBranch({ title: "接受提议" }),
        makeModelBranch({ title: "拒绝提议", premise: "主角当场拒绝并公开证据。" }),
      ],
    });
  }

  function runtime(projectRoot: string): AgentContext {
    return { client: { provider: "openai" } as never, model: "fake", projectRoot };
  }

  async function fixture(): Promise<{ root: string; bookDir: string }> {
    const root = await mkdtemp(join(tmpdir(), "inkos-forecast-flow-"));
    roots.push(root);
    const bookDir = join(root, "works", "demo-book", "source");
    await writeForecastFixtureBook(bookDir);
    return { root, bookDir };
  }
});
