import { createRequire } from "node:module";
import { recoverAtomicFileSets } from "@actalk/inkos-core";
import { findProjectRoot } from "./utils.js";
import { Command } from "commander";
import { initCommand } from "./commands/init.js";
import { configCommand } from "./commands/config.js";
import { bookCommand } from "./commands/book.js";
import { chapterCommand } from "./commands/chapter.js";
import { writeCommand } from "./commands/write.js";
import { autoCommand } from "./commands/auto.js";
import { reviewCommand } from "./commands/review.js";
import { statusCommand } from "./commands/status.js";
import { radarCommand } from "./commands/radar.js";
import { upCommand, downCommand } from "./commands/daemon.js";
import { doctorCommand } from "./commands/doctor.js";
import { exportCommand } from "./commands/export.js";
import { reviseCommand } from "./commands/revise.js";
import { agentCommand } from "./commands/agent.js";
import { updateCommand } from "./commands/update.js";
import { detectCommand } from "./commands/detect.js";
import { styleCommand } from "./commands/style.js";
import { analyticsCommand } from "./commands/analytics.js";
import { importCommand } from "./commands/import.js";
import { fanficCommand } from "./commands/fanfic.js";
import { shortCommand } from "./commands/short-fiction.js";
import { forecastCommand } from "./commands/forecast.js";
import { translateCommand } from "./commands/translate.js";
import { createStudioCommand, launchStudioEntry } from "./commands/studio.js";
import { createInteractCommand, type InteractCommandHooks } from "./commands/interact.js";
import { createTuiCommand } from "./commands/tui.js";
import { launchTui } from "./tui/app.js";
import { workCommand } from "./commands/work.js";

const require = createRequire(import.meta.url);
const { version } = require("../package.json") as { version: string };

export interface ProgramHooks {
  readonly launchTui?: (projectRoot: string) => Promise<void> | void;
  readonly launchStudio?: (projectRoot: string, port: string) => Promise<void> | void;
  readonly studioRecentProjectPath?: string;
  readonly readInteractionInput?: InteractCommandHooks["readInput"];
}

export function createProgram(hooks: ProgramHooks = {}): Command {
  const program = new Command();

  program
    .name("inkos")
    .description("InkOS — Multi-agent novel production system")
    .version(version)
    .enablePositionalOptions()
    .option("--service <service>", "Override LLM service for this CLI run")
    .option("--model <model>", "Override LLM model for this CLI run")
    .option("--api-key-env <envVar>", "Read LLM API key from this environment variable for this CLI run")
    .option("--base-url <url>", "Override LLM base URL for this CLI run")
    .option("--api-format <chat|responses|anthropic>", "Override LLM API format for this CLI run")
    .option("--stream", "Force streaming LLM responses for this CLI run")
    .option("--no-stream", "Force non-streaming LLM responses for this CLI run")
    .action(async () => {
      await launchStudioEntry(process.cwd(), "4567", {
        launchStudio: hooks.launchStudio,
        recentProjectPath: hooks.studioRecentProjectPath,
      });
    });

  program.addCommand(initCommand);
  program.addCommand(configCommand);
  program.addCommand(bookCommand);
  program.addCommand(workCommand);
  program.addCommand(chapterCommand);
  program.addCommand(writeCommand);
  program.addCommand(autoCommand);
  program.addCommand(reviewCommand);
  program.addCommand(statusCommand);
  program.addCommand(radarCommand);
  program.addCommand(upCommand);
  program.addCommand(downCommand);
  program.addCommand(doctorCommand);
  program.addCommand(exportCommand);
  program.addCommand(reviseCommand);
  program.addCommand(agentCommand);
  program.addCommand(updateCommand);
  program.addCommand(detectCommand);
  program.addCommand(styleCommand);
  program.addCommand(analyticsCommand);
  program.addCommand(importCommand);
  program.addCommand(fanficCommand);
  program.addCommand(shortCommand);
  program.addCommand(forecastCommand);
  program.addCommand(translateCommand);
  program.addCommand(createStudioCommand({
    launchStudio: hooks.launchStudio,
    recentProjectPath: hooks.studioRecentProjectPath,
  }));
  program.addCommand(createInteractCommand({
    readInput: hooks.readInteractionInput,
  }));
  program.addCommand(createTuiCommand({ launchTui: hooks.launchTui }));

  return program;
}

export async function runProgram(
  argv: string[] = process.argv,
  hooks: ProgramHooks = {},
): Promise<void> {
  const program = createProgram(hooks);
  program.hook("preAction", async () => {
    let root: string;
    try { root = findProjectRoot(); }
    catch { return; } // init and help may run outside a project.
    await recoverAtomicFileSets(root, true);
  });
  await program.parseAsync(argv);
}
