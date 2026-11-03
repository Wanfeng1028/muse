import { spawnSync } from "node:child_process";
import { copyFile, mkdir, mkdtemp, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("built Cursor installer CLI", () => {
  it("applies, verifies, and rolls back against a fixture directory", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "om-installer-cli-"));
    const cursorDir = path.join(root, ".cursor");
    await mkdir(cursorDir);
    await copyFile(
      path.join(process.cwd(), "fixtures", "cursor", "mcp.json"),
      path.join(cursorDir, "mcp.json"),
    );
    const cli = path.join(process.cwd(), "dist", "installer-cli.cjs");
    const common = [
      "--cursor-dir",
      cursorDir,
      "--runtime-command",
      process.execPath,
      "--mcp-entry",
      path.join(process.cwd(), "dist", "mcp.cjs"),
      "--discovery",
      path.join(root, "cursor-broker.json"),
      "--credential-file",
      path.join(root, "credential"),
      "--capture-command",
      process.execPath,
      "--data-dir",
      path.join(root, "data"),
    ];

    expect(run(cli, ["apply", ...common]).status).toBe(0);
    expect(run(cli, ["verify", "--cursor-dir", cursorDir]).status).toBe(0);

    // Local package scope: rollback (and its preview) are disabled and must
    // refuse before touching anything, with the exact visible copy.
    const before = await readFile(path.join(cursorDir, "mcp.json"), "utf8");
    const rollback = run(cli, ["rollback", "--cursor-dir", cursorDir]);
    expect(rollback.status).toBe(1);
    expect(rollback.stderr).toContain("体验版暂不支持");
    const previewRollback = run(cli, [
      "preview-rollback",
      "--cursor-dir",
      cursorDir,
    ]);
    expect(previewRollback.status).toBe(1);
    expect(previewRollback.stderr).toContain("体验版暂不支持");
    // Zero mutation: the installed config is byte-identical after refusing.
    expect(await readFile(path.join(cursorDir, "mcp.json"), "utf8")).toBe(
      before,
    );

    const config = JSON.parse(
      await readFile(path.join(cursorDir, "mcp.json"), "utf8"),
    );
    expect(config.mcpServers["fixture-existing-server"]).toBeDefined();
    // Install stays enabled, so our entry is present and the disabled rollback
    // above did not remove it.
    expect(config.mcpServers["one-memory"]).toBeDefined();
  }, 15_000);
});

function run(cli: string, args: string[]) {
  return spawnSync(process.execPath, [cli, ...args], {
    encoding: "utf8",
  });
}
