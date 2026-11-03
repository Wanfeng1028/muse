/**
 * 原版来源：sdk/src/openagents/mods/coordination/task_delegation/capability_matcher.py
 * 原版许可证：Apache-2.0
 * 本包代码沿用仓库 MIT 许可
 * 设计移植：将 Python 中的 DEFAULT_MATCHING_PROMPT 与 parse_llm_response 积植为 TypeScript 纯函数
 */
export interface LlmMatchingResult {
  matches: boolean;
  confidence: number;
  reason: string;
}

export function buildLlmMatchingPrompt(capabilityDescription: string, agentId: string, capabilities: unknown): string {
  return [
    "You are an agent capability matcher. Given a task requirement and an agent's capabilities, determine if the agent can handle the task.",
    "",
    `,Task Requirement: ${capabilityDescription}`,
    "",
    `Agent: ${agentId}`,
    "",
    `Capabilities: ${JSON.stringify(capabilities, null, 2)}`,
    "",
    'Respond with JSON only (no markdown, no explanation): {"matches": true, "confidence": 0.8, "reason": "brief explanation"}',
    "",
    "The confidence should be between 0.0 and 1.0, where:",
    "- 1.0 = perfect match, agent has all required capabilities",
    "- 0.7-0.9 = good match, agent can likely handle the task",
    "- 0.4-0.6 = partial match, agent may be able to help",
    "- 0.0-0.3 = poor match, agent lacks key capabilities",
    "",
    'Only set "matches" to true if confidence >= 0.5.'
  ].join("\n");
}

export function parseLlmMatchingResponse(response: string): LlmMatchingResult {
  const trimmed = response.trim();
  let jsonString = trimmed;

  if (trimmed.startsWith("```")) {
    const lines = trimmed.split("\n");
    const innerLines: string[] = [];
    let inside = false;
    for (const line of lines) {
      if (line.trimStart().startsWith("```")) {
        inside = !inside;
        continue;
      }
      if (inside) {
        innerLines.push(line);
      }
    }
    jsonString = innerLines.join("\n");
  }

  try {
    const parsed = JSON.parse(jsonString);
    return {
      matches: typeof parsed.matches === "boolean" ? parsed.matches : false,
      confidence: typeof parsed.confidence === "number" ? parsed.confidence : 0.5,
      reason: typeof parsed.reason === "string" ? parsed.reason : ""
    };
  } catch {
    return {
      matches: false,
      confidence: 0,
      reason: "Failed to parse LLM response"
    };
  }
}