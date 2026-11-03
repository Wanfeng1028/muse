import { Command } from "commander";
import { loadWorkManifest, PipelineRunner, runAgentSession } from "@actalk/inkos-core";
import { buildPipelineConfig, loadConfig, createClient, findProjectRoot, resolveBookId, resolveContext, log, logError } from "../utils.js";

export const agentCommand = new Command("agent")
  .description("Natural language agent mode (LLM orchestrates via tool-use)")
  .argument("<instruction>", "Natural language instruction")
  .option("--book <bookId>", "Bind this request to an existing book")
  .option("--work <workId>", "Bind this request to any existing creative Work")
  .option("--session <sessionId>", "Reuse an agent session id")
  .option("--context <text>", "Additional context (natural language)")
  .option("--context-file <path>", "Read additional context from file")
  .option("--json", "Output JSON (suppress progress messages)")
  .option("--quiet", "Suppress non-JSON console output")
  .action(async (instruction: string, opts) => {
    try {
      const config = await loadConfig();
      const client = createClient(config);
      const root = findProjectRoot();
      const context = await resolveContext(opts);

      const fullInstruction = context
        ? `${instruction}\n\n补充信息：${context}`
        : instruction;

      const bookId = opts.book ? await resolveBookId(opts.book, root) : null;
      if (opts.book && opts.work) throw new Error("Use either --book or --work, not both.");
      const work = opts.work ? await loadWorkManifest(root, String(opts.work).trim()) : null;
      const trimmed = fullInstruction.trim();
      const actionSource = trimmed.startsWith("/") ? "slash" : "free-text";
      const requestedIntent = bookId && trimmed === "/write"
        ? "write_next"
        : !bookId && trimmed === "/create"
          ? "create_book"
          : undefined;
      const sessionKind = work
        ? "work"
        : bookId
        ? "book"
        : requestedIntent === "create_book"
          ? "book-create"
          : "chat";
      const sessionId = opts.session?.trim() || `cli-agent-${Date.now().toString(36)}`;
      const pipeline = new PipelineRunner(buildPipelineConfig(config, root, {
        externalContext: context,
        quiet: opts.quiet || opts.json,
      }));

      const result = await runAgentSession(
        {
          sessionId,
          bookId,
          sessionKind,
          ...(work ? { profileId: work.profileId, workId: work.id } : {}),
          actionSource,
          requestedIntent,
          language: config.language ?? "zh",
          pipeline,
          projectRoot: root,
          model: client._piModel
            ? client._piModel
            : { provider: config.llm.provider ?? "openai", modelId: config.llm.model },
          apiKey: client._apiKey,
          stream: client.stream,
          proxyUrl: client.proxyUrl,
        },
        fullInstruction,
      );

      const failure = result.errorMessage ?? (result.completion?.status === "blocked" ? result.completion.message : undefined);
      if (opts.json) {
        log(JSON.stringify({ result }));
      } else if (failure) {
        logError(failure);
      } else if (!opts.quiet && result.responseText.trim()) {
        log(result.responseText);
      }
      if (failure) process.exitCode = 1;
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Agent failed: ${e}`);
      }
      process.exit(1);
    }
  });
