import type { StoryGraph } from "./graph-schema.js";
import { visibleChoices, applyEffects, initVarState } from "./evaluator.js";
import type { VarState } from "./evaluator.js";

export interface RuntimePath {
  readonly finalState?: VarState;
  readonly nodeIds: readonly string[];
  readonly endingId: string | null;
  readonly length: number;
}

const DEFAULT_MAX_PATHS = 200;
const DEFAULT_MAX_DEPTH = 50;

/** Find an executable, non-repeating route without spending the budget on loop variants. */
export function findSimpleRuntimeRoute(
  graph: StoryGraph,
  options: { endingNodeId?: string; minChoices: number; maxExpansions?: number },
): { route?: RuntimePath; truncated: boolean } {
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  const start = graph.nodes.find(node => node.type === "start");
  let expansions = 0;
  let truncated = false;
  const walk = (id: string, state: VarState, trail: string[]): RuntimePath | undefined => {
    if (trail.includes(id)) return;
    if (++expansions > (options.maxExpansions ?? 100_000)) { truncated = true; return; }
    const node = nodes.get(id);
    if (!node) return;
    const next = [...trail, id];
    if (node.type === "ending") {
      if ((!options.endingNodeId || id === options.endingNodeId) && next.length - 1 >= options.minChoices) {
        return { nodeIds: next, length: next.length, endingId: graph.endings.find(ending => ending.nodeId === id)?.id ?? null, finalState: state };
      }
      return;
    }
    for (const choice of visibleChoices(node, state)) {
      const route = walk(choice.targetNodeId, applyEffects(state, choice.effects), next);
      if (route) return route;
      if (truncated) return;
    }
  };
  return { route: start ? walk(start.id, initVarState(graph.variables), []) : undefined, truncated };
}

function varStateKey(vars: VarState): string {
  return JSON.stringify(Object.keys(vars).sort().map(key => [key, vars[key]]));
}

/** Explore reachable node/state pairs once, including dead ends and state-changing loops. */
export function exploreRuntimeStates(
  graph: StoryGraph,
  options: { maxStates?: number } = {},
): { states: Array<{ nodeId: string; state: VarState; visibleChoiceCount: number }>; truncated: boolean } {
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  const start = graph.nodes.find(node => node.type === "start");
  const states: Array<{ nodeId: string; state: VarState; visibleChoiceCount: number }> = [];
  if (!start) return { states, truncated: false };
  const limit = options.maxStates ?? 10_000;
  const queue = [{ nodeId: start.id, state: initVarState(graph.variables) }];
  const seen = new Set([JSON.stringify([start.id, varStateKey(queue[0]!.state)])]);
  let truncated = false;
  for (let index = 0; index < queue.length; index++) {
    const current = queue[index]!;
    const node = nodes.get(current.nodeId);
    if (!node) continue;
    const choices = node.type === "ending" ? [] : visibleChoices(node, current.state);
    states.push({ ...current, visibleChoiceCount: choices.length });
    for (const choice of choices) {
      const state = applyEffects(current.state, choice.effects);
      const key = JSON.stringify([choice.targetNodeId, varStateKey(state)]);
      if (seen.has(key)) continue;
      if (queue.length >= limit) { truncated = true; continue; }
      seen.add(key);
      queue.push({ nodeId: choice.targetNodeId, state });
    }
  }
  return { states, truncated };
}

export function enumerateRuntimePaths(
  graph: StoryGraph,
  opts?: { maxPaths?: number; maxDepth?: number; includeState?:boolean },
): { paths: RuntimePath[]; truncated: boolean } {
  const maxPaths = opts?.maxPaths ?? DEFAULT_MAX_PATHS;
  const maxDepth = opts?.maxDepth ?? DEFAULT_MAX_DEPTH;
  const nodeById = new Map(graph.nodes.map((n) => [n.id, n]));
  const endingByNodeId = new Map(graph.endings.map((e) => [e.nodeId, e.id]));
  const start = graph.nodes.find((n) => n.type === "start");
  const paths: RuntimePath[] = [];
  let truncated = false;
  if (!start) return { paths, truncated };

  const walk = (nodeId: string, vars: VarState, trail: string[], onPath: Set<string>, depth: number): void => {
    if (paths.length >= maxPaths) { truncated = true; return; }
    if (depth > maxDepth) { truncated = true; return; }
    const visitKey = `${nodeId}\u0000${varStateKey(vars)}`;
    if (onPath.has(visitKey)) return; // No-op cycles are already represented by this exact node+state.
    const nextOnPath = new Set(onPath);
    nextOnPath.add(visitKey);
    const node = nodeById.get(nodeId);
    if (!node) return;
    const nextTrail = [...trail, nodeId];
    if (node.type === "ending") {
      paths.push({ nodeIds: nextTrail, endingId: endingByNodeId.get(nodeId) ?? null, length: nextTrail.length,...(opts?.includeState?{finalState:{...vars}}:{}) });
      return;
    }
    const choices = visibleChoices(node, vars);
    if (choices.length === 0) {
      // dead-end leaf (no ending): record as a terminal path with null ending
      paths.push({ nodeIds: nextTrail, endingId: null, length: nextTrail.length,...(opts?.includeState?{finalState:{...vars}}:{}) });
      return;
    }
    for (const choice of choices) {
      if (paths.length >= maxPaths) { truncated = true; return; }
      const nextVars = applyEffects(vars, choice.effects);
      walk(choice.targetNodeId, nextVars, nextTrail, nextOnPath, depth + 1);
    }
  };

  walk(start.id, initVarState(graph.variables), [], new Set(), 0);
  return { paths, truncated };
}
