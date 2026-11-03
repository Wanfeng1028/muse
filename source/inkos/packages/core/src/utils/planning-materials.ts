import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

export interface PlanningSeedMaterials {
  readonly authorIntent: string;
  readonly currentFocus: string;
  readonly brief: string;
  readonly previousEndingExcerpt?: string;
}

async function readFileOrDefault(path: string): Promise<string> {
  try {
    return await readFile(path, "utf-8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return "";
    throw error;
  }
}

async function readPreviousEndingExcerpt(
  bookDir: string,
  chapterNumber: number,
): Promise<string | undefined> {
  const previousChapter = chapterNumber - 1;
  if (previousChapter < 1) {
    return undefined;
  }

  const chaptersDir = join(bookDir, "chapters");
  const padded = String(previousChapter).padStart(4, "0");
  try {
    const files = await readdir(chaptersDir);
    const match = files.find((file) => file.startsWith(padded) && file.endsWith(".md"));
    if (!match) {
      return undefined;
    }
    const markdown = await readFile(join(chaptersDir, match), "utf-8");
    const body = markdown
      .split("\n")
      .slice(1)
      .join("\n")
      .trim();
    if (!body) {
      return undefined;
    }
    return body;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

export async function loadPlanningSeedMaterials(params: {
  readonly bookDir: string;
  readonly chapterNumber: number;
}): Promise<PlanningSeedMaterials> {
  const storyDir = join(params.bookDir, "story");
  const sourcePaths = {
    authorIntent: join(storyDir, "author_intent.md"),
    currentFocus: join(storyDir, "current_focus.md"),
    brief: join(storyDir, "brief.md"),
  } as const;
  const [
    authorIntent,
    currentFocus,
    previousEndingExcerpt,
    brief,
  ] = await Promise.all([
    readFileOrDefault(sourcePaths.authorIntent),
    readFileOrDefault(sourcePaths.currentFocus),
    readPreviousEndingExcerpt(params.bookDir, params.chapterNumber),
    readFileOrDefault(sourcePaths.brief),
  ]);

  return {
    authorIntent,
    currentFocus,
    brief,
    previousEndingExcerpt,
  };
}
