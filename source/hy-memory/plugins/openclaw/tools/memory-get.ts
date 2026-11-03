import { Type } from "@sinclair/typebox";
import type { ToolDeps } from "./index.ts";

export function createMemoryGetTool(deps: ToolDeps) {
  const { provider } = deps;

  return {
    name: "memory_get",
    label: "Memory Get",
    description: "Retrieve a specific memory by its ID from HY Memory. Requires a valid memoryId obtained from memory_search or memory_list.",
    parameters: Type.Object({
      memoryId: Type.String({ description: "The memory ID to retrieve" }),
    }),

    async execute(_toolCallId: string, params: Record<string, unknown>) {
      const { memoryId } = params as { memoryId: string };
      try {
        const memory = await provider.get(memoryId);
        if (!memory) {
          return {
            content: [{ type: "text", text: `Memory ${memoryId} not found.` }],
            details: { error: "not_found" },
          };
        }
        return {
          content: [
            {
              type: "text",
              text: `Memory ${memory.memory_id}:\n${memory.content}\n\nLayer: ${memory.layer ?? "unknown"}`,
            },
          ],
          details: { memory },
        };
      } catch (err) {
        return {
          content: [
            { type: "text", text: `Memory get failed: ${String(err)}` },
          ],
          details: { error: String(err) },
        };
      }
    },
  };
}
