import { mkdir, mkdtemp, readdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  mcpConfigPath,
  planRecallInstall,
  qwenCodeLayout,
  rollbackRecallInstall,
  verifyRecallInstall,
} from "./recall-installer.js";

/** Exactly what `qwen mcp add` then `qwen mcp remove` leaves on disk: an empty
 * server map spread over two lines, a `$version` key the host maintains, and
 * no trailing newline. Written by the host, not by us, which is the point. */
const HOST_WRITTEN_SETTINGS = '{\n  "mcpServers": {\n  },\n  "$version": 4\n}';

describe("Qwen Code recall installer", () => {
  it("merges into settings.json and installs the Skill", async () => {
    const { layout, configPath } = await fixture();
    await writeFile(configPath, HOST_WRITTEN_SETTINGS);

    const plan = await planRecallInstall(layout, runtime());
    await applyRecallInstall(plan);
    await verifyRecallInstall(layout);

    expect(plan.actions).toEqual(["merge-mcp", "create-skill"]);
    const merged = JSON.parse(await readFile(configPath, "utf8"));
    expect(merged.mcpServers["one-memory"].command).toBe(
      "/opt/one-memory/bin/one-memory",
    );
    // `settings.json` is every user setting, not a servers file. Keys we do not
    // understand — the host's own `$version` among them — have to survive a
    // merge, or installing recall would quietly reset the host's config.
    expect(merged.$version).toBe(4);
    expect(await readFile(String(layout.skillPath), "utf8")).toContain(
      "MemHub_recall",
    );
  });

  it("gives back the same settings, though not the same bytes", async () => {
    const { layout, configPath } = await fixture();
    await writeFile(configPath, HOST_WRITTEN_SETTINGS);

    await applyRecallInstall(await planRecallInstall(layout, runtime()));
    await rollbackRecallInstall(layout);

    const restored = await readFile(configPath, "utf8");
    // The guarantee for a JSON host is the value, not the layout: the file is
    // re-serialised on the way out, so the host's two-line empty object and
    // missing final newline come back in our style. Claiming "byte for byte"
    // here would be an overclaim — it only holds for the TOML hosts, whose
    // editor preserves the original text.
    expect(JSON.parse(restored)).toEqual(JSON.parse(HOST_WRITTEN_SETTINGS));
    expect(restored).not.toBe(HOST_WRITTEN_SETTINGS);
    // Restoring the whole file verbatim would be worse than this: it would also
    // revert settings the user changed after installing, which we never owned.
  });

  it("takes its skills directory with it when it created one", async () => {
    const { layout, qwenDir } = await fixture();
    await writeFile(mcpConfigPath(layout), HOST_WRITTEN_SETTINGS);

    await applyRecallInstall(await planRecallInstall(layout, runtime()));
    await rollbackRecallInstall(layout);

    // Qwen Code ships no `skills` directory, so the one holding our Skill is
    // ours two levels deep. Removing only the inner level left an empty
    // `skills/` behind in every such host — found on the real machine.
    expect((await readdir(qwenDir)).sort()).toEqual(["settings.json"]);
  });

  it("keeps a skills directory that holds someone else's skill", async () => {
    const { layout, qwenDir } = await fixture();
    await writeFile(mcpConfigPath(layout), HOST_WRITTEN_SETTINGS);
    const theirs = path.join(qwenDir, "skills", "their-skill");
    await mkdir(theirs, { recursive: true });
    await writeFile(path.join(theirs, "SKILL.md"), "theirs\n");

    await applyRecallInstall(await planRecallInstall(layout, runtime()));
    await rollbackRecallInstall(layout);

    // The cleanup walks up two levels, so it has to stop at anything occupied.
    expect(await readdir(path.join(qwenDir, "skills"))).toEqual([
      "their-skill",
    ]);
  });
});

async function fixture() {
  const qwenDir = await mkdtemp(path.join(os.tmpdir(), "om-qwen-"));
  const layout = qwenCodeLayout(qwenDir);
  return { layout, qwenDir, configPath: mcpConfigPath(layout) };
}

function runtime() {
  return {
    runtimeCommand: "/opt/one-memory/bin/one-memory",
    mcpEntryPath: "/opt/one-memory/mcp/entry.mjs",
    discoveryPath: "/opt/one-memory/runtime.json",
  };
}
