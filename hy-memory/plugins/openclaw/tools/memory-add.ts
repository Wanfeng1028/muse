import { Type } from "@sinclair/typebox";
import type { ToolDeps } from "./index.ts";

export function createMemoryAddTool(deps: ToolDeps) {
  const { cfg, provider } = deps;

  return {
    name: "memory_add",
    label: "Memory Add",
    description:
      "Save information to long-term memory via HY Memory. Pass 'text' when YOU (the agent) have already distilled the information into a concrete fact — it is stored directly (reconciled against existing memories, but no re-extraction). Pass 'messages' (raw conversation) only when you want the system to extract facts for you via LLM. Prefer 'text' for known facts. Do NOT use memory_update to store new facts.",
    parameters: Type.Object({
      text: Type.Optional(
        Type.String({
          description:
            "An already-distilled fact to store directly (skips LLM extraction, still reconciled).",
        }),
      ),
      messages: Type.Optional(
        Type.Array(
          Type.Object({
            role: Type.String(),
            content: Type.String(),
          }),
          {
            description:
              "Raw conversation messages to run through LLM fact extraction.",
          },
        ),
      ),
      userId: Type.Optional(Type.String({ description: "User ID scope" })),
      agentId: Type.Optional(Type.String({ description: "Agent ID scope" })),
      sessionId: Type.Optional(
        Type.String({ description: "Session ID scope" }),
      ),
    }),

    async execute(_toolCallId: string, params: Record<string, unknown>) {
      const { text, messages, userId, agentId, sessionId } = params as {
        text?: string;
        messages?: Array<{ role: string; content: string }>;
        userId?: string;
        agentId?: string;
        sessionId?: string;
      };

      if (!text && (!messages || messages.length === 0)) {
        return {
          content: [
            {
              type: "text",
              text: "No content provided. Pass 'text' or 'messages'.",
            },
          ],
          details: { error: "missing_content" },
        };
      }

      const start = Date.now();
      try {
        const scope = {
          user_id: userId || cfg.userId,
          agent_id: agentId || cfg.agentId,
          session_id: sessionId || cfg.sessionId,
        };

        // 'text' = agent already distilled the fact → skip extract, go straight
        // to reconcile. 'messages' = raw conversation → full LLM digest.
        const result =
          messages && messages.length > 0
            ? await provider.add(messages, scope)
            : await provider.addExtracted(text!, scope);

        if (result.success) {
          return {
            content: [
              {
                type: "text",
                text: `Memory stored successfully (id: ${result.memory_id}, elapsed: ${result.elapsed_ms}ms)`,
              },
            ],
            details: { ...result, latency_ms: Date.now() - start },
          };
        } else {
          return {
            content: [
              {
                type: "text",
                text: `Memory storage failed: ${result.error_message ?? "unknown error"}`,
              },
            ],
            details: { ...result, latency_ms: Date.now() - start },
          };
        }
      } catch (err) {
        return {
          content: [
            { type: "text", text: `Memory add failed: ${String(err)}` },
          ],
          details: { error: String(err) },
        };
      }
    },
  };
}
