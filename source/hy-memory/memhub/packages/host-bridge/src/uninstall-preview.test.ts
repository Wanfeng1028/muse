import { mkdir, mkdtemp, readFile, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  applyRecallUninstall,
  cursorLayout,
  mcpConfigPath,
  piLayout,
  planRecallInstall,
  planRecallUninstall,
  previewRecallUninstall,
} from "./recall-installer.js";

async function fixture(kind: "cursor" | "pi") {
  const root = await mkdtemp(path.join(os.tmpdir(), "uninstall-preview-"));
  const hostDir = path.join(root, kind === "cursor" ? ".cursor" : ".pi/agent");
  await mkdir(hostDir, { recursive: true });
  const layout = kind === "cursor" ? cursorLayout(hostDir) : piLayout(hostDir);
  const runtime = {
    runtimeCommand: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    mcpEntryPath: "/Applications/MemHub.app/Contents/Resources/mcp.cjs",
    discoveryPath: path.join(root, "discovery.json"),
    recallCliPath: "/Applications/MemHub.app/Contents/Resources/recall.cjs",
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

async function missing(target: string): Promise<boolean> {
  try {
    await stat(target);
    return false;
  } catch {
    return true;
  }
}

describe("uninstall preview", () => {
  it("shows the edit without making it", async () => {
    const { layout, runtime } = await fixture("cursor");
    const original = longConfig();
    await writeFile(mcpConfigPath(layout), original, { encoding: "utf8" });
    await applyRecallInstall(await planRecallInstall(layout, runtime));
    const installed = await readFile(mcpConfigPath(layout), "utf8");

    const preview = previewRecallUninstall(await planRecallUninstall(layout));

    expect(preview.hostId).toBe("cursor");
    // Previewing changes nothing: the install is still fully in place.
    expect(await readFile(mcpConfigPath(layout), "utf8")).toBe(installed);
    expect(await missing(layout.skillPath ?? "")).toBe(false);

    const config = preview.files.find(
      (file) => file.path === mcpConfigPath(layout),
    );
    expect(config?.owner).toBe("host");
    expect(config?.deleted).toBe(false);
    // Only the region that goes away, not 60 lines of the user's settings.
    expect(config?.hunk?.removed.join("\n")).toContain("one-memory");
    expect(config?.hunk?.added.join("\n")).not.toContain("one-memory");
    expect(config?.hunk?.removed.length).toBeLessThan(20);
  });

  it("says a file goes away rather than diffing it against nothing", async () => {
    const { layout, runtime } = await fixture("cursor");
    await applyRecallInstall(await planRecallInstall(layout, runtime));

    const preview = previewRecallUninstall(await planRecallUninstall(layout));

    // The skill is entirely ours and displaced nothing, so it is removed.
    // Reporting that as a hunk removing every line would bury the point.
    const skill = preview.files.find((file) => file.path === layout.skillPath);
    expect(skill?.owner).toBe("one-memory");
    expect(skill?.deleted).toBe(true);
    expect(skill?.hunk).toBeNull();
    // Cursor had no mcp.json before the install, so that goes too.
    const config = preview.files.find(
      (file) => file.path === mcpConfigPath(layout),
    );
    expect(config?.deleted).toBe(true);
  });

  it("describes exactly what apply then writes", async () => {
    const { layout, runtime } = await fixture("cursor");
    const original = longConfig();
    await writeFile(mcpConfigPath(layout), original, { encoding: "utf8" });
    await applyRecallInstall(await planRecallInstall(layout, runtime));
    const installed = await readFile(mcpConfigPath(layout), "utf8");

    const plan = await planRecallUninstall(layout);
    const preview = previewRecallUninstall(plan);
    await applyRecallUninstall(plan, preview.fingerprint);

    // Rebuilding the file from the hunk has to give what actually landed, or
    // the diff the user approved was not the edit that happened.
    const hunk = preview.files.find(
      (file) => file.path === mcpConfigPath(layout),
    )?.hunk;
    const lines = installed.split("\n");
    const rebuilt = [
      ...lines.slice(0, (hunk?.startLine ?? 1) - 1),
      ...(hunk?.added ?? []),
      ...lines.slice((hunk?.startLine ?? 1) - 1 + (hunk?.removed.length ?? 0)),
    ].join("\n");
    expect(rebuilt).toBe(await readFile(mcpConfigPath(layout), "utf8"));
    // And the user's own settings came back exactly as they were.
    expect(await readFile(mcpConfigPath(layout), "utf8")).toBe(original);
  });

  it("refuses an approval for a file that has since moved", async () => {
    const { layout, runtime } = await fixture("cursor");
    await writeFile(mcpConfigPath(layout), longConfig(), { encoding: "utf8" });
    await applyRecallInstall(await planRecallInstall(layout, runtime));

    const preview = previewRecallUninstall(await planRecallUninstall(layout));
    // The user adds a server of their own between seeing the diff and clicking.
    const current = await readFile(mcpConfigPath(layout), "utf8");
    await writeFile(
      mcpConfigPath(layout),
      current.replace('"mcpServers": {', '"mcpServers": {\n    "theirs": {},'),
      { encoding: "utf8" },
    );

    const fresh = await planRecallUninstall(layout);
    await expect(
      applyRecallUninstall(fresh, preview.fingerprint),
    ).rejects.toThrow(/changed since the preview/);
    // Refused means refused: we are still installed, and their server is intact.
    expect(await readFile(mcpConfigPath(layout), "utf8")).toContain("theirs");
    expect(await readFile(mcpConfigPath(layout), "utf8")).toContain(
      "one-memory",
    );

    // Approving the state that is actually there goes through, and keeps what
    // they added.
    const now = await planRecallUninstall(layout);
    await applyRecallUninstall(now, previewRecallUninstall(now).fingerprint);
    const after = await readFile(mcpConfigPath(layout), "utf8");
    expect(after).toContain("theirs");
    expect(after).not.toContain("one-memory");
  });

  it("still uninstalls when no approval is passed", async () => {
    const { layout, runtime } = await fixture("cursor");
    await writeFile(mcpConfigPath(layout), longConfig(), { encoding: "utf8" });
    await applyRecallInstall(await planRecallInstall(layout, runtime));

    // The CLI has no one to show a diff to, so the fingerprint is optional.
    await applyRecallUninstall(await planRecallUninstall(layout));

    expect(await readFile(mcpConfigPath(layout), "utf8")).toBe(longConfig());
    expect(await missing(layout.journalPath)).toBe(true);
  });

  it("previews a host whose whole install is one skill", async () => {
    const { layout, runtime } = await fixture("pi");
    await applyRecallInstall(await planRecallInstall(layout, runtime));

    const plan = await planRecallUninstall(layout);
    const preview = previewRecallUninstall(plan);

    // Pi has no MCP config. The preview is the skill plus the capture extension.
    expect(preview.files).toHaveLength(2);
    expect(preview.files.every((file) => file.deleted)).toBe(true);
    await applyRecallUninstall(plan, preview.fingerprint);
    expect(await missing(layout.skillPath ?? "")).toBe(true);
  });
});
