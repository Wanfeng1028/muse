import { Command } from "commander";
import { StateManager, formatLengthCount, resolveLengthCountingMode } from "@actalk/inkos-core";
import { findProjectRoot, log, logError } from "../utils.js";

export const reviewCommand = new Command("review")
  .description("Show persisted review observations")
  .argument("[book-id]", "Book ID; omit to inspect all works")
  .option("--json", "Output JSON")
  .action(async (bookId: string | undefined, opts) => {
    try {
      const root = findProjectRoot();
      const state = new StateManager(root);
      const rows: unknown[] = [];
      for (const id of bookId ? [bookId] : await state.listBooks()) {
        const [book, chapters] = await Promise.all([
          state.loadBookConfig(id),
          state.loadChapterIndex(id),
        ]);
        const countingMode = resolveLengthCountingMode(book.language);
        for (const chapter of chapters.filter((item) => item.observations.length > 0)) {
          const row = {
            bookId: id,
            chapter: chapter.number,
            title: chapter.title,
            wordCount: chapter.wordCount,
            observations: chapter.observations,
          };
          rows.push(row);
          if (!opts.json) {
            log(`\n${book.title} · Ch.${chapter.number} "${chapter.title}" · ${formatLengthCount(chapter.wordCount, countingMode)}`);
            for (const observation of chapter.observations) {
              log(`  ${observation.code}: ${observation.summary}`);
            }
          }
        }
      }
      if (opts.json) log(JSON.stringify({ observations: rows }, null, 2));
      else if (rows.length === 0) log("No review observations.");
    } catch (error) {
      if (opts.json) log(JSON.stringify({ error: String(error) }));
      else logError(`Failed to load review observations: ${error}`);
      process.exit(1);
    }
  });
