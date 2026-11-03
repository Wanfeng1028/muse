/**
 * Detection observation runner. Scores are recorded but never mutate prose.
 */

import type { DetectionConfig } from "../models/project.js";
import type { DetectionHistoryEntry } from "../models/detection.js";
import { detectAIContent, type DetectionResult } from "../agents/detector.js";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

export interface DetectChapterResult {
  readonly chapterNumber: number;
  readonly detection: DetectionResult;
}

export async function detectChapter(
  config: DetectionConfig,
  content: string,
  chapterNumber: number,
  bookDir?: string,
): Promise<DetectChapterResult> {
  const detection = await detectAIContent(config, content);
  if (bookDir) {
    await recordHistory(bookDir, {
      chapterNumber,
      timestamp: detection.detectedAt,
      provider: detection.provider,
      score: detection.score,
      action: "detect",
      attempt: 0,
    });
  }
  return {
    chapterNumber,
    detection,
  };
}

/** Append an entry to detection_history.json. */
async function recordHistory(
  bookDir: string,
  entry: DetectionHistoryEntry,
): Promise<void> {
  const historyPath = join(bookDir, "story", "detection_history.json");
  let history: DetectionHistoryEntry[] = [];

  try {
    const raw = await readFile(historyPath, "utf-8");
    history = JSON.parse(raw);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }

  history.push(entry);

  await mkdir(join(bookDir, "story"), { recursive: true });
  await writeFile(historyPath, JSON.stringify(history, null, 2), "utf-8");
}

/** Load detection history from disk. */
export async function loadDetectionHistory(
  bookDir: string,
): Promise<ReadonlyArray<DetectionHistoryEntry>> {
  const historyPath = join(bookDir, "story", "detection_history.json");
  try {
    const raw = await readFile(historyPath, "utf-8");
    return JSON.parse(raw);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}
