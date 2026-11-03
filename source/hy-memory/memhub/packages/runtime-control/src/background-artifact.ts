import { createHash } from "node:crypto";
import { constants, type Stats } from "node:fs";
import * as fs from "node:fs/promises";
import path from "node:path";
import {
  type DistributionManifest,
  verifyInstalledDistribution,
} from "./local-install.js";
import {
  type RuntimeInstallLayout,
  runtimeInstallLayout,
} from "./service-plan.js";

const MAX_MANIFEST_BYTES = 4 * 1024 * 1024;
const MAX_ENTRIES = 100000;
const REQUIRED_FILES = [
  "bin/node",
  "bin/one-memory",
  "bin/one-memory.cjs",
  "core/one-memory",
  "runtime/runtime.cjs",
  "host-bridge/mcp.cjs",
  "host-bridge/recall-cli.cjs",
  "host-bridge/sync-hook/manifest.json",
  "web/index.html",
] as const;
const RESOURCE_FIELDS = [
  "nodeCommand",
  "runtimeEntry",
  "coreCommand",
  "mcpEntryPath",
  "recallCliPath",
  "syncHookAssetsDirectory",
] as const;

function fail(): never {
  throw new Error("background_artifact_invalid");
}
function absolute(value: unknown): string {
  if (
    typeof value !== "string" ||
    !path.isAbsolute(value) ||
    path.normalize(value) !== value ||
    /[\0\r\n]/.test(value)
  )
    fail();
  return value;
}
function within(root: string, target: string): boolean {
  const relative = path.relative(root, target);
  return (
    relative === "" ||
    (!path.isAbsolute(relative) &&
      relative !== ".." &&
      !relative.startsWith(`..${path.sep}`))
  );
}
function owned(info: Stats): void {
  if (
    info.uid !== process.getuid?.() ||
    (info.mode & 0o022) !== 0 ||
    (info.mode & 0o7000) !== 0
  )
    fail();
}
async function directory(target: string): Promise<Stats> {
  const info = await fs.lstat(target);
  if (
    !info.isDirectory() ||
    info.isSymbolicLink() ||
    (await fs.realpath(target)) !== target
  )
    fail();
  owned(info);
  return info;
}
function stamp(info: Stats): readonly number[] {
  return [
    info.dev,
    info.ino,
    info.mode,
    info.uid,
    info.gid,
    info.nlink,
    info.size,
    info.mtimeMs,
    info.ctimeMs,
  ];
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object")
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`,
      )
      .join(",")}}`;
  return JSON.stringify(value);
}
function exact(
  value: unknown,
  keys: readonly string[],
  optionalKeys: readonly string[] = [],
): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  const present = Object.keys(value);
  if (keys.some((key) => !Object.hasOwn(value, key))) fail();
  for (const key of present) {
    if (!keys.includes(key) && !optionalKeys.includes(key)) fail();
  }
}
function safeRelative(value: string): boolean {
  return (
    value.length > 0 &&
    !path.isAbsolute(value) &&
    !/[\\\0\r\n]/.test(value) &&
    value
      .split("/")
      .every((part) => part !== "" && part !== "." && part !== "..")
  );
}

async function manifest(root: string): Promise<DistributionManifest> {
  const target = path.join(root, "manifest.json");
  const named = await fs.lstat(target);
  if (
    !named.isFile() ||
    named.isSymbolicLink() ||
    named.nlink !== 1 ||
    named.size > MAX_MANIFEST_BYTES
  )
    fail();
  owned(named);
  const handle = await fs.open(
    target,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  );
  try {
    const before = await handle.stat();
    if (canonical(stamp(before)) !== canonical(stamp(named))) fail();
    const bytes = Buffer.alloc(before.size + 1);
    let length = 0;
    while (length < bytes.length) {
      const result = await handle.read({
        buffer: bytes,
        offset: length,
        length: bytes.length - length,
        position: length,
      });
      if (!result.bytesRead) break;
      length += result.bytesRead;
    }
    if (
      length !== before.size ||
      canonical(stamp(before)) !== canonical(stamp(await handle.stat())) ||
      canonical(stamp(before)) !== canonical(stamp(await fs.lstat(target)))
    )
      fail();
    const value: unknown = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(
        bytes.subarray(0, length),
      ),
    );
    exact(
      value,
      ["schema_version", "product", "version", "platform", "arch", "files"],
      ["build_number"],
    );
    if (
      value.schema_version !== 1 ||
      value.product !== "one-memory-runtime" ||
      typeof value.version !== "string" ||
      !/^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$/.test(value.version) ||
      (value.build_number !== undefined &&
        (typeof value.build_number !== "number" ||
          !Number.isSafeInteger(value.build_number) ||
          value.build_number < 0)) ||
      value.platform !== process.platform ||
      value.arch !== process.arch
    )
      fail();
    const files = value.files;
    if (
      !files ||
      typeof files !== "object" ||
      Array.isArray(files) ||
      Object.keys(files).length > MAX_ENTRIES
    )
      fail();
    if (REQUIRED_FILES.some((file) => !Object.hasOwn(files, file))) fail();
    for (const [name, digest] of Object.entries(files)) {
      if (
        name === "manifest.json" ||
        !safeRelative(name) ||
        typeof digest !== "string" ||
        digest.length !== 64 ||
        !/^[a-f0-9]{64}$/.test(digest)
      )
        fail();
    }
    return value as unknown as DistributionManifest;
  } finally {
    await handle.close();
  }
}

async function tree(root: string): Promise<string> {
  const entries: unknown[] = [];
  async function visit(current: string, depth: number): Promise<void> {
    if (depth > 64 || entries.length >= MAX_ENTRIES) fail();
    const info = await fs.lstat(current);
    const relative = path.relative(root, current);
    if (relative && !safeRelative(relative)) fail();
    if (info.isSymbolicLink()) {
      if (info.uid !== process.getuid?.() || info.nlink !== 1) fail();
      const link = await fs.readlink(current);
      const lexical = path.resolve(path.dirname(current), link);
      if (!within(root, lexical)) fail();
      const resolved = await fs.realpath(current);
      if (!within(root, resolved)) fail();
      const target = await fs.lstat(resolved);
      if (!target.isFile() || target.nlink !== 1) fail();
      owned(target);
      entries.push([relative, stamp(info), link, resolved, stamp(target)]);
      return;
    }
    owned(info);
    if (!info.isDirectory() && (!info.isFile() || info.nlink !== 1)) fail();
    entries.push([relative, stamp(info)]);
    if (info.isDirectory()) {
      for (const name of (await fs.readdir(current)).sort())
        await visit(path.join(current, name), depth + 1);
    }
  }
  await visit(root, 0);
  return canonical(entries);
}

/** Read-only gate for an already installed artifact in a trusted maintenance window.
 * No signature/OS registration claim; pre/post checks are not a same-UID sandbox
 * or an atomic filesystem snapshot. Callers must exclude concurrent installers.
 */
export async function verifyBackgroundArtifact(
  layout: RuntimeInstallLayout,
): Promise<{ digest: string; version: string; root: string }> {
  try {
    if (
      (process.platform !== "darwin" && process.platform !== "linux") ||
      layout.platform !== process.platform
    )
      fail();
    // Snapshot trusted inputs before awaits; never normalize to a different data instance.
    const checked = { ...layout };
    const current = absolute(checked.installRoot);
    const dataDir = absolute(checked.dataDir);
    absolute(checked.home);
    if (
      path.basename(current) !== "current" ||
      current
        .split(path.sep)
        .some((part) => part.toLowerCase().endsWith(".app")) ||
      current === "/Volumes" ||
      current.startsWith("/Volumes/")
    )
      fail();
    const parent = path.dirname(current);
    if (within(parent, dataDir) || within(dataDir, parent)) fail();
    const standard = runtimeInstallLayout({
      platform: checked.platform,
      home: checked.home,
      installRoot: current,
      dataDir,
    });
    if (RESOURCE_FIELDS.some((field) => checked[field] !== standard[field]))
      fail();
    const parentBefore = stamp(await directory(parent));
    const versions = path.join(parent, "versions");
    const versionsBefore = stamp(await directory(versions));
    const linkBefore = await fs.lstat(current);
    if (
      !linkBefore.isSymbolicLink() ||
      linkBefore.uid !== process.getuid?.() ||
      linkBefore.nlink !== 1
    )
      fail();
    const link = await fs.readlink(current);
    const root = path.resolve(parent, link);
    if (
      path.dirname(root) !== versions ||
      (await fs.realpath(current)) !== root
    )
      fail();
    await directory(root);
    const beforeManifest = await manifest(root);
    if (
      path.basename(root) !==
      `${beforeManifest.version}-${beforeManifest.platform}-${beforeManifest.arch}`
    )
      fail();
    for (const file of REQUIRED_FILES) {
      const info = await fs.lstat(path.join(root, file));
      if (!info.isFile() || info.isSymbolicLink()) fail();
    }
    await directory(path.join(root, "host-bridge/sync-hook"));
    const beforeTree = await tree(root);
    const verified = await verifyInstalledDistribution(
      root,
      checked.platform,
      process.arch,
    );
    if (
      canonical(verified) !== canonical(beforeManifest) ||
      canonical(await manifest(root)) !== canonical(beforeManifest) ||
      (await tree(root)) !== beforeTree ||
      canonical(stamp(await directory(parent))) !== canonical(parentBefore) ||
      canonical(stamp(await directory(versions))) !==
        canonical(versionsBefore) ||
      (await fs.readlink(current)) !== link ||
      canonical(stamp(await fs.lstat(current))) !== canonical(stamp(linkBefore))
    )
      fail();
    return {
      digest: createHash("sha256").update(canonical(verified)).digest("hex"),
      version: verified.version,
      root,
    };
  } catch {
    return fail();
  }
}
