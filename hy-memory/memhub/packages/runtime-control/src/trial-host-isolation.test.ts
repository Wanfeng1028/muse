import { createHash } from "node:crypto";
import {
  chmod,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  type RecallHostLayout,
  type RecallRuntime,
  readInstalledRecallCommand,
} from "@one-memory/host-bridge/installer";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HostPermissions } from "./host-permissions.js";
import { recallHosts } from "./recall-hosts.js";
import { createRuntimeService } from "./runtime-cli.js";

// A trial build keeps its own data directory beside the daily one, but it
// runs against the same host configs. Nothing it does on its own may rewrite
// an entry the daily app installed: that reroutes the user's hosts to a
// credential the trial never issued, and recall is refused everywhere.

const roots: string[] = [];
afterEach(async () => {
  vi.unstubAllEnvs();
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

const LINKED = [
  "cursor",
  "claude-code",
  "codex",
  "opencode",
  "workbuddy",
  "pi",
];

function bundle(
  root: string,
  name: string,
): Omit<RecallRuntime, "discoveryPath"> {
  const app = path.join(root, `${name}.app`, "Contents");
  return {
    runtimeCommand: path.join(app, "MacOS", name),
    mcpEntryPath: path.join(app, "Resources", "host-bridge", "mcp.cjs"),
    recallCliPath: path.join(app, "Resources", "host-bridge", "recall-cli.cjs"),
    captureCommand: path.join(app, "Resources", "core", "one-memory"),
  };
}

function recallRuntime(
  dataDir: string,
  programs: Omit<RecallRuntime, "discoveryPath">,
): RecallRuntime & { dataDir: string } {
  return {
    ...programs,
    discoveryPath: path.join(dataDir, "integrations", "cursor-broker.json"),
    dataDir,
  };
}

async function machine() {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "om-trial-isolation-")),
  );
  roots.push(root);
  const home = path.join(root, "home");
  vi.stubEnv("HOME", home);
  vi.stubEnv("DSH_HOME", path.join(home, ".dsh"));
  vi.stubEnv("XDG_CONFIG_HOME", path.join(home, ".config"));
  vi.stubEnv("CODEX_HOME", path.join(home, ".codex"));
  vi.stubEnv("CLAUDE_CONFIG_DIR", path.join(home, ".claude"));
  for (const dir of [".cursor", ".claude", ".codex", ".workbuddy"])
    await mkdir(path.join(home, dir), { recursive: true });
  await mkdir(path.join(home, ".config", "opencode"), { recursive: true });
  await mkdir(path.join(home, ".pi", "agent"), { recursive: true });
  for (const name of ["MemHub", "MemHub Trial", "MemHub 2"]) {
    const programs = bundle(root, name);
    for (const target of [
      programs.runtimeCommand,
      programs.mcpEntryPath,
      programs.recallCliPath,
      programs.captureCommand,
    ]) {
      if (!target) continue;
      await mkdir(path.dirname(target), { recursive: true });
      await writeFile(target, "#!/bin/sh\nexit 0\n");
      await chmod(target, 0o700);
    }
  }
  await writeFile(
    path.join(home, ".cursor", "mcp.json"),
    `${JSON.stringify({ mcpServers: { neighbor: { command: "keep" } } })}\n`,
  );
  await writeFile(path.join(home, ".claude.json"), "{}\n");
  const dailyData = path.join(home, ".one-memory");
  const trialData = path.join(home, ".one-memory-trial-demo0925");
  await mkdir(dailyData, { mode: 0o700 });
  await mkdir(trialData, { mode: 0o700 });
  const hosts = (
    await recallHosts(home, { ...process.env, ONE_MEMORY_HOST_HOME: home })
  ).filter((host) => host.hostId !== "openclaw");
  return {
    root,
    home,
    dailyData,
    trialData,
    hosts,
    layout(hostId: string): RecallHostLayout {
      const host = hosts.find((candidate) => candidate.hostId === hostId);
      if (!host) throw new Error(`no ${hostId} layout`);
      return host.layout;
    },
  };
}

type Machine = Awaited<ReturnType<typeof machine>>;

function absolutePaths(value: unknown, found: string[] = []): string[] {
  if (typeof value === "string" && path.isAbsolute(value)) found.push(value);
  else if (Array.isArray(value))
    for (const item of value) absolutePaths(item, found);
  else if (value && typeof value === "object")
    for (const item of Object.values(value)) absolutePaths(item, found);
  return found;
}

/** Proves the host side is the temporary home before anything may write. */
function assertIsolated(context: Machine) {
  expect(os.homedir()).toBe(context.home);
  const paths = absolutePaths(context.hosts.map((host) => host.layout));
  expect(paths.length).toBeGreaterThan(20);
  for (const file of paths)
    expect(file.startsWith(`${context.root}${path.sep}`)).toBe(true);
}

/** The daily app's own confirmed install, the state the trial found. */
async function linkDailyApp(context: Machine) {
  const daily = await HostPermissions.open(
    context.dailyData,
    recallRuntime(context.dailyData, bundle(context.root, "MemHub")),
  );
  for (const hostId of LINKED) {
    const layout = context.layout(hostId);
    const preview = await daily.previewInstall(layout);
    await daily.install(layout, preview.fingerprint);
  }
  return daily;
}

async function hostFiles(context: Machine): Promise<Map<string, string>> {
  const skipped = new Set([context.dailyData, context.trialData]);
  const files = new Map<string, string>();
  const walk = async (directory: string) => {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      if (skipped.has(full)) continue;
      if (entry.isDirectory()) await walk(full);
      else
        files.set(
          full,
          createHash("sha256")
            .update(await readFile(full))
            .digest("hex"),
        );
    }
  };
  await walk(context.home);
  return files;
}

async function expectFixtureIsTheReportedOne(context: Machine) {
  const files = await hostFiles(context);
  const home = context.home;
  for (const file of [
    path.join(home, ".cursor", "mcp.json"),
    path.join(home, ".cursor", "hooks.json"),
    path.join(home, ".claude.json"),
    path.join(home, ".claude", "settings.json"),
    path.join(home, ".codex", "config.toml"),
    path.join(home, ".config", "opencode", "opencode.json"),
  ])
    expect(files.has(file)).toBe(true);
  expect(
    [...files.keys()].some(
      (file) =>
        file.startsWith(path.join(home, ".workbuddy", "plugins")) &&
        file.endsWith(path.join("hooks", "hooks.json")),
    ),
  ).toBe(true);
  const cursor = await readInstalledRecallCommand(context.layout("cursor"));
  expect(
    cursor?.env.ONE_MEMORY_HOST_CREDENTIAL_FILE?.startsWith(context.dailyData),
  ).toBe(true);
  return files;
}

async function trialRuntimeStartup(context: Machine) {
  const trial = bundle(context.root, "MemHub Trial");
  const service = await createRuntimeService({
    dataDir: context.trialData,
    hostHome: context.home,
    runtimeEntry: path.join(context.root, "trial-runtime.cjs"),
    coreCommand: trial.captureCommand ?? "",
    coreArgs: ["serve"],
    webDirectory: path.join(context.root, "trial-web"),
    mcpEntryPath: trial.mcpEntryPath,
    recallCliPath: trial.recallCliPath ?? "",
    syncHookAssetsDirectory: path.join(context.root, "trial-sync-hook"),
    nodeCommand: trial.runtimeCommand,
  });
  // The part of `service.start()` that runs before Core is launched: open the
  // host store and do its startup host maintenance. Core itself is not needed
  // for what reaches the host files.
  const startup = service as unknown as {
    options: { createSupervisor(): Promise<unknown> };
  };
  await startup.options.createSupervisor();
}

describe.skipIf(process.platform === "win32")(
  "a trial build next to the daily app",
  () => {
    it("resolves every host path under the temporary home", async () => {
      assertIsolated(await machine());
    });

    it("does not touch the daily app's hosts while its Runtime starts", async () => {
      const context = await machine();
      assertIsolated(context);
      await linkDailyApp(context);
      const before = await expectFixtureIsTheReportedOne(context);

      await trialRuntimeStartup(context);

      expect(await hostFiles(context)).toEqual(before);
    }, 60_000);

    it("does not touch the daily app's hosts when its page asks for a command repair", async () => {
      const context = await machine();
      assertIsolated(context);
      await linkDailyApp(context);
      const before = await expectFixtureIsTheReportedOne(context);
      const trial = await HostPermissions.open(
        context.trialData,
        recallRuntime(context.trialData, bundle(context.root, "MemHub Trial")),
      );

      for (const host of context.hosts)
        await trial.repairInstalledCommand(host.layout);

      expect(await hostFiles(context)).toEqual(before);
    }, 60_000);

    it("does not record its link check into the daily app's install journals", async () => {
      // Opening an app's detail page probes the link and stores the verdict in
      // the host-side journal. A trial probing the daily app's entry would
      // overwrite the daily install's recorded self check with its own.
      const context = await machine();
      assertIsolated(context);
      await linkDailyApp(context);
      const before = await expectFixtureIsTheReportedOne(context);
      const trial = await HostPermissions.open(
        context.trialData,
        recallRuntime(context.trialData, bundle(context.root, "MemHub Trial")),
      );

      for (const host of context.hosts)
        await trial.recordLinkCheck(host.layout);

      expect(await hostFiles(context)).toEqual(before);
    }, 60_000);

    it("still records its own link check", async () => {
      const context = await machine();
      assertIsolated(context);
      const daily = await linkDailyApp(context);
      const journal = context.layout("cursor").journalPath;
      const before = await readFile(journal, "utf8");

      await daily.recordLinkCheck(context.layout("cursor"));

      expect(await readFile(journal, "utf8")).not.toBe(before);
    }, 60_000);

    it("still repoints its own hosts when the daily app moves", async () => {
      // The positive side of the two above: the same repair writes when the
      // entry is this data directory's own, so an unchanged file above is the
      // repair declining rather than the repair being unable to write.
      const context = await machine();
      assertIsolated(context);
      await linkDailyApp(context);
      const before = await expectFixtureIsTheReportedOne(context);
      const upgraded = await HostPermissions.open(
        context.dailyData,
        recallRuntime(context.dailyData, bundle(context.root, "MemHub 2")),
      );

      const repaired = await upgraded.repairInstalledCommands(
        context.hosts.map((host) => host.layout),
      );

      expect([...repaired].sort()).toEqual([...LINKED].sort());
      expect(await hostFiles(context)).not.toEqual(before);
      const cursor = await readInstalledRecallCommand(context.layout("cursor"));
      expect(cursor?.command).toBe(
        bundle(context.root, "MemHub 2").runtimeCommand,
      );
      expect(cursor?.env.ONE_MEMORY_HOST_CREDENTIAL_FILE).toBe(
        upgraded.runtimeFor(context.layout("cursor")).credentialFile,
      );
    }, 60_000);

    it("leaves a host the user explicitly moved to the trial where they put it", async () => {
      // Symmetric case: once the user connects a host from inside the trial,
      // the daily app starting again must not take it back on its own.
      const context = await machine();
      assertIsolated(context);
      const daily = await linkDailyApp(context);
      const trial = await HostPermissions.open(
        context.trialData,
        recallRuntime(context.trialData, bundle(context.root, "MemHub Trial")),
      );
      const cursor = context.layout("cursor");
      const preview = await trial.previewInstall(cursor);
      await trial.install(cursor, preview.fingerprint);
      const moved = await hostFiles(context);
      expect(
        (await readInstalledRecallCommand(cursor))?.env
          .ONE_MEMORY_HOST_CREDENTIAL_FILE,
      ).toBe(trial.runtimeFor(cursor).credentialFile);

      await daily.repairInstalledCommand(cursor);

      expect(await hostFiles(context)).toEqual(moved);
    }, 60_000);
  },
);
