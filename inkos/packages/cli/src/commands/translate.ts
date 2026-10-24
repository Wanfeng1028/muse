import { Command } from "commander";
import {
  createTranslationCreateTool,
  createTranslationRunTool,
  createTranslationExportTool,
  createBuiltInWorkProfileRegistry,
  executeExplicitCapabilityTool,
  loadAvailableAgentSkills,
  PipelineRunner,
  resolveProfileSkillActivations,
} from "@actalk/inkos-core";
import { buildPipelineConfig, findProjectRoot, loadConfig, log, logError } from "../utils.js";

export const translateCommand = new Command("translate")
  .description("Translate and localize novels/scripts across languages");

translateCommand
  .command("init")
  .description("Create a translation project from EPUB/PDF/TXT/Markdown")
  .requiredOption("--from <path>", "Source file path")
  .requiredOption("--source <language>", "Source language, e.g. ja, en, zh, ko, auto")
  .requiredOption("--target <language>", "Target language, e.g. zh, en, ja")
  .option("--title <title>", "Override translation title")
  .option("--segment-max-chars <n>", "Max chars per segment before splitting long paragraphs", parseInt)
  .option("--json", "Output JSON")
  .action(async (opts) => {
    try {
      const root = findProjectRoot();
      const action = await executeExplicitCapabilityTool({
        projectRoot: root,
        binding: { capabilityId: "translation", actionId: "translation_create", profileId: "translation", risk: "recoverable-write" },
        tool: createTranslationCreateTool(root),
        parameters: {
          filePath: opts.from,
          sourceLanguage: opts.source,
          targetLanguage: opts.target,
          title: opts.title,
          segmentMaxChars: opts.segmentMaxChars,
        },
      });
      const result = action.data as {
        manifest: { id: string; title: string; chapters: ReadonlyArray<unknown> };
        manifestPath: string;
      };
      if (opts.json) {
        log(JSON.stringify(result, null, 2));
      } else {
        log(`Translation project created: ${result.manifest.id}`);
        log(`Title: ${result.manifest.title}`);
        log(`Chapters: ${result.manifest.chapters.length}`);
        log(`Manifest: ${result.manifestPath}`);
      }
    } catch (error) {
      fail("Failed to create translation project", error, opts.json);
    }
  });

translateCommand
  .command("run")
  .description("Translate pending segments and write a review report")
  .argument("<project-id>", "Translation Work ID")
  .option("--batch-size <n>", "Segments per model call", parseInt)
  .option("--max-tokens <n>", "Max output tokens per translation batch", parseInt)
  .option("--json", "Output JSON")
  .action(async (projectId: string, opts) => {
    try {
      const root = findProjectRoot();
      const config = await loadConfig({ requireApiKey: true, projectRoot: root });
      const configuredSkills = await loadAvailableAgentSkills({ projectRoot: root });
      const activatedSkills = resolveProfileSkillActivations(
        configuredSkills.skills,
        createBuiltInWorkProfileRegistry().require("translation"),
      );
      const pipeline = new PipelineRunner(buildPipelineConfig(config, root, { quiet: Boolean(opts.json) }));
      const action = await executeExplicitCapabilityTool({
        projectRoot: root,
        binding: { capabilityId: "translation", actionId: "translation_run", profileId: "translation", risk: "recoverable-write" },
        tool: createTranslationRunTool(pipeline, root, projectId, { defaultSkills: activatedSkills }),
        workId: projectId,
        parameters: { batchSize: opts.batchSize, maxTokens: opts.maxTokens },
      });
      const result = action.data as {
        translatedSegments: number;
        reviewedChapters: number;
        reportPath: string;
        skillIds: ReadonlyArray<string>;
      };
      if (opts.json) {
        log(JSON.stringify(result, null, 2));
      } else {
        log(`Skills: ${result.skillIds.join(", ")}`);
        log(`Translated segments: ${result.translatedSegments}`);
        log(`Reviewed chapters: ${result.reviewedChapters}`);
        log(`Report: ${result.reportPath}`);
      }
    } catch (error) {
      fail("Translation run failed", error, opts.json);
    }
  });

translateCommand
  .command("export")
  .description("Export translated text to Markdown/TXT/EPUB")
  .argument("<project-id>", "Translation Work ID")
  .option("--format <format>", "Output format: md, txt, epub", "md")
  .option("--output <path>", "Output file path")
  .option("--json", "Output JSON")
  .action(async (projectId: string, opts) => {
    try {
      const root = findProjectRoot();
      const action = await executeExplicitCapabilityTool({
        projectRoot: root,
        binding: { capabilityId: "translation", actionId: "translation_export", profileId: "translation", risk: "recoverable-write" },
        tool: createTranslationExportTool(root, projectId),
        workId: projectId,
        parameters: { format: opts.format, outputPath: opts.output },
      });
      const result = action.data as { chaptersExported: number; outputPath: string };
      if (opts.json) {
        log(JSON.stringify(result, null, 2));
      } else {
        log(`Exported ${result.chaptersExported} chapter(s)`);
        log(`Output: ${result.outputPath}`);
      }
    } catch (error) {
      fail("Translation export failed", error, opts.json);
    }
  });

function fail(prefix: string, error: unknown, json: boolean): never {
  if (json) {
    log(JSON.stringify({ error: String(error) }));
  } else {
    logError(`${prefix}: ${error}`);
  }
  process.exit(1);
}
