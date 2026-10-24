import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { createLLMClient, StateManager, createLogger, createStderrSink, createJsonLineSink, resolveEffectiveLLMConfig, loadLLMEnvLayers, GLOBAL_CONFIG_DIR, GLOBAL_ENV_PATH, createBuiltInWorkProfileRegistry, loadAvailableAgentSkills, mergeActivatedSkillGuidance, resolveProfileSkillActivations, type ActivatedSkillGuidance, type EffectiveLLMConfigResult, type LLMApiFormat, type LLMConfigCliOverrides, type ProjectConfig, type PipelineConfig, type LogSink } from "@actalk/inkos-core";

export { GLOBAL_CONFIG_DIR, GLOBAL_ENV_PATH };


export async function resolveContext(opts: {
  readonly context?: string;
  readonly contextFile?: string;
}): Promise<string | undefined> {
  if (opts.context) return opts.context;
  if (opts.contextFile) {
    return readFile(resolve(opts.contextFile), "utf-8");
  }
  // Read from stdin if piped (non-TTY)
  if (!process.stdin.isTTY) {
    const chunks: Buffer[] = [];
    for await (const chunk of process.stdin) {
      chunks.push(chunk as Buffer);
    }
    const text = Buffer.concat(chunks).toString("utf-8").trim();
    if (text.length > 0) return text;
  }
  return undefined;
}

export function findProjectRoot(): string {
  return process.cwd();
}

export async function resolveCliProfileSkills(
  projectRoot: string,
  profileId: string,
  options: { readonly includeRecommended?: boolean; readonly extraSkillIds?: ReadonlyArray<string> } = {},
): Promise<ActivatedSkillGuidance[]> {
  const available = await loadAvailableAgentSkills({ projectRoot });
  const profileSkills = resolveProfileSkillActivations(
    available.skills,
    createBuiltInWorkProfileRegistry().require(profileId),
    { includeRecommended: options.includeRecommended },
  );
  const byId = new Map(available.skills.map((skill) => [skill.id, skill]));
  const extras = (options.extraSkillIds ?? []).map((id) => {
    const skill = byId.get(id);
    if (!skill) throw new Error(`CLI operation requires unavailable skill: ${id}`);
    return { skill, resources: [] };
  });
  return mergeActivatedSkillGuidance(profileSkills, extras);
}

export async function loadConfig(options?: {
  readonly requireApiKey?: boolean;
  readonly projectRoot?: string;
  readonly cli?: LLMConfigCliOverrides;
}): Promise<ProjectConfig> {
  return (await loadConfigWithDiagnostics(options)).config;
}

export async function loadConfigWithDiagnostics(options?: {
  readonly requireApiKey?: boolean;
  readonly projectRoot?: string;
  readonly cli?: LLMConfigCliOverrides;
}): Promise<EffectiveLLMConfigResult> {
  const root = options?.projectRoot ?? findProjectRoot();
  const cli = {
    ...parseLLMOverridesFromArgv(process.argv.slice(2)),
    ...options?.cli,
  };
  const envLayers = await loadLLMEnvLayers(root);
  return resolveEffectiveLLMConfig({
    consumer: "cli",
    projectRoot: root,
    envLayers,
    cli,
    requireApiKey: options?.requireApiKey,
  });
}

export function createClient(config: ProjectConfig) {
  return createLLMClient(config.llm);
}

export function parseLLMOverridesFromArgv(argv: readonly string[]): LLMConfigCliOverrides {
  const overrides: {
    service?: string;
    model?: string;
    apiKeyEnv?: string;
    baseUrl?: string;
    apiFormat?: LLMApiFormat;
    stream?: boolean;
  } = {};

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (!arg) continue;

    const [flag, inlineValue] = arg.split("=", 2) as [string, string | undefined];
    const nextValue = () => inlineValue ?? argv[++i];

    if (flag === "--service") {
      const value = nextValue();
      if (value) overrides.service = value;
    } else if (flag === "--model") {
      const value = nextValue();
      if (value) overrides.model = value;
    } else if (flag === "--api-key-env") {
      const value = nextValue();
      if (value) overrides.apiKeyEnv = value;
    } else if (flag === "--base-url") {
      const value = nextValue();
      if (value) overrides.baseUrl = value;
    } else if (flag === "--api-format") {
      const value = nextValue();
      if (value === "chat" || value === "responses" || value === "anthropic") overrides.apiFormat = value;
    } else if (flag === "--stream") {
      overrides.stream = true;
    } else if (flag === "--no-stream") {
      overrides.stream = false;
    }
  }

  return overrides;
}

export function buildPipelineConfig(
  config: ProjectConfig,
  root: string,
  extra?: Partial<Pick<PipelineConfig, "notifyChannels" | "radarSources" | "externalContext">> & {
    readonly quiet?: boolean;
    readonly logFile?: NodeJS.WritableStream;
  },
): PipelineConfig {
  const sinks: LogSink[] = [];
  if (!extra?.quiet) {
    sinks.push(createStderrSink({ minLevel: "info" }));
  }
  if (extra?.logFile) {
    sinks.push(createJsonLineSink(extra.logFile));
  }

  const hasLogging = sinks.length > 0;
  const logger = hasLogging ? createLogger({ tag: "inkos", sinks }) : undefined;

  const onStreamProgress = hasLogging
    ? (progress: { readonly elapsedMs: number; readonly totalChars: number; readonly chineseChars: number; readonly status: string }) => {
        if (progress.status === "streaming") {
          logger?.info(
            `streaming ${Math.round(progress.elapsedMs / 1000)}s, ${progress.totalChars} chars (${progress.chineseChars} CJK)`,
          );
        }
      }
    : undefined;

  return {
    client: createLLMClient(config.llm),
    model: config.llm.model,
    projectRoot: root,
    defaultLLMConfig: config.llm,
    modelOverrides: config.modelOverrides,
    notifyChannels: extra?.notifyChannels ?? config.notify,
    radarSources: extra?.radarSources,
    externalContext: extra?.externalContext,
    logger,
    onStreamProgress,
  };
}

export function log(message: string): void {
  process.stdout.write(`${message}\n`);
}

export function logError(message: string): void {
  process.stderr.write(`[ERROR] ${message}\n`);
}

/**
 * Resolve book-id: if provided use it, otherwise auto-detect when exactly one book exists.
 * Validates that the book actually exists.
 */
export async function resolveBookId(
  bookIdArg: string | undefined,
  root: string,
): Promise<string> {
  const state = new StateManager(root);
  const books = await state.listBooks();

  if (bookIdArg) {
    if (!books.includes(bookIdArg)) {
      const available = books.length > 0 ? books.join(", ") : "(none)";
      throw new Error(
        `Book "${bookIdArg}" not found. Available books: ${available}`,
      );
    }
    return bookIdArg;
  }

  if (books.length === 0) {
    throw new Error(
      "No books found. Create one first:\n  inkos book create --title '...' --genre xuanhuan",
    );
  }
  if (books.length === 1) {
    return books[0]!;
  }
  throw new Error(
    `Multiple books found: ${books.join(", ")}\nPlease specify a book-id.`,
  );
}
