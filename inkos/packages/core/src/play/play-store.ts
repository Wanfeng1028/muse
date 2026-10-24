import { appendFile, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { PlayPresentationSchema, legacyPresentation, type PlayPresentation } from "./play-presentation.js";
import { legacyReceiptChoices } from "./play-presentation-legacy.js";
import { join, normalize, sep } from "node:path";
import { z } from "zod";
import {
  PlayCurrentStateSchema,
  PlayEventSchema,
  type PlayCurrentState,
  type PlayCurrentStateInput,
  type PlayEvent,
} from "../models/play.js";
import type { PlayGraphSnapshot } from "./play-db.js";
import type { PlayGraphDB } from "./play-db-factory.js";
import { commitAtomicFileSet } from "../utils/atomic-file-set.js";
import { syncWorkSourceArtifacts } from "../harness/source-sync.js";
import { createWorkManifest,loadWorkManifest } from "../harness/work-store.js";
import {createBuiltInWorkProfileRegistry} from '../harness/builtin-profiles.js';
import { listWorkManifests, workDirectory } from "../harness/work-store.js";

const PlayTranscriptTurnSchema = z.object({
  role: z.enum(["user", "assistant", "system", "tool"]),
  content: z.string(),
  timestamp: z.number().int().nonnegative(),
  suggestedActions: z.array(z.string()).optional(),
}).strict();

export type PlayTranscriptTurn = z.infer<typeof PlayTranscriptTurnSchema>;

const PlayWorldSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  premise: z.string(),
  worldContract: z.string(),
  visualContract: z.string(),
  mode: z.enum(["open", "guided"]),
  choiceCount:z.number().int().positive().optional(),
  language: z.enum(["zh", "en"]),
  createdAt: z.string().min(1),
  updatedAt: z.string().min(1),
}).strict();

export type PlayWorld = z.infer<typeof PlayWorldSchema>;
export type PlayWorldInput = Omit<z.input<typeof PlayWorldSchema>, "createdAt" | "updatedAt"> & {
  readonly createdAt?: string;
  readonly updatedAt?: string;
};

export interface PlayRunSummary {
  readonly id: string;
  readonly updatedAt: string;
  readonly eventCount: number;
  readonly transcriptCount: number;
}

export interface PlayRunSnapshot {
  readonly id: string;
  readonly turn: number;
  readonly createdAt: string;
  readonly eventsRaw: string;
  readonly transcriptRaw: string;
  readonly currentStateRaw: string;
  readonly sceneProjection: string;
  readonly stateProjection: string;
  readonly graph: PlayGraphSnapshot;
  readonly presentation?: PlayPresentation | null;
}

export class PlayStore {
  constructor(private readonly projectRoot: string) {}

  worldDir(worldId: string): string {
    return join(workDirectory(this.projectRoot, assertSafeSegment(worldId)), "source");
  }

  runDir(worldId: string, runId: string): string {
    return join(this.worldDir(worldId), "runs", assertSafeSegment(runId));
  }

  async ensureWorld(worldId: string): Promise<void> {
    await mkdir(this.worldDir(worldId), { recursive: true });
  }

  async ensureWorldDefinition(worldId: string): Promise<PlayWorld> {
    const existing = await this.loadWorld(worldId);
    if (existing) return existing;
    throw new Error(`Interactive-world Work is missing world.json: ${worldId}`);
  }

  async createWorld(input: PlayWorldInput): Promise<PlayWorld> {
    const now = new Date().toISOString();
    let existingWork;
    try{existingWork=await loadWorkManifest(this.projectRoot,input.id);}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
    if(existingWork&&!createBuiltInWorkProfileRegistry(this.projectRoot).require(existingWork.profileId).capabilityIds.includes('interactive-world'))throw Object.assign(new Error('The existing Work does not declare interactive-world capability'),{code:'WORK_CAPABILITY_REQUIRED'});
    const world = PlayWorldSchema.parse({
      ...input,
      ...(existingWork?{title:existingWork.title,language:existingWork.language}:{}),
      id: assertSafeSegment(input.id),
      createdAt: input.createdAt ?? now,
      updatedAt: input.updatedAt ?? now,
    });
    const worldWrite = {
      relativePath: join("works", world.id, "source", "world.json"),
      content: `${JSON.stringify(world, null, 2)}\n`,
    };
    const work = existingWork ?? createWorkManifest({
      id: world.id,
      title: world.title,
      profileId: "interactive-world",
      language: world.language,
      status: "draft",
      now: world.createdAt,
      metadata: { mode: world.mode },
    });
    await commitAtomicFileSet({
      rootDir: this.projectRoot,
      writes: [
        worldWrite,
        {
          relativePath: join("works", world.id, "work.json"),
          content: `${JSON.stringify(work, null, 2)}\n`,
        },
      ],
    });
    await syncWorkSourceArtifacts({ projectRoot: this.projectRoot, workId: world.id, updatedAt: world.updatedAt, accept: false });
    return world;
  }

  async updateWorld(
    worldId: string,
    patch: Partial<Pick<PlayWorld, "premise" | "worldContract" | "visualContract" | "mode" | "choiceCount">>,
    options: { readonly accept?: boolean } = {},
  ): Promise<PlayWorld> {
    const current = await this.loadWorld(worldId);
    if (!current) {
      throw new Error(`Play world not found: ${worldId}`);
    }
    const world = PlayWorldSchema.parse({
      ...current,
      ...patch,
      id: current.id,
      title: current.title,
      language: current.language,
      createdAt: current.createdAt,
      updatedAt: new Date().toISOString(),
    });
    await commitAtomicFileSet({
      rootDir: this.projectRoot,
      writes: [{
        relativePath: join("works", world.id, "source", "world.json"),
        content: `${JSON.stringify(world, null, 2)}\n`,
      }],
    });
    await syncWorkSourceArtifacts({
      projectRoot: this.projectRoot,
      workId: world.id,
      updatedAt: world.updatedAt,
      accept: options.accept !== false,
      acceptPaths: ["source/world.json"],
    });
    return world;
  }

  async loadWorld(worldId: string): Promise<PlayWorld | null> {
    try {
      const raw = await readFile(join(this.worldDir(worldId), "world.json"), "utf-8");
      return PlayWorldSchema.parse(JSON.parse(raw));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }
  }

  async listWorlds(): Promise<PlayWorld[]> {
    const worlds: PlayWorld[] = [];
    for (const work of await listWorkManifests(this.projectRoot, "interactive-world")) {
      const world = await this.loadWorld(work.id);
      if (!world) throw new Error(`Interactive-world Work is missing world.json: ${work.id}`);
      worlds.push(world);
    }
    return worlds.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt) || a.id.localeCompare(b.id));
  }

  async ensureRun(worldId: string, runId: string): Promise<void> {
    const dir = this.runDir(worldId, runId);
    await Promise.all([
      mkdir(dir, { recursive: true }),
      mkdir(join(dir, "state"), { recursive: true }),
      mkdir(join(dir, "projections"), { recursive: true }),
      mkdir(join(dir, "summaries"), { recursive: true }),
      mkdir(join(dir, "checkpoints"), { recursive: true }),
    ]);
  }

  async listRuns(worldId: string): Promise<PlayRunSummary[]> {
    const runsRoot = join(this.worldDir(worldId), "runs");
    let entries: string[];
    try {
      entries = await readdir(runsRoot);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw error;
    }

    const runs: PlayRunSummary[] = [];
    for (const entry of entries.sort()) {
      if (!isSafeSegment(entry)) continue;
      const runDir = join(runsRoot, entry);
      const entryStat = await stat(runDir);
      if (!entryStat.isDirectory()) continue;
      const [events, transcript] = await Promise.all([
        this.readEvents(worldId, entry),
        this.readTranscript(worldId, entry),
      ]);
      runs.push({
        id: entry,
        updatedAt: entryStat.mtime.toISOString(),
        eventCount: events.length,
        transcriptCount: transcript.length,
      });
    }
    return runs.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt) || a.id.localeCompare(b.id));
  }

  async appendEvent(worldId: string, runId: string, event: PlayEvent): Promise<void> {
    await this.ensureRun(worldId, runId);
    await this.appendJsonLine(
      this.eventsPath(worldId, runId),
      PlayEventSchema.parse(event),
    );
  }

  async appendRawEventLine(worldId: string, runId: string, line: string): Promise<void> {
    await this.ensureRun(worldId, runId);
    await appendFile(this.eventsPath(worldId, runId), `${line}\n`, "utf-8");
  }

  async readEvents(worldId: string, runId: string): Promise<PlayEvent[]> {
    return this.readJsonLines(this.eventsPath(worldId, runId), PlayEventSchema);
  }

  async appendTranscriptTurn(
    worldId: string,
    runId: string,
    turn: PlayTranscriptTurn,
  ): Promise<void> {
    await this.ensureRun(worldId, runId);
    await this.appendJsonLine(
      this.transcriptPath(worldId, runId),
      PlayTranscriptTurnSchema.parse(turn),
    );
  }

  async readTranscript(worldId: string, runId: string): Promise<PlayTranscriptTurn[]> {
    return this.readJsonLines(this.transcriptPath(worldId, runId), PlayTranscriptTurnSchema);
  }

  async readPresentation(worldId: string, runId: string): Promise<PlayPresentation | null> {
    try {
      return PlayPresentationSchema.nullable().parse(JSON.parse(await readFile(join(this.runDir(worldId, runId), "presentation.json"), "utf8")));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    const scene = await this.readOptionalRunFile(worldId, runId, "projections/scene.md");
    if (!scene.trim()) return null;
    const turn = (await this.loadCurrentState(worldId, runId))?.turn ?? 0;
    const legacy = legacyPresentation(turn, scene.trim(), await this.readOptionalRunFile(worldId, runId, "transcript.jsonl"));
    if (legacy.suggestedActions !== null) return legacy;
    const world = await this.loadWorld(worldId);
    return { ...legacy, suggestedActions: world?.mode === "open" ? []
      : await legacyReceiptChoices(this.projectRoot, worldId, runId, turn, scene) };
  }

  async savePresentation(worldId: string, runId: string, presentation: PlayPresentation): Promise<void> {
    const parsed = PlayPresentationSchema.parse(presentation);
    await commitAtomicFileSet({ rootDir: this.runDir(worldId, runId), writes: [
      { relativePath: "presentation.json", content: JSON.stringify(parsed, null, 2) + "\n" },
      { relativePath: "projections/scene.md", content: parsed.sceneText + "\n" },
    ] });
  }

  async readCurrentSuggestedActions(worldId: string, runId: string, turn: number, sceneText: string): Promise<string[] | undefined> {
    const presentation = await this.readPresentation(worldId, runId);
    return presentation?.turn === turn && presentation.sceneText.trim() === sceneText.trim()
      ? presentation.suggestedActions ?? undefined : undefined;
  }

  async saveCurrentState(
    worldId: string,
    runId: string,
    state: PlayCurrentStateInput,
  ): Promise<void> {
    await this.ensureRun(worldId, runId);
    const parsed = PlayCurrentStateSchema.parse(state);
    await writeFile(
      join(this.runDir(worldId, runId), "state", "current.json"),
      `${JSON.stringify(parsed, null, 2)}\n`,
      "utf-8",
    );
  }

  async loadCurrentState(worldId: string, runId: string): Promise<PlayCurrentState | null> {
    try {
      const raw = await readFile(join(this.runDir(worldId, runId), "state", "current.json"), "utf-8");
      return PlayCurrentStateSchema.parse(JSON.parse(raw));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }
  }

  async writeProjection(
    worldId: string,
    runId: string,
    relativePath: string,
    content: string,
  ): Promise<void> {
    await this.ensureRun(worldId, runId);
    const target = this.safeRunChildPath(worldId, runId, relativePath);
    await mkdir(join(target, ".."), { recursive: true });
    await writeFile(target, content, "utf-8");
  }

  async readProjection(worldId: string, runId: string, relativePath: string): Promise<string> {
    if (relativePath === "projections/scene.md") {
      const presentation = await this.readPresentation(worldId, runId);
      if (presentation) return `${presentation.sceneText}\n`;
    }
    return readFile(this.safeRunChildPath(worldId, runId, relativePath), "utf-8");
  }

  async captureRunSnapshot(
    worldId: string,
    runId: string,
    input: {
      readonly id: string;
      readonly turn: number;
      readonly graph: PlayGraphSnapshot;
    },
  ): Promise<PlayRunSnapshot> {
    await this.ensureRun(worldId, runId);
    return {
      id: input.id,
      turn: input.turn,
      createdAt: new Date().toISOString(),
      eventsRaw: await this.readOptionalRunFile(worldId, runId, "events.jsonl"),
      transcriptRaw: await this.readOptionalRunFile(worldId, runId, "transcript.jsonl"),
      currentStateRaw: await this.readOptionalRunFile(worldId, runId, join("state", "current.json")),
      sceneProjection: await this.readOptionalRunFile(worldId, runId, join("projections", "scene.md")),
      stateProjection: await this.readOptionalRunFile(worldId, runId, join("projections", "state.md")),
      graph: structuredClone(input.graph),
      presentation: await this.readPresentation(worldId, runId),
    };
  }

  async saveCheckpoint(
    worldId: string,
    runId: string,
    snapshot: PlayRunSnapshot,
  ): Promise<void> {
    await this.ensureRun(worldId, runId);
    await writeFile(
      this.safeRunChildPath(worldId, runId, join("checkpoints", `${assertSafeSegment(snapshot.id)}.json`)),
      `${JSON.stringify(snapshot, null, 2)}\n`,
      "utf-8",
    );
  }

  async loadCheckpoint(
    worldId: string,
    runId: string,
    checkpointId: string,
  ): Promise<PlayRunSnapshot | null> {
    return this.loadSnapshotFile(worldId, runId, join("checkpoints", `${assertSafeSegment(checkpointId)}.json`));
  }

  async saveVariant(
    worldId: string,
    runId: string,
    turn: number,
    snapshot: PlayRunSnapshot,
  ): Promise<string> {
    const variantId = `v-${randomUUID()}`;
    await this.ensureRun(worldId, runId);
    const relativePath = join("variants", `turn-${turn}`, `${variantId}.json`);
    await mkdir(join(this.runDir(worldId, runId), "variants", `turn-${turn}`), { recursive: true });
    await writeFile(
      this.safeRunChildPath(worldId, runId, relativePath),
      `${JSON.stringify({ ...snapshot, id: variantId }, null, 2)}\n`,
      "utf-8",
    );
    return variantId;
  }

  async loadVariant(
    worldId: string,
    runId: string,
    turn: number,
    variantId: string,
  ): Promise<PlayRunSnapshot | null> {
    return this.loadSnapshotFile(worldId, runId, join("variants", `turn-${turn}`, `${assertSafeSegment(variantId)}.json`));
  }

  async restoreRunSnapshot(
    worldId: string,
    runId: string,
    snapshot: PlayRunSnapshot,
    db: PlayGraphDB,
  ): Promise<readonly string[]> {
    await this.ensureRun(worldId, runId);
    const stateTurn = snapshot.currentStateRaw.trim() ? PlayCurrentStateSchema.parse(JSON.parse(snapshot.currentStateRaw)).turn : 0;
    const presentation = snapshot.presentation ?? (snapshot.sceneProjection.trim()
      ? legacyPresentation(stateTurn, snapshot.sceneProjection.trim(), snapshot.transcriptRaw) : null);
    if (presentation && presentation.turn !== stateTurn) throw Object.assign(new Error("Presentation does not belong to the snapshot turn."), { code: "PLAY_PRESENTATION_CONFLICT" });
    const beforeGraph = db.snapshot();
    db.replaceWithSnapshot(snapshot.graph);
    try {
      await commitAtomicFileSet({ rootDir: this.runDir(worldId, runId), writes: [
        { relativePath: "events.jsonl", content: snapshot.eventsRaw },
        { relativePath: "transcript.jsonl", content: snapshot.transcriptRaw },
        { relativePath: "state/current.json", content: snapshot.currentStateRaw },
        { relativePath: "presentation.json", content: JSON.stringify(presentation) + "\n" },
        { relativePath: "projections/scene.md", content: presentation ? presentation.sceneText + "\n" : snapshot.sceneProjection },
        { relativePath: "projections/state.md", content: snapshot.stateProjection },
      ] });
    } catch (error) { db.replaceWithSnapshot(beforeGraph); throw error; }
    return ["play.db", "events.jsonl", "transcript.jsonl", "state/current.json", "presentation.json", "projections/scene.md", "projections/state.md"]
      .map(path => `source/runs/${runId}/${path}`);
  }

  private eventsPath(worldId: string, runId: string): string {
    return join(this.runDir(worldId, runId), "events.jsonl");
  }

  private transcriptPath(worldId: string, runId: string): string {
    return join(this.runDir(worldId, runId), "transcript.jsonl");
  }

  private async appendJsonLine(path: string, value: unknown): Promise<void> {
    await appendFile(path, `${JSON.stringify(value)}\n`, "utf-8");
  }

  private async readJsonLines<T>(
    path: string,
    schema: { parse(value: unknown): T },
  ): Promise<T[]> {
    let raw: string;
    try {
      raw = await readFile(path, "utf-8");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw error;
    }

    const rows: T[] = [];
    for (const [index, line] of raw.split(/\r?\n/).entries()) {
      if (!line.trim()) continue;
      try {
        rows.push(schema.parse(JSON.parse(line)));
      } catch (error) {
        throw new Error(`Invalid Play event at ${path}:${index + 1}: ${String(error)}`);
      }
    }
    return rows;
  }

  private async readOptionalRunFile(worldId: string, runId: string, relativePath: string): Promise<string> {
    try {
      return await readFile(this.safeRunChildPath(worldId, runId, relativePath), "utf-8");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return "";
      throw error;
    }
  }

  private async loadSnapshotFile(worldId: string, runId: string, relativePath: string): Promise<PlayRunSnapshot | null> {
    try {
      const raw = await readFile(this.safeRunChildPath(worldId, runId, relativePath), "utf-8");
      return PlayRunSnapshotSchema.parse(JSON.parse(raw));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }
  }

  private safeRunChildPath(worldId: string, runId: string, relativePath: string): string {
    if (!relativePath || relativePath.startsWith("/") || relativePath.includes("\0")) {
      throw new Error(`Unsafe play path: ${relativePath}`);
    }
    const normalized = normalize(relativePath);
    if (normalized === ".." || normalized.startsWith(`..${sep}`)) {
      throw new Error(`Unsafe play path: ${relativePath}`);
    }
    return join(this.runDir(worldId, runId), normalized);
  }
}

const PlayRunSnapshotSchema: z.ZodType<PlayRunSnapshot> = z.object({
  id: z.string().min(1),
  turn: z.number().int().min(0),
  createdAt: z.string().min(1),
  eventsRaw: z.string(),
  transcriptRaw: z.string(),
  currentStateRaw: z.string(),
  presentation: PlayPresentationSchema.nullable().optional(),
  sceneProjection: z.string(),
  stateProjection: z.string(),
  graph: z.object({
    entities: z.array(z.unknown()),
    edges: z.array(z.unknown()),
    stateSlots: z.array(z.unknown()),
    events: z.array(z.unknown()),
  }) as z.ZodType<PlayGraphSnapshot>,
});

function assertSafeSegment(value: string): string {
  if (!isSafeSegment(value)) {
    throw new Error(`Unsafe play path segment: ${value}`);
  }
  return value;
}

function isSafeSegment(value: string): boolean {
  return Boolean(value) &&
    !value.includes("/") &&
    !value.includes("\\") &&
    !value.includes("\0") &&
    value !== "." &&
    value !== "..";
}
