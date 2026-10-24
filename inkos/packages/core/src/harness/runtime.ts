import { withWorkMutationScope, runInWorkMutationQueue } from "../utils/work-mutation-scope.js";
import { StateManager } from "../state/manager.js";
import { withExecutionEvidence } from "./execution-evidence.js";
import { actionFailureFacts } from "./action-observation.js";
import { randomUUID } from "node:crypto";
import {
  HARNESS_VERSION,
  type ActionResult,
  type CreativeEpisode,
  type WorkManifest,
  type WorkProfile,
} from "./contracts.js";
import {
  CapabilityRegistry,
  type CapabilityAction,
  type CapabilityExecutionContext,
} from "./capability-registry.js";
import { CreativeEpisodeStore } from "./episode-store.js";
import { WorkProfileRegistry } from "./profile-registry.js";

export type ActionRequestSource = "agent" | "explicit";


export interface HarnessEpisodeHandle {
  readonly episode: CreativeEpisode;
  readonly profile: WorkProfile;
  readonly work: WorkManifest | null;
  readonly authorRequest?: string;
  readonly baselineWork?: WorkManifest | null;
}

export class ActionConfirmationRequiredError extends Error {
  constructor(
    readonly capabilityId: string,
    readonly actionId: string,
    readonly risk: CapabilityAction["risk"],
  ) {
    super(`Action requires confirmation: ${capabilityId}.${actionId}`);
    this.name = "ActionConfirmationRequiredError";
  }
}

export class CreativeHarnessRuntime {
  constructor(
    readonly projectRoot: string,
    readonly capabilities: CapabilityRegistry,
    readonly profiles: WorkProfileRegistry,
    readonly episodes: CreativeEpisodeStore,
  ) {}

  startEpisode(input: {
    readonly profileId: string;
    readonly work?: WorkManifest | null;
    readonly episodeId?: string;
    readonly startedAt?: string;
    readonly authorRequest?: string;
    readonly baselineWork?: WorkManifest | null;
  }): HarnessEpisodeHandle {
    this.episodes.recoverInterruptedEpisodes();
    const profile = this.profiles.require(input.profileId);
    const work = input.work ?? null;
    if (work && work.profileId !== profile.id) {
      throw new Error(`Work "${work.id}" uses profile "${work.profileId}", not "${profile.id}"`);
    }
    const episode = this.episodes.create({
      version: HARNESS_VERSION,
      id: input.episodeId ?? `episode-${randomUUID()}`,
      workId: work?.id ?? null,
      profileId: profile.id,
      status: "running",
      startedAt: input.startedAt ?? new Date().toISOString(),
      completedAt: null,
    });
    this.episodes.append({
      episodeId: episode.id,
      workId: episode.workId,
      type: "episode-started",
      payload: { profileId: profile.id, ...(input.authorRequest ? {authorRequest:input.authorRequest} : {}),
        baseline: (input.baselineWork === undefined ? work : input.baselineWork)?.artifacts.map(a=>({artifactId:a.id,revisionId:a.currentRevisionId})) ?? null },
    }, episode.startedAt);
    return { episode, profile, work, authorRequest: input.authorRequest, baselineWork: input.baselineWork === undefined ? work : input.baselineWork };
  }

  async executeAction(input: {
    readonly handle: HarnessEpisodeHandle;
    readonly capabilityId: string;
    readonly actionId: string;
    readonly parameters: unknown;
    readonly source: ActionRequestSource;
    readonly confirmed?: boolean;
    readonly signal?: AbortSignal;
    readonly onUpdate?: (partialResult: unknown) => void;
  }): Promise<ActionResult> {
    const { capability, action } = this.capabilities.resolve(input.capabilityId, input.actionId);
    if (!input.handle.profile.capabilityIds.includes(capability.id)) {
      throw new Error(`Profile "${input.handle.profile.id}" cannot use capability "${capability.id}"`);
    }
    if (!isActionAuthorized(input.handle.profile, action, input.source, input.confirmed === true)) {
      this.episodes.append({
        episodeId: input.handle.episode.id,
        workId: input.handle.episode.workId,
        type: "action-confirmation-required",
        capabilityId: capability.id,
        actionId: action.id,
        payload: { risk: action.risk, source: input.source },
      });
      throw new ActionConfirmationRequiredError(capability.id, action.id, action.risk);
    }
    const actionExecutionId = `action-${randomUUID()}`;
    let actionWorkId = this.episodes.requireEpisode(input.handle.episode.id).workId;
    try {
      const invoke = async () => {
        if (input.signal?.aborted) throw input.signal.reason;
        this.episodes.append({
          episodeId: input.handle.episode.id,
          workId: input.handle.episode.workId,
          type: "action-started",
          capabilityId: capability.id,
          actionId: action.id,
          payload: { actionExecutionId, risk: action.risk, source: input.source, parameters: input.parameters },
        });
        const context: CapabilityExecutionContext = {
          projectRoot: this.projectRoot,
          episodeId: input.handle.episode.id,
          work: input.handle.work,
          profile: input.handle.profile,
          signal: input.signal,
          onUpdate: input.onUpdate,
          appendEvent: async (event) => {
            this.episodes.append(event);
          },
        };
        return withExecutionEvidence((type, payload) => {
          if (type === "work-artifacts-synced" && typeof payload.workId === "string") {
            actionWorkId = payload.workId;
            if (!this.episodes.requireEpisode(input.handle.episode.id).workId) this.episodes.bindWork(input.handle.episode.id, actionWorkId);
          }
          this.episodes.append({
            episodeId: input.handle.episode.id, workId: actionWorkId, capabilityId: capability.id, actionId: action.id,
            type, payload: { ...payload, actionExecutionId },
          });
        }, () => this.capabilities.invoke(
          capability.id,
          action.id,
          context,
          input.parameters,
        ), input.handle.profile, input.handle.work, input.handle.authorRequest, input.handle.baselineWork);
      };
      const result = action.risk === "read" || !input.handle.work || action.managesWorkLock
        ? await invoke()
        : await runInWorkMutationQueue(
            `${this.projectRoot}\0${input.handle.work.id}`,
            () => withWorkMutationScope(this.projectRoot, input.handle.work!.id,
              () => new StateManager(this.projectRoot).acquireBookLock(input.handle.work!.id), invoke),
          );
      const episodeWorkId = bindCreatedWork(this.episodes, input.handle, result);
      if (input.signal?.aborted) {
        this.episodes.append({ episodeId: input.handle.episode.id, workId: episodeWorkId,
          type: "action-output-retained", capabilityId: capability.id, actionId: action.id,
          payload: { actionExecutionId, result } });
        input.signal.throwIfAborted();
      }
      this.episodes.append({
        episodeId: input.handle.episode.id,
        workId: episodeWorkId,
        type: "action-completed",
        capabilityId: capability.id,
        actionId: action.id,
        payload: {
          actionExecutionId,
          result,
          status: result.status,
          summary: result.summary,
          artifactCount: result.artifacts.length,
          observationCount: result.observations.length,
        },
      });
      return result;
    } catch (error) {
      const { message, ...failure } = actionFailureFacts(error);
      this.episodes.append({
        episodeId: input.handle.episode.id,
        workId: actionWorkId,
        type: input.signal?.aborted ? "action-cancelled" : "action-failed",
        capabilityId: capability.id,
        actionId: action.id,
        payload: { actionExecutionId, error: message, ...failure },
      });
      throw error;
    }
  }

  finishEpisode(
    handle: HarnessEpisodeHandle,
    status: "completed" | "failed" | "cancelled",
    completedAt?: string,
  ): CreativeEpisode {
    const episode = this.episodes.requireEpisode(handle.episode.id);
    this.episodes.append({
      episodeId: episode.id,
      workId: episode.workId,
      type: `episode-${status}`,
      payload: {},
    }, completedAt);
    return this.episodes.finish(episode.id, status, completedAt);
  }
}

function bindCreatedWork(
  episodes: CreativeEpisodeStore,
  handle: HarnessEpisodeHandle,
  result: ActionResult,
): string | null {
  const current = episodes.requireEpisode(handle.episode.id);
  if (current.workId) return current.workId;
  const workIds = new Set(result.artifacts.map((artifact) => artifact.workId));
  if (workIds.size !== 1) return null;
  return episodes.bindWork(handle.episode.id, [...workIds][0]!).workId;
}

export function isActionAuthorized(
  profile: WorkProfile,
  action: Pick<CapabilityAction, "risk" | "requiresConfirmation">,
  source: ActionRequestSource,
  confirmed: boolean,
): boolean {
  if (action.risk === "read") return true;
  if (confirmed) return true;
  if (action.requiresConfirmation) return false;
  if (action.risk === "destructive-write") return false;
  return source === "explicit"
    ? profile.confirmation.explicitRecoverableMutation === "execute"
    : profile.confirmation.inferredMutation === "execute";
}
