import { estimateTextTokens } from "../llm/provider.js";
import type { WorkManifest, WorkProfile } from "./contracts.js";

export type ContextProtection = "protected" | "compressible";

export interface ContextFragment {
  readonly id: string;
  readonly source: string;
  readonly content: string;
  readonly protection: ContextProtection;
  readonly priority: number;
  readonly relevance?: number;
  readonly pointer?: string;
}

export interface ContextRecipe {
  readonly id: string;
  readonly sourceIds: ReadonlyArray<string>;
}

export interface ContextLoadRequest {
  readonly projectRoot: string;
  readonly work: WorkManifest | null;
  readonly profile: WorkProfile;
  readonly actionId: string;
  readonly intent: string;
  readonly signal?: AbortSignal;
}

export interface ContextSourceProvider {
  readonly id: string;
  load(request: ContextLoadRequest): Promise<ReadonlyArray<ContextFragment>>;
}

export interface SemanticContextCompileRequest {
  readonly recipeId: string;
  readonly intent: string;
  readonly maxTokens: number;
  readonly fragments: ReadonlyArray<ContextFragment>;
  readonly signal?: AbortSignal;
}

export interface SemanticContextCompileResult {
  readonly content: string;
  readonly sourceIds: ReadonlyArray<string>;
}

export type SemanticContextCompiler = (
  request: SemanticContextCompileRequest,
) => Promise<SemanticContextCompileResult>;

export interface CompiledContextTrace {
  readonly recipeId: string;
  readonly budgetTokens: number;
  readonly protectedTokens: number;
  readonly compressibleTokens: number;
  readonly finalTokens: number;
  readonly protectedSourceIds: ReadonlyArray<string>;
  readonly compressibleSourceIds: ReadonlyArray<string>;
  readonly compiledSourceIds: ReadonlyArray<string>;
  readonly compressionTriggered: boolean;
}

export interface CompiledContext {
  readonly markdown: string;
  readonly fragments: ReadonlyArray<ContextFragment>;
  readonly trace: CompiledContextTrace;
}

export class ProtectedContextOverflowError extends Error {
  constructor(readonly protectedTokens: number, readonly budgetTokens: number) {
    super(`Protected context exceeds budget: ${protectedTokens}/${budgetTokens} tokens`);
    this.name = "ProtectedContextOverflowError";
  }
}

export class ContextCompilationRequiredError extends Error {
  constructor(readonly totalTokens: number, readonly budgetTokens: number) {
    super(`Context requires semantic compilation: ${totalTokens}/${budgetTokens} tokens`);
    this.name = "ContextCompilationRequiredError";
  }
}

export class ContextSourceRegistry {
  private readonly providers = new Map<string, ContextSourceProvider>();

  register(provider: ContextSourceProvider): void {
    if (this.providers.has(provider.id)) throw new Error(`Context source already registered: ${provider.id}`);
    this.providers.set(provider.id, provider);
  }

  require(id: string): ContextSourceProvider {
    const provider = this.providers.get(id);
    if (!provider) throw new Error(`Unknown context source: ${id}`);
    return provider;
  }
}

export async function compileContext(input: {
  readonly recipe: ContextRecipe;
  readonly sources: ContextSourceRegistry;
  readonly request: ContextLoadRequest;
  readonly budgetTokens: number;
  readonly compiler?: SemanticContextCompiler;
}): Promise<CompiledContext> {
  if (!Number.isInteger(input.budgetTokens) || input.budgetTokens <= 0) {
    throw new Error(`Context budget must be a positive integer: ${input.budgetTokens}`);
  }
  if (input.request.signal?.aborted) throw input.request.signal.reason;
  const loaded = await Promise.all(input.recipe.sourceIds.map((id) => input.sources.require(id).load(input.request)));
  const fragments = dedupeFragments(loaded.flat());
  const protectedFragments = sortFragments(fragments.filter((fragment) => fragment.protection === "protected"));
  const compressibleFragments = sortFragments(fragments.filter((fragment) => fragment.protection === "compressible"));
  const protectedTokens = estimateFragments(protectedFragments);
  const compressibleTokens = estimateFragments(compressibleFragments);
  const totalTokens = protectedTokens + compressibleTokens;
  if (protectedTokens > input.budgetTokens) {
    throw new ProtectedContextOverflowError(protectedTokens, input.budgetTokens);
  }
  if (totalTokens <= input.budgetTokens) {
    return buildResult({
      recipeId: input.recipe.id,
      budgetTokens: input.budgetTokens,
      protectedFragments,
      compressibleFragments,
      protectedTokens,
      compressibleTokens,
      finalFragments: [...protectedFragments, ...compressibleFragments],
      compiledSourceIds: [],
      compressionTriggered: false,
    });
  }
  if (!input.compiler) throw new ContextCompilationRequiredError(totalTokens, input.budgetTokens);
  const availableTokens = input.budgetTokens - protectedTokens;
  const compiled = await input.compiler({
    recipeId: input.recipe.id,
    intent: input.request.intent,
    maxTokens: availableTokens,
    fragments: compressibleFragments,
    signal: input.request.signal,
  });
  const content = compiled.content.trim();
  if (!content) throw new Error("Semantic context compiler returned empty content");
  const knownIds = new Set(compressibleFragments.map((fragment) => fragment.id));
  const sourceIds = [...new Set(compiled.sourceIds)];
  if (sourceIds.some((id) => !knownIds.has(id))) {
    throw new Error("Semantic context compiler returned an unknown source id");
  }
  const compiledFragment: ContextFragment = {
    id: `compiled-${input.recipe.id}`,
    source: `compiled:${input.recipe.id}`,
    content,
    protection: "compressible",
    priority: 0,
    pointer: sourceIds.join(", "),
  };
  const finalFragments = [...protectedFragments, compiledFragment];
  const finalTokens = estimateFragments(finalFragments);
  if (finalTokens > input.budgetTokens) {
    throw new Error(`Compiled context still exceeds budget: ${finalTokens}/${input.budgetTokens} tokens`);
  }
  return buildResult({
    recipeId: input.recipe.id,
    budgetTokens: input.budgetTokens,
    protectedFragments,
    compressibleFragments,
    protectedTokens,
    compressibleTokens,
    finalFragments,
    compiledSourceIds: sourceIds,
    compressionTriggered: true,
  });
}

function buildResult(input: {
  readonly recipeId: string;
  readonly budgetTokens: number;
  readonly protectedFragments: ReadonlyArray<ContextFragment>;
  readonly compressibleFragments: ReadonlyArray<ContextFragment>;
  readonly protectedTokens: number;
  readonly compressibleTokens: number;
  readonly finalFragments: ReadonlyArray<ContextFragment>;
  readonly compiledSourceIds: ReadonlyArray<string>;
  readonly compressionTriggered: boolean;
}): CompiledContext {
  const finalTokens = estimateFragments(input.finalFragments);
  return {
    markdown: input.finalFragments.map(renderFragment).join("\n\n"),
    fragments: input.finalFragments,
    trace: {
      recipeId: input.recipeId,
      budgetTokens: input.budgetTokens,
      protectedTokens: input.protectedTokens,
      compressibleTokens: input.compressibleTokens,
      finalTokens,
      protectedSourceIds: input.protectedFragments.map((fragment) => fragment.id),
      compressibleSourceIds: input.compressibleFragments.map((fragment) => fragment.id),
      compiledSourceIds: input.compiledSourceIds,
      compressionTriggered: input.compressionTriggered,
    },
  };
}

function renderFragment(fragment: ContextFragment): string {
  return [
    `## ${fragment.source}`,
    fragment.pointer ? `Source pointer: ${fragment.pointer}` : "",
    fragment.content,
  ].filter(Boolean).join("\n");
}

function estimateFragments(fragments: ReadonlyArray<ContextFragment>): number {
  return fragments.reduce((total, fragment) => total + estimateTextTokens(renderFragment(fragment)), 0);
}

function sortFragments(fragments: ReadonlyArray<ContextFragment>): ContextFragment[] {
  return [...fragments].sort((left, right) => (
    (right.priority - left.priority)
    || ((right.relevance ?? 0) - (left.relevance ?? 0))
    || left.id.localeCompare(right.id)
  ));
}

function dedupeFragments(fragments: ReadonlyArray<ContextFragment>): ContextFragment[] {
  const byId = new Map<string, ContextFragment>();
  for (const fragment of fragments) {
    if (!fragment.id.trim()) throw new Error("Context fragment id cannot be empty");
    if (byId.has(fragment.id)) throw new Error(`Duplicate context fragment id: ${fragment.id}`);
    byId.set(fragment.id, fragment);
  }
  return [...byId.values()];
}
