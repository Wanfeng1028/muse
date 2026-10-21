import { Type } from "@sinclair/typebox";
import type { ToolDeps } from "./index.ts";

export function createMemoryListTool(deps: ToolDeps) {
  const { cfg, provider } = deps;

  return {
    name: "memory_list",
    label: "Memory List",
    description: "List all stored memories for a user. Returns memory IDs and content. Can be used to browse memories or find a memoryId and decide whether to update or delete a matching memory. For delete requests, inspect the content before choosing memory_update or memory_delete.",
    parameters: Type.Object({
      userId: Type.Optional(Type.String({ description: "User ID (default: configured)" })),
      agentId: Type.Optional(Type.String({ description: "Agent ID filter" })),
      limit: Type.Optional(Type.Number({ description: "Max results (default: 50)" })),
    }),

    async execute(_toolCallId: string, params: Record<string, unknown>) {
      const { userId, agentId, limit } = params as {
        userId?: string; agentId?: string; limit?: number;
      };

      try {
        const result = await provider.list({
          user_id: userId || cfg.userId,
          agent_id: agentId,
          limit: limit ?? 50,
        });

        const payload: Record<string, unknown> = { vdb: result.vdb };
        if (result.graph) {
          payload.graph = result.graph;
        }
        const vdbTotal = result.vdb?.total ?? 0;
        const graphTotal = result.graph?.total ?? 0;

        return {
          content: [{ type: "text", text: JSON.stringify(payload) }],
          details: { vdb_total: vdbTotal, graph_total: graphTotal, payload },
        };
      } catch (err) {
        return {
          content: [{ type: "text", text: `Memory list failed: ${String(err)}` }],
          details: { error: String(err) },
        };
      }
    },
  };
}
