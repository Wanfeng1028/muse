import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readdir, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

it("builds two self-contained node24 assets and exact fixed-name hash manifest outside default dist", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "d37-build-assets-"));
  const script = fileURLToPath(
    new URL("../../../scripts/build-hook-assets.mjs", import.meta.url),
  );
  try {
    const result = spawnSync(
      process.execPath,
      [script, "--outdir", path.join(root, "assets")],
      {
        cwd: root,
        env: { PATH: "/usr/bin:/bin", HOME: root },
        encoding: "utf8",
        timeout: 15000,
      },
    );
    expect(result.status, result.stderr).toBe(0);
    expect(await readdir(path.join(root, "assets"))).toEqual([
      "manifest.json",
      "notification.mjs",
      "runtime.mjs",
    ]);
    const files: Record<string, { sha256: string; bytes: number }> = {};
    for (const name of ["runtime.mjs", "notification.mjs"]) {
      const content = await readFile(path.join(root, "assets", name));
      files[name] = {
        sha256: createHash("sha256").update(content).digest("hex"),
        bytes: content.byteLength,
      };
      expect(content.toString()).not.toMatch(
        /from ["']\.\/chunk-|\/test-source-changed/,
      );
    }
    expect(
      JSON.parse(
        await readFile(path.join(root, "assets/manifest.json"), "utf8"),
      ),
    ).toEqual({
      schemaVersion: 1,
      runtimeCapability: "mh-c01-runtime-v1",
      notificationCapability: "source-change-v1",
      runtimeTarget: "node24",
      files,
    });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}, 20000);
