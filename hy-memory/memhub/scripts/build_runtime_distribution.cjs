#!/usr/bin/env node

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const {
  chmod,
  copyFile,
  cp,
  lstat,
  mkdir,
  readFile,
  readlink,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
} = require("node:fs/promises");
const { createReadStream } = require("node:fs");
const path = require("node:path");
const { assertSemver, resolveBuildVersion } = require("./release-version.cjs");
const { readReleaseContract } = require("./release-contract.cjs");

const COMMIT = /^[0-9a-f]{40}$/;

async function sha256(file) {
  const digest = createHash("sha256");
  const info = await lstat(file);
  if (info.isSymbolicLink()) {
    digest.update("symlink\0");
    digest.update(await readlink(file));
    return digest.digest("hex");
  }
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
}

async function copyTree(source, target) {
  const resolved = await realpath(source);
  const info = await lstat(resolved);
  if (!info.isDirectory() || info.isSymbolicLink()) {
    throw new Error(`runtime source is not a directory: ${source}`);
  }
  await cp(resolved, target, {
    recursive: true,
    dereference: false,
    verbatimSymlinks: true,
    errorOnExist: true,
    force: false,
  });
}

function commandOutput(command, args, code) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(
      `${code}: ${result.stderr || result.stdout || "unknown error"}`,
    );
  }
  return result.stdout;
}

function machoDependencies(file) {
  const output = commandOutput(
    "/usr/bin/otool",
    ["-L", file],
    "runtime_node_otool_failed",
  );
  return output
    .split(/\r?\n/)
    .slice(1)
    .map((line) => line.trim().match(/^(\S+) \(/)?.[1] ?? null)
    .filter((value) => value !== null);
}

function machoRpaths(file) {
  const output = commandOutput(
    "/usr/bin/otool",
    ["-l", file],
    "runtime_node_otool_failed",
  );
  const lines = output.split(/\r?\n/);
  const rpaths = [];
  for (let index = 0; index < lines.length; index += 1) {
    if (lines[index]?.trim() !== "cmd LC_RPATH") continue;
    const match = lines
      .slice(index + 1, index + 5)
      .join("\n")
      .match(/\bpath (\S+) \(offset/);
    if (match) rpaths.push(match[1]);
  }
  return rpaths;
}

function isSystemDylib(dependency) {
  return (
    dependency.startsWith("/usr/lib/") ||
    dependency.startsWith("/System/Library/")
  );
}

async function resolveMacosDependency(dependency, loader, executable) {
  const candidates = [];
  if (dependency.startsWith("@rpath/")) {
    const suffix = dependency.slice("@rpath/".length);
    for (const rpath of machoRpaths(loader)) {
      const expanded = rpath
        .replace(/^@loader_path/, path.dirname(loader))
        .replace(/^@executable_path/, path.dirname(executable));
      candidates.push(path.join(expanded, suffix));
    }
    for (const rpath of machoRpaths(executable)) {
      const expanded = rpath
        .replace(/^@loader_path/, path.dirname(executable))
        .replace(/^@executable_path/, path.dirname(executable));
      candidates.push(path.join(expanded, suffix));
    }
  } else if (dependency.startsWith("@loader_path/")) {
    candidates.push(
      path.join(path.dirname(loader), dependency.slice("@loader_path/".length)),
    );
  } else if (dependency.startsWith("@executable_path/")) {
    candidates.push(
      path.join(
        path.dirname(executable),
        dependency.slice("@executable_path/".length),
      ),
    );
  } else if (path.isAbsolute(dependency)) {
    candidates.push(dependency);
  }
  for (const candidate of candidates) {
    const resolved = await realpath(candidate).catch(() => null);
    if (resolved !== null) return resolved;
  }
  throw new Error(`runtime_node_dependency_missing:${dependency}`);
}

async function packageMacosNodeDependencies(sourceNode, packagedNode, stage) {
  const kind = spawnSync("/usr/bin/file", ["-b", sourceNode], {
    encoding: "utf8",
  });
  if (kind.status !== 0 || !kind.stdout.includes("Mach-O")) return [];
  const libraryDir = path.join(stage, "lib");
  await mkdir(libraryDir, { recursive: true, mode: 0o700 });
  const copied = new Map();
  const queue = [{ source: await realpath(sourceNode), target: packagedNode }];
  const packaged = [];
  while (queue.length > 0) {
    const current = queue.shift();
    for (const dependency of machoDependencies(current.source)) {
      if (isSystemDylib(dependency)) continue;
      const source = await resolveMacosDependency(
        dependency,
        current.source,
        sourceNode,
      );
      const name = path.basename(source);
      const existing = copied.get(name);
      if (existing !== undefined && existing !== source) {
        throw new Error(`runtime_node_dependency_collision:${name}`);
      }
      const target = path.join(libraryDir, name);
      if (existing === undefined) {
        await copyFile(source, target);
        await chmod(target, 0o700);
        copied.set(name, source);
        packaged.push(path.relative(stage, target));
        queue.push({ source, target });
      }
      commandOutput(
        "/usr/bin/install_name_tool",
        ["-change", dependency, `@rpath/${name}`, current.target],
        "runtime_node_dependency_rewrite_failed",
      );
    }
    if (current.target !== packagedNode) {
      commandOutput(
        "/usr/bin/install_name_tool",
        ["-id", `@rpath/${path.basename(current.target)}`, current.target],
        "runtime_node_dependency_id_failed",
      );
    }
  }
  for (const relative of packaged) {
    commandOutput(
      "/usr/bin/codesign",
      ["--force", "--sign", "-", path.join(stage, relative)],
      "runtime_node_dependency_sign_failed",
    );
  }
  commandOutput(
    "/usr/bin/codesign",
    ["--force", "--sign", "-", packagedNode],
    "runtime_node_sign_failed",
  );
  return packaged.sort();
}

async function treeFiles(root, current = root) {
  const { readdir } = require("node:fs/promises");
  const entries = await readdir(current, { withFileTypes: true });
  entries.sort((left, right) => left.name.localeCompare(right.name));
  const files = [];
  for (const entry of entries) {
    const target = path.join(current, entry.name);
    if (entry.isSymbolicLink()) {
      const resolved = await realpath(target);
      const relative = path.relative(await realpath(root), resolved);
      assert(
        !relative.startsWith("..") && !path.isAbsolute(relative),
        `runtime resource link escapes distribution: ${target}`,
      );
      files.push(path.relative(root, target));
    } else if (entry.isDirectory()) {
      files.push(...(await treeFiles(root, target)));
    } else if (entry.isFile()) {
      files.push(path.relative(root, target));
    } else {
      throw new Error(`unsupported runtime resource: ${target}`);
    }
  }
  return files;
}

async function newestMtime(root) {
  const { readdir } = require("node:fs/promises");
  const entries = await readdir(root, { withFileTypes: true });
  let newest = 0;
  for (const entry of entries) {
    const target = path.join(root, entry.name);
    if (entry.isDirectory()) {
      newest = Math.max(newest, await newestMtime(target));
    } else if (entry.isFile() || entry.isSymbolicLink()) {
      newest = Math.max(newest, (await stat(target)).mtimeMs);
    }
  }
  return newest;
}

async function assertRuntimeControlFresh(sourceRoot) {
  const runtimeSource = path.join(
    sourceRoot,
    "packages",
    "runtime-control",
    "src",
  );
  const runtimeDist = path.join(
    sourceRoot,
    "packages",
    "runtime-control",
    "dist",
    "runtime.cjs",
  );
  const sourceMtime = Math.max(
    await newestMtime(runtimeSource),
    (
      await stat(
        path.join(sourceRoot, "packages", "runtime-control", "package.json"),
      )
    ).mtimeMs,
  );
  const distMtime = (await stat(runtimeDist)).mtimeMs;
  assert(
    distMtime >= sourceMtime,
    "runtime-control dist is stale; rebuild it before packaging",
  );
}

async function assertCoreFresh(sourceRoot, platform) {
  const coreRoot = path.join(sourceRoot, "apps", "core");
  const sourceMtime = Math.max(
    await newestMtime(path.join(coreRoot, "src")),
    (await stat(path.join(coreRoot, "one-memory.spec"))).mtimeMs,
    (await stat(path.join(coreRoot, "pyproject.toml"))).mtimeMs,
  );
  const coreBinary = path.join(
    coreRoot,
    "dist",
    "one-memory-runtime",
    platform === "win32" ? "one-memory.exe" : "one-memory",
  );
  const distMtime = (await stat(coreBinary)).mtimeMs;
  assert(
    distMtime >= sourceMtime,
    "core distribution is stale; rebuild the PyInstaller Core before packaging",
  );
}

/** The CLI bundles its own copy of `@one-memory/runtime-control`.
 *
 * That is how a stale `apps/cli/dist/one-memory.cjs` shipped an install path
 * that ignored the non-default-port change in `service-plan.ts`, while
 * `packages/runtime-control/dist` was fresh: the package's `bin/one-memory`
 * runs the CLI bundle, not the runtime-control dist. Guard the CLI bundle too,
 * against both its own sources and runtime-control's, since it inlines the
 * latter.
 */
async function assertCliFresh(sourceRoot) {
  const cliBundle = path.join(
    sourceRoot,
    "apps",
    "cli",
    "dist",
    "one-memory.cjs",
  );
  const cliSource = path.join(sourceRoot, "apps", "cli", "src");
  // A fixture without CLI sources still packs the (fixture) bundle; there is
  // nothing to compare against, so the guard is a no-op rather than a crash.
  const cliSourceExists = await lstat(cliSource).then(
    () => true,
    () => false,
  );
  if (!cliSourceExists) return;
  const mtimeOf = (file) =>
    stat(file).then(
      (info) => info.mtimeMs,
      () => 0,
    );
  const sourceMtime = Math.max(
    await newestMtime(cliSource),
    await newestMtime(
      path.join(sourceRoot, "packages", "runtime-control", "src"),
    ),
    await mtimeOf(path.join(sourceRoot, "apps", "cli", "package.json")),
    await mtimeOf(
      path.join(sourceRoot, "packages", "runtime-control", "package.json"),
    ),
  );
  const distMtime = (await stat(cliBundle)).mtimeMs;
  assert(
    distMtime >= sourceMtime,
    "CLI bundle is stale; rebuild @one-memory/cli before packaging (it inlines runtime-control)",
  );
}

async function buildRuntimeDistribution(options) {
  const sourceRoot = path.resolve(options.sourceRoot);
  const output = path.resolve(options.output);
  const stage = `${output}.stage`;
  assertSemver(options.version, "runtime distribution version");
  assert(
    Number.isSafeInteger(options.buildNumber) && options.buildNumber >= 0,
    `build_number must be a non-negative safe integer: ${options.buildNumber}`,
  );
  const gitCommit = options.gitCommit ?? null;
  assert(
    gitCommit === null ||
      (typeof gitCommit === "string" && COMMIT.test(gitCommit)),
    `git_commit must be a full lowercase SHA-1: ${String(gitCommit)}`,
  );
  const releaseContract = options.releaseContract ?? readReleaseContract();
  if (options.assertRuntimeControlFresh !== false) {
    await assertRuntimeControlFresh(sourceRoot);
  }
  if (options.assertCoreFresh !== false) {
    await assertCoreFresh(sourceRoot, options.platform);
  }
  if (options.assertCliFresh !== false) {
    await assertCliFresh(sourceRoot);
  }
  await rm(stage, { recursive: true, force: true });
  await mkdir(path.join(stage, "bin"), { recursive: true, mode: 0o700 });
  try {
    await copyFile(
      path.join(sourceRoot, "apps", "cli", "dist", "one-memory.cjs"),
      path.join(stage, "bin", "one-memory.cjs"),
    );
    await copyFile(
      options.nodeCommand,
      path.join(stage, "bin", nodeName(options.platform)),
    );
    if (options.platform === "darwin") {
      await packageMacosNodeDependencies(
        options.nodeCommand,
        path.join(stage, "bin", nodeName(options.platform)),
        stage,
      );
    }
    await copyTree(
      path.join(sourceRoot, "apps", "core", "dist", "one-memory-runtime"),
      path.join(stage, "core"),
    );
    await copyTree(
      path.join(sourceRoot, "packages", "runtime-control", "dist"),
      path.join(stage, "runtime"),
    );
    await copyTree(
      path.join(sourceRoot, "packages", "host-bridge", "dist"),
      path.join(stage, "host-bridge"),
    );
    await copyTree(
      path.join(sourceRoot, "apps", "web", "dist"),
      path.join(stage, "web"),
    );
    await mkdir(path.join(stage, "licenses"), { recursive: true, mode: 0o700 });
    for (const [source, target] of [
      ["SBOM.spdx.json", "SBOM.spdx.json"],
      ["THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"],
      ["LICENSE", "licenses/LICENSE.one-memory"],
      [
        "packages/host-bridge/src/memmy-adapter/claude-code/LICENSE.memmy",
        "licenses/LICENSE.memmy",
      ],
      [
        "packages/host-bridge/src/memmy-adapter/claude-code/PROVENANCE.md",
        "licenses/PROVENANCE.memmy.md",
      ],
    ]) {
      await copyFile(path.join(sourceRoot, source), path.join(stage, target));
    }
    const launcher = path.join(stage, "bin", cliName(options.platform));
    await writeFile(
      launcher,
      cliLauncher(options.platform, {
        buildNumber: options.buildNumber,
        version: options.version,
        packageId: options.packageId,
      }),
      {
        encoding: "utf8",
        mode: 0o700,
        flag: "wx",
      },
    );
    await chmod(launcher, 0o700);

    const relativeFiles = await treeFiles(stage);
    for (const required of [
      `bin/${nodeName(options.platform)}`,
      `bin/${cliName(options.platform)}`,
      "bin/one-memory.cjs",
      `core/${options.platform === "win32" ? "one-memory.exe" : "one-memory"}`,
      "runtime/runtime.cjs",
      ...(options.platform === "darwin" ? ["runtime/service-observer"] : []),
      "host-bridge/mcp.cjs",
      "host-bridge/recall-cli.cjs",
      "host-bridge/sync-hook/manifest.json",
      "web/index.html",
      "SBOM.spdx.json",
      "THIRD_PARTY_NOTICES.md",
      "licenses/LICENSE.one-memory",
      "licenses/LICENSE.memmy",
      "licenses/PROVENANCE.memmy.md",
    ]) {
      assert(
        relativeFiles.includes(required),
        `missing runtime artifact: ${required}`,
      );
    }
    const files = {};
    for (const relative of relativeFiles) {
      if (relative === "manifest.json") continue;
      files[relative] = await sha256(path.join(stage, relative));
    }
    const manifest = {
      schema_version: releaseContract.runtimeManifestSchema,
      product: "one-memory-runtime",
      version: options.version,
      build_number: options.buildNumber,
      git_commit: gitCommit,
      runtime_protocol: releaseContract.runtimeProtocol,
      supported_cli_protocol: releaseContract.runtimeSupportedCliProtocol,
      // The formal visible package identity, so a host install can bind to the
      // same artifact the App and diagnostics reference. `one-memory` decides
      // this when built by hand; the hourly builder passes the package-root
      // name. Absent identity is recorded explicitly rather than guessed.
      package_id: options.packageId ?? null,
      platform: options.platform,
      arch: options.arch,
      files,
    };
    await writeFile(
      path.join(stage, "manifest.json"),
      `${JSON.stringify(manifest, null, 2)}\n`,
      { encoding: "utf8", mode: 0o600 },
    );
    await rm(output, { recursive: true, force: true });
    await rename(stage, output);
    return manifest;
  } catch (error) {
    await rm(stage, { recursive: true, force: true });
    throw error;
  }
}

/** Assert a runtime distribution is exactly `manifest.files ∪ {manifest.json}`.
 *
 * The installer refuses anything else with `distribution_manifest_incomplete`,
 * so this is the same contract the lifecycle harness checks. Run it on a dist
 * directory before installing it, and never write smoke data, readiness
 * receipts or owner markers into that directory: those belong beside the dist,
 * not inside it. Returns the manifest on success. */
async function assertDistributionSelfContained(distRoot) {
  const manifest = JSON.parse(
    await readFile(path.join(distRoot, "manifest.json"), "utf8"),
  );
  const declared = Object.keys(manifest.files ?? {}).sort();
  // treeFiles walks depth-first; the installer compares default-sorted arrays,
  // so sort here too or the comparison is order-sensitive for no reason.
  const actual = (await treeFiles(distRoot)).sort();
  const expected = [...declared, "manifest.json"].sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    const extra = actual.filter((file) => !expected.includes(file));
    const missing = expected.filter((file) => !actual.includes(file));
    throw new Error(
      `distribution_manifest_incomplete extra=${JSON.stringify(extra)} missing=${JSON.stringify(missing)}`,
    );
  }
  return manifest;
}

function nodeName(platform) {
  return platform === "win32" ? "node.exe" : "node";
}

function cliName(platform) {
  return platform === "win32" ? "one-memory.cmd" : "one-memory";
}

function resolveGitCommit(sourceRoot, environment = process.env) {
  const supplied = environment.ONE_MEMORY_COMMIT?.trim();
  if (supplied) {
    if (!COMMIT.test(supplied)) {
      throw new Error(
        `ONE_MEMORY_COMMIT must be a full lowercase SHA-1: ${supplied}`,
      );
    }
    return supplied;
  }
  const result = require("node:child_process").spawnSync(
    "git",
    ["rev-parse", "HEAD"],
    { cwd: sourceRoot, encoding: "utf8" },
  );
  const value = result.stdout?.trim();
  if (result.status !== 0 || !COMMIT.test(value)) {
    throw new Error("runtime distribution git commit unavailable");
  }
  return value;
}

function cliLauncher(platform, identity = {}) {
  // Stamp package identity into the launcher so the diagnostic chain carries
  // the same build/package/round ids as the UI, no matter which host starts
  // the runtime (Desktop, CLI, or LaunchAgent).
  const packageId =
    identity.packageId ?? `one-memory-runtime-build-${identity.buildNumber}`;
  const round = String(identity.buildNumber);
  const buildId = packageId;
  if (platform === "win32") {
    return [
      "@echo off",
      `set ONE_MEMORY_BUILD_ID=${buildId}`,
      `set ONE_MEMORY_PACKAGE_ID=${packageId}`,
      `set ONE_MEMORY_ROUND=${round}`,
      `set ONE_MEMORY_BUILD_NUMBER=${round}`,
      `set ONE_MEMORY_VERSION=${identity.version ?? "development"}`,
      "set ONE_MEMORY_DIAGNOSTICS=1",
      '"%~dp0node.exe" "%~dp0one-memory.cjs" %*',
      "",
    ].join("\r\n");
  }
  return `#!/bin/sh
# Package identity for the shared diagnostic chain.
ONE_MEMORY_BUILD_ID="\${ONE_MEMORY_BUILD_ID:-${buildId}}"
ONE_MEMORY_PACKAGE_ID="\${ONE_MEMORY_PACKAGE_ID:-${packageId}}"
ONE_MEMORY_ROUND="\${ONE_MEMORY_ROUND:-${round}}"
ONE_MEMORY_BUILD_NUMBER="\${ONE_MEMORY_BUILD_NUMBER:-${round}}"
ONE_MEMORY_VERSION="\${ONE_MEMORY_VERSION:-${identity.version ?? "development"}}"
ONE_MEMORY_DIAGNOSTICS=1
export ONE_MEMORY_BUILD_ID ONE_MEMORY_PACKAGE_ID ONE_MEMORY_ROUND ONE_MEMORY_BUILD_NUMBER ONE_MEMORY_VERSION ONE_MEMORY_DIAGNOSTICS
SELF=$0
while [ -L "$SELF" ]; do
  DIR=$(CDPATH= cd -P -- "$(dirname -- "$SELF")" && pwd) || exit 1
  LINK=$(readlink "$SELF") || exit 1
  case "$LINK" in
    /*) SELF=$LINK ;;
    *) SELF=$DIR/$LINK ;;
  esac
done
DIR=$(CDPATH= cd -P -- "$(dirname -- "$SELF")" && pwd) || exit 1
# Name this payload's root so the Runtime can tell a non-default install from
# the everyday one and pick its Core port accordingly. A managed install runs
# from install/versions/version/bin; its service identity belongs to the
# install root, not to the selected version directory. A standalone distribution
# has no versions parent and continues to name its own payload root.
PAYLOAD_ROOT=$(CDPATH= cd -P -- "$DIR/.." && pwd) || exit 1
PAYLOAD_PARENT=$(CDPATH= cd -P -- "$PAYLOAD_ROOT/.." && pwd) || exit 1
case "$PAYLOAD_PARENT" in
  */versions) ONE_MEMORY_INSTALL_ROOT=$(CDPATH= cd -P -- "$PAYLOAD_PARENT/.." && pwd) || exit 1 ;;
  *) ONE_MEMORY_INSTALL_ROOT=$PAYLOAD_ROOT ;;
esac
export ONE_MEMORY_INSTALL_ROOT
exec "$DIR/node" "$DIR/one-memory.cjs" "$@"
`;
}

async function main() {
  const [output, platform, arch, requestedVersion, buildNumberRaw] =
    process.argv.slice(2);
  const sourceRoot = path.resolve(__dirname, "..");
  const version = resolveBuildVersion(
    requestedVersion === undefined
      ? process.env
      : { ...process.env, ONE_MEMORY_VERSION: requestedVersion },
    sourceRoot,
  );
  const buildNumber = Number(buildNumberRaw);
  // The package id is the staged directory's own name, which is what every
  // hourly receipt and owner marker already uses.
  const packageId = path.basename(path.resolve(output));
  if (
    !output ||
    !["darwin", "linux", "win32"].includes(platform) ||
    !arch ||
    buildNumberRaw === undefined ||
    !Number.isSafeInteger(buildNumber) ||
    buildNumber < 0
  ) {
    throw new Error(
      "Usage: build_runtime_distribution.cjs <output> <darwin|linux|win32> <arch> [version] <build_number>",
    );
  }
  const manifest = await buildRuntimeDistribution({
    sourceRoot,
    output,
    platform,
    arch,
    version,
    buildNumber,
    gitCommit: resolveGitCommit(sourceRoot),
    packageId,
    nodeCommand: process.execPath,
  });
  process.stdout.write(`${JSON.stringify(manifest, null, 2)}\n`);
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  buildRuntimeDistribution,
  treeFiles,
  assertCoreFresh,
  assertRuntimeControlFresh,
  assertCliFresh,
  assertDistributionSelfContained,
  packageMacosNodeDependencies,
  resolveGitCommit,
};
