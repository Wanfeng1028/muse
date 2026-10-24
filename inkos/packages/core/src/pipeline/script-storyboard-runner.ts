import { access, mkdir, readFile } from "node:fs/promises";
import { basename, join } from "node:path";
import type { AgentContext } from "../agents/base.js";
import { materializeStoryGraph } from "../interactive-film/generate.js";
import {readFilmRequirements,checkFilmRequirements,type FilmRequirements}from'../interactive-film/delivery-requirements.js';
import { commitAtomicFileSet } from "../utils/atomic-file-set.js";
import {
  InteractiveFilmCreationAgent,
  ScriptCreationAgent,
  StoryboardCreationAgent,
  renderInteractiveFilmSpec,
  renderScriptSpec,
  renderStoryboardSpec,
  type InteractiveFilmCreationInput,
  type ScriptCreationInput,
  type ScriptTargetFormat,
  type StoryboardCreationInput,
} from "../agents/script-storyboard.js";
import { safeChildPath } from "../utils/path-safety.js";
import { toPosixPath } from "../utils/posix-path.js";
import { syncWorkSourceArtifacts } from "../harness/source-sync.js";
import { createWorkManifest, loadWorkManifest, saveWorkManifest } from "../harness/work-store.js";
import { readArtifactRevision } from "../harness/artifact-reader.js";
import { createBuiltInWorkProfileRegistry } from '../harness/builtin-profiles.js';
import { currentExecutionAuthorRequest } from '../harness/execution-evidence.js';

export interface ScriptCreationRunOptions {
  readonly projectRoot: string;
  readonly runtime: AgentContext;
  readonly title: string;
  readonly instruction: string;
  readonly sourceKind?: string;
  readonly targetFormat?: ScriptTargetFormat;
  readonly sourceText?: string;
  readonly sourcePath?: string;
  readonly requirements?: string;
  readonly episodeCount?: number;
  readonly episodeDuration?: string;
  readonly language?: "zh" | "en";
  readonly projectId?: string;
  readonly onProgress?: (message: string) => void;
}

export interface StoryboardCreationRunOptions {
  readonly projectRoot: string;
  readonly runtime: AgentContext;
  readonly title: string;
  readonly instruction: string;
  readonly sourceKind?: string;
  readonly sourceText?: string;
  readonly sourcePath?: string;
  readonly requirements?: string;
  readonly visualStyle?: string;
  readonly aspectRatio?: string;
  readonly granularity?: string;
  readonly maxShots?: number;
  readonly language?: "zh" | "en";
  readonly projectId?: string;
  readonly onProgress?: (message: string) => void;
}

export interface InteractiveFilmCreationRunOptions {
  readonly deliveryRequirements?: FilmRequirements;
  readonly projectRoot: string;
  readonly runtime: AgentContext;
  readonly title: string;
  readonly instruction: string;
  readonly sourceKind?: string;
  readonly sourceText?: string;
  readonly sourcePath?: string;
  readonly requirements?: string;
  readonly targetAudience?: string;
  readonly episodeCount?: number;
  readonly episodeDuration?: string;
  readonly budget?: string;
  readonly referenceMode?: string;
  readonly language?: "zh" | "en";
  readonly projectId?: string;
  readonly onProgress?: (message: string) => void;
}

export interface ScriptCreationRunResult {
  readonly projectId: string;
  readonly baseDir: string;
  readonly specPath: string;
  readonly scriptPath: string;
}

export interface InteractiveFilmCreationRunResult {
  readonly delivery:ReturnType<typeof checkFilmRequirements>;
  readonly observations:ReadonlyArray<{code:string;category:'quality';assessment:'issue'|'unavailable';summary:string;evidence:string[]}>;
  readonly projectId: string;
  readonly baseDir: string;
  readonly storyGraphPath: string;
  readonly specPath: string;
  readonly storyTreePath: string;
  readonly flagsPath: string;
  readonly scriptPath: string;
  readonly storyboardPath: string;
  readonly imagePromptsPath: string;
  readonly assetsManifestPath: string;
  readonly assetsDir: string;
}

export interface StoryboardCreationRunResult {
  readonly projectId: string;
  readonly baseDir: string;
  readonly specPath: string;
  readonly storyboardPath: string;
  readonly imagePromptsPath: string;
  readonly assetsManifestPath: string;
  readonly assetsDir: string;
}

export interface StoryboardImageAssetVariant {
  readonly id: string;
  readonly path: string;
  readonly status: "pending" | "generated" | "selected" | "failed";
  readonly model?: string;
  readonly provider?: string;
  readonly createdAt?: string;
  readonly error?: string;
}

export interface StoryboardImageAsset {
  readonly shotId: string;
  readonly prompt: string;
  readonly sourceRefs: readonly string[];
  readonly variants: readonly StoryboardImageAssetVariant[];
  readonly selectedPath?: string;
  readonly status: "prompt_ready" | "generated" | "selected" | "failed";
}

export interface StoryboardAssetsManifest {
  readonly version: 1;
  readonly kind: "storyboard_assets";
  readonly title: string;
  readonly projectId: string;
  readonly baseDir: string;
  readonly storyboardPath: string;
  readonly imagePromptsPath: string;
  readonly assetsDir: string;
  readonly sourceDir: string;
  readonly generatedDir: string;
  readonly selectedDir: string;
  readonly createdAt: string;
  readonly assets: readonly StoryboardImageAsset[];
}

export async function runScriptCreation(
  options: ScriptCreationRunOptions,
): Promise<ScriptCreationRunResult> {
  const projectId = safeSegment(options.projectId ?? slugify(options.title));
  const baseDir = relPath("works", projectId, "source");
  const sourceText = await resolveSourceText(options.projectRoot, options.sourceText, options.sourcePath, projectId);
  const input: ScriptCreationInput = {
    authorRequest: currentExecutionAuthorRequest(),
    title: options.title,
    sourceKind: options.sourceKind,
    targetFormat: options.targetFormat,
    sourceText,
    requirements: mergeRequirements(options.instruction, options.requirements, options.language),
    episodeCount: options.episodeCount,
    episodeDuration: options.episodeDuration,
    language: options.language,
  };

  options.onProgress?.("Writing script creation spec...");
  const spec = renderScriptSpec(input);
  await ensureUnwrittenWork(options.projectRoot, projectId, options.title, "script", options.language ?? "zh");
  await persistProductionInputs(options.projectRoot, projectId, [
    textArtifact(join(baseDir, "script-spec.md"), spec),
  ], sourceText);

  options.onProgress?.("Writing script draft...");
  const agent = new ScriptCreationAgent(options.runtime);
  const script = await agent.writeScript(input);
  const artifacts = [
    textArtifact(join(baseDir, "script-spec.md"), spec),
    textArtifact(join(baseDir, "script.md"), script),
  ];
  assertNonEmptyArtifacts(artifacts);
  await syncWorkSourceArtifacts({ projectRoot: options.projectRoot, workId: projectId, accept: true, writes: artifacts });

  return {
    projectId,
    baseDir,
    specPath: relPath(baseDir, "script-spec.md"),
    scriptPath: relPath(baseDir, "script.md"),
  };
}

export async function runInteractiveFilmCreation(
  options: InteractiveFilmCreationRunOptions,
): Promise<InteractiveFilmCreationRunResult> {
  const projectId = safeSegment(options.projectId ?? slugify(options.title));
  const baseDir = relPath("works", projectId, "source");
  const deliveryRequirements=options.deliveryRequirements??await readFilmRequirements(options.projectRoot,projectId);
  const sourceText = await resolveSourceText(options.projectRoot, options.sourceText, options.sourcePath, projectId);
  const input: InteractiveFilmCreationInput = {
    authorRequest: currentExecutionAuthorRequest(),
    title: options.title,
    sourceKind: options.sourceKind,
    sourceText,
    requirements: mergeRequirements(options.instruction, [options.requirements,deliveryRequirements?JSON.stringify(deliveryRequirements):undefined].filter(Boolean).join('\n'), options.language),
    targetAudience: options.targetAudience,
    episodeCount: options.episodeCount,
    episodeDuration: options.episodeDuration,
    budget: options.budget,
    referenceMode: options.referenceMode,
    language: options.language,
  };

  options.onProgress?.("Writing interactive-film creation spec...");
  const spec = renderInteractiveFilmSpec(input);
  await ensureUnwrittenWork(options.projectRoot, projectId, options.title, "interactive-film", options.language ?? "zh");
  await persistProductionInputs(options.projectRoot, projectId, [
    textArtifact(join(baseDir, "interactive-spec.md"), spec),
    ...(deliveryRequirements?[textArtifact(join(baseDir,'delivery-requirements.json'),JSON.stringify(deliveryRequirements,null,2))]:[]),
  ], sourceText);

  options.onProgress?.("Writing story tree, flags, script, storyboard, and image prompts...");
  const agent = new InteractiveFilmCreationAgent(options.runtime);
  const compiled = await agent.createInteractiveFilmPackage(input);
  const { storyTree, flags, script, storyboard } = compiled;
  const imagePromptItems = compiled.imagePrompts;
  const imagePrompts = renderImagePrompts(imagePromptItems);
  const storyGraphPath = relPath(baseDir, "story-graph.json");
  await persistCandidateArtifacts(options.projectRoot, projectId, [
    textArtifact(join(baseDir, "story-tree.md"), storyTree),
    textArtifact(join(baseDir, "flags.md"), flags),
    textArtifact(join(baseDir, "script.md"), script),
    textArtifact(join(baseDir, "storyboard.md"), storyboard),
    textArtifact(join(baseDir, "image-prompts.md"), imagePrompts),
  ]);

  await ensureProjectDir(options.projectRoot, join(baseDir, "assets", "source"));
  await ensureProjectDir(options.projectRoot, join(baseDir, "assets", "generated"));
  await ensureProjectDir(options.projectRoot, join(baseDir, "assets", "selected"));
  const assetsManifest = createStoryboardAssetsManifest({
    title: options.title,
    projectId,
    baseDir,
    storyboardPath: join(baseDir, "storyboard.md"),
    imagePromptsPath: join(baseDir, "image-prompts.md"),
    imagePrompts: imagePromptItems,
    createdAt: new Date().toISOString(),
  });

  options.onProgress?.("Validating interactive-film story graph...");
  const graph = materializeStoryGraph({
    projectId,
    title: options.title,
    content: compiled.storyGraph,
  });
  const delivery=checkFilmRequirements(graph,deliveryRequirements);
  const artifacts = [
    textArtifact(join(baseDir, "interactive-spec.md"), spec),
    textArtifact(join(baseDir, "story-tree.md"), storyTree),
    textArtifact(join(baseDir, "flags.md"), flags),
    textArtifact(join(baseDir, "script.md"), script),
    textArtifact(join(baseDir, "storyboard.md"), storyboard),
    textArtifact(join(baseDir, "image-prompts.md"), imagePrompts),
    textArtifact(join(baseDir, "assets.json"), JSON.stringify(assetsManifest, null, 2)),
    textArtifact(storyGraphPath, JSON.stringify(graph, null, 2)),
    textArtifact(join(baseDir,'delivery-report.json'),JSON.stringify(delivery,null,2)),
  ];
  assertNonEmptyArtifacts(artifacts);
  await syncWorkSourceArtifacts({ projectRoot: options.projectRoot, workId: projectId, accept: true, writes: artifacts });

  return {
    projectId,
    baseDir,
    storyGraphPath,
    delivery,
    observations:delivery.issues.map(issue=>({code:issue.code,category:'quality',assessment:delivery.status==='unverified'?'unavailable':'issue',summary:JSON.stringify(issue),evidence:[relPath(baseDir,'delivery-report.json')]})),
    specPath: relPath(baseDir, "interactive-spec.md"),
    storyTreePath: relPath(baseDir, "story-tree.md"),
    flagsPath: relPath(baseDir, "flags.md"),
    scriptPath: relPath(baseDir, "script.md"),
    storyboardPath: relPath(baseDir, "storyboard.md"),
    imagePromptsPath: relPath(baseDir, "image-prompts.md"),
    assetsManifestPath: relPath(baseDir, "assets.json"),
    assetsDir: relPath(baseDir, "assets"),
  };
}

export async function runStoryboardCreation(
  options: StoryboardCreationRunOptions,
): Promise<StoryboardCreationRunResult> {
  const projectId = safeSegment(options.projectId ?? slugify(options.title));
  const baseDir = relPath("works", projectId, "source");
  const sourceText = await resolveSourceText(options.projectRoot, options.sourceText, options.sourcePath, projectId);
  const input: StoryboardCreationInput = {
    authorRequest: currentExecutionAuthorRequest(),
    title: options.title,
    sourceKind: options.sourceKind,
    sourceText,
    requirements: mergeRequirements(options.instruction, options.requirements, options.language),
    visualStyle: options.visualStyle,
    aspectRatio: options.aspectRatio,
    granularity: options.granularity,
    maxShots: options.maxShots,
    language: options.language,
  };

  options.onProgress?.("Writing storyboard creation spec...");
  const spec = renderStoryboardSpec(input);
  await ensureUnwrittenWork(options.projectRoot, projectId, options.title, "storyboard", options.language ?? "zh");
  await persistProductionInputs(options.projectRoot, projectId, [
    textArtifact(join(baseDir, "storyboard-spec.md"), spec),
  ], sourceText);

  options.onProgress?.("Writing storyboard and image prompts...");
  const agent = new StoryboardCreationAgent(options.runtime);
  const storyboardPackage = await agent.writeStoryboard(input);
  const storyboard = storyboardPackage.storyboard;
  await persistCandidateArtifacts(options.projectRoot, projectId, [
    textArtifact(join(baseDir, "storyboard.md"), storyboard),
  ]);
  const imagePromptItems = storyboardPackage.imagePrompts;
  const imagePrompts = renderImagePrompts(imagePromptItems);
  await ensureProjectDir(options.projectRoot, join(baseDir, "assets", "source"));
  await ensureProjectDir(options.projectRoot, join(baseDir, "assets", "generated"));
  await ensureProjectDir(options.projectRoot, join(baseDir, "assets", "selected"));
  const assetsManifest = createStoryboardAssetsManifest({
    title: options.title,
    projectId,
    baseDir,
    storyboardPath: join(baseDir, "storyboard.md"),
    imagePromptsPath: join(baseDir, "image-prompts.md"),
    imagePrompts: imagePromptItems,
    createdAt: new Date().toISOString(),
  });
  const artifacts = [
    textArtifact(join(baseDir, "storyboard-spec.md"), spec),
    textArtifact(join(baseDir, "storyboard.md"), storyboard),
    textArtifact(join(baseDir, "image-prompts.md"), imagePrompts),
    textArtifact(join(baseDir, "assets.json"), JSON.stringify(assetsManifest, null, 2)),
  ];
  assertNonEmptyArtifacts(artifacts);
  await syncWorkSourceArtifacts({ projectRoot: options.projectRoot, workId: projectId, accept: true, writes: artifacts });

  return {
    projectId,
    baseDir,
    specPath: relPath(baseDir, "storyboard-spec.md"),
    storyboardPath: relPath(baseDir, "storyboard.md"),
    imagePromptsPath: relPath(baseDir, "image-prompts.md"),
    assetsManifestPath: relPath(baseDir, "assets.json"),
    assetsDir: relPath(baseDir, "assets"),
  };
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function createStoryboardAssetsManifest(args: {
  readonly title: string;
  readonly projectId: string;
  readonly baseDir: string;
  readonly storyboardPath: string;
  readonly imagePromptsPath: string;
  readonly imagePrompts: ReadonlyArray<string>;
  readonly createdAt: string;
}): StoryboardAssetsManifest {
  const assetsDir = relPath(args.baseDir, "assets");
  return {
    version: 1,
    kind: "storyboard_assets",
    title: args.title,
    projectId: args.projectId,
    baseDir: toPosixPath(args.baseDir),
    storyboardPath: toPosixPath(args.storyboardPath),
    imagePromptsPath: toPosixPath(args.imagePromptsPath),
    assetsDir,
    sourceDir: relPath(assetsDir, "source"),
    generatedDir: relPath(assetsDir, "generated"),
    selectedDir: relPath(assetsDir, "selected"),
    createdAt: args.createdAt,
    assets: args.imagePrompts.map((prompt, index) => {
      const shotId = `shot-${String(index + 1).padStart(3, "0")}`;
      return {
        shotId,
        prompt,
        sourceRefs: [],
        variants: [],
        status: "prompt_ready",
      };
    }),
  };
}

function renderImagePrompts(prompts: ReadonlyArray<string>): string {
  return prompts.map((prompt, index) => `${index + 1}. ${prompt}`).join("\n");
}

async function resolveSourceText(
  projectRoot: string,
  sourceText: string | undefined,
  sourcePath: string | undefined,
  workId: string,
): Promise<string | undefined> {
  const direct = sourceText?.trim();
  if (direct) return direct;
  const path = sourcePath?.trim();
  if (path) return readFile(safeChildPath(projectRoot, path), "utf-8");
  try {
    const work = await loadWorkManifest(projectRoot, workId);
    const source = work.artifacts.find(artifact => artifact.revisions.some(revision => revision.id === artifact.currentRevisionId && revision.path === "source/source-material.md"));
    if (!source) return undefined;
    return (await readArtifactRevision({ projectRoot, workId, artifactId: source.id })).bytes.toString("utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

function textArtifact(relativePath: string, content: string): {
  readonly relativePath: string;
  readonly content: string;
} {
  return {
    relativePath,
    content: content.endsWith("\n") ? content : `${content}\n`,
  };
}

function assertNonEmptyArtifacts(
  artifacts: ReadonlyArray<{ readonly relativePath: string; readonly content: string }>,
): void {
  for (const artifact of artifacts) {
    if (!artifact.content.trim()) {
      throw new Error(`Production artifact is empty: ${artifact.relativePath}`);
    }
  }
}

/** Work lifecycle is independent of whether its first production has completed. */
async function ensureUnwrittenWork(
  projectRoot: string,
  projectId: string,
  title: string,
  profileId: "script" | "storyboard" | "interactive-film",
  language: "zh" | "en",
): Promise<void> {
  try {
    const existing = await loadWorkManifest(projectRoot, projectId);
    const recovery = { action: "workspace__inspect_work", parameters: { workId: projectId },
      reason: "Inspect the existing Work and revise its current artifacts; do not recreate it under another ID." };
    if (!createBuiltInWorkProfileRegistry(projectRoot).require(existing.profileId).capabilityIds.includes(profileId)) {
      throw Object.assign(new Error(`Work "${projectId}" does not declare the ${profileId} capability.`), { code: "WORK_PROFILE_MISMATCH", requiredCapabilityId:profileId, recovery });
    }
    if (existing.status === "archived") {
      throw Object.assign(new Error(`Work "${projectId}" is archived.`), { code: "WORK_ARCHIVED", recovery });
    }
    const productionPaths = profileId === "script" ? ["source/script.md"]
      : profileId === "storyboard" ? ["source/storyboard.md"]
      : ["source/story-graph.json", "source/story-tree.md", "source/script.md", "source/storyboard.md"];
    for (const path of productionPaths) {
      const artifact = existing.artifacts.find(item => item.revisions.some(revision => revision.path === path));
      if (artifact?.currentRevisionId) {
        throw Object.assign(new Error(`Work "${projectId}" already has a current production artifact: ${path}.`), { code: "WORK_ALREADY_PRODUCED", recovery });
      }
      // Registered candidates can be retried; never overwrite unregistered source bytes.
      if (!artifact) {
        let exists = false;
        try { await access(join(projectRoot, "works", projectId, path)); exists = true; }
        catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
        if (exists) throw Object.assign(new Error(`Production source is not registered: ${path}.`), { code: "WORK_SOURCE_UNREGISTERED", recovery });
      }
    }
    return;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  await saveWorkManifest(projectRoot, createWorkManifest({
    id: projectId,
    title,
    profileId,
    language,
    status: "draft",
  }));
}

async function persistCandidateArtifacts(
  projectRoot: string,
  projectId: string,
  artifacts: ReadonlyArray<{ readonly relativePath: string; readonly content: string }>,
): Promise<void> {
  assertNonEmptyArtifacts(artifacts);
  await commitAtomicFileSet({ rootDir: projectRoot, writes: artifacts });
  await syncWorkSourceArtifacts({ projectRoot, workId: projectId, accept: false });
}

/** Preserve the actual supplied input before generation, independently of draft acceptance. */
async function persistProductionInputs(
  projectRoot: string,
  workId: string,
  specifications: ReadonlyArray<{ readonly relativePath: string; readonly content: string }>,
  sourceText: string | undefined,
): Promise<void> {
  const sourcePath = "source/source-material.md";
  await mkdir(join(projectRoot, "works", workId, "source"), { recursive: true });
  await syncWorkSourceArtifacts({ projectRoot, workId, accept: Boolean(sourceText),
    acceptPaths: sourceText ? [sourcePath] : [],
    writes: [...specifications, ...(sourceText ? [{ relativePath: join("works", workId, sourcePath), content: sourceText }] : [])],
  });
}

async function ensureProjectDir(projectRoot: string, relativePath: string): Promise<void> {
  await mkdir(safeChildPath(projectRoot, relativePath), { recursive: true });
}

function mergeRequirements(
  instruction: string,
  requirements: string | undefined,
  language: "zh" | "en" = "zh",
): string {
  const extraLabel = language === "en" ? "Additional requirements:" : "补充要求：";
  return [
    instruction.trim(),
    requirements?.trim() ? `\n${extraLabel}\n${requirements.trim()}` : "",
  ].filter(Boolean).join("\n");
}

// Project-relative path for results and manifests: always "/" separators.
function relPath(...segments: string[]): string {
  return toPosixPath(join(...segments));
}

function safeSegment(value: string): string {
  const text = value.trim();
  if (!text || text === "." || text === ".." || text.includes("/") || text.includes("\\") || text.includes("\0")) {
    throw new Error(`Invalid project id: ${JSON.stringify(value)}`);
  }
  return text.slice(0, 80);
}

function slugify(value: string): string {
  const text = value
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
  return text || `script-${Date.now()}`;
}

export async function projectFileExists(projectRoot: string, relativePath: string): Promise<boolean> {
  try {
    await access(safeChildPath(projectRoot, relativePath));
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}
