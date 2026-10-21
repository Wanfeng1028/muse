import { createHash } from "node:crypto";
import * as fs from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, it, vi } from "vitest";
import { verifyBackgroundArtifact } from "./background-artifact.js";
import { verifyInstalledDistribution } from "./local-install.js";
import { runtimeInstallLayout } from "./service-plan.js";

vi.mock("./local-install.js", async (original) => {
  const real = await original<typeof import("./local-install.js")>();
  return {
    ...real,
    verifyInstalledDistribution: vi.fn(real.verifyInstalledDistribution),
  };
});
const roots: string[] = [];
const platform = process.platform === "darwin" ? "darwin" : "linux";
const hash = (content: string | Buffer) =>
  createHash("sha256").update(content).digest("hex");
async function fixture() {
  const home = await fs.realpath(
    await fs.mkdtemp(path.join(tmpdir(), "bg-artifact-")),
  );
  roots.push(home);
  const parent = path.join(home, "installed");
  const root = path.join(
    parent,
    "versions",
    `1.2.3-${platform}-${process.arch}`,
  );
  await fs.mkdir(root, { recursive: true, mode: 0o700 });
  // A manifest whose `arch` must be backed by the actual Mach-O slice, so the
  // native payloads carry a real 64-bit header instead of plain text.
  const nativeFixture = Buffer.alloc(8);
  nativeFixture.writeUInt32LE(0xfeedfacf, 0); // MH_MAGIC_64
  nativeFixture.writeUInt32LE(
    process.arch === "arm64" ? 0x0100000c : 0x01000007,
    4,
  );
  const files: Record<string, string | Buffer> = {
    "bin/node": nativeFixture,
    "bin/one-memory": "cli launcher fixture",
    "bin/one-memory.cjs": "cli fixture",
    "core/one-memory": nativeFixture,
    "runtime/runtime.cjs": "runtime fixture",
    "host-bridge/mcp.cjs": "mcp fixture",
    "host-bridge/recall-cli.cjs": "recall fixture",
    "host-bridge/sync-hook/manifest.json": "{}",
    "web/index.html": "web fixture",
  };
  for (const [name, text] of Object.entries(files)) {
    await fs.mkdir(path.dirname(path.join(root, name)), {
      recursive: true,
      mode: 0o700,
    });
    await fs.writeFile(path.join(root, name), text, {
      mode:
        name.startsWith("bin/") || name === "core/one-memory" ? 0o700 : 0o600,
    });
  }
  const manifest = {
    schema_version: 1,
    product: "one-memory-runtime",
    version: "1.2.3",
    build_number: 1,
    platform,
    arch: process.arch,
    files: Object.fromEntries(
      Object.entries(files).map(([name, text]) => [name, hash(text)]),
    ),
  };
  const manifestPath = path.join(root, "manifest.json");
  const writeManifest = () =>
    fs.writeFile(manifestPath, JSON.stringify(manifest), { mode: 0o600 });
  await writeManifest();
  const current = path.join(parent, "current");
  await fs.symlink(path.relative(parent, root), current);
  const layout = runtimeInstallLayout({
    platform,
    home,
    installRoot: current,
    dataDir: path.join(home, "custom data "),
  });
  return {
    home,
    parent,
    root,
    current,
    layout,
    manifest,
    manifestPath,
    writeManifest,
  };
}
afterEach(async () => {
  vi.restoreAllMocks();
  await Promise.all(
    roots
      .splice(0)
      .map((root) => fs.rm(root, { recursive: true, force: true })),
  );
});

it("verifies installed resources without creating the independent data directory or changing current", async () => {
  const f = await fixture();
  const before = await fs.readFile(f.manifestPath, "utf8");
  const link = await fs.readlink(f.current);
  const result = await verifyBackgroundArtifact(f.layout);
  expect(result).toEqual({
    root: f.root,
    version: "1.2.3",
    digest: expect.stringMatching(/^[a-f0-9]{64}$/),
  });
  expect(await fs.readFile(f.manifestPath, "utf8")).toBe(before);
  expect(await fs.readlink(f.current)).toBe(link);
  await expect(fs.lstat(f.layout.dataDir)).rejects.toMatchObject({
    code: "ENOENT",
  });
  expect(f.layout.dataDir.endsWith("custom data ")).toBe(true);
});

it("canonical digest ignores object key order and whitespace but includes the entire manifest", async () => {
  const f = await fixture();
  const first = await verifyBackgroundArtifact(f.layout);
  await fs.writeFile(
    f.manifestPath,
    JSON.stringify(
      {
        files: Object.fromEntries(Object.entries(f.manifest.files).reverse()),
        arch: f.manifest.arch,
        platform: f.manifest.platform,
        version: f.manifest.version,
        build_number: f.manifest.build_number,
        product: f.manifest.product,
        schema_version: 1,
      },
      null,
      2,
    ),
  );
  expect((await verifyBackgroundArtifact(f.layout)).digest).toBe(first.digest);
  await fs.writeFile(path.join(f.root, "web/index.html"), "new web");
  f.manifest.files["web/index.html"] = hash("new web");
  await f.writeManifest();
  expect((await verifyBackgroundArtifact(f.layout)).digest).not.toBe(
    first.digest,
  );
});

it.each(["win32", platform === "darwin" ? "linux" : "darwin"] as const)(
  "rejects platform %s without validating another machine's artifact",
  async (other) => {
    const f = await fixture();
    await expect(
      verifyBackgroundArtifact({ ...f.layout, platform: other }),
    ).rejects.toThrow("background_artifact_invalid");
  },
);

it.each([
  "nodeCommand",
  "runtimeEntry",
  "coreCommand",
  "mcpEntryPath",
  "recallCliPath",
  "syncHookAssetsDirectory",
] as const)("rejects layout resource substitution: %s", async (field) => {
  const f = await fixture();
  await expect(
    verifyBackgroundArtifact({
      ...f.layout,
      [field]: path.join(f.home, "other"),
    }),
  ).rejects.toThrow("background_artifact_invalid");
});

it("requires an independent absolute data directory and leaves it untouched", async () => {
  const f = await fixture();
  for (const dataDir of [
    "relative",
    "",
    "/tmp/bad\npath",
    f.root,
    path.join(f.current, "data"),
    f.parent,
  ]) {
    await expect(
      verifyBackgroundArtifact({ ...f.layout, dataDir }),
    ).rejects.toThrow("background_artifact_invalid");
  }
});

it("refuses a direct version directory or a regular current entry", async () => {
  const f = await fixture();
  await expect(
    verifyBackgroundArtifact(
      runtimeInstallLayout({ ...f.layout, installRoot: f.root }),
    ),
  ).rejects.toThrow();
  await fs.unlink(f.current);
  await fs.mkdir(f.current);
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
});

it("rejects external, nested or symlink version targets", async () => {
  const f = await fixture();
  await fs.unlink(f.current);
  await fs.symlink(f.home, f.current);
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
  await fs.unlink(f.current);
  const alias = path.join(f.parent, "versions", "alias");
  await fs.symlink(f.root, alias);
  await fs.symlink("versions/alias", f.current);
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
});

it("rejects unsafe parent or version directory permissions without chmod repair", async () => {
  const f = await fixture();
  for (const dir of [f.parent, path.dirname(f.root), f.root]) {
    await fs.chmod(dir, 0o777);
    await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
    expect((await fs.stat(dir)).mode & 0o777).toBe(0o777);
    await fs.chmod(dir, 0o700);
  }
});

it("rejects package-bundle current layouts", async () => {
  const f = await fixture();
  const app = path.join(f.home, "Temporary.app");
  await fs.rename(f.parent, app);
  const layout = runtimeInstallLayout({
    platform,
    home: f.home,
    installRoot: path.join(app, "current"),
    dataDir: f.layout.dataDir,
  });
  await expect(verifyBackgroundArtifact(layout)).rejects.toThrow();
});

it.each(["version", "arch", "platform"] as const)(
  "requires installed directory/host match for manifest %s",
  async (field) => {
    const f = await fixture();
    Object.assign(f.manifest, {
      [field]: field === "version" ? "2.0.0" : "wrong",
    });
    await f.writeManifest();
    await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow(
      "background_artifact_invalid",
    );
  },
);

it("refuses a hash mismatch or an unlisted file", async () => {
  const f = await fixture();
  await fs.writeFile(path.join(f.root, "web/index.html"), "corrupt");
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
  await fs.writeFile(path.join(f.root, "web/index.html"), "web fixture");
  await fs.writeFile(path.join(f.root, "unlisted"), "unknown");
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
});

it("rejects missing required resources even if manifest agrees with the incomplete tree", async () => {
  const f = await fixture();
  await fs.unlink(path.join(f.root, "runtime/runtime.cjs"));
  delete f.manifest.files["runtime/runtime.cjs"];
  await f.writeManifest();
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
});

it("rejects unsafe manifest extras, malformed content and path aliases", async () => {
  const f = await fixture();
  for (const content of [
    "{SECRET",
    JSON.stringify({ ...f.manifest, secret: "DO_NOT_EXPOSE" }),
    JSON.stringify({
      ...f.manifest,
      files: { ...f.manifest.files, "bin/../node": hash("x") },
    }),
  ]) {
    await fs.writeFile(f.manifestPath, content);
    const error = await verifyBackgroundArtifact(f.layout).catch(
      (reason: unknown) => reason,
    );
    expect(error).toEqual(new Error("background_artifact_invalid"));
    expect(error).not.toHaveProperty("cause");
  }
});

it("does not follow a symlink manifest or an external file link", async () => {
  const f = await fixture();
  const outside = path.join(f.home, "outside");
  await fs.writeFile(outside, await fs.readFile(f.manifestPath));
  await fs.unlink(f.manifestPath);
  await fs.symlink(outside, f.manifestPath);
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
  await fs.unlink(f.manifestPath);
  await f.writeManifest();
  await fs.symlink(outside, path.join(f.root, "external"));
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
});

it("retains a safe internal file symlink but rejects a link chain escaping the real root", async () => {
  const f = await fixture();
  await fs.symlink("web/index.html", path.join(f.root, "z-web-link"));
  f.manifest.files["z-web-link"] = hash("symlink\0web/index.html");
  await f.writeManifest();
  expect((await verifyBackgroundArtifact(f.layout)).root).toBe(f.root);
  await fs.unlink(path.join(f.root, "web/index.html"));
  const outside = path.join(f.home, "outside");
  await fs.writeFile(outside, "web fixture");
  await fs.symlink(outside, path.join(f.root, "web/index.html"));
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
});

it("rejects unexpected hardlinks and writable resource files", async () => {
  const f = await fixture();
  const resource = path.join(f.root, "bin/node");
  await fs.link(resource, path.join(f.home, "alias"));
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
  await fs.unlink(path.join(f.home, "alias"));
  await fs.chmod(resource, 0o777);
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
});

it("rejects oversized manifests without reading them unboundedly", async () => {
  const f = await fixture();
  await fs.writeFile(f.manifestPath, " ".repeat(4 * 1024 * 1024 + 1));
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow();
});

it("accepts a complete manifest with web-link beside web/index.html", async () => {
  const f = await fixture();
  await fs.symlink("web/index.html", path.join(f.root, "web-link"));
  f.manifest.files["web-link"] = hash("symlink\0web/index.html");
  await f.writeManifest();
  await expect(verifyBackgroundArtifact(f.layout)).resolves.toMatchObject({
    root: f.root,
    version: f.manifest.version,
  });
});

it.each(["current", "content", "manifest"])(
  "rejects %s changes across verification instead of returning stale approval",
  async (change) => {
    const f = await fixture();
    const real =
      await vi.importActual<typeof import("./local-install.js")>(
        "./local-install.js",
      );
    vi.mocked(verifyInstalledDistribution).mockImplementationOnce(
      async (...args) => {
        const verified = await real.verifyInstalledDistribution(...args);
        if (change === "current") {
          await fs.unlink(f.current);
          await fs.symlink(f.root, f.current);
        } else if (change === "content") {
          await fs.writeFile(
            path.join(f.root, "web/index.html"),
            "changed after hash verification",
          );
        } else {
          await fs.writeFile(
            f.manifestPath,
            JSON.stringify({ ...f.manifest, version: "new" }),
          );
        }
        return verified;
      },
    );
    await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow(
      "background_artifact_invalid",
    );
  },
);

it("rejects an in-tree directory link before invoking the stream hash verifier", async () => {
  const f = await fixture();
  await fs.symlink("web", path.join(f.root, "z-directory-link"));
  vi.mocked(verifyInstalledDistribution).mockClear();
  await expect(verifyBackgroundArtifact(f.layout)).rejects.toThrow(
    "background_artifact_invalid",
  );
  expect(verifyInstalledDistribution).not.toHaveBeenCalled();
});
