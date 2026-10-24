import { StoryGraphSchema, type StoryGraph } from "./graph-schema.js";
import type { StoryGraphContentSubmission } from "./tool-schemas.js";
import { validateStoryGraph } from "./validation.js";

export interface MaterializeStoryGraphInput {
  readonly projectId: string;
  readonly title: string;
  readonly content: StoryGraphContentSubmission;
}

export function materializeStoryGraph(input: MaterializeStoryGraphInput): StoryGraph {
  const graph = StoryGraphSchema.parse({
    ...input.content,
    schemaVersion: 1,
    projectId: input.projectId,
    title: input.title,
  });
  const reasons = graphValidationReasons(graph);
  if (reasons.length > 0) {
    throw new Error(`Story graph is not playable: ${reasons.join("; ")}`);
  }
  return graph;
}

function graphValidationReasons(graph: StoryGraph): string[] {
  const startCount = graph.nodes.filter((node) => node.type === "start").length;
  const branchCount = graph.nodes.filter((node) => {
    if (node.choices.length < 2) return false;
    const outcomes = new Set(node.choices.map((choice) => JSON.stringify({
      targetNodeId: choice.targetNodeId,
      condition: choice.condition,
      effects: choice.effects,
    })));
    return outcomes.size > 1;
  }).length;
  const report = validateStoryGraph(graph);
  return [
    ...(startCount !== 1 ? [`expected exactly one start node, received ${startCount}`] : []),
    ...(branchCount < 1 ? ["expected at least one meaningful branching decision"] : []),
    ...(graph.endings.length < 1 ? ["expected at least one ending"] : []),
    ...report.issues.filter((issue) => issue.level === "error").map((issue) => issue.message),
  ];
}
