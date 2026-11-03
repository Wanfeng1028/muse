import { describe, expect, it } from "vitest";
import { analyzeDetectionInsights } from "../agents/detection-insights.js";
import type { DetectionHistoryEntry } from "../models/detection.js";

describe("detection observations", () => {
  it("summarizes the latest observation per chapter without a pass state", () => {
    const history: DetectionHistoryEntry[] = [
      { chapterNumber: 1, timestamp: "2026-01-01T00:00:00Z", provider: "custom", score: 0.8, action: "detect", attempt: 0 },
      { chapterNumber: 1, timestamp: "2026-01-01T00:01:00Z", provider: "custom", score: 0.4, action: "rewrite", attempt: 1 },
      { chapterNumber: 2, timestamp: "2026-01-02T00:00:00Z", provider: "custom", score: 0.3, action: "detect", attempt: 0 },
    ];

    expect(analyzeDetectionInsights(history)).toEqual({
      totalObservations: 3,
      avgLatestScore: 0.35,
      chapterBreakdown: [
        { chapterNumber: 1, latestScore: 0.4, observationCount: 2 },
        { chapterNumber: 2, latestScore: 0.3, observationCount: 1 },
      ],
    });
  });

  it("returns an empty observation set", () => {
    expect(analyzeDetectionInsights([])).toEqual({
      totalObservations: 0,
      avgLatestScore: 0,
      chapterBreakdown: [],
    });
  });
});
