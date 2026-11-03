import type {
  ChapterTrace,
  ContextPackage,
} from "../models/input-governance.js";
import { estimateTextTokens } from "../llm/provider.js";
import {
  ChapterTraceSchema,
} from "../models/input-governance.js";
import type { PlanChapterOutput } from "../agents/planner.js";

export function buildGovernedTrace(params: {
  readonly chapterNumber: number;
  readonly plan: PlanChapterOutput;
  readonly contextPackage: ContextPackage;
  readonly composerInputs: ReadonlyArray<string>;
  readonly notes?: ReadonlyArray<string>;
  readonly compression?: ChapterTrace["compression"];
  readonly retrieval?: ChapterTrace["retrieval"];
}): ChapterTrace {
  const protectedEntries = params.contextPackage.selectedContext.filter((entry) =>
    isProtectedContextSource(entry),
  );
  const compressibleEntries = params.contextPackage.selectedContext.filter((entry) =>
    !isProtectedContextSource(entry),
  );
  const protectedTokens = sumContextTokens(protectedEntries);
  const compressibleTokens = sumContextTokens(compressibleEntries);

  return ChapterTraceSchema.parse({
    chapter: params.chapterNumber,
    plannerInputs: params.plan.plannerInputs,
    composerInputs: params.composerInputs,
    selectedSources: params.contextPackage.selectedContext.map((entry) => entry.source),
    contextTiers: {
      protectedSources: protectedEntries.map((entry) => entry.source),
      compressibleSources: compressibleEntries.map((entry) => entry.source),
    },
    tokenBudget: {
      protectedTokens,
      compressibleTokens,
      totalSelectedTokens: protectedTokens + compressibleTokens,
    },
    ...(params.compression ? { compression: params.compression } : {}),
    ...(params.retrieval ? { retrieval: params.retrieval } : {}),
    notes: params.notes ?? [],
  });
}

export function isProtectedContextSource(input: ContextPackage["selectedContext"][number]): boolean {
  return input.protection === "protected";
}

function sumContextTokens(entries: ReadonlyArray<ContextPackage["selectedContext"][number]>): number {
  return entries.reduce((total, entry) => total + estimateContextSourceTokens(entry), 0);
}

function estimateContextSourceTokens(entry: ContextPackage["selectedContext"][number]): number {
  return estimateTextTokens([entry.source, entry.reason, entry.excerpt].filter(Boolean).join("\n"));
}
