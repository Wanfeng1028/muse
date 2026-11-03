import type { DetectionHistoryEntry, DetectionStats } from "../models/detection.js";

export function analyzeDetectionInsights(
  history: ReadonlyArray<DetectionHistoryEntry>,
): DetectionStats {
  const grouped = new Map<number, DetectionHistoryEntry[]>();
  for (const entry of history) {
    grouped.set(entry.chapterNumber, [...(grouped.get(entry.chapterNumber) ?? []), entry]);
  }
  const chapterBreakdown = [...grouped.entries()]
    .map(([chapterNumber, entries]) => {
      const latest = [...entries].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).at(-1);
      return {
        chapterNumber,
        latestScore: latest?.score ?? 0,
        observationCount: entries.length,
      };
    })
    .sort((a, b) => a.chapterNumber - b.chapterNumber);
  const avgLatestScore = chapterBreakdown.length > 0
    ? chapterBreakdown.reduce((sum, item) => sum + item.latestScore, 0) / chapterBreakdown.length
    : 0;
  return {
    totalObservations: history.length,
    avgLatestScore: Math.round(avgLatestScore * 1000) / 1000,
    chapterBreakdown,
  };
}
