import type { AgentTool } from "@mariozechner/pi-agent-core";
import { join } from "node:path";
import type { ActionResult } from "./contracts.js";
import { CreativeEpisodeStore } from "./episode-store.js";
import { createBuiltInWorkProfileRegistry } from "./builtin-profiles.js";
import { createSingleToolCapabilityRegistry, type ConfirmedCapabilityBinding } from "./production-capabilities.js";
import { CreativeHarnessRuntime } from "./runtime.js";
import { loadWorkManifest } from "./work-store.js";
import { opaqueConversationId, runWithAgentTrajectory } from "../llm/agent-trajectory.js";

export async function executeExplicitCapabilityTool(input: {
  readonly projectRoot: string;
  readonly binding: ConfirmedCapabilityBinding;
  readonly tool: AgentTool<any, any>;
  readonly parameters: unknown;
  readonly workId?: string | null;
  readonly episodeId?: string;
  readonly conversationId?: string;
  readonly authorRequest?: string;
  readonly signal?: AbortSignal;
  readonly onUpdate?: (partialResult: unknown) => void;
}): Promise<ActionResult> {
  const work = input.workId ? await loadWorkManifest(input.projectRoot, input.workId) : null;
  const profiles = createBuiltInWorkProfileRegistry(input.projectRoot);
  const workProfile = work ? profiles.require(work.profileId) : null;
  const profile = workProfile?.capabilityIds.includes(input.binding.capabilityId)
    ? workProfile
    : profiles.require(input.binding.profileId);
  const episodeWork = work?.profileId === profile.id ? work : null;
  const registry = createSingleToolCapabilityRegistry({ binding: input.binding, tool: input.tool });
  const episodes = new CreativeEpisodeStore(join(input.projectRoot, ".inkos", "harness.sqlite"));
  const runtime = new CreativeHarnessRuntime(input.projectRoot, registry, profiles, episodes);
  const handle = runtime.startEpisode({
    profileId: profile.id,
    work: episodeWork,
    authorRequest: input.authorRequest,
    ...(input.episodeId ? { episodeId: input.episodeId } : {}),
  });
  try {
    const result = await runWithAgentTrajectory({
      conversationId: opaqueConversationId(input.conversationId ?? handle.episode.id),
      runId: handle.episode.id,
      agentRole: "subagent",
    }, () => runtime.executeAction({
        handle,
        capabilityId: input.binding.capabilityId,
        actionId: input.binding.actionId,
        parameters: input.parameters,
        source: "explicit",
        confirmed: true,
        signal: input.signal,
        onUpdate: input.onUpdate,
      }));
    runtime.finishEpisode(handle, "completed");
    return result;
  } catch (error) {
    try {
      runtime.finishEpisode(handle, input.signal?.aborted ? "cancelled" : "failed");
    } catch {
      // Preserve the original action error if the episode is already terminal.
    }
    throw error;
  } finally {
    episodes.close();
  }
}
