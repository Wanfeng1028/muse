import { Type } from "@sinclair/typebox";
import type { ToolDeps } from "./index.ts";

export function createMemorySearchTool(deps: ToolDeps) {
  const { cfg, provider } = deps;

  return {
    name: "memory_search",
    label: "Memory Search",
    description:
      "Search through long-term memories stored in HY Memory. Returns memory IDs and content ranked by semantic similarity. Use this to find a memoryId before calling memory_update or memory_delete. For user delete requests, call memory_search first, inspect the returned content, then decide: if removing the target content still leaves a complete memory, use memory_update with the remaining text; otherwise use memory_delete.",
    parameters: Type.Object({
      query: Type.String({ description: "Search query" }),
      limit: Type.Optional(
        Type.Number({ description: `Max results (default: ${cfg.topK})` }),
      ),
      userId: Type.Optional(
        Type.String({ description: "User ID to scope search" }),
      ),
    }),

    async execute(_toolCallId: string, params: Record<string, unknown>) {
      const { query, limit, userId } = params as {
        query: string;
        limit?: number;
        userId?: string;
      };

      const start = Date.now();
      try {
        const uid = (userId as string) || cfg.userId;
        const result = await provider.search(query, {
          user_id: uid,
          limit: limit ?? cfg.topK,
          min_score: cfg.searchThreshold,
        });

        if (!result.memories || result.memories.length === 0) {
          return {
            content: [{ type: "text", text: "No relevant memories found." }],
            details: { count: 0 },
          };
        }

        const text = result.memories
          .map(
            (r, i) =>
              `${i + 1}. ${r.content} (score: ${((r.score ?? 0) * 100).toFixed(0)}%, layer: ${r.layer ?? "?"}, id: ${r.memory_id})`,
          )
          .join("\n");

        return {
          content: [
            {
              type: "text",
              text: `Found ${result.memories.length} memories:\n\n${text}`,
            },
          ],
          details: {
            count: result.memories.length,
            memories: result.memories,
            elapsed_ms: Date.now() - start,
          },
        };
      } catch (err) {
        return {
          content: [
            { type: "text", text: `Memory search failed: ${String(err)}` },
          ],
          details: { error: String(err) },
        };
      }
    },
  };
}
