import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  cursorLayout,
  hermesLayout,
  mcpConfigPath,
  planRecallInstall,
  previewRecallInstall,
} from "./recall-installer.js";

async function fixture(kind: "cursor" | "hermes") {
  const root = await mkdtemp(path.join(os.tmpdir(), "preview-"));
  const hostDir = path.join(root, kind === "cursor" ? ".cursor" : ".hermes");
  await mkdir(hostDir, { recursive: true });
  const layout =
    kind === "cursor" ? cursorLayout(hostDir) : hermesLayout(hostDir);
  const runtime = {
    runtimeCommand: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    mcpEntryPath: "/Applications/MemHub.app/Contents/Resources/mcp.cjs",
    discoveryPath: path.join(root, "discovery.json"),
  };
  return { root, layout, runtime };
}

/** A settings document long enough that showing it whole would not be a review. */
function longConfig(): string {
  const filler = Array.from(
    { length: 60 },
    (_, index) => `  "setting${index}": ${index},`,
  );
  return `{\n${filler.join("\n")}\n  "mcpServers": {}\n}\n`;
}

describe("install preview", () => {
  it("shows the edit without making it", async () => {
    const { layout, runtime } = await fixture("cursor");
    await writeFile(mcpConfigPath(layout), longConfig(), { encoding: "utf8" });

    const plan = await planRecallInstall(layout, runtime);
    const preview = await previewRecallInstall(plan);

    expect(preview.hostId).toBe("cursor");
    // Nothing is written by previewing.
    expect(await readFile(mcpConfigPath(layout), "utf8")).toBe(longConfig());
    await expect(readFile(layout.skillPath ?? "", "utf8")).rejects.toThrow(
      /ENOENT/,
    );

    const config = preview.files.find(
      (file) => file.path === mcpConfigPath(layout),
    );
    expect(config?.owner).toBe("host");
    expect(config?.existed).toBe(true);
    // Only the changed region, not 60 lines of the user's own settings.
    expect(config?.hunk?.added.join("\n")).toContain("one-memory");
    expect(config?.hunk?.added.length).toBeLessThan(20);
    expect(config?.hunk?.contextBefore.length).toBeGreaterThan(0);
  });

  it("marks a file of ours as ours, and as new", async () => {
    const { layout, runtime } = await fixture("cursor");

    const preview = await previewRecallInstall(
      await planRecallInstall(layout, runtime),
    );

    const skill = preview.files.find((file) => file.path === layout.skillPath);
    expect(skill?.owner).toBe("one-memory");
    expect(skill?.existed).toBe(false);
    expect(skill?.hunk?.removed).toEqual([]);
  });

  it("describes exactly what apply then writes", async () => {
    const { layout, runtime } = await fixture("hermes");
    const before = "model:\n  default: qwen-plus\n";
    await writeFile(mcpConfigPath(layout), before, { encoding: "utf8" });

    const plan = await planRecallInstall(layout, runtime);
    const preview = await previewRecallInstall(plan);
    await applyRecallInstall(plan, preview.fingerprint);

    // Reconstructing the file from the hunk has to give what actually landed,
    // or the diff the user approved was not the edit that happened.
    const hunk = preview.files.find(
      (file) => file.path === mcpConfigPath(layout),
    )?.hunk;
    const lines = before.split("\n");
    const rebuilt = [
      ...lines.slice(0, (hunk?.startLine ?? 1) - 1),
      ...(hunk?.added ?? []),
      ...lines.slice((hunk?.startLine ?? 1) - 1 + (hunk?.removed.length ?? 0)),
    ].join("\n");
    expect(rebuilt).toBe(await readFile(mcpConfigPath(layout), "utf8"));
  });

  it("refuses an approval for a file that has since moved", async () => {
    const { layout, runtime } = await fixture("cursor");
    await writeFile(mcpConfigPath(layout), longConfig(), { encoding: "utf8" });

    const preview = await previewRecallInstall(
      await planRecallInstall(layout, runtime),
    );
    // The host, or the user, edits its settings between the preview and the click.
    await writeFile(mcpConfigPath(layout), `${longConfig()}\n`, {
      encoding: "utf8",
    });

    // The desktop confirms, then plans again before applying — so the plan's
    // own staleness check passes, having been made against the new file. The
    // approved fingerprint is what still refers to the state the user saw, and
    // is therefore the only thing left that can catch this.
    const fresh = await planRecallInstall(layout, runtime);
    await expect(
      applyRecallInstall(fresh, preview.fingerprint),
    ).rejects.toThrow(/changed since the preview/);

    // And approving the state that is actually there goes through.
    const current = await previewRecallInstall(
      await planRecallInstall(layout, runtime),
    );
    await applyRecallInstall(
      await planRecallInstall(layout, runtime),
      current.fingerprint,
    );
    expect(await readFile(mcpConfigPath(layout), "utf8")).toContain(
      "one-memory",
    );
  });

  it("still installs when no approval is passed", async () => {
    const { layout, runtime } = await fixture("cursor");

    // The CLI has no one to show a diff to, so the fingerprint is optional.
    await applyRecallInstall(await planRecallInstall(layout, runtime));

    expect(await readFile(mcpConfigPath(layout), "utf8")).toContain(
      "one-memory",
    );
  });
});
