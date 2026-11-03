import { Command } from "commander";
import {
  PipelineRunner,
  StateManager,
  createImportCanonTool,
  createImportChaptersTool,
  executeExplicitCapabilityTool,
} from "@actalk/inkos-core";
import { resolve } from "node:path";
import { loadConfig, buildPipelineConfig, findProjectRoot, resolveBookId, log, logError, resolveCliProfileSkills } from "../utils.js";
import {
  formatImportCanonComplete,
  formatImportCanonStart,
  formatImportChaptersComplete,
  formatImportChaptersResume,
  resolveCliLanguage,
} from "../localization.js";

export const importCommand = new Command("import")
  .description("Import external data into a book");

importCommand
  .command("canon")
  .description("Import parent book's canon for spinoff writing")
  .argument("[target-book-id]", "Target book ID (auto-detected if only one book)")
  .requiredOption("--from <parent-book-id>", "Parent book ID to import canon from")
  .option("--json", "Output JSON")
  .action(async (targetBookIdArg: string | undefined, opts) => {
    try {
      const root = findProjectRoot();
      const targetBookId = await resolveBookId(targetBookIdArg, root);
      const config = await loadConfig();
      const state = new StateManager(root);
      const targetBook = await state.loadBookConfig(targetBookId);
      const language = resolveCliLanguage(targetBook.language);

      const pipeline = new PipelineRunner(buildPipelineConfig(config, root));

      if (!opts.json) log(formatImportCanonStart(language, opts.from, targetBookId));

      await executeExplicitCapabilityTool({
        projectRoot: root,
        binding: { capabilityId: "longform", actionId: "import_canon", profileId: "longform-novel", risk: "recoverable-write" },
        tool: createImportCanonTool(pipeline, targetBookId),
        workId: targetBookId,
        parameters: { parentBookId: opts.from },
      });

      if (opts.json) {
        log(JSON.stringify({
          targetBookId,
          parentBookId: opts.from,
          output: "story/parent_canon.md",
        }, null, 2));
      } else {
        for (const line of formatImportCanonComplete(language)) {
          log(line);
        }
      }
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Canon import failed: ${e}`);
      }
      process.exit(1);
    }
  });

importCommand
  .command("chapters")
  .description("Import existing chapters for continuation writing. Reverse-engineers all truth files.")
  .argument("[book-id]", "Target book ID (auto-detected if only one book)")
  .requiredOption("--from <path>", "Path to a text file (auto-split) or directory of .md/.txt files")
  .option("--split <regex>", "Custom regex for chapter splitting (single-file mode)")
  .option("--resume-from <n>", "Resume from chapter N (for interrupted imports)", parseInt)
  .option("--series", "Treat as a new series (shared universe, independent story) instead of direct continuation")
  .option("--json", "Output JSON")
  .action(async (bookIdArg: string | undefined, opts) => {
    try {
      const root = findProjectRoot();
      const bookId = await resolveBookId(bookIdArg, root);
      const config = await loadConfig();

      const state = new StateManager(root);
      const book = await state.loadBookConfig(bookId);
      const language = resolveCliLanguage(book.language);
      const existingChapterCount = (await state.getNextChapterNumber(bookId)) - 1;
      if (existingChapterCount > 0 && !opts.resumeFrom) {
        throw new Error(
          `Book "${bookId}" already has ${existingChapterCount} chapter(s). ` +
          `Use --resume-from <n> to append, or delete existing chapters first.`
        );
      }

      const fromPath = resolve(opts.from);
      if (!opts.json) {
        log(language === "en"
          ? `Reading chapters from "${fromPath}" for import into "${bookId}".`
          : `正在读取「${fromPath}」，准备导入到「${bookId}」。`);
        if (opts.resumeFrom) {
          log(formatImportChaptersResume(language, opts.resumeFrom));
        }
      }

      const pipeline = new PipelineRunner(buildPipelineConfig(config, root));

      const activatedSkills = await resolveCliProfileSkills(root, "longform-novel", {
        extraSkillIds: ["inkos-story-import"],
      });
      const action = await executeExplicitCapabilityTool({
        projectRoot: root,
        binding: { capabilityId: "longform", actionId: "import_chapters", profileId: "longform-novel", risk: "recoverable-write" },
        tool: createImportChaptersTool(pipeline, bookId, root, { defaultSkills: activatedSkills }),
        workId: bookId,
        parameters: {
          bookId,
          sourcePath: fromPath,
          ...(opts.split ? { splitPattern: opts.split } : {}),
          ...(opts.resumeFrom ? { resumeFrom: opts.resumeFrom } : {}),
          importMode: opts.series ? "series" : "continuation",
        },
      });
      const result = action.data as {
        readonly importedCount: number;
        readonly totalWords: number;
        readonly nextChapter: number;
      };

      if (opts.json) {
        log(JSON.stringify(result, null, 2));
      } else {
        for (const line of formatImportChaptersComplete(language, {
          importedCount: result.importedCount,
          totalWords: result.totalWords,
          nextChapter: result.nextChapter,
          continueBookId: bookId,
        })) {
          log(line);
        }
      }
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Chapter import failed: ${e}`);
      }
      process.exit(1);
    }
  });
