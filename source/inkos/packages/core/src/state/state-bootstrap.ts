import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

export async function resolveDurableStoryProgress(params: {
  readonly bookDir: string;
}): Promise<number> {
  const chaptersDir = join(params.bookDir, "chapters");
  let indexNumbers: number[];
  let fileNumbers: number[];
  try {
    const [indexRaw, entries] = await Promise.all([
      readFile(join(chaptersDir, "index.json"), "utf-8"),
      readdir(chaptersDir),
    ]);
    const parsed = JSON.parse(indexRaw) as unknown;
    if (!Array.isArray(parsed)) throw new Error("Chapter index must be an array.");
    indexNumbers = parsed.map((entry) => {
      const number = (entry as { number?: unknown })?.number;
      if (!Number.isInteger(number) || (number as number) <= 0) throw new Error("Chapter index contains an invalid number.");
      return number as number;
    });
    fileNumbers = entries.flatMap((entry) => {
      const match = /^(\d+)_/u.exec(entry);
      return match ? [Number.parseInt(match[1]!, 10)] : [];
    });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return 0;
    throw error;
  }
  const indexed = new Set(indexNumbers);
  const files = new Set(fileNumbers);
  const orphaned = [...files].filter((number) => !indexed.has(number));
  const missing = [...indexed].filter((number) => !files.has(number));
  if (orphaned.length > 0 || missing.length > 0) {
    throw new Error(`Chapter index/files disagree (orphaned=${orphaned.join(",") || "none"}; missing=${missing.join(",") || "none"}).`);
  }
  return resolveContiguousChapterPrefix(indexNumbers);
}

export function resolveContiguousChapterPrefix(chapterNumbers: ReadonlyArray<number>): number {
  const chapters = new Set(
    chapterNumbers.filter((chapter): chapter is number => Number.isInteger(chapter) && chapter > 0),
  );
  let contiguousChapter = 0;
  while (chapters.has(contiguousChapter + 1)) contiguousChapter += 1;
  return contiguousChapter;
}
