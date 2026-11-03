const assert = require("node:assert/strict");
const {
  chmod,
  mkdtemp,
  mkdir,
  readFile,
  readlink,
  realpath,
  rm,
  symlink,
  utimes,
  writeFile,
} = require("node:fs/promises");
const { spawnSync } = require("node:child_process");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

const {
  assertCoreFresh,
  assertDistributionSelfContained,
  buildRuntimeDistribution,
  packageMacosNodeDependencies,
} = require("./build_runtime_distribution.cjs");

async function fixture(platform = "linux") {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-runtime-dist-"));
  await mkdir(path.join(root, "packages/runtime-control/src"), {
    recursive: true,
  });
  await writeFile(
    path.join(root, "packages/runtime-control/package.json"),
    JSON.stringify({ name: "@one-memory/runtime-control", version: "0.0.0" }),
  );
  await writeFile(
    path.join(root, "packages/runtime-control/src/core-supervisor.ts"),
    "// fixture source\n",
  );
  await mkdir(path.join(root, "apps/core/src/one_memory"), {
    recursive: true,
  });
  await writeFile(
    path.join(root, "apps/core/src/one_memory/context_memory.py"),
    "# fixture core source\n",
  );
  await writeFile(
    path.join(root, "apps/core/one-memory.spec"),
    "# fixture spec\n",
  );
  await writeFile(path.join(root, "apps/core/pyproject.toml"), "[project]\n");
  for (const file of [
    "apps/cli/dist/one-memory.cjs",
    "apps/core/dist/one-memory-runtime/one-memory",
    "packages/runtime-control/dist/runtime.cjs",
    "packages/host-bridge/dist/mcp.cjs",
    "packages/host-bridge/dist/recall-cli.cjs",
    "packages/host-bridge/dist/sync-hook/manifest.json",
    "apps/web/dist/index.html",
    "SBOM.spdx.json",
    "THIRD_PARTY_NOTICES.md",
    "LICENSE",
    "packages/host-bridge/src/memmy-adapter/claude-code/LICENSE.memmy",
    "packages/host-bridge/src/memmy-adapter/claude-code/PROVENANCE.md",
  ]) {
    await mkdir(path.dirname(path.join(root, file)), { recursive: true });
    await writeFile(
      path.join(root, file),
      file === "apps/cli/dist/one-memory.cjs"
        ? 'process.stdout.write(process.execPath + "\\n")'
        : file === "SBOM.spdx.json"
          ? JSON.stringify({
              SPDXID: "SPDXRef-Package-memmy-agent-derived",
              name: "MemTensor memmy-agent",
            })
          : file === "THIRD_PARTY_NOTICES.md"
            ? "# Third-Party Notices\n\nMemTensor memmy-agent, MIT\n"
            : file ===
                "packages/host-bridge/src/memmy-adapter/claude-code/LICENSE.memmy"
              ? "MIT License\nCopyright (c) 2026-present MemTensor\n"
              : file,
      { mode: 0o700 },
    );
  }
  const node = path.join(root, platform === "win32" ? "node.exe" : "node");
  await writeFile(node, "node", { mode: 0o700 });
  return { root, node, output: path.join(root, "release") };
}

test("builds one manifest for CLI, Runtime, Core, Host Bridge and Web", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));

  const manifest = await buildRuntimeDistribution({
    sourceRoot: value.root,
    output: value.output,
    platform: "linux",
    arch: "x64",
    version: "1.0.0",
    buildNumber: 42,
    gitCommit: "a".repeat(40),
    nodeCommand: value.node,
  });

  assert.equal(manifest.build_number, 42);
  assert.equal(manifest.git_commit, "a".repeat(40));
  assert.equal(manifest.runtime_protocol, 1);
  assert.deepEqual(manifest.supported_cli_protocol, { min: 1, max: 1 });
  for (const file of [
    "bin/node",
    "bin/one-memory",
    "bin/one-memory.cjs",
    "core/one-memory",
    "runtime/runtime.cjs",
    "host-bridge/mcp.cjs",
    "web/index.html",
    "SBOM.spdx.json",
    "THIRD_PARTY_NOTICES.md",
    "licenses/LICENSE.one-memory",
    "licenses/LICENSE.memmy",
    "licenses/PROVENANCE.memmy.md",
  ]) {
    assert.equal(typeof manifest.files[file], "string", file);
  }
  const sbom = JSON.parse(
    await readFile(path.join(value.output, "SBOM.spdx.json"), "utf8"),
  );
  const notice = await readFile(
    path.join(value.output, "THIRD_PARTY_NOTICES.md"),
    "utf8",
  );
  assert.match(notice, /MemTensor|LICENSE\.memmy/);
  assert.ok(
    JSON.stringify(sbom).includes("MemTensor") ||
      JSON.stringify(sbom).includes("memmy"),
  );
  assert.deepEqual(
    JSON.parse(
      await readFile(path.join(value.output, "manifest.json"), "utf8"),
    ),
    manifest,
  );
});

test("macOS distribution requires and hashes the native service observer", async (t) => {
  const value = await fixture("darwin");
  t.after(() => rm(value.root, { recursive: true, force: true }));
  const options = {
    sourceRoot: value.root,
    output: value.output,
    platform: "darwin",
    arch: "arm64",
    version: "1.0.0",
    buildNumber: 43,
    nodeCommand: value.node,
  };
  await assert.rejects(buildRuntimeDistribution(options), /service-observer/);
  await writeFile(
    path.join(value.root, "packages/runtime-control/dist/service-observer"),
    "synthetic observer",
    { mode: 0o755 },
  );
  const manifest = await buildRuntimeDistribution(options);
  assert.match(manifest.files["runtime/service-observer"], /^[a-f0-9]{64}$/);
});

test("macOS packages a relocatable Node dylib closure", async (t) => {
  if (process.platform !== "darwin") return;
  const root = await mkdtemp(path.join(os.tmpdir(), "om-node-runtime-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const packagedNode = path.join(root, "bin", "node");
  await mkdir(path.dirname(packagedNode), { recursive: true });
  await (await import("node:fs/promises")).copyFile(
    process.execPath,
    packagedNode,
  );

  const libraries = await packageMacosNodeDependencies(
    process.execPath,
    packagedNode,
    root,
  );
  // Official Node builds may depend only on macOS system libraries, in which
  // case there is no private dylib closure to copy.
  assert.ok(Array.isArray(libraries));
  const result = spawnSync(packagedNode, ["-e", "process.stdout.write('ok')"], {
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, "ok");
});

test("resource copying preserves internal relative symlink targets", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  await symlink(
    "index.html",
    path.join(value.root, "apps/web/dist/linked.html"),
  );
  await mkdir(path.join(value.root, "apps/web/dist/assets"));
  await writeFile(
    path.join(value.root, "apps/web/dist/assets/app.js"),
    "asset",
  );
  await symlink("assets", path.join(value.root, "apps/web/dist/linked-assets"));
  const manifest = await buildRuntimeDistribution({
    sourceRoot: value.root,
    output: value.output,
    platform: "linux",
    arch: "x64",
    version: "1.0.0",
    buildNumber: 44,
    nodeCommand: value.node,
  });
  assert.equal(
    await readlink(path.join(value.output, "web/linked.html")),
    "index.html",
  );
  assert.equal(
    await readlink(path.join(value.output, "web/linked-assets")),
    "assets",
  );
  assert.match(manifest.files["web/linked.html"], /^[a-f0-9]{64}$/);
  assert.match(manifest.files["web/linked-assets"], /^[a-f0-9]{64}$/);
  assert.notEqual(
    manifest.files["web/linked.html"],
    manifest.files["web/index.html"],
  );
});

test("does not replace an existing distribution when a required input is missing", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  await mkdir(value.output);
  await writeFile(path.join(value.output, "keep"), "old release");
  await rm(path.join(value.root, "apps/web/dist/index.html"));

  await assert.rejects(
    buildRuntimeDistribution({
      sourceRoot: value.root,
      output: value.output,
      platform: "linux",
      arch: "x64",
      version: "1.0.0",
      buildNumber: 45,
      nodeCommand: value.node,
    }),
  );
  assert.equal(
    await readFile(path.join(value.output, "keep"), "utf8"),
    "old release",
  );
});

test("the packaged launcher stamps build identity and turns on diagnostics", async (t) => {
  if (process.platform === "win32") return;
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  await buildRuntimeDistribution({
    sourceRoot: value.root,
    output: value.output,
    platform: "linux",
    arch: "x64",
    version: "1.0.0",
    buildNumber: 85,
    packageId: "One-Memory-H85-6929cbd-candidate",
    nodeCommand: value.node,
  });
  const launcher = await readFile(
    path.join(value.output, "bin", "one-memory"),
    "utf8",
  );
  // Without the identity stamp the diagnostic chain has no build/package/round
  // ids, and without Diagnostics=1 Core writes no kernel half at all.
  assert.match(
    launcher,
    /ONE_MEMORY_BUILD_ID="\$\{ONE_MEMORY_BUILD_ID:-One-Memory-H85-6929cbd-candidate\}"/,
  );
  assert.match(
    launcher,
    /ONE_MEMORY_PACKAGE_ID="\$\{ONE_MEMORY_PACKAGE_ID:-One-Memory-H85-6929cbd-candidate\}"/,
  );
  assert.match(launcher, /ONE_MEMORY_ROUND="\$\{ONE_MEMORY_ROUND:-85\}"/);
  assert.match(
    launcher,
    /ONE_MEMORY_BUILD_NUMBER="\$\{ONE_MEMORY_BUILD_NUMBER:-85\}"/,
  );
  assert.match(launcher, /ONE_MEMORY_DIAGNOSTICS=1/);
  // The Runtime derives its Core port from whether it is the everyday install,
  // so the launcher has to name its own root.
  assert.match(launcher, /ONE_MEMORY_INSTALL_ROOT=/);
  // The dist manifest now carries the formal package identity so a host install
  // can bind to the same artifact (C5 identity binding); it must echo the
  // builder-supplied packageId rather than being inferred.
  const manifest = JSON.parse(
    await readFile(path.join(value.output, "manifest.json"), "utf8"),
  );
  assert.equal(manifest.package_id, "One-Memory-H85-6929cbd-candidate");
});

test("self-containment rejects a dist polluted with smoke/readiness/owner files", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  await buildRuntimeDistribution({
    sourceRoot: value.root,
    output: value.output,
    platform: "linux",
    arch: "x64",
    version: "1.0.0",
    buildNumber: 85,
    nodeCommand: value.node,
  });
  // A clean build is self-contained.
  await assert.doesNotReject(assertDistributionSelfContained(value.output));

  // Writing runtime state into the dist is exactly what the installer refuses
  // with `distribution_manifest_incomplete` (H85 lifecycle matrix).
  await mkdir(path.join(value.output, "smoke-data"), { recursive: true });
  await writeFile(
    path.join(value.output, "smoke-data", "one-memory.sqlite3"),
    "",
  );
  await writeFile(path.join(value.output, "readiness.json"), "{}");
  await writeFile(path.join(value.output, ".one-memory-hourly-owned"), "x\n");
  await assert.rejects(
    assertDistributionSelfContained(value.output),
    /distribution_manifest_incomplete/,
  );
});

test("the public CLI launcher resolves its distribution through a PATH symlink", async (t) => {
  if (process.platform === "win32") return;
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  await buildRuntimeDistribution({
    sourceRoot: value.root,
    output: value.output,
    platform: "linux",
    arch: "x64",
    version: "1.0.0",
    buildNumber: 46,
    nodeCommand: value.node,
  });
  // The fixture's fake bundled node becomes executable for this path test by
  // replacing it with the current real Node binary after manifest generation.
  await rm(path.join(value.output, "bin", "node"));
  await (await import("node:fs/promises")).copyFile(
    process.execPath,
    path.join(value.output, "bin", "node"),
  );
  if (process.platform === "darwin") {
    await packageMacosNodeDependencies(
      process.execPath,
      path.join(value.output, "bin", "node"),
      value.output,
    );
  }
  await chmod(path.join(value.output, "bin", "node"), 0o700);
  const publicBin = path.join(value.root, "public-bin");
  await mkdir(publicBin);
  const command = path.join(publicBin, "one-memory");
  await symlink(path.join(value.output, "bin", "one-memory"), command);

  const result = spawnSync(command, [], { encoding: "utf8" });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(
    await realpathSafe(result.stdout.trim()),
    await realpathSafe(path.join(value.output, "bin", "node")),
  );
});

test("the installed CLI launcher names the managed install root, not its version directory", async (t) => {
  if (process.platform === "win32") return;
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  const installRoot = path.join(value.root, "managed");
  const selected = path.join(installRoot, "versions", "1.0.0-test");
  if (process.platform === "darwin") {
    await writeFile(
      path.join(value.root, "packages/runtime-control/dist/service-observer"),
      "synthetic observer",
      { mode: 0o755 },
    );
  }
  await buildRuntimeDistribution({
    sourceRoot: value.root,
    output: selected,
    platform: process.platform === "darwin" ? "darwin" : "linux",
    arch: process.arch,
    version: "1.0.0",
    buildNumber: 47,
    nodeCommand: value.node,
  });
  await rm(path.join(selected, "bin", "node"));
  await (await import("node:fs/promises")).copyFile(
    process.execPath,
    path.join(selected, "bin", "node"),
  );
  if (process.platform === "darwin") {
    await packageMacosNodeDependencies(
      process.execPath,
      path.join(selected, "bin", "node"),
      selected,
    );
  }
  await writeFile(
    path.join(selected, "bin", "one-memory.cjs"),
    "process.stdout.write(process.env.ONE_MEMORY_INSTALL_ROOT || '')",
  );
  const publicBin = path.join(value.root, "managed-bin");
  await mkdir(publicBin);
  const command = path.join(publicBin, "one-memory");
  await symlink(path.join(selected, "bin", "one-memory"), command);

  const result = spawnSync(command, [], { encoding: "utf8" });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(
    await realpathSafe(result.stdout),
    await realpathSafe(installRoot),
  );
});

async function realpathSafe(target) {
  return realpath(target);
}

test("rejects a missing or unsafe build number before writing", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));

  await assert.rejects(
    buildRuntimeDistribution({
      sourceRoot: value.root,
      output: value.output,
      platform: "linux",
      arch: "x64",
      version: "1.0.0",
      nodeCommand: value.node,
    }),
    /build_number must be a non-negative safe integer/,
  );
  await assert.rejects(
    buildRuntimeDistribution({
      sourceRoot: value.root,
      output: value.output,
      platform: "linux",
      arch: "x64",
      version: "1.0.0",
      buildNumber: 1.5,
      nodeCommand: value.node,
    }),
    /build_number must be a non-negative safe integer/,
  );
});

test("rejects a non-SemVer Runtime identity before staging files", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  await assert.rejects(
    buildRuntimeDistribution({
      sourceRoot: value.root,
      output: value.output,
      platform: "linux",
      arch: "x64",
      version: "release-one",
      buildNumber: 1,
      nodeCommand: path.join(value.root, "node"),
    }),
    /valid SemVer/,
  );
});

test("refuses to package a stale runtime-control dist", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  const old = new Date(Date.now() - 60_000);
  await utimes(
    path.join(value.root, "packages/runtime-control/src/core-supervisor.ts"),
    new Date(),
    new Date(),
  );
  await utimes(
    path.join(value.root, "packages/runtime-control/dist/runtime.cjs"),
    old,
    old,
  );

  await assert.rejects(
    buildRuntimeDistribution({
      sourceRoot: value.root,
      output: value.output,
      platform: "linux",
      arch: "x64",
      version: "1.0.0",
      buildNumber: 50,
      nodeCommand: value.node,
    }),
    /runtime-control dist is stale/,
  );
});

test("refuses to package a stale CLI bundle that inlines runtime-control", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  // The CLI bundle inlines runtime-control's service-plan. A runtime-control
  // source change with a stale CLI bundle is exactly how the H87 package
  // shipped an install path that still ignored the per-root Core port.
  await mkdir(path.join(value.root, "apps/cli/src"), { recursive: true });
  await writeFile(
    path.join(value.root, "apps/cli/src/cli.ts"),
    "// fixture cli source\n",
    { mode: 0o700 },
  );
  const old = new Date(Date.now() - 60_000);
  await utimes(
    path.join(value.root, "packages/runtime-control/src/core-supervisor.ts"),
    new Date(),
    new Date(),
  );
  // Keep runtime-control itself fresh so only the CLI staleness check can trip.
  await utimes(
    path.join(value.root, "packages/runtime-control/dist/runtime.cjs"),
    new Date(Date.now() + 60_000),
    new Date(Date.now() + 60_000),
  );
  await utimes(path.join(value.root, "apps/cli/dist/one-memory.cjs"), old, old);

  await assert.rejects(
    buildRuntimeDistribution({
      sourceRoot: value.root,
      output: value.output,
      platform: "linux",
      arch: "x64",
      version: "1.0.0",
      buildNumber: 51,
      nodeCommand: value.node,
    }),
    /CLI bundle is stale/,
  );
});

test("refuses to package a stale Core distribution", async (t) => {
  const value = await fixture();
  t.after(() => rm(value.root, { recursive: true, force: true }));
  await mkdir(path.join(value.root, "apps/core/src/one_memory"), {
    recursive: true,
  });
  await writeFile(
    path.join(value.root, "apps/core/src/one_memory/context_memory.py"),
    "# newer source\n",
  );
  await writeFile(
    path.join(value.root, "apps/core/one-memory.spec"),
    "# spec\n",
  );
  await writeFile(
    path.join(value.root, "apps/core/pyproject.toml"),
    "[project]\n",
  );
  const old = new Date(Date.now() - 60_000);
  await utimes(
    path.join(value.root, "apps/core/src/one_memory/context_memory.py"),
    new Date(),
    new Date(),
  );
  await utimes(
    path.join(value.root, "apps/core/dist/one-memory-runtime/one-memory"),
    old,
    old,
  );

  await assert.rejects(
    assertCoreFresh(value.root, "linux"),
    /core distribution is stale/,
  );
  await assert.rejects(
    buildRuntimeDistribution({
      sourceRoot: value.root,
      output: value.output,
      platform: "linux",
      arch: "x64",
      version: "1.0.0",
      buildNumber: 51,
      nodeCommand: value.node,
    }),
    /core distribution is stale/,
  );
});
