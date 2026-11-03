import type { StoryGraph } from "./graph-schema.js";

export function summarizeStoryGraph(graph: StoryGraph): string {
  const lines: string[] = [];
  lines.push(`# 互动影游：${graph.title || graph.projectId}`);
  if (graph.worldAnchor) {
    const w = graph.worldAnchor;
    lines.push(`核心：${w.storyCore} / 主题：${w.theme} / 题材：${w.genre} / 规则：${w.worldRules} / 时长：${w.durationMinutes}分`);
  }
  if (graph.variables.length > 0) {
    lines.push(`变量：${graph.variables.map((v) => v.name).join(", ")}`);
  }
  lines.push("节点：");
  for (const n of graph.nodes) {
    const edges = n.choices.map((c) => `${c.text}→${c.targetNodeId}`).join(", ");
    lines.push(`- ${n.id}[${n.type}] ${n.title}${edges ? ` -> ${edges}` : ""}`);
  }
  return lines.join("\n");
}

export function buildFilmAuthoringContext(graph: StoryGraph): string {
  // A later scene can depend on any earlier clue or conversation, not just an
  // adjacent node. The shared worker context budget handles large graphs.
  return JSON.stringify(graph);
}
