function textFromContentParts(content: unknown): string {
  if (!Array.isArray(content)) return "";

  return content
    .map((part) => {
      if (!part || typeof part !== "object") return "";
      const item = part as Record<string, unknown>;
      return item.type === "text" && typeof item.text === "string" ? item.text : "";
    })
    .filter(Boolean)
    .join("\n");
}

/** Model observations carry control facts; the author sees their display text. */
export function toolResultDisplayText(text: string): string {
  try {
    const observation = JSON.parse(text);
    if (observation?.status === "success" && typeof observation.summary === "string"
      && Array.isArray(observation.artifacts) && Array.isArray(observation.observations)
      && observation.facts && typeof observation.facts === "object") {
      return typeof observation.content === "string" ? observation.content : observation.summary;
    }
  } catch { /* Ordinary source text is already a display value. */ }
  return text;
}

export function summarizeToolResult(result: unknown): string {
  let text = "";

  if (typeof result === "string") {
    text = result;
  } else if (result && typeof result === "object") {
    const record = result as Record<string, unknown>;
    const details = record.details as { displayText?: unknown } | undefined;
    if (typeof details?.displayText === "string") return details.displayText;
    if (typeof record.content === "string") text = record.content;
    else text = textFromContentParts(record.content);
    if (!text && typeof record.text === "string") text = record.text;
    if (!text && typeof record.message === "string") text = record.message;
  }

  if (!text) {
    if (result === undefined || result === null) return "";
    try {
      text = JSON.stringify(result);
    } catch {
      text = "";
    }
  }

  return toolResultDisplayText(text);
}
