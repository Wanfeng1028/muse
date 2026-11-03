import { Type } from "@sinclair/typebox";
import type { ToolDeps } from "./index.ts";

export function createMemoryDeleteTool(deps: ToolDeps) {
  const { cfg, provider } = deps;

  return {
    name: "memory_delete",
    label: "Memory Delete",
    description: "Delete a specific memory by ID, or delete all memories for a user (requires confirm: true). When deleting a specific memory, memoryId must be obtained by calling memory_search first. Do NOT guess or fabricate the memoryId. For user delete requests: first call memory_search to find the target memory, then inspect its content. If removing the requested content still leaves a complete, meaningful memory, use memory_update instead (pass the remaining text). Only use memory_delete when the entire memory should be removed, or when removing the target content would leave incomplete/meaningless residual text.",
    parameters: Type.Object({
      memoryId: Type.Optional(Type.String({ description: "Memory ID to delete (UUID format, obtain via memory_search)" })),
      all: Type.Optional(Type.Boolean({ description: "Delete ALL memories. Requires confirm: true." })),
      confirm: Type.Optional(Type.Boolean({ description: "Safety gate for bulk delete" })),
      userId: Type.Optional(Type.String({ description: "User ID scope (for --all)" })),
    }),

    async execute(_toolCallId: string, params: Record<string, unknown>) {
      const { memoryId, all, confirm, userId } = params as {
        memoryId?: string; all?: boolean; confirm?: boolean; userId?: string;
      };

      try {
        if (memoryId) {
          const result = await provider.delete(memoryId);
          return {
            content: [{ type: "text", text: `Memory ${memoryId} deleted.` }],
            details: { action: "deleted", id: memoryId, ...result },
          };
        }

        if (all) {
          if (!confirm) {
            return {
              content: [{ type: "text", text: "Bulk deletion requires confirm: true." }],
              details: { error: "confirmation_required" },
            };
          }
          const uid = userId || cfg.userId;
          const result = await provider.deleteAll({ user_id: uid });
          return {
            content: [{ type: "text", text: `All memories deleted for user "${uid}" (${result.deleted_count} removed).` }],
            details: { action: "deleted_all", ...result },
          };
        }

        return {
          content: [{ type: "text", text: "Provide memoryId or all: true." }],
          details: { error: "missing_param" },
        };
      } catch (err) {
        return {
          content: [{ type: "text", text: `Memory delete failed: ${String(err)}` }],
          details: { error: String(err) },
        };
      }
    },
  };
}
