import type { StoryGraph } from "./graph-schema.js";
import { enumerateRuntimePaths } from "./paths.js";

export function analyzePathDistribution(graph: StoryGraph): {
  total: number;
  truncated: boolean;
  byEnding: Record<string, number>;
  lengthHistogram: Record<number, number>;
} {
  const { paths, truncated } = enumerateRuntimePaths(graph);
  const byEnding: Record<string, number> = {};
  const lengthHistogram: Record<number, number> = {};
  for (const path of paths) {
    const ending = path.endingId ?? "(dead-end)";
    byEnding[ending] = (byEnding[ending] ?? 0) + 1;
    lengthHistogram[path.length] = (lengthHistogram[path.length] ?? 0) + 1;
  }
  return { total: paths.length, truncated, byEnding, lengthHistogram };
}
