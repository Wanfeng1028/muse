/** Pi is the first host where the skill is the entire install.
 *
 * Every other host got an MCP server entry, and the skill was guidance layered
 * on top. Pi has no MCP config at all, so if the installer quietly wrote one
 * anyway — or wrote MCP wording into the skill — the install would report
 * success while recall stayed unreachable. These tests are about that: what
 * lands on disk, and whether the text names something Pi can actually run.
 */

import {
  mkdir,
  mkdtemp,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  piLayout,
  planRecallInstall,
  previewRecallInstall,
  type RecallHostLayout,
  type RecallRuntime,
  rollbackRecallInstall,
  verifyRecallInstall,
} from "./recall-installer.js";

let root: string;
let layout: RecallHostLayout;
let runtime: RecallRuntime;

beforeEach(async () => {
  root = await mkdtemp(path.join(tmpdir(), "one-memory-pi-"));
  // Mirrors the real install: skills live under `<pi>/agent/skills`.
  const agent = path.join(root, "agent");
  await mkdir(path.join(agent, "skills"), { recursive: true });
  layout = piLayout(agent);
  runtime = {
    runtimeCommand: path.join(root, "MemHub.app", "MacOS", "MemHub"),
    mcpEntryPath: path.join(root, "bridge", "mcp.cjs"),
    discoveryPath: path.join(root, "discovery.json"),
    recallCliPath: path.join(root, "bridge", "recall-cli.cjs"),
  };
});

afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

async function install(): Promise<void> {
  await applyRecallInstall(await planRecallInstall(layout, runtime));
}

async function skillText(): Promise<string> {
  return await readFile(layout.skillPath as string, "utf8");
}

describe("installing recall into a host with no MCP config", () => {
  it("writes the skill and nothing else of the host's", async () => {
    const plan = await planRecallInstall(layout, runtime);
    expect(plan.paths.mcp).toBeNull();
    expect(plan.next.server).toBeNull();
    // No `create-mcp`/`merge-mcp`: there is no config to create or merge into,
    // and claiming one would misreport what the user approved.
    expect(plan.actions).toEqual(["create-skill"]);

    await applyRecallInstall(plan);
    expect(await skillText()).toContain("memhub-recall");
  });

  it("tells the model to run the command, not to call a tool", async () => {
    await install();
    const skill = await skillText();
    // The whole point of the CLI channel. `om_recall` here would send the
    // model looking for a tool Pi does not have, and it would then report
    // that memory is unavailable.
    expect(skill).not.toContain("om_recall");
    expect(skill).not.toContain("MCP tool");
    expect(skill).toContain(runtime.recallCliPath as string);
  });

  it("names paths that exist in this install, not a PATH lookup", async () => {
    await install();
    const skill = await skillText();
    // Pi runs exactly what is written, and nothing of ours is on `PATH`.
    expect(skill).toContain(`"${runtime.runtimeCommand}"`);
    expect(skill).toContain(
      `ONE_MEMORY_BROKER_DISCOVERY="${runtime.discoveryPath}"`,
    );
    // Without this the app binary opens a window instead of running a script.
    expect(skill).toContain('ELECTRON_RUN_AS_NODE="1"');
  });

  it("keeps the project reachable by passing the working directory", async () => {
    await install();
    // A scope cannot be constructed outside Core, so this flag is the only way
    // the current project's memories are reached at all.
    expect(await skillText()).toContain('--workspace-path "$PWD"');
  });

  it("previews the skill it is about to write", async () => {
    const preview = await previewRecallInstall(
      await planRecallInstall(layout, runtime),
    );
    expect(preview.files.map((file) => file.owner)).toEqual([
      "one-memory",
      "one-memory",
    ]);
    expect(preview.files[0].existed).toBe(false);
    expect(preview.files[1].path).toContain("one-memory-capture.js");
    // Nothing on disk yet, despite having been previewed.
    await expect(stat(layout.skillPath as string)).rejects.toThrow();
  });

  it("verifies against the discovery path the skill actually names", async () => {
    await install();
    const before = await verifyRecallInstall(layout);
    expect(before.hostId).toBe("pi");
    expect(before.discoveryPath).toBe(runtime.discoveryPath);
    // Absent is not a failure — the app writes it when it first runs — but it
    // has to be reported, because a wrong path passes every other check.
    expect(before.discoveryPresent).toBe(false);

    await writeFile(runtime.discoveryPath, "{}", { encoding: "utf8" });
    expect((await verifyRecallInstall(layout)).discoveryPresent).toBe(true);
  });

  it("reinstalls without treating its own skill as the user's", async () => {
    await install();
    await install();
    await expect(verifyRecallInstall(layout)).resolves.toMatchObject({
      hostId: "pi",
    });
    // A reinstall that recorded our own skill as `previous_skill` would make
    // uninstall put MemHub back instead of removing it.
    await rollbackRecallInstall(layout);
    await expect(stat(layout.skillPath as string)).rejects.toThrow();
  });

  it("leaves no trace when uninstalled", async () => {
    await install();
    await rollbackRecallInstall(layout);
    await expect(stat(layout.skillPath as string)).rejects.toThrow();
    await expect(stat(layout.journalPath)).rejects.toThrow();
    // Our own directory bearing our name is a trace too.
    await expect(stat(path.dirname(layout.journalPath))).rejects.toThrow();
    // The skill directory Pi scans must not be left holding an empty entry.
    await expect(
      stat(path.dirname(layout.skillPath as string)),
    ).rejects.toThrow();
  });

  it("refuses to touch a memhub-recall skill it does not own", async () => {
    const skillPath = layout.skillPath as string;
    await mkdir(path.dirname(skillPath), { recursive: true });
    await writeFile(skillPath, "# hand written by the user\n", {
      encoding: "utf8",
    });
    await expect(planRecallInstall(layout, runtime)).rejects.toThrow(
      /unmanaged memhub-recall Skill/,
    );
    expect(await readFile(skillPath, "utf8")).toBe(
      "# hand written by the user\n",
    );
  });

  it("refuses to install with no recall command to name", async () => {
    const { recallCliPath: _dropped, ...withoutCli } = runtime;
    await expect(planRecallInstall(layout, withoutCli)).rejects.toThrow(
      /recallCliPath/,
    );
    // Refused before anything was written, which is the point of checking in
    // the plan rather than while writing the skill.
    await expect(stat(layout.skillPath as string)).rejects.toThrow();
  });
});

describe("layouts that contradict themselves", () => {
  it("refuses a config-less host that claims the MCP channel", async () => {
    await expect(
      planRecallInstall({ ...layout, channel: "mcp" }, runtime),
    ).rejects.toThrow(/channel cannot be "mcp"/);
  });

  it("refuses a config-less host with no skill either", async () => {
    await expect(
      planRecallInstall({ ...layout, skillPath: null }, runtime),
    ).rejects.toThrow(/neither a config nor a skill/);
  });

  it("refuses a format that disagrees with whether a config exists", async () => {
    await expect(
      planRecallInstall({ ...layout, format: "json" }, runtime),
    ).rejects.toThrow(/format "none"/);
    await expect(
      planRecallInstall(
        { ...layout, configPath: path.join(root, "mcp.json") },
        runtime,
      ),
    ).rejects.toThrow(/format "none"/);
  });
});
