import {
  RuntimeStateDeltaSchema,
  type HookRecord,
  type NewHookCandidate,
  type RuntimeStateDelta,
} from "../models/runtime-state.js";

export interface HookArbiterDecision {
  readonly action: "created";
  readonly reason: string;
  readonly hookId?: string;
  readonly candidate: NewHookCandidate;
}

type PendingHookCandidate = NewHookCandidate;

export function arbitrateRuntimeStateDeltaHooks(params: {
  readonly hooks: ReadonlyArray<HookRecord>;
  readonly delta: RuntimeStateDelta;
  readonly allowNewHooks?: boolean;
}): {
  readonly resolvedDelta: RuntimeStateDelta;
  readonly decisions: ReadonlyArray<HookArbiterDecision>;
} {
  const delta = RuntimeStateDeltaSchema.parse(params.delta);
  const workingHooks = params.hooks.map((hook) => ({ ...hook }));
  const knownHookIds = new Set(workingHooks.map((hook) => hook.hookId));
  const upsertsById = new Map<string, HookRecord>();
  const mentions = uniqueHookIds(delta.hookOps.mention, "mention");
  const resolves = uniqueHookIds(delta.hookOps.resolve, "resolve");
  const defers = uniqueHookIds(delta.hookOps.defer, "defer");
  const decisions: HookArbiterDecision[] = [];

  for (const hook of delta.hookOps.upsert) {
    if (knownHookIds.has(hook.hookId)) {
      const normalized = { ...hook };
      upsertsById.set(normalized.hookId, normalized);
      replaceWorkingHook(workingHooks, normalized);
      continue;
    }

    throw new Error(`Hook upsert references unknown hook id: ${hook.hookId}. Submit a newHookCandidate instead.`);
  }

  if (params.allowNewHooks === false && delta.newHookCandidates.length > 0) {
    throw new Error("This settlement forbids new hooks, but the model submitted newHookCandidates.");
  }
  for (const candidate of delta.newHookCandidates) {
    if (!candidate.type.trim() || !candidate.expectedPayoff.trim()) {
      throw new Error("New hook candidates require non-empty type and expectedPayoff.");
    }

    const created = createCanonicalHook({
      candidate,
      chapter: delta.chapter,
      existingIds: new Set([
        ...workingHooks.map((hook) => hook.hookId),
        ...upsertsById.keys(),
      ]),
    });
    upsertsById.set(created.hookId, created);
    workingHooks.push(created);
    decisions.push({
      action: "created",
    reason: "admit",
      hookId: created.hookId,
      candidate,
    });
  }

  const resolvedDelta = RuntimeStateDeltaSchema.parse({
    ...delta,
    hookOps: {
      upsert: [...upsertsById.values()].sort(sortHooks),
      mention: mentions
        .filter((hookId) => !upsertsById.has(hookId))
        .filter((hookId) => !resolves.includes(hookId))
        .filter((hookId) => !defers.includes(hookId))
        .sort(),
      resolve: resolves,
      defer: defers,
    },
    newHookCandidates: [],
  });

  return {
    resolvedDelta,
    decisions,
  };
}

function createCanonicalHook(params: {
  readonly candidate: PendingHookCandidate;
  readonly chapter: number;
  readonly existingIds: ReadonlySet<string>;
}): HookRecord {
  return {
    hookId: buildCanonicalHookId(params.candidate, params.existingIds),
    startChapter: params.chapter,
    type: params.candidate.type.trim(),
    status: "open",
    lastAdvancedChapter: params.chapter,
    expectedPayoff: params.candidate.expectedPayoff.trim(),
    notes: params.candidate.notes.trim(),
  };
}

function buildCanonicalHookId(
  _candidate: PendingHookCandidate,
  existingIds: ReadonlySet<string>,
): string {
  const base = "hook";
  let next = base;
  let suffix = 2;

  while (existingIds.has(next)) {
    next = `${base}-${suffix}`;
    suffix += 1;
  }

  return next;
}

function replaceWorkingHook(workingHooks: HookRecord[], hook: HookRecord): void {
  const index = workingHooks.findIndex((candidate) => candidate.hookId === hook.hookId);
  if (index >= 0) {
    workingHooks[index] = hook;
    return;
  }

  workingHooks.push(hook);
}

function sortHooks(left: HookRecord, right: HookRecord): number {
  return left.startChapter - right.startChapter
    || left.lastAdvancedChapter - right.lastAdvancedChapter
    || left.hookId.localeCompare(right.hookId);
}

function uniqueHookIds(values: ReadonlyArray<string>, operation: string): string[] {
  const normalized = values.map((value) => value.trim());
  if (normalized.some((value) => !value)) throw new Error(`Hook ${operation} contains an empty id.`);
  if (new Set(normalized).size !== normalized.length) throw new Error(`Hook ${operation} contains duplicate ids.`);
  return normalized;
}
