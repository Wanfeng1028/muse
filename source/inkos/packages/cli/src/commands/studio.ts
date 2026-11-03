import { Command } from "commander";
import { findProjectRoot, log, logError, GLOBAL_CONFIG_DIR } from "../utils.js";
import { spawn } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { ensureProjectDirectoryInitialized } from "../project-bootstrap.js";

export interface StudioLaunchSpec {
  readonly studioEntry: string;
  readonly command: string;
  readonly args: string[];
}

export interface BrowserLaunchSpec {
  readonly command: string;
  readonly args: string[];
}

export interface StudioCommandHooks {
  readonly launchStudio?: (projectRoot: string, port: string) => Promise<void> | void;
  readonly recentProjectPath?: string;
}

const DEFAULT_RECENT_STUDIO_PROJECT_PATH = join(GLOBAL_CONFIG_DIR, "studio-project.json");

export async function resolveStudioProjectRoot(
  requestedRoot: string,
  options: { readonly explicitProject?: boolean; readonly recentProjectPath?: string } = {},
): Promise<{ readonly root: string; readonly source: "requested" | "recent" | "new" }> {
  const root = resolve(requestedRoot);
  const recentProjectPath = options.recentProjectPath ?? DEFAULT_RECENT_STUDIO_PROJECT_PATH;
  if (await isInkOSProject(root)) {
    await saveRecentStudioProject(recentProjectPath, root);
    return { root, source: "requested" };
  }

  if (!options.explicitProject) {
    const recent = await loadRecentStudioProject(recentProjectPath);
    if (recent && await isInkOSProject(recent)) {
      return { root: recent, source: "recent" };
    }
  }

  return { root, source: "new" };
}

async function prepareStudioRoot(
  root: string,
  options: { readonly explicitProject?: boolean; readonly recentProjectPath?: string } = {},
): Promise<{ readonly root: string; readonly initialized: boolean; readonly source: "requested" | "recent" | "new" }> {
  const resolved = await resolveStudioProjectRoot(root, options);
  const initialized = await ensureProjectDirectoryInitialized(resolved.root, { language: "zh" });
  await saveRecentStudioProject(options.recentProjectPath ?? DEFAULT_RECENT_STUDIO_PROJECT_PATH, resolved.root);
  return { ...resolved, initialized };
}

async function isInkOSProject(root: string): Promise<boolean> {
  try {
    await access(join(root, "inkos.json"));
    return true;
  } catch {
    return false;
  }
}

async function loadRecentStudioProject(path: string): Promise<string | undefined> {
  try {
    const parsed = JSON.parse(await readFile(path, "utf-8")) as { projectRoot?: unknown };
    return typeof parsed.projectRoot === "string" && parsed.projectRoot.trim()
      ? resolve(parsed.projectRoot)
      : undefined;
  } catch {
    return undefined;
  }
}

async function saveRecentStudioProject(path: string, projectRoot: string): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, JSON.stringify({ projectRoot }, null, 2), "utf-8");
}

async function firstAccessiblePath(paths: readonly string[]): Promise<string | undefined> {
  for (const path of paths) {
    try {
      await access(path);
      return path;
    } catch {
      // continue
    }
  }
  return undefined;
}

const cliPackageRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

export function toNodeImportSpecifier(path: string): string {
  if (/^[A-Za-z]:[\\/]/.test(path)) {
    return `file:///${path.replace(/\\/g, "/")}`;
  }
  return path;
}

export function resolveBrowserLaunch(
  platform: NodeJS.Platform,
  url: string,
): BrowserLaunchSpec {
  if (platform === "darwin") {
    return { command: "open", args: [url] };
  }
  if (platform === "win32") {
    return { command: "cmd", args: ["/c", "start", "", url] };
  }
  return { command: "xdg-open", args: [url] };
}

export async function resolveStudioLaunch(root: string): Promise<StudioLaunchSpec | null> {
  const sourceEntry = await firstAccessiblePath([
    join(root, "packages", "studio", "src", "api", "index.ts"),
    join(root, "..", "packages", "studio", "src", "api", "index.ts"),
    join(root, "..", "studio", "src", "api", "index.ts"),
  ]);
  if (sourceEntry) {
    const studioPackageRoot = dirname(dirname(dirname(sourceEntry)));
    const localTsxLoader = await firstAccessiblePath([
      join(studioPackageRoot, "node_modules", "tsx", "dist", "loader.mjs"),
    ]);
    if (localTsxLoader) {
      return {
        studioEntry: sourceEntry,
        command: "node",
        args: ["--import", toNodeImportSpecifier(localTsxLoader), sourceEntry, root],
      };
    }

    const localTsx = await firstAccessiblePath([
      join(studioPackageRoot, "node_modules", ".bin", "tsx"),
    ]);
    if (localTsx) {
      return {
        studioEntry: sourceEntry,
        command: localTsx,
        args: [sourceEntry, root],
      };
    }
    return {
      studioEntry: sourceEntry,
      command: "npx",
      args: ["tsx", sourceEntry, root],
    };
  }

  const builtEntry = await firstAccessiblePath([
    join(root, "node_modules", "@actalk", "inkos-studio", "dist", "api", "index.js"),
    join(root, "node_modules", "@actalk", "inkos-studio", "server.cjs"),
    join(cliPackageRoot, "node_modules", "@actalk", "inkos-studio", "dist", "api", "index.js"),
    join(cliPackageRoot, "node_modules", "@actalk", "inkos-studio", "server.cjs"),
    join(cliPackageRoot, "..", "inkos-studio", "dist", "api", "index.js"),
    join(cliPackageRoot, "..", "inkos-studio", "server.cjs"),
  ]);
  if (builtEntry) {
    return {
      studioEntry: builtEntry,
      command: "node",
      args: [builtEntry, root],
    };
  }

  return null;
}

export async function launchStudioWorkbench(root: string, port: string, initialHash = ""): Promise<void> {
  const url = `http://localhost:${port}${initialHash}`;
  const launch = await resolveStudioLaunch(root);

  if (!launch) {
    logError(
      "InkOS Studio not found. If you cloned the repo, run:\n" +
      "  cd packages/studio && pnpm install && pnpm build\n" +
      "Then run 'inkos studio' from the project root.",
    );
    process.exit(1);
  }

  log(`Starting InkOS Studio on ${url}`);

  const child = spawn(launch.command, launch.args, {
    cwd: root,
    stdio: "inherit",
    env: { ...process.env, INKOS_STUDIO_PORT: port },
  });

  child.on("error", (e) => {
    logError(`Failed to start studio: ${e.message}`);
    process.exit(1);
  });

  const browserLaunch = resolveBrowserLaunch(process.platform, url);
  const browser = spawn(browserLaunch.command, browserLaunch.args, {
    cwd: root,
    stdio: "ignore",
    detached: true,
  });
  browser.on("error", () => {
    // Best effort only — server startup should not fail just because browser open failed.
  });
  if (typeof browser.unref === "function") {
    browser.unref();
  }

  child.on("exit", (code) => {
    process.exit(code ?? 0);
  });
}

export async function launchStudioEntry(
  root: string,
  port: string,
  hooks: StudioCommandHooks = {},
  options: { readonly explicitProject?: boolean } = {},
): Promise<void> {
  const prepared = await prepareStudioRoot(root, {
    explicitProject: options.explicitProject,
    recentProjectPath: hooks.recentProjectPath,
  });
  if (prepared.initialized) {
    log(`No inkos.json found in ${prepared.root}. Initialized a minimal InkOS project for Studio.`);
  } else if (prepared.source === "recent") {
    log(`No InkOS project found in ${resolve(root)}. Reopening recent project: ${prepared.root}`);
  }

  if (hooks.launchStudio) {
    await hooks.launchStudio(prepared.root, port);
    return;
  }

  await launchStudioWorkbench(prepared.root, port, prepared.initialized ? "#/services" : "");
}

export function createStudioCommand(hooks: StudioCommandHooks = {}): Command {
  return new Command("studio")
  .description("Start InkOS Studio web workbench")
  .option("-p, --port <port>", "Server port", "4567")
  .option("--project <path>", "Open or initialize a specific InkOS project directory")
  .action(async (opts) => {
    const root = opts.project ? resolve(opts.project) : findProjectRoot();
    const port = opts.port;
    await launchStudioEntry(root, port, hooks, { explicitProject: Boolean(opts.project) });
  });
}

export const studioCommand = createStudioCommand();
