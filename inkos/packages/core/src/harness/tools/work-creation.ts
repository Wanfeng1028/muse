import { Type } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { createBuiltInWorkProfileRegistry } from "../builtin-profiles.js";
import { createInitialWorkManifestWrite } from "../source-sync.js";
import { loadWorkManifest } from "../work-store.js";
import { commitAtomicFileSet } from "../../utils/atomic-file-set.js";
import { StateManager } from "../../state/manager.js";
import { withWorkMutationScope } from "../../utils/work-mutation-scope.js";
import type { CapabilityRegistry } from "../capability-registry.js";
import { readArtifactRevision } from "../artifact-reader.js";
import type { AtomicFileWrite } from "../../utils/atomic-file-set.js";
const CreateParameters = Type.Object({ workId: Type.String(), profileId: Type.String(), title: Type.String({ minLength: 1 }), intent: Type.String({ minLength: 1 }), language: Type.Optional(Type.String()),
  source: Type.Optional(Type.Object({workId:Type.String(),artifactId:Type.String(),revisionId:Type.Optional(Type.String())},{additionalProperties:false,description:"For adaptation or derivation, pass the verified source text artifact from read/inspect_work here. The host preserves that exact revision for production and review; do not summarize or copy its text into intent."})),
});
export function createProfileWorkTools(root: string, capabilities: CapabilityRegistry): AgentTool<any>[] {
  return [
    { name: "list_work_profiles", label: "List creative profiles", description: "List installed creative profiles and the methods and actions they compose.", parameters: Type.Object({}),
      execute: async () => ({ content: [{ type: "text", text: JSON.stringify(createBuiltInWorkProfileRegistry(root).list()) }], details: { kind: "work_profiles" } }),
    },
    { name: "create_work", label: "Create work from profile", description: "Create and bind a Work using an installed Profile, persist the user's brief, and activate the Profile's production actions for the next step. When deriving from an existing work, supply its source artifact reference.", parameters: CreateParameters,
      execute: async (_id, params) => {
        const profile = createBuiltInWorkProfileRegistry(root).require(params.profileId);
        capabilities.forProfile(profile);
        return withWorkMutationScope(root, params.workId, () => new StateManager(root).acquireBookLock(params.workId), async () => {
          try { await loadWorkManifest(root, params.workId); throw Object.assign(new Error("Work already exists"), { code: "WORK_ALREADY_EXISTS" }); }
          catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
          const writes: AtomicFileWrite[] = [{ relativePath: `works/${params.workId}/source/brief.md`, content: params.intent }];
          const lineage = [];
          if (params.source) {
            const source = await readArtifactRevision({projectRoot:root,workId:params.source.workId,artifactId:params.source.artifactId,revisionId:params.source.revisionId});
            if (!source.revision.contentType.startsWith('text/') && source.revision.contentType !== 'application/json') throw Object.assign(new Error('Derivation source must be a text artifact.'),{code:'SOURCE_NOT_TEXT'});
            writes.push({relativePath:`works/${params.workId}/source/source-material.md`,content:source.bytes});
            lineage.push({relation:'derived-from',sourceWorkId:source.work.id,sourceArtifactId:source.artifact.id,sourceRevisionId:source.revision.id});
          }
          const initial = createInitialWorkManifestWrite({ workId: params.workId, title: params.title, profileId: profile.id, language: params.language ?? "zh", writes, metadata: { intent: params.intent }, lineage });
          await commitAtomicFileSet({ rootDir: root, writes: [...writes, initial.write] });
          return { content: [{ type: "text", text: `Created ${params.title} with profile ${profile.id}.` }], details: { kind: "work_created", workId: params.workId, profileId: profile.id, lineage } };
        });
      },
    },
  ];
}
