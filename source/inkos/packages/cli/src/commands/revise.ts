import { Command } from "commander";
import {
  DEFAULT_REVISE_MODE,
  PipelineRunner,
  StateManager,
  createReviseChapterTool,
  executeExplicitCapabilityTool,
  type ReviseMode,
} from "@actalk/inkos-core";
import { loadConfig, buildPipelineConfig, findProjectRoot, resolveBookId, log, logError, resolveCliProfileSkills } from "../utils.js";
import {
  formatNotifyCommandTitle,
  formatNotifyFailureBody,
  formatNotifyReviseBody,
  resolveCliLanguage,
  type CliLanguage,
} from "../localization.js";
import { sendCommandNotification } from "../notify-helper.js";

export const reviseCommand = new Command("revise")
  .description("Revise a chapter from user direction and review observations")
  .argument("[book-id]", "Book ID (auto-detected if only one book)")
  .argument("[chapter]", "Chapter number (defaults to latest)")
  .option("--mode <mode>", "Revise mode: spot-fix, polish, rewrite, rework, anti-detect", DEFAULT_REVISE_MODE)
  .option("--brief <text>", "One-off creative guidance for this revise/rewrite only")
  .option("--json", "Output JSON")
  .option("--notify", "Send a notification to configured notify channels when the command finishes")
  .action(async (bookIdArg: string | undefined, chapterStr: string | undefined, opts) => {
    let notifyLanguage: CliLanguage = "zh";
    let notifyBookName: string | undefined;
    try {
      const config = await loadConfig();
      const root = findProjectRoot();

      let bookId: string;
      let chapterNumber: number | undefined;
      if (bookIdArg && /^\d+$/.test(bookIdArg)) {
        bookId = await resolveBookId(undefined, root);
        chapterNumber = parseInt(bookIdArg, 10);
      } else {
        bookId = await resolveBookId(bookIdArg, root);
        chapterNumber = chapterStr ? parseInt(chapterStr, 10) : undefined;
      }

      const state = new StateManager(root);
      const book = await state.loadBookConfig(bookId);
      const language = resolveCliLanguage(book.language);
      notifyLanguage = language;
      notifyBookName = book.title ?? bookId;
      const pipeline = new PipelineRunner(buildPipelineConfig(config, root, {
        externalContext: opts.brief,
      }));

      const mode = opts.mode as ReviseMode;
      if (!opts.json) log(`Revising "${bookId}"${chapterNumber ? ` chapter ${chapterNumber}` : " (latest)"} [mode: ${mode}]...`);

      const activatedSkills = await resolveCliProfileSkills(root, "longform-novel", { includeRecommended: true });
      const action = await executeExplicitCapabilityTool({
        projectRoot: root,
        binding: { capabilityId: "longform", actionId: "revise_chapter", profileId: "longform-novel", risk: "recoverable-write" },
        tool: createReviseChapterTool(pipeline, bookId, { activeSkills: () => activatedSkills }),
        workId: bookId,
        parameters: {
          instruction: opts.brief?.trim() || "Revise the chapter from its persisted observations and Work authority.",
          bookId,
          ...(chapterNumber ? { chapterNumber } : {}),
          mode,
        },
      });
      const result = action.data as {
        readonly chapterNumber: number;
        readonly wordCount: number;
        readonly changed: boolean;
        readonly observations: ReadonlyArray<unknown>;
      };

      if (opts.json) {
        log(JSON.stringify(result, null, 2));
      } else {
        log(result.changed
          ? `  Chapter ${result.chapterNumber} revised`
          : `  Chapter ${result.chapterNumber}: no actionable change`);
        log(`  Words: ${result.wordCount}`);
        log(`  Review observations: ${result.observations.length}`);
      }

      // Unlike write commands, the pipeline sends no notification for
      // reviseDraft, so --notify always sends the completion notification here.
      if (opts.notify) {
        await sendCommandNotification({
          title: formatNotifyCommandTitle(language, "revise", notifyBookName, true),
          body: formatNotifyReviseBody(language, {
            chapterNumber: result.chapterNumber,
            changed: result.changed,
            wordCount: result.wordCount,
            observationCount: result.observations.length,
          }),
        }, config);
      }
    } catch (e) {
      if (opts.notify) {
        await sendCommandNotification({
          title: formatNotifyCommandTitle(notifyLanguage, "revise", notifyBookName, false),
          body: formatNotifyFailureBody(notifyLanguage, e),
        });
      }
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Revise failed: ${e}`);
      }
      process.exit(1);
    }
  });
