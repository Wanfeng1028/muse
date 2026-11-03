import { readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { z } from "zod";
import type { PlanChapterOutput } from "../agents/planner.js";
import {
  ChapterIntentSchema,
  ChapterMemoSchema,
  type ChapterIntent,
} from "../models/input-governance.js";

/**
 * The typed JSON cache is authoritative. The sibling intent Markdown is only
 * a human-readable projection and is never parsed back into runtime state.
 */

const PersistedPlanSchema = z.object({
  version: z.literal(2),
  intent: ChapterIntentSchema,
  memo: ChapterMemoSchema,
  plannerInputs: z.array(z.string()),
});

function planPath(bookDir: string, chapterNumber: number): string {
  const runtimeDir = join(bookDir, "story", "runtime");
  const padded = String(chapterNumber).padStart(4, "0");
  return join(runtimeDir, `chapter-${padded}.plan.json`);
}

function intentPath(bookDir: string, chapterNumber: number): string {
  const runtimeDir = join(bookDir, "story", "runtime");
  const padded = String(chapterNumber).padStart(4, "0");
  return join(runtimeDir, `chapter-${padded}.intent.md`);
}

export async function savePersistedPlan(
  bookDir: string,
  plan: PlanChapterOutput,
): Promise<void> {
  const value = PersistedPlanSchema.parse({
    version: 2,
    intent: plan.intent,
    memo: plan.memo,
    plannerInputs: plan.plannerInputs,
  });
  await writeFile(planPath(bookDir, plan.memo.chapter), `${JSON.stringify(value, null, 2)}\n`, "utf-8");
}

export async function loadPersistedPlan(
  bookDir: string,
  chapterNumber: number,
): Promise<PlanChapterOutput | null> {
  let raw: string;
  try {
    raw = await readFile(planPath(bookDir, chapterNumber), "utf-8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }

  const persisted: z.infer<typeof PersistedPlanSchema> = PersistedPlanSchema.parse(JSON.parse(raw));
  if (persisted.memo.chapter !== chapterNumber || persisted.intent.chapter !== chapterNumber) {
    throw new Error(`Persisted plan chapter identity does not match chapter ${chapterNumber}.`);
  }

  let intentMarkdown = persisted.memo.body;
  try {
    intentMarkdown = await readFile(intentPath(bookDir, chapterNumber), "utf-8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }

  return {
    intent: persisted.intent,
    memo: persisted.memo,
    intentMarkdown,
    plannerInputs: persisted.plannerInputs,
    runtimePath: intentPath(bookDir, chapterNumber),
  };
}

export function relativeToBookDir(bookDir: string, absolutePath: string): string {
  return relative(bookDir, absolutePath).replaceAll("\\", "/");
}
