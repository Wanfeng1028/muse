import { Command } from "commander";
import { StateManager, computeAnalytics } from "@actalk/inkos-core";
import { loadConfig, findProjectRoot, resolveBookId, log, logError } from "../utils.js";

export const analyticsCommand = new Command("analytics")
  .alias("stats")
  .description("Show analytics and token stats for a book")
  .argument("[book-id]", "Book ID (auto-detected if only one book)")
  .option("--json", "Output JSON")
  .action(async (bookIdArg: string | undefined, opts) => {
    try {
      await loadConfig();
      const root = findProjectRoot();
      const bookId = await resolveBookId(bookIdArg, root);
      const state = new StateManager(root);
      const chapters = await state.loadChapterIndex(bookId);

      const analytics = computeAnalytics(bookId, chapters);

      if (opts.json) {
        log(JSON.stringify(analytics, null, 2));
      } else {
        log(`Analytics for "${bookId}":`);
        log("");
        log(`  Total chapters: ${analytics.totalChapters}`);
        log(`  Total words: ${analytics.totalWords.toLocaleString()}`);
        log(`  Avg words/chapter: ${analytics.avgWordsPerChapter.toLocaleString()}`);
        log(`  Review observations: ${analytics.observationCount}`);
        log(`  Chapters with observations: ${analytics.chaptersWithObservations}`);
        log("");

        if (analytics.tokenStats) {
          log("  Token usage:");
          log(`    Total tokens: ${analytics.tokenStats.totalTokens.toLocaleString()}`);
          log(`    Prompt tokens: ${analytics.tokenStats.totalPromptTokens.toLocaleString()}`);
          log(`    Completion tokens: ${analytics.tokenStats.totalCompletionTokens.toLocaleString()}`);
          log(`    Avg tokens/chapter: ${analytics.tokenStats.avgTokensPerChapter.toLocaleString()}`);
          if (analytics.tokenStats.recentTrend.length > 0) {
            log("    Recent trend:");
            for (const { chapter, totalTokens } of analytics.tokenStats.recentTrend) {
              log(`      Ch.${chapter}: ${totalTokens.toLocaleString()} tokens`);
            }
          }
          log("");
        }

      }
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Analytics failed: ${e}`);
      }
      process.exit(1);
    }
  });
