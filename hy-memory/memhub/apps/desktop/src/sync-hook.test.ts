import { createHash } from "node:crypto";
import {
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  hasSyncHookArtifacts,
  loadSyncHookAssets,
  syncHookPreview,
} from "./sync-hook";

const roots: string[] = [];
const hash = (value: string) =>
  createHash("sha256").update(value).digest("hex");
afterEach(async () => {
  for (const root of roots.splice(0))
    await rm(root, { recursive: true, force: true });
});
async function fixture() {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "om-sync-assets-")),
  );
  roots.push(root);
  const files = {
    "runtime.mjs": 'export const marker = "mh-c01-runtime-v1";',
    "notification.mjs": 'export const capability = "source-change-v1";',
  };
  for (const [name, value] of Object.entries(files))
    await writeFile(path.join(root, name), value);
  const manifest = {
    schemaVersion: 1,
    runtimeCapability: "mh-c01-runtime-v1",
    notificationCapability: "source-change-v1",
    runtimeTarget: "node24",
    files: Object.fromEntries(
      Object.entries(files).map(([name, value]) => [
        name,
        { sha256: hash(value), bytes: Buffer.byteLength(value) },
      ]),
    ),
  };
  await writeFile(path.join(root, "manifest.json"), JSON.stringify(manifest));
  return { root, files, manifest };
}

describe("trusted sync hook assets and previews", () => {
  it("requires the exact two self-contained asset hashes", async () => {
    const f = await fixture();
    const assets = await loadSyncHookAssets(f.root);
    expect(assets.runtime).toBe(f.files["runtime.mjs"]);
    await writeFile(path.join(f.root, "runtime.mjs"), "changed");
    await expect(loadSyncHookAssets(f.root)).rejects.toThrow(
      "sync_hook_assets_unavailable",
    );
  });
  it.each(["extra", "capability", "hash", "missing"])(
    "rejects %s manifest data",
    async (condition) => {
      const f = await fixture();
      const manifest: Record<string, unknown> = { ...f.manifest };
      if (condition === "extra") manifest.endpoint = "http://untrusted";
      if (condition === "capability")
        manifest.notificationCapability = "unknown";
      if (condition === "hash")
        manifest.files = {
          ...f.manifest.files,
          "runtime.mjs": { sha256: "not-a-hash", bytes: 1 },
        };
      if (condition === "missing")
        manifest.files = { "runtime.mjs": f.manifest.files["runtime.mjs"] };
      await writeFile(
        path.join(f.root, "manifest.json"),
        JSON.stringify(manifest),
      );
      await expect(loadSyncHookAssets(f.root)).rejects.toThrow(
        "sync_hook_assets_unavailable",
      );
    },
  );
  it("previews only paths and operations, and binds installation revisions", () => {
    const plan = {
      operation: "install",
      fingerprint: "a".repeat(64),
      files: [
        { path: "settings.json", content: "old", after: "new", mode: 0o600 },
        {
          path: ".one-memory/mh-c01/config.json",
          content: null,
          after: "private configuration",
          mode: 0o600,
        },
      ],
    } as Parameters<typeof syncHookPreview>[1];
    const identity = {
      installationId: "fixture-installation",
      revision: 1,
      credentialDigest: "b".repeat(64),
    };
    const preview = syncHookPreview("/fixture/.claude", plan, identity);
    expect(preview.files).toEqual([
      {
        path: "/fixture/.claude/settings.json",
        action: "update",
        owner: "host",
      },
      {
        path: "/fixture/.claude/.one-memory/mh-c01/config.json",
        action: "create",
        owner: "one-memory",
      },
    ]);
    expect(JSON.stringify(preview)).not.toMatch(
      /private configuration|credentialDigest|bbbb/,
    );
    expect(
      syncHookPreview("/fixture/.claude", plan, { ...identity, revision: 2 })
        .fingerprint,
    ).not.toBe(preview.fingerprint);
  });
  it("detects leftover hook files but does not treat retained state as an installed hook", async () => {
    const f = await fixture();
    const root = path.join(f.root, "claude");
    await mkdir(path.join(root, ".one-memory/mh-c01/state"), {
      recursive: true,
    });
    await writeFile(
      path.join(root, ".one-memory/mh-c01/state/session.json"),
      "{}",
    );
    expect(await hasSyncHookArtifacts(root)).toBe(false);
    await writeFile(path.join(root, ".one-memory/mh-c01/hook.mjs"), "owned");
    expect(await hasSyncHookArtifacts(root)).toBe(true);
    expect(
      await readFile(
        path.join(root, ".one-memory/mh-c01/state/session.json"),
        "utf8",
      ),
    ).toBe("{}");
  });
});
