/** A single detection/rewrite event recorded in detection_history.json. */
export interface DetectionHistoryEntry {
  readonly chapterNumber: number;
  readonly timestamp: string;
  readonly provider: string;
  readonly score: number;
  readonly action: "detect" | "rewrite";
  readonly attempt: number;
}

/** Aggregated detection statistics. */
export interface DetectionStats {
  readonly totalObservations: number;
  readonly avgLatestScore: number;
  readonly chapterBreakdown: ReadonlyArray<{
    readonly chapterNumber: number;
    readonly latestScore: number;
    readonly observationCount: number;
  }>;
}
