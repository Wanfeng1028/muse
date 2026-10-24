import type { LLMClient } from "./provider.js";
import { estimateTextTokens } from "./provider.js";

export function semanticInputBudget(
  client: LLMClient,
  options: { readonly reservedOutputTokens: number; readonly promptOverheadTokens?: number },
): number | undefined {
  const contextWindow = client._piModel?.contextWindow;
  if (!contextWindow || !Number.isFinite(contextWindow)) return undefined;
  const overhead = options.promptOverheadTokens ?? 4096;
  return Math.max(1, contextWindow - options.reservedOutputTokens - overhead);
}

/** Split an over-budget input into a lossless sequence of model-sized chunks. */
export function splitTextByEstimatedTokens(text: string, budgetTokens: number): string[] {
  if (estimateTextTokens(text) <= budgetTokens) return [text];
  const lines = text.match(/[^\n]*\n|[^\n]+$/g) ?? [text];
  const chunks: string[] = [];
  let current = "";

  const flush = () => {
    if (current) chunks.push(current);
    current = "";
  };

  for (const line of lines) {
    if (estimateTextTokens(line) > budgetTokens) {
      flush();
      chunks.push(...splitOversizedUnit(line, budgetTokens));
      continue;
    }
    const candidate = current + line;
    if (current && estimateTextTokens(candidate) > budgetTokens) flush();
    current += line;
  }
  flush();
  return chunks;
}

function splitOversizedUnit(text: string, budgetTokens: number): string[] {
  const chars = Array.from(text);
  const chunks: string[] = [];
  let start = 0;
  while (start < chars.length) {
    let low = start + 1;
    let high = chars.length;
    let end = low;
    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      if (estimateTextTokens(chars.slice(start, mid).join("")) <= budgetTokens) {
        end = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }
    chunks.push(chars.slice(start, end).join(""));
    start = end;
  }
  return chunks;
}
