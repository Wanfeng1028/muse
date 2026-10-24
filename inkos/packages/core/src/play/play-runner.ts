import type { AgentContext } from "../agents/base.js";
import { join } from "node:path";
import {
  PlayActionIntentSchema,
  PlayMutationSchema,
  type PlayEntity,
  type PlayActionIntent,
  type PlayMutation,
  type PlayMutationInput,
} from "../models/play.js";
import {
  PlayOpeningStateAgent,
  PlayTurnAgent,
  type PlaySceneRender,
  type PlayTurnResult,
} from "./play-agents.js";
import { createPlayDB } from "./play-db-factory.js";
import { applyPlayMutation, seedPlayGraph, validatePlayMutation, type PlayReducerDB } from "./play-reducer.js";
import { PlayStore, type PlayWorld } from "./play-store.js";
import { createPlayPresentation } from "./play-presentation.js";
import type { PlayGraphSnapshot } from "./play-db.js";
import { syncWorkSourceArtifacts, captureWorkSourceState, changedWorkSourcePaths } from "../harness/source-sync.js";
import { compileContext, ContextSourceRegistry, type ContextFragment } from "../harness/context-compiler.js";
import { createBuiltInWorkProfileRegistry } from "../harness/builtin-profiles.js";
import { semanticInputBudget } from "../llm/semantic-input.js";
import { SemanticContextCompilerAgent } from "../agents/semantic-context-compiler.js";

export interface PlayOpeningStateLike {
  readonly extract: (input: {
    readonly turn: number;
    readonly sceneText: string;
    readonly suggestedActions: readonly string[];
    readonly context: string;
    readonly language?: "zh" | "en";
    readonly worldPremise?: string;
  }) => Promise<PlayMutationInput>;
}

export interface PlayTurnLike {
  readonly renderExisting?: (input: Parameters<PlayTurnLike["run"]>[0]) => Promise<PlaySceneRender>;
  readonly run: (input: {
    readonly validateMutation?: (mutation:PlayMutation)=>void;
    readonly choiceCount?:number;
    readonly turn: number;
    readonly input: string;
    readonly context: string;
    readonly replayContext?: string;
    readonly mode: "open" | "guided";
    readonly language?: "zh" | "en";
    readonly worldPremise?: string;
    readonly currentSuggestedActions?: readonly string[];
  }) => Promise<PlayTurnResult>;
}

export interface PlayRunnerOptions {
  readonly projectRoot: string;
  readonly worldId: string;
  readonly runId: string;
  readonly ctx?: AgentContext;
  readonly store?: PlayStore;
  readonly db?: PlayReducerDB;
  readonly agents?: {
    readonly openingState?: PlayOpeningStateLike;
    readonly turn?: PlayTurnLike;
  };
}

export interface PlayStepResult extends PlaySceneRender {
  readonly action: PlayActionIntent;
  readonly mutation: PlayMutation;
}

function assertPlayChoices(world:{mode:'open'|'guided';choiceCount?:number},actions:readonly string[]):void{
  const expected=world.mode==='open'?0:world.choiceCount;
  if(expected!==undefined&&actions.length!==expected)throw Object.assign(new Error(`Expected ${expected} guided choices; received ${actions.length}`),{code:'PLAY_CHOICE_COUNT_MISMATCH',expected,actual:actions.length});
  if(actions.some(a=>!a.trim())||new Set(actions.map(a=>a.trim())).size!==actions.length)throw Object.assign(new Error('Choices must be nonempty and distinct'),{code:'PLAY_CHOICES_INVALID'});
}

export interface PlayReplayResult extends PlayStepResult {
  readonly previousVariantId?: string;
  readonly variantId?: string;
  readonly replayedInput: string;
}

export interface PlayVariantRestoreResult {
  readonly turn: number;
  readonly variantId: string;
  readonly sceneText: string;
  readonly suggestedActions?: readonly string[];
}

export interface PlayOpeningSeedResult {
  readonly mutation: PlayMutation;
}

export class PlayOpeningSeedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PlayOpeningSeedError";
  }
}

export class PlayRunner {
  private readonly store: PlayStore;
  private readonly db: PlayReducerDB;
  private readonly ownsDb: boolean;
  private dbClosed = false;
  private readonly openingState: PlayOpeningStateLike;
  private readonly turnAgent: PlayTurnLike;
  private readonly contextCompiler: SemanticContextCompilerAgent | null;
  private readonly contextBudgetTokens: number | undefined;

  constructor(private readonly options: PlayRunnerOptions) {
    this.store = options.store ?? new PlayStore(options.projectRoot);
    this.ownsDb = !options.db;
    this.db = options.db ?? createPlayDB(this.store.runDir(options.worldId, options.runId));
    if (!options.ctx && (!options.agents?.openingState || !options.agents.turn)) {
      throw new Error("PlayRunner requires ctx when default play agents are used.");
    }
    const ctx = options.ctx;
    this.openingState = options.agents?.openingState ?? new PlayOpeningStateAgent(ctx!);
    this.turnAgent = options.agents?.turn ?? new PlayTurnAgent(ctx!);
    this.contextCompiler = ctx ? new SemanticContextCompilerAgent(ctx) : null;
    this.contextBudgetTokens = ctx
      ? semanticInputBudget(ctx.client, {
          reservedOutputTokens: ctx.client.defaults.maxTokens,
          promptOverheadTokens: 4096,
        })
      : undefined;
  }

  /**
   * 关闭 runner 自己创建的数据库连接（外部传入的 db 由调用方负责关闭）。
   * SQLite 文件句柄不关闭时 Windows 上无法删除 play.db；node:sqlite 的
   * close 不允许二次调用，所以这里做幂等保护。
   */
  close(): void {
    if (this.ownsDb && !this.dbClosed) {
      this.dbClosed = true;
      (this.db as { close?: () => void }).close?.();
    }
  }

  async seedOpening(input: {
    readonly sceneText: string;
    readonly suggestedActions?: readonly string[];
  }): Promise<PlayOpeningSeedResult | null> {
    const sourceBefore = await captureWorkSourceState(this.options.projectRoot, this.options.worldId);
    const world = await this.store.ensureWorldDefinition(this.options.worldId);
    await this.store.ensureRun(this.options.worldId, this.options.runId);
    const existing = readGraphSnapshot(this.db);
    if (isOpeningGraphReady(existing)) {
      return null;
    }

    const language = world.language;
    const action: PlayActionIntent = {
      actionKind: "look",
      intent: language === "en" ? "Seed the opening state for the first playable scene." : "播种第一幕已成立的开场状态。",
      manner: "",
      risk: "",
      ambiguity: "",
      secondaryActions: [],
    };
    const worldContext = renderPlayWorldContext(world, language);
    const context = await this.buildContextBrief(input.sceneText, language, world, input.sceneText);
    const mutation = PlayMutationSchema.parse(await this.openingState.extract({
      turn: 0,
      sceneText: input.sceneText,
      suggestedActions: input.suggestedActions ?? [],
      context,
      language,
      worldPremise: worldContext,
    }));

    seedPlayGraph({
      db: this.db,
      mutation,
    });
    const seededGraph = readGraphSnapshot(this.db);
    if (mutation.blocked || !isOpeningGraphReady(seededGraph)) {
      throw new PlayOpeningSeedError(
        mutation.blockedReason
          || (language === "en"
            ? "The opening scene did not produce a usable player/world graph. Retry world creation."
            : "开场没有生成可用的玩家与世界图谱，请重试创建互动世界。"),
      );
    }
    await this.store.writeProjection(this.options.worldId, this.options.runId, "projections/state.md", renderStateBrief({ action, mutation }));
    await syncWorkSourceArtifacts({ projectRoot: this.options.projectRoot, workId: this.options.worldId, accept: true , acceptPaths: await changedWorkSourcePaths(this.options.projectRoot, this.options.worldId, sourceBefore) });
    return { mutation };
  }

  async step(input: string, options: { readonly replayContext?: string } = {}): Promise<PlayStepResult> {
    const sourceBefore = await captureWorkSourceState(this.options.projectRoot, this.options.worldId);
    const rawInput = input.trim();
    if (!rawInput) throw new Error("Play input is empty.");

    await this.store.ensureWorldDefinition(this.options.worldId);
    await this.store.ensureRun(this.options.worldId, this.options.runId);
    const turn = (await this.store.readEvents(this.options.worldId, this.options.runId)).length + 1;
    try {
      const result = await this.executeStep(rawInput, turn, options);
      await syncWorkSourceArtifacts({ projectRoot: this.options.projectRoot, workId: this.options.worldId, accept: true , acceptPaths: await changedWorkSourcePaths(this.options.projectRoot, this.options.worldId, sourceBefore) });
      return result;
    } catch (error) {
      try {
        await syncWorkSourceArtifacts({ projectRoot: this.options.projectRoot, workId: this.options.worldId, accept: false });
      } catch (syncError) {
        throw new AggregateError([error, syncError], `Play turn ${turn} failed and candidate artifacts could not be recorded`);
      }
      throw error;
    }
  }

  private async executeStep(
    rawInput: string,
    turn: number,
    options: { readonly replayContext?: string },
  ): Promise<PlayStepResult> {
    const world = await this.store.ensureWorldDefinition(this.options.worldId);
    const language = world.language;
    const sceneBrief = await this.readOptionalProjection("projections/scene.md");
    const worldContext = renderPlayWorldContext(world, language);
    const context = await this.buildContextBrief(sceneBrief, language, world, rawInput);
    const turnResult = await this.turnAgent.run({
      validateMutation:mutation=>validatePlayMutation(this.db,mutation),
      turn,
      input: rawInput,
      context,
      replayContext: options.replayContext,
      mode: world.mode,
      choiceCount:world.choiceCount,
      language,
      worldPremise: worldContext,
    });
    const action = PlayActionIntentSchema.parse(turnResult.action);
    assertPlayChoices(world,turnResult.suggestedActions);
    const finalMutation = PlayMutationSchema.parse(turnResult.mutation);
    const render: PlaySceneRender = {
      sceneText: turnResult.sceneText,
      suggestedActions: turnResult.suggestedActions,
    };
    const finalStateBrief = renderStateBrief({ action, mutation: finalMutation });

    // Commit everything together, only after the scene and graph reconciliation are in hand.
    const beforeGraph = readGraphSnapshot(this.db);
    const rollbackSnapshot = beforeGraph && this.db.replaceWithSnapshot
      ? await this.store.captureRunSnapshot(this.options.worldId, this.options.runId, {
          id: `before-turn-${turn}`,
          turn,
          graph: beforeGraph,
        })
      : null;
    if (rollbackSnapshot) {
      await this.store.saveCheckpoint(this.options.worldId, this.options.runId, rollbackSnapshot);
    }

    try {
      const applied = applyPlayMutation({
        db: this.db,
        mutation: finalMutation,
        rawInput,
      });
      await this.store.appendEvent(this.options.worldId, this.options.runId, applied.event);
      await this.store.writeProjection(this.options.worldId, this.options.runId, "projections/state.md", finalStateBrief);
      await this.store.saveCurrentState(this.options.worldId, this.options.runId, {
        turn,
        lastEventId: applied.event.id,
        lastAction: action,
        lastSummary: finalMutation.summary,
        timeAdvance: finalMutation.timeAdvance ?? null,
        blocked: finalMutation.blocked,
        worldContract: world.worldContract,
        visualContract: world.visualContract,
      });
      await this.store.savePresentation(this.options.worldId, this.options.runId, createPlayPresentation(turn, render.sceneText, render.suggestedActions));
      await this.store.appendTranscriptTurn(this.options.worldId, this.options.runId, {
        role: "user",
        content: rawInput,
        timestamp: Date.now(),
      });
      await this.store.appendTranscriptTurn(this.options.worldId, this.options.runId, {
        role: "assistant",
        content: render.sceneText,
        suggestedActions: [...render.suggestedActions],
        timestamp: Date.now(),
      });
    } catch (error) {
      if (!rollbackSnapshot) throw error;
      try {
        await this.store.restoreRunSnapshot(
          this.options.worldId,
          this.options.runId,
          rollbackSnapshot,
          requireRestorableGraphDB(this.db),
        );
      } catch (rollbackError) {
        throw new AggregateError([error, rollbackError], `Play turn ${turn} failed and rollback was incomplete`);
      }
      throw error;
    }

    return {
      ...render,
      action,
      mutation: finalMutation,
    };
  }

  async regenerateLastTurn(input?: string, instruction?: string, options?: { readonly preserveChoices?: boolean }): Promise<PlayReplayResult> {
    const sourceBefore = await captureWorkSourceState(this.options.projectRoot, this.options.worldId);
    const events = await this.store.readEvents(this.options.worldId, this.options.runId);
    const last = events.at(-1);
    if (!last) throw new Error("No Play turn to regenerate.");
    const replayedInput = input?.trim() || last.rawInput;
    const db = requireRestorableGraphDB(this.db);
    const currentGraph = readGraphSnapshot(this.db);
    const previousVariantId = currentGraph
      ? await this.store.saveVariant(
          this.options.worldId,
          this.options.runId,
          last.turn,
          await this.store.captureRunSnapshot(this.options.worldId, this.options.runId, {
            id: `current-turn-${last.turn}`,
            turn: last.turn,
            graph: currentGraph,
          }),
        )
      : undefined;
    const checkpoint = await this.store.loadCheckpoint(this.options.worldId, this.options.runId, `before-turn-${last.turn}`);
    if (!checkpoint) {
      throw new Error(`Missing checkpoint before turn ${last.turn}; cannot regenerate safely.`);
    }
    if (!input?.trim() || input.trim() === last.rawInput) {
      if (!currentGraph || !this.turnAgent.renderExisting) {
        throw Object.assign(new Error("Scene-only regeneration is unavailable."), { code: "PLAY_SCENE_REWRITE_UNAVAILABLE" });
      }
      const current = await this.store.captureRunSnapshot(this.options.worldId, this.options.runId, {
        id: `regenerated-turn-${last.turn}`, turn: last.turn, graph: currentGraph,
      });
      const world = await this.store.ensureWorldDefinition(this.options.worldId);
      const keptChoices = options?.preserveChoices
        ? world.mode === "open" ? [] : await this.store.readCurrentSuggestedActions(this.options.worldId, this.options.runId, last.turn, current.sceneProjection)
        : undefined;
      if (options?.preserveChoices && keptChoices === undefined) throw Object.assign(new Error("The current choices have no matching saved render; regenerate the turn's choices before a scene-only rewrite."), { code: "PLAY_CHOICES_UNAVAILABLE" });
      if (keptChoices) assertPlayChoices(world, keptChoices);
      const generated = await this.turnAgent.renderExisting({
        turn: last.turn, input: last.rawInput, mode: world.mode, choiceCount:world.choiceCount,language: world.language,
        worldPremise: renderPlayWorldContext(world, world.language),
        context: await this.buildContextBrief(current.sceneProjection, world.language, world, last.rawInput),
        replayContext: [buildReplayContext({ originalInput: last.rawInput, language: world.language }), instruction?.trim()].filter(Boolean).join("\n\n"),
        currentSuggestedActions: keptChoices,
      });
      const render = { ...generated, suggestedActions: keptChoices ?? generated.suggestedActions };
      const transcript = current.transcriptRaw.trim().split("\n").filter(Boolean).map(line => JSON.parse(line));
      assertPlayChoices(world,render.suggestedActions);
      if (transcript.at(-1)?.role !== "assistant") throw new Error("Latest Play transcript has no assistant scene.");
      transcript[transcript.length - 1] = { ...transcript.at(-1), content: render.sceneText, suggestedActions: [...render.suggestedActions] };
      const rewritten = { ...current, presentation: createPlayPresentation(last.turn, render.sceneText, render.suggestedActions),
        sceneProjection: `${render.sceneText}\n`, transcriptRaw: transcript.map(row => JSON.stringify(row)).join("\n") + "\n" };
      try {
        await this.store.restoreRunSnapshot(this.options.worldId, this.options.runId, rewritten, db);
        await syncWorkSourceArtifacts({ projectRoot: this.options.projectRoot, workId: this.options.worldId, accept: true , acceptPaths: await changedWorkSourcePaths(this.options.projectRoot, this.options.worldId, sourceBefore) });
      } catch (error) {
        await this.store.restoreRunSnapshot(this.options.worldId, this.options.runId, current, db);
        throw error;
      }
      const variantId = await this.store.saveVariant(this.options.worldId, this.options.runId, last.turn, rewritten);
      const state = await this.store.loadCurrentState(this.options.worldId, this.options.runId);
      return { ...render, previousVariantId, variantId, replayedInput,
        action: PlayActionIntentSchema.parse(state?.lastAction),
        mutation: PlayMutationSchema.parse({ eventId: last.id, turn: last.turn, actionKind: last.actionKind,
          summary: last.outcomeSummary, entities: { upsert: [] }, edges: { upsert: [], expire: [] },
          stateSlots: { upsert: [] }, evidence: { transitions: [] }, blocked: false, blockedReason: "", notes: [] }),
      };
    }
    const original = previousVariantId
      ? await this.store.loadVariant(this.options.worldId, this.options.runId, last.turn, previousVariantId)
      : null;
    let result: PlayStepResult;
    try {
      await this.store.restoreRunSnapshot(this.options.worldId, this.options.runId, checkpoint, db);
      result = await this.step(replayedInput, {
        replayContext: buildReplayContext({
          originalInput: last.rawInput,
          replacementInput: input?.trim(),
          language: (await this.store.ensureWorldDefinition(this.options.worldId)).language,
        }),
      });
    } catch (error) {
      if (original) {
        await this.store.restoreRunSnapshot(this.options.worldId, this.options.runId, original, db);
        await syncWorkSourceArtifacts({ projectRoot: this.options.projectRoot, workId: this.options.worldId, accept: true , acceptPaths: await changedWorkSourcePaths(this.options.projectRoot, this.options.worldId, sourceBefore) });
      }
      throw error;
    }
    const nextGraph = readGraphSnapshot(this.db);
    const variantId = nextGraph
      ? await this.store.saveVariant(
          this.options.worldId,
          this.options.runId,
          last.turn,
          await this.store.captureRunSnapshot(this.options.worldId, this.options.runId, {
            id: `regenerated-turn-${last.turn}`,
            turn: last.turn,
            graph: nextGraph,
          }),
        )
      : undefined;
    return {
      ...result,
      previousVariantId,
      variantId,
      replayedInput,
    };
  }

  async restoreVariant(input: {
    readonly turn: number;
    readonly variantId: string;
  }): Promise<PlayVariantRestoreResult> {
    const sourceBefore = await captureWorkSourceState(this.options.projectRoot, this.options.worldId);
    const db = requireRestorableGraphDB(this.db);
    const snapshot = await this.store.loadVariant(this.options.worldId, this.options.runId, input.turn, input.variantId);
    if (!snapshot) {
      throw new Error(`Play variant not found: turn ${input.turn} / ${input.variantId}`);
    }
    const restoredPaths = await this.store.restoreRunSnapshot(this.options.worldId, this.options.runId, snapshot, db);
    await syncWorkSourceArtifacts({ projectRoot: this.options.projectRoot, workId: this.options.worldId, accept: true,
      acceptPaths: [...restoredPaths, ...await changedWorkSourcePaths(this.options.projectRoot, this.options.worldId, sourceBefore)],
    });
    const presentation = await this.store.readPresentation(this.options.worldId, this.options.runId);
    return {
      turn: input.turn,
      variantId: input.variantId,
      sceneText: presentation?.sceneText ?? snapshot.sceneProjection.trim(),
      ...(presentation?.suggestedActions ? { suggestedActions: presentation.suggestedActions } : {}),
    };
  }

  private async buildContextBrief(
    sceneBrief: string,
    language: "zh" | "en",
    world: PlayWorld,
    intent: string,
  ): Promise<string> {
    const stateBrief = await this.readOptionalProjection("projections/state.md");
    const transcript = await this.store.readTranscript(this.options.worldId, this.options.runId);
    const worldContext = renderPlayWorldContext(world, language);
    const graph = readGraphSnapshot(this.db);
    const activeEdges = (graph?.edges ?? []).filter(edge => edge.validUntilEventId == null);
    const playerAdjacentIds = new Set<string>(["actor_player"]);
    for (const edge of activeEdges) {
      if (edge.fromId === "actor_player") playerAdjacentIds.add(edge.toId);
      if (edge.toId === "actor_player") playerAdjacentIds.add(edge.fromId);
    }
    const fragments: ContextFragment[] = [
      { id: "play-world", source: "World contract", content: worldContext, protection: "protected", priority: 100 },
      ...(sceneBrief ? [{ id: "play-scene", source: "Current scene", content: sceneBrief, protection: "protected" as const, priority: 95 }] : []),
      ...(stateBrief ? [{ id: "play-state", source: "Current state", content: stateBrief, protection: "protected" as const, priority: 95 }] : []),
      { id: "play-current-graph", source: "Current relationships and tracked state", content: JSON.stringify({ activeRelationships: activeEdges, stateSlots: graph?.stateSlots ?? [] }), protection: "protected", priority: 100, pointer: "play.db" },
      ...(transcript.length ? [{
        id: "play-history",
        source: "Earlier player actions and scenes. Retain established facts; later events and current state govern changes in time, location, holdings and obligations.",
        content: JSON.stringify(transcript.map(({role, content}) => ({role, content}))),
        protection: "compressible" as const,
        priority: 60,
        pointer: "transcript.jsonl",
      }] : []),
      ...(graph?.entities ?? []).map((entity) => ({
        id: `play-entity-${entity.id}`,
        source: `Entity ${entity.id}`,
        content: renderEntity(entity, language),
        protection: playerAdjacentIds.has(entity.id) ? "protected" as const : "compressible" as const,
        priority: playerAdjacentIds.has(entity.id) ? 90 : 40,
        pointer: `play.db#entity:${entity.id}`,
      })),
    ];
    if (this.contextBudgetTokens === undefined) {
      return fragments.map((fragment) => fragment.content).filter(Boolean).join("\n\n");
    }
    const sources = new ContextSourceRegistry();
    sources.register({ id: "play-current", async load() { return fragments; } });
    const compiled = await compileContext({
      recipe: { id: "interactive-world-turn", sourceIds: ["play-current"] },
      sources,
      request: {
        projectRoot: this.options.projectRoot,
        work: null,
        profile: createBuiltInWorkProfileRegistry().require("interactive-world"),
        actionId: "play_step",
        intent,
        signal: this.options.ctx?.signal,
      },
      budgetTokens: this.contextBudgetTokens,
      compiler: this.contextCompiler
        ? (request) => this.contextCompiler!.compile({
            intent: request.intent,
            maxTokens: request.maxTokens,
            fragments: request.fragments,
            language,
          })
        : undefined,
    });
    return compiled.markdown;
  }

  private async readOptionalProjection(relativePath: string): Promise<string> {
    try {
      return await this.store.readProjection(this.options.worldId, this.options.runId, relativePath);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return "";
      throw error;
    }
  }
}

function isOpeningGraphReady(graph: PlayGraphSnapshot | null): boolean {
  if (!graph) return false;
  return graph.entities.some((entity) => entity.id === "actor_player")
    && graph.entities.some((entity) => entity.id !== "actor_player");
}

function buildReplayContext(input: {
  readonly originalInput: string;
  readonly replacementInput?: string;
  readonly language: "zh" | "en";
}): string {
  const replacement = input.replacementInput?.trim();
  if (input.language === "en") {
    return [
      "This is a regeneration of the previous turn, not a new next turn.",
      `Original player input: ${input.originalInput}`,
      replacement && replacement !== input.originalInput ? `Replacement instruction from user: ${replacement}` : "",
      "Keep it as the same player action unless the replacement explicitly changes that action.",
      "The Current state summary is authoritative, especially the Time section. Do not move the clock backward, invent a different elapsed time, or write another timestamp.",
      "Do not add new player actions the user did not take. Vary prose, sensory detail, pressure, and emphasis while staying inside the same applied state.",
      "Concrete new facts, people, objects, locations, or clues must already be present in Applied changes or Current state summary.",
    ].filter(Boolean).join("\n");
  }
  return [
    "这是在重写上一回合，不是推进新的下一回合。",
    `原玩家动作：${input.originalInput}`,
    replacement && replacement !== input.originalInput ? `用户替换说明：${replacement}` : "",
    "除非替换说明明确改变动作，否则保持同一个玩家动作。",
    "当前状态摘要是权威，尤其是 Time/时间段：不得倒退时间，不得另写经过时长，也不得写另一个钟点。",
    "不要加入玩家没有做的新动作。可以换表达、感官细节、压迫和侧重点，但必须留在同一份已应用状态里。",
    "具体新事实、人物、物件、地点或线索必须已经出现在已应用变化或当前状态摘要中。",
  ].filter(Boolean).join("\n");
}

function renderPlayWorldContext(world: PlayWorld | null | undefined, language: "zh" | "en"): string {
  if (!world) return "";
  const premise = world.premise?.trim();
  const worldContract = world.worldContract?.trim();
  const visualContract = world.visualContract?.trim();
  const isEn = language === "en";
  const blocks = [
    premise
      ? `${isEn ? "Opening premise (current state supersedes completed objectives and changed facts)" : "开场前提（已完成目标和已变化事实以当前状态为准）"}:\n${premise}`
      : "",
    worldContract
      ? `${isEn ? "World contract (high priority; obey before genre defaults)" : "世界契约（高优先级，先于题材惯例）"}:\n${worldContract}`
      : "",
    visualContract
      ? `${isEn ? "Visual contract (for scene and image consistency)" : "视觉契约（保持场景和配图一致）"}:\n${visualContract}`
      : "",
  ].filter(Boolean);
  return blocks.join("\n\n");
}

function readGraphSnapshot(db: PlayReducerDB): PlayGraphSnapshot | null {
  const maybeSnapshot = (db as { readonly snapshot?: unknown }).snapshot;
  if (typeof maybeSnapshot !== "function") {
    return null;
  }
  return maybeSnapshot.call(db) as PlayGraphSnapshot;
}

function requireRestorableGraphDB(db: PlayReducerDB): PlayReducerDB & {
  snapshot: () => PlayGraphSnapshot;
  replaceWithSnapshot: (snapshot: PlayGraphSnapshot) => void;
} {
  if (typeof db.snapshot !== "function" || typeof db.replaceWithSnapshot !== "function") {
    throw new Error("Play graph database cannot restore snapshots.");
  }
  return db as PlayReducerDB & {
    snapshot: () => PlayGraphSnapshot;
    replaceWithSnapshot: (snapshot: PlayGraphSnapshot) => void;
  };
}

function renderEntity(entity: PlayEntity, language: "zh" | "en"): string {
  const isEn = language === "en";
  const detail = [entity.summary, entity.status ? `${isEn ? "status" : "状态"}: ${entity.status}` : ""]
    .filter(Boolean)
    .join(isEn ? "; " : "；");
  return `${entity.id} [${entity.type}; ${isEn ? "description last updated" : "描述最后更新"}: ${entity.updatedEventId}]: ${entity.label}${detail ? ` — ${detail}` : ""}`;
}

function renderStateBrief(input: {
  readonly action: PlayActionIntent;
  readonly mutation: PlayMutation;
}): string {
  const lines = [
    `# Play State`,
    "",
    `- action: ${input.action.actionKind} ${input.action.intent}`.trim(),
    `- summary: ${input.mutation.summary || input.mutation.blockedReason}`,
  ];
  if (input.mutation.entities.upsert.length > 0) {
    lines.push("", "## Entities");
    for (const entity of input.mutation.entities.upsert) {
      lines.push(`- ${entity.id} [${entity.type}]: ${entity.label}${entity.summary ? ` — ${entity.summary}` : ""}`);
    }
  }
  if (input.mutation.edges.upsert.length > 0) {
    lines.push("", "## Edges");
    for (const edge of input.mutation.edges.upsert) {
      const role = typeof edge.value?.role === "string" && edge.value.role.trim()
        ? ` role=${edge.value.role.trim()}`
        : "";
      lines.push(`- ${edge.fromId} -[${edge.type}${role}]-> ${edge.toId}`);
    }
  }
  if (input.mutation.stateSlots.upsert.length > 0) {
    lines.push("", "## State Slots");
    for (const slot of input.mutation.stateSlots.upsert) {
      lines.push(`- ${slot.id}: ${JSON.stringify(slot.value)}`);
    }
  }
  if (input.mutation.timeAdvance) {
    lines.push("", "## Time");
    if (input.mutation.timeAdvance.elapsed) {
      lines.push(`- elapsed: ${input.mutation.timeAdvance.elapsed}`);
    }
    if (input.mutation.timeAdvance.anchor) {
      lines.push(`- anchor: ${input.mutation.timeAdvance.anchor}`);
    }
    if (input.mutation.timeAdvance.rationale) {
      lines.push(`- rationale: ${input.mutation.timeAdvance.rationale}`);
    }
    if (input.mutation.timeAdvance.synchronized.length > 0) {
      lines.push("- synchronized:");
      for (const item of input.mutation.timeAdvance.synchronized) {
        lines.push(`  - ${item}`);
      }
    }
  }
  if (input.mutation.evidence.transitions.length > 0) {
    lines.push("", "## Evidence");
    for (const transition of input.mutation.evidence.transitions) {
      lines.push(`- ${transition.entityId}: ${transition.to}${transition.reason ? ` — ${transition.reason}` : ""}`);
    }
  }
  return `${lines.join("\n")}\n`;
}
