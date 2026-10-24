/**
 * Interactive-world (Play) illustration: turn world-graph entities and key
 * moments into images. Reuses the same image-provider plumbing as cover
 * generation (resolveCoverGenerationRequest + generateImageFromPrompt) so a
 * single cover-API configuration drives both.
 *
 * Images and their status live in a per-run sidecar (run/images/) decoupled
 * from the event log — generation is async and is not part of game state.
 */
import { Buffer } from "node:buffer";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { commitAtomicFileSet, type AtomicFileWrite } from '../utils/atomic-file-set.js';
import { loadAvailableAgentSkills } from '../skills/builtin-loader.js';
import { hydrateActivatedSkillGuidance } from '../agent/skill-tool.js';
import { appendActivatedSkillGuidance } from '../agents/base.js';
import { recordExecutionEvidence } from '../harness/execution-evidence.js';
import { z } from "zod";
import { Type } from '@sinclair/typebox';
import { runWorkerAgentTool } from '../agent/worker-agent.js';
import { createLLMClient } from '../llm/provider.js';
import { resolveEffectiveLLMConfig } from '../utils/effective-llm-config.js';
import { loadLLMEnvLayers } from '../utils/llm-env.js';
import type{PlayGraphSnapshot}from'./play-db.js';
import type { PlayCurrentState } from '../models/play.js';
import {
  generateImageFromPrompt,
  loadImageReference,
  resolveCoverGenerationRequest,
} from "../pipeline/short-fiction-runner.js";

export interface PlayImageWorldContext {
  readonly visualFacts?:string;
  readonly premise?: string;
  readonly worldContract?: string;
  readonly visualContract?: string;
  readonly currentMoment?: { readonly turn: number; readonly anchor?: string; readonly summary?: string };
}

type PlayImageWorldInput = string | PlayImageWorldContext | undefined;

function renderImageWorldContext(input: PlayImageWorldInput): string {
  if (!input) return "";
  if (typeof input === "string") {
    const premise = input.trim();
    return premise ? `世界设定：${premise}` : "";
  }
  const premise = input.premise?.trim();
  const worldContract = input.worldContract?.trim();
  const visualContract = input.visualContract?.trim();
  return [
    premise ? `开场前提（不代表当前持有关系或任务进度）：${premise}` : "",
    worldContract ? `世界契约：${worldContract}` : "",
    visualContract ? `视觉契约：${visualContract}` : "",
    input.currentMoment ? `当前时刻（优先于实体描述中的旧时间和历史动作）：${JSON.stringify(input.currentMoment)}` : '',
    input.visualFacts?`人物与物件资料：外观和颜色参考实体描述；描述可能保留开场动作。当前持有人只按 currentHoldings 和有效关系判断，不按较早描述或开场任务恢复物品。已归还且留在另一地点的物件，不画回玩家手上。只描绘当前场景出现者。\n${input.visualFacts}`:'',
  ].filter(Boolean).join("\n");
}

export function playImageContext(world:PlayImageWorldContext|undefined,graph:Pick<PlayGraphSnapshot,'entities'|'edges'>,state?:PlayCurrentState|null):PlayImageWorldContext|undefined{
  if(state)world={...world,currentMoment:{turn:state.turn,anchor:state.timeAdvance?.anchor,summary:state.lastSummary??undefined}};
  const entities=graph.entities.filter(e=>e.type==='actor'||e.type==='item');
  if(!entities.length)return world;
  const names=new Map(graph.entities.map(e=>[e.id,e.label]));
  const activeEdges=graph.edges.filter(e=>e.validUntilEventId==null);
  return{...world,visualFacts:JSON.stringify({
    entities:entities.map(({id,label,summary,status,updatedEventId})=>({id,label,summary,status,descriptionUpdatedEventId:updatedEventId})),
    currentHoldings:activeEdges.filter(e=>e.value?.role==='holding'||e.type==='holds').map(e=>({holderId:e.fromId,holder:names.get(e.fromId)??e.fromId,itemId:e.toId,item:names.get(e.toId)??e.toId,sinceEventId:e.validFromEventId})),
    relations:activeEdges.map(e=>({from:names.get(e.fromId)??e.fromId,relation:e.type,to:names.get(e.toId)??e.toId,value:e.value})),
  })};
}

/**
 * Build a style-consistent image prompt for a world entity. The world premise
 * anchors era / setting / art style so every illustration in one run looks like
 * it belongs to the same world.
 */
export function buildPlayEntityImagePrompt(
  entity: { readonly type: string; readonly label: string; readonly summary?: string },
  worldPremise?: PlayImageWorldInput,
): string {
  const worldContext = renderImageWorldContext(worldPremise);
  const summary = entity.summary?.trim();
  return [
    worldContext,
    `对象类型：${entity.type}`,
    `对象：${entity.label}`,
    summary ? `细节：${summary}` : "",
  ].filter(Boolean).join("\n");
}

/** Build a wide illustration prompt for the current moment from its scene prose. */
export function buildPlaySceneImagePrompt(sceneText: string, worldPremise?: PlayImageWorldInput): string {
  const worldContext = renderImageWorldContext(worldPremise);
  return [
    worldContext,
    "当前场景：",
    sceneText.trim(),
  ].filter(Boolean).join("\n");
}

/** Replayed prose or a changed visual contract must not reuse an older image. */
export function playSceneImageKey(turn: number, sceneText: string, world?: PlayImageWorldInput): string {
  const hash=createHash('sha256').update(buildPlaySceneImagePrompt(sceneText,world)).digest('hex').slice(0,16);
  return `scene-turn-${turn}-${hash}`;
}

export type PlayImageStatus = "ready" | "failed";

export interface PlayImageEntry {
  readonly status: PlayImageStatus;
  readonly file?: string;
  readonly error?: string;
}

export type PlayImageManifest = Record<string, PlayImageEntry>;

const PlayImageEntrySchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("ready"), file: z.string().min(1), error: z.string().optional() }).strict(),
  z.object({ status: z.literal("failed"), file: z.string().optional(), error: z.string().min(1) }).strict(),
]);
const PlayImageManifestSchema = z.record(z.string(), PlayImageEntrySchema);

function manifestPath(runDir: string): string {
  return join(runDir, "images", "manifest.json");
}

export async function readPlayImageManifest(runDir: string): Promise<PlayImageManifest> {
  try {
    const raw = await readFile(manifestPath(runDir), "utf-8");
    return PlayImageManifestSchema.parse(JSON.parse(raw));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
}

export async function writePlayImageManifest(runDir: string, manifest: PlayImageManifest): Promise<void> {
  await mkdir(join(runDir, "images"), { recursive: true });
  const parsed = PlayImageManifestSchema.parse(manifest);
  await writeFile(manifestPath(runDir), JSON.stringify(parsed, null, 2), "utf-8");
}

/** Immutably set one manifest entry and persist it. Returns the new manifest. */
export async function setPlayImageEntry(
  runDir: string,
  key: string,
  entry: PlayImageEntry,
): Promise<PlayImageManifest> {
  const current = await readPlayImageManifest(runDir);
  const next = { ...current, [key]: entry };
  await writePlayImageManifest(runDir, next);
  return next;
}

/**
 * Per-run auto-illustration toggles. Default all-off: nothing is generated
 * until the user opts in (and the cover API is configured).
 */
export interface PlayImageSettings {
  readonly actors: boolean;
  readonly moments: boolean;
  readonly inventory: boolean;
}

export const DEFAULT_PLAY_IMAGE_SETTINGS: PlayImageSettings = {
  actors: false,
  moments: false,
  inventory: false,
};

const PlayImageSettingsSchema = z.object({
  actors: z.boolean(),
  moments: z.boolean(),
  inventory: z.boolean(),
}).strict();

function settingsPath(runDir: string): string {
  return join(runDir, "images", "settings.json");
}

export async function readPlayImageSettings(runDir: string): Promise<PlayImageSettings> {
  try {
    return PlayImageSettingsSchema.parse(JSON.parse(await readFile(settingsPath(runDir), "utf-8")));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return DEFAULT_PLAY_IMAGE_SETTINGS;
    throw error;
  }
}

export async function writePlayImageSettings(runDir: string, settings: PlayImageSettings): Promise<void> {
  await mkdir(join(runDir, "images"), { recursive: true });
  await writeFile(settingsPath(runDir), JSON.stringify(PlayImageSettingsSchema.parse(settings), null, 2), "utf-8");
}

/** Filesystem-safe leaf name derived from an entity id / scene key. */
export function playImageFileName(key: string, extension: "png" | "jpg"): string {
  const safe = key.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80) || "image";
  return `${safe}.${extension}`;
}

/**
 * Generate one image for a Play key (entity id or scene key), write it under
 * run/images/, and record the result in the manifest. Never throws on a
 * generation failure — it records {status:"failed"} so the caller/UI can
 * surface it and retry. Throws only if cover generation is not configured.
 */
export async function generatePlayImage(input: {
  readonly root: string;
  readonly runDir: string;
  readonly key: string;
  readonly prompt: string;
  readonly size?: string;
  readonly signal?: AbortSignal;
  readonly prepareSceneBrief?: boolean;
  readonly withCommitLock?: <T>(task: () => Promise<T>) => Promise<T>;
  readonly commit?: (writes: ReadonlyArray<AtomicFileWrite>) => Promise<void>;
}): Promise<PlayImageEntry> {
  // Resolution failure (no cover API configured) is a real misconfiguration —
  // let it surface so the endpoint can return a clear "configure first".
  const request = await resolveCoverGenerationRequest({ root: input.root });
  const available=await loadAvailableAgentSkills({projectRoot:input.root});
  const skill=new Map(available.skills.map(skill=>[skill.id,skill])).get('inkos-play-illustration');
  if(!skill)throw new Error('Required illustration Skill unavailable: inkos-play-illustration');
  const activations=await hydrateActivatedSkillGuidance([{skill,resources:[]}],input.prompt) ?? [];
  const sourcePrompt=appendActivatedSkillGuidance([{role:'user',content:input.prompt}],activations).map(message=>message.content).join('\n\n');
  let prompt=sourcePrompt;
  recordExecutionEvidence('skills-applied',{worker:'play-image',skills:activations.map(({skill,resources})=>({
    id:skill.id,source:skill.source,hash:createHash('sha256').update(skill.body).digest('hex'),
    references:resources.map(resource=>({path:resource.path,hash:createHash('sha256').update(resource.body).digest('hex')})),
  }))});
  const imageDir=join(input.runDir,'images');
  const locked = input.withCommitLock ?? (async <T>(task: () => Promise<T>) => task());
  const commit = input.commit ?? (async (writes: ReadonlyArray<AtomicFileWrite>) => { await commitAtomicFileSet({rootDir:input.root,writes}); });
  const reference = await locked(async () => {
    const current = (await readPlayImageManifest(input.runDir))[input.key];
    return current?.status === "ready" && current.file
      ? loadImageReference(input.root, relative(input.root, join(imageDir, current.file))) : undefined;
  });
  await locked(()=>commit([{
    relativePath:relative(input.root,join(imageDir,playImageFileName(input.key,'png').slice(0,-4)+'.source.md')),content:sourcePrompt,
  }]));
  const persist=async(entry:PlayImageEntry,image?:{file:string;buffer:Buffer})=>locked(async()=>{
    if(image)input.signal?.throwIfAborted();
    const previous = await readPlayImageManifest(input.runDir);
    const current = previous[input.key];
    const manifest={...previous,[input.key]:entry.status === "failed" && current?.status === "ready"
      ? {...current, error:entry.error} : entry};
    const writes:AtomicFileWrite[]=[{relativePath:relative(input.root,manifestPath(input.runDir)),content:JSON.stringify(manifest,null,2)+'\n'}];
    if(image)writes.push(
      {relativePath:relative(input.root,join(imageDir,image.file)),content:image.buffer},
      {relativePath:relative(input.root,join(imageDir,image.file.replace(/\.(png|jpg)$/u,'.request.md'))),content:prompt},
      {relativePath:relative(input.root,join(imageDir,image.file.replace(/\.(png|jpg)$/u,'.source.md'))),content:sourcePrompt},
    );
    await commit(writes);
    return entry;
  });
  try {
    if(input.prepareSceneBrief){
      const {llm}=await resolveEffectiveLLMConfig({consumer:'studio',projectRoot:input.root,envLayers:await loadLLMEnvLayers(input.root)});
      const brief=await runWorkerAgentTool(createLLMClient(llm),llm.model,[
        {role:'system',content:'Describe one illustration of the final current moment from the supplied reference. Follow the illustration guidance and explicit visual contract. Current moment and active possession/location facts take precedence over opening assumptions, earlier entity descriptions and earlier actions in the scene. Keep the established viewpoint and state explicitly where visible participants are relative to the camera and physical boundaries. Include only participants and objects visible from that viewpoint. Describe a still picture, not a sequence. Omit state identifiers, controls, unchosen options and off-screen history. Return one concise visual paragraph through the tool.'},
        {role:'user',content:sourcePrompt},
      ],{name:'submit_visual_brief',label:'Describe current illustration',description:'Submit an image prompt grounded in the current visible moment.',parameters:Type.Object({prompt:Type.String({minLength:1})})},{maxTokens:1400,signal:input.signal});
      prompt=brief.prompt;
    }
    input.signal?.throwIfAborted();
    await locked(()=>commit([{
      relativePath:relative(input.root,join(imageDir,playImageFileName(input.key,'png').slice(0,-4)+'.request.md')),content:prompt,
    }]));
    const { buffer, extension } = await generateImageFromPrompt(
      request,
      prompt,
      input.size ?? "1024x1024",
      input.signal,
      reference,
    );
    // A stable scene key selects the current image; each distinct image gets a
    // stable immutable URL so regeneration preserves history and refreshes UI.
    const contentHash=createHash('sha256').update(buffer).digest('hex').slice(0,16);
    const file = playImageFileName(`${contentHash}-${input.key}`, extension);
    const entry: PlayImageEntry = { status: "ready", file };
    return persist(entry,{file,buffer});
  } catch (error) {
    const entry: PlayImageEntry = {
      status: "failed",
      error: error instanceof Error ? error.message : String(error),
    };
    return persist(entry);
  }
}
