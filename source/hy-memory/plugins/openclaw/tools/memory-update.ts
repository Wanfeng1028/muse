import { Type } from "@sinclair/typebox";
import type { ToolDeps } from "./index.ts";

export function createMemoryUpdateTool(deps: ToolDeps) {
  const { provider } = deps;

  return {
    name: "memory_update",
    label: "Memory Update",
    description: "Update an existing memory's content. Atomic, preserves history. IMPORTANT: memoryId is a UUID that must be obtained by calling memory_search first. Do NOT guess or fabricate the memoryId. Do NOT use this tool to respond to user requests like 'modify my memory' or 'change memory X to Y' — memory content should only be managed by the system, not directly edited by users. The only valid use case is partial deletion: when a user delete request targets only part of an existing memory and the remaining content after removal is still a complete, meaningful memory, pass the remaining text as the new content. Do NOT use memory_update to store new facts or when the remaining content would be incomplete or meaningless.",
    parameters: Type.Object({
      memoryId: Type.String({ description: "The memory ID to update (UUID format, obtain via memory_search)" }),
      text: Type.String({ description: "The new text (replaces old)" }),
    }),

    async execute(_toolCallId: string, params: Record<string, unknown>) {
      const { memoryId, text } = params as { memoryId: string; text: string };
      try {
        const result = await provider.update(memoryId, text);
        if (result.success) {
          return {
            content: [{ type: "text", text: `Updated memory ${memoryId}.` }],
            details: { action: "updated", id: memoryId },
          };
        }
        return {
          content: [{ type: "text", text: `Update failed: ${result.error_message ?? "unknown"}` }],
          details: { error: result.error_message },
        };
      } catch (err) {
        return {
          content: [{ type: "text", text: `Memory update failed: ${String(err)}` }],
          details: { error: String(err) },
        };
      }
    },
  };
}
