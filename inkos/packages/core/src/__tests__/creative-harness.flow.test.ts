import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { Type } from "@sinclair/typebox";
import { afterEach, describe, expect, it } from "vitest";
import {
  ActionConfirmationRequiredError,
  ActionResultSchema,
  CapabilityRegistry,
  CreativeEpisodeStore,
  CreativeHarnessRuntime,
  createBuiltInWorkProfileRegistry,
  createInitialWorkManifestWrite,
  createReplaceWorkArtifactTool,
  createTranslationCreateTool,
  createTranslationExportTool,
  createTranslationRunTool,
  defineCapabilityAction,
  executeExplicitCapabilityTool,
  loadWorkManifest,
  listWorkManifests,
} from "../harness/index.js";
import { commitAtomicFileSet } from "../utils/atomic-file-set.js";
import { loadTranslationManifest } from "../translation/run-store.js";
import { createSkillRegistry } from "../skills/index.js";
import { createUseSkillTool, hydrateActivatedSkillGuidance, type ActivatedSkillGuidance } from "../agent/skill-tool.js";
import { PipelineRunner } from "../pipeline/runner.js";
import { createReadTool } from "../agent/agent-tools.js";
import { createBookFoundationTool } from "../harness/tools/longform-production.js";
import { syncWorkSourceArtifacts } from "../harness/source-sync.js";

describe("creative harness mini-flows", () => {
  const roots: string[] = [];

  afterEach(async () => {
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it("creates, runs, exports, and traces one translation Work", async () => {
    const root = await tempProject("translation");
    await writeFile(join(root, "source.md"), "# Arrival\n\nThe rain began.\n");

    const created = await executeExplicitCapabilityTool({
      projectRoot: root,
      binding: { capabilityId: "translation", actionId: "translation_create", profileId: "translation", risk: "recoverable-write" },
      tool: createTranslationCreateTool(root),
      parameters: {
        filePath: "source.md",
        sourceLanguage: "English",
        targetLanguage: "Chinese (Simplified)",
        title: "Rain Translation",
      },
      episodeId: "episode-create",
    });
    const workId = (created.data as { manifest: { id: string } }).manifest.id;
    const candidates = await syncWorkSourceArtifacts({projectRoot:root,workId,accept:false,writes:[
      {relativePath:`works/${workId}/source/notes.md`,content:"An unrelated candidate awaiting its own decision."},
    ]});
    const unrelated=candidates.artifacts.find(a=>a.revisions.some(r=>r.path==='source/notes.md'))!;
    const pipeline = {
      runWithAgentContext: async (_context: unknown, task: () => Promise<unknown>) => task(),
      createAgentContext: (role: string) => ({ client: {}, model: role }),
    };

    const run = await executeExplicitCapabilityTool({
      projectRoot: root,
      binding: { capabilityId: "translation", actionId: "translation_run", profileId: "translation", risk: "recoverable-write" },
      tool: createTranslationRunTool(pipeline as never, root, workId, {
        createModel: ({model}) => ({
          translateSegments: async (request) => {
            expect(model).toBe("translation");
            return { segments: request.segments.map((segment) => ({ index: segment.index, target: `译：${segment.source}` })), glossary: [] };
          },
          reviewChapter: async () => {
            expect(model).toBe("auditor");
            return { summary: "Reviewed", observations: [{code:"MEANING_MISMATCH",category:"quality",assessment:"issue",summary:"A source fact changed in translation.",evidence:["segment:1"]}] };
          },
        }),
      }),
      workId,
      parameters: { batchSize: 8 },
      episodeId: "episode-run",
    });
    const exported = await executeExplicitCapabilityTool({
      projectRoot: root,
      binding: { capabilityId: "translation", actionId: "translation_export", profileId: "translation", risk: "recoverable-write" },
      tool: createTranslationExportTool(root, workId),
      workId,
      parameters: { format: "md" },
      episodeId: "episode-export",
    });

    const manifest = await loadWorkManifest(root, workId);
    expect(manifest.artifacts.find(a=>a.id===unrelated.id)?.currentRevisionId).toBeNull();
    const reviewedArtifact = manifest.artifacts.find(artifact => artifact.revisions.some(revision => revision.id === artifact.currentRevisionId && revision.path === "source/translated/chapter-0001.json"))!;
    expect(run.observations).toEqual(expect.arrayContaining([expect.objectContaining({code:"MEANING_MISMATCH",assessment:"issue",scope:"chapter:1",target:{workId,artifactId:reviewedArtifact.id,revisionId:reviewedArtifact.currentRevisionId}})]));
    const outputPath = (exported.data as { outputPath: string }).outputPath;
    const episodes = new CreativeEpisodeStore(join(root, ".inkos", "harness.sqlite"));
    expect({
      create: created.status,
      run: run.status,
      export: exported.status,
      profile: manifest.profileId,
      episodes: episodes.listEpisodes({ workId }).map((episode) => episode.status),
    }).toEqual({
      create: "success",
      run: "success",
      export: "success",
      profile: "translation",
      episodes: ["completed", "completed", "completed"],
    });
    expect(manifest.artifacts.length).toBeGreaterThan(0);
    expect((await readFile(outputPath)).byteLength).toBeGreaterThan(0);
    expect(episodes.requireEpisode("episode-create").workId).toBe(workId);
    episodes.close();
  });

  it("enforces action authority, versions an accepted artifact, and recovers interruption", async () => {
    const root = await tempProject("mutation");
    const initial = createInitialWorkManifestWrite({
      workId: "script-work",
      title: "Script Work",
      profileId: "script",
      language: "en",
      writes: [{ relativePath: "works/script-work/source/script.md", content: "# Draft\n" }],
    });
    await commitAtomicFileSet({
      rootDir: root,
      writes: [
        { relativePath: "works/script-work/source/script.md", content: "# Draft\n" },
        initial.write,
      ],
    });
    const before = await loadWorkManifest(root, "script-work");
    const currentRevisionId = before.artifacts[0]!.currentRevisionId!;
    await executeExplicitCapabilityTool({
      projectRoot: root,
      binding: { capabilityId: "workspace", actionId: "replace_work_artifact", profileId: "script", risk: "recoverable-write" },
      tool: createReplaceWorkArtifactTool(root, "script-work"),
      workId: "script-work",
      parameters: {
        path: "source/script.md",
        content: "# Revised\n",
        expectedRevisionId: currentRevisionId,
      },
      episodeId: "episode-edit",
    });

    const capabilities = new CapabilityRegistry();
    capabilities.register({
      id: "script",
      title: "Script",
      description: "",
      actions: [defineCapabilityAction({
        id: "commit",
        title: "Commit",
        description: "Commit script state.",
        risk: "recoverable-write",
        requiresConfirmation: true,
        parameters: Type.Object({}),
        async execute() {
          return ActionResultSchema.parse({
            status: "success",
            summary: "committed",
            artifacts: [],
            observations: [],
          });
        },
      })],
    });
    const episodes = new CreativeEpisodeStore(join(root, ".inkos", "harness.sqlite"));
    try {
    const runtime = new CreativeHarnessRuntime(root, capabilities, createBuiltInWorkProfileRegistry(), episodes);
    const handle = runtime.startEpisode({
      episodeId: "episode-authority",
      profileId: "script",
      work: await loadWorkManifest(root, "script-work"),
    });
    await expect(runtime.executeAction({
      handle,
      capabilityId: "script",
      actionId: "commit",
      parameters: {},
      source: "agent",
    })).rejects.toBeInstanceOf(ActionConfirmationRequiredError);
    await runtime.executeAction({
      handle,
      capabilityId: "script",
      actionId: "commit",
      parameters: {},
      source: "agent",
      confirmed: true,
    });
    runtime.finishEpisode(handle, "completed");
    episodes.create({
      version: 2,
      id: "episode-interrupted",
      workId: "script-work",
      profileId: "script",
      status: "running",
      startedAt: "2026-08-26T00:00:00.000Z",
      completedAt: null,
    });
    expect(episodes.recoverInterruptedEpisodes("2026-08-26T00:01:00.000Z")).toBe(0);
    const legacyDb = new DatabaseSync(join(root, ".inkos", "harness.sqlite"));
    legacyDb.exec("UPDATE creative_episodes SET owner_pid = NULL WHERE status = 'running'");
    legacyDb.close();
    expect(episodes.recoverInterruptedEpisodes("2026-08-26T00:01:00.000Z")).toBe(1);

    const after = await loadWorkManifest(root, "script-work");
    const artifact = after.artifacts[0]!;
    const previousRevision = artifact.revisions.find((revision) => revision.id === currentRevisionId)!;
    const currentRevision = artifact.revisions.find((revision) => revision.id === artifact.currentRevisionId)!;
    expect({
      revisions: artifact.revisions.length,
      currentRevisionChanged: artifact.currentRevisionId !== currentRevisionId,
      previousSnapshot: await readFile(join(root, "works", "script-work", previousRevision.snapshotPath!), "utf-8"),
      currentSnapshot: await readFile(join(root, "works", "script-work", currentRevision.snapshotPath!), "utf-8"),
      authorityEpisode: episodes.requireEpisode("episode-authority").status,
      interruptedEpisode: episodes.requireEpisode("episode-interrupted").status,
    }).toEqual({
      revisions: 2,
      currentRevisionChanged: true,
      previousSnapshot: "# Draft\n",
      currentSnapshot: "# Revised\n",
      authorityEpisode: "completed",
      interruptedEpisode: "failed",
    });
    } finally { episodes.close(); }
  });

  it("lists canonical Works without treating runtime-only directories as Works", async () => {
    const root = await tempProject("work-list");
    const initial = createInitialWorkManifestWrite({
      workId: "script-work",
      title: "Script Work",
      profileId: "script",
      language: "en",
      writes: [{ relativePath: "works/script-work/source/script.md", content: "# Draft\n" }],
    });
    await commitAtomicFileSet({
      rootDir: root,
      writes: [
        { relativePath: "works/script-work/source/script.md", content: "# Draft\n" },
        initial.write,
      ],
    });
    await mkdir(join(root, "works", "play-session", "source", "runs", "main"), { recursive: true });

    expect((await listWorkManifests(root)).map((work) => work.id)).toEqual(["script-work"]);

    await expect(createReadTool(root, { scope: "project" }).execute("missing-read", {
      path: "works/script-work/source/missing.md",
    })).rejects.toMatchObject({
      code: "WORK_FILE_NOT_FOUND",
      requestedPath: "works/script-work/source/missing.md",
    });
  });

  it("retrieves only task-relevant Skill references for the main agent and production worker", async () => {
    const root = await tempProject("skill-retrieval");
    const baseDir = join(root, "skill");
    await mkdir(join(baseDir, "references"), { recursive: true });
    await writeFile(join(baseDir, "references", "dialogue.md"), "# Dialogue\n\nDistinct voice and conversational pressure.\n");
    await writeFile(join(baseDir, "references", "cover.md"), "# Cover\n\nPortrait composition and title treatment.\n");
    const skill = {
      id: "story-craft",
      name: "Story craft",
      description: "Story craft methods",
      body: "Use relevant craft references.",
      source: "project" as const,
      baseDir,
    };
    let activated: ActivatedSkillGuidance | undefined;
    const tool = createUseSkillTool({
      registry: createSkillRegistry({ skills: [skill] }),
      onActivate: (value) => { activated = value; },
    });
    await tool.execute("skill-call", { skillId: skill.id, query: "dialogue voice" });
    const hydrated = await hydrateActivatedSkillGuidance([{ skill, resources: [] }], "dialogue voice");

    expect({
      mainAgent: activated?.resources.map((resource) => resource.path),
      worker: hydrated?.[0]?.resources.map((resource) => resource.path),
    }).toEqual({
      mainAgent: ["references/dialogue.md"],
      worker: ["references/dialogue.md"],
    });
  });

  it("preserves a draft Work when foundation generation cannot start", async () => {
    const root = await tempProject("draft-recovery");
    const pipeline = new PipelineRunner({
      client: {} as never,
      model: "unavailable",
      projectRoot: root,
    });
    const now = new Date().toISOString();
    await expect(executeExplicitCapabilityTool({projectRoot:root,tool:createBookFoundationTool(pipeline),
      binding:{capabilityId:'longform',actionId:'create_book',profileId:'longform-novel',risk:'recoverable-write'},parameters:{
      bookId: "recoverable-book",
      instruction: "Create fixture foundation",
      title: "Recoverable Book",
      genre: "mystery",
      platform: "other",
      status: "outlining",
      targetChapters: 12,
      chapterWordCount: 800,
      language: "en",
      createdAt: now,
      updatedAt: now,
    }})).rejects.toThrow();

    const manifest = await loadWorkManifest(root, "recoverable-book");
    const episodes = new CreativeEpisodeStore(join(root,'.inkos/harness.sqlite'));
    try {
      expect(episodes.listEpisodes({workId:'recoverable-book'})[0]?.status).toBe('failed');
      episodes.create({version:2,id:'legacy-attempt',workId:null,profileId:'longform-novel',status:'running',startedAt:now,completedAt:null});
      episodes.append({episodeId:'legacy-attempt',workId:null,type:'action-started',payload:{parameters:{projectId:'recoverable-book'}}});
      episodes.finish('legacy-attempt','failed');
      expect(episodes.listEpisodes({workId:'recoverable-book'}).map(episode=>episode.id)).toContain('legacy-attempt');
      expect(episodes.listEpisodes({workId:'unrelated-work'})).toEqual([]);
    }
    finally { episodes.close(); }
    expect({
      status: manifest.status,
      sourceConfig: JSON.parse(await readFile(join(root, "works", "recoverable-book", "source", "book.json"), "utf-8")).id,
    }).toEqual({
      status: "draft",
      sourceConfig: "recoverable-book",
    });
  });

  async function tempProject(name: string): Promise<string> {
    const root = await mkdtemp(join(tmpdir(), `inkos-${name}-flow-`));
    roots.push(root);
    await writeFile(join(root, "inkos.json"), JSON.stringify({ language: "en" }));
    return root;
  }
});
