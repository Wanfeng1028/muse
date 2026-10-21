const assert = require("node:assert/strict");
const { mkdtemp, mkdir, writeFile, symlink, rm } = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");
const {
  packageResourceManifest,
  treeManifest,
} = require("./packaged_resource_manifest.cjs");

test("runtime hashes include nested libraries and detect a changed byte", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-runtime-hashes-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, "_internal"));
  await writeFile(path.join(root, "one-memory"), "executable");
  const library = path.join(root, "_internal/library.dylib");
  await writeFile(library, "library-v1");
  await symlink("_internal/library.dylib", path.join(root, "library-link"));
  const before = await treeManifest(root);
  assert.equal(Object.keys(before).length, 3);
  assert.deepEqual(before["library-link"], {
    symlink: "_internal/library.dylib",
  });
  await writeFile(library, "library-v2");
  const after = await treeManifest(root);
  assert.equal(before["one-memory"], after["one-memory"]);
  assert.notEqual(
    before["_internal/library.dylib"],
    after["_internal/library.dylib"],
  );
});

test("runtime links cannot reference a file outside the distributed folder", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-runtime-links-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, "runtime"));
  await writeFile(path.join(root, "outside"), "not included");
  await symlink("../outside", path.join(root, "runtime/library"));
  await assert.rejects(treeManifest(path.join(root, "runtime")), /escapes/);
});

test("package manifest includes the public CLI and standalone Runtime", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-package-manifest-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const file of [
    "app.asar",
    "web/index.html",
    "cli/one-memory.cjs",
    "runtime/runtime.cjs",
    "host-bridge/mcp.cjs",
    "host-bridge/recall-cli.cjs",
    "host-bridge/installer-cli.cjs",
    "core/one-memory",
    "web/assets/app.js",
  ]) {
    await mkdir(path.dirname(path.join(root, file)), { recursive: true });
    await writeFile(path.join(root, file), file);
  }

  const manifest = await packageResourceManifest(root);

  assert.equal(typeof manifest["cli/one-memory.cjs"], "string");
  assert.equal(typeof manifest["runtime/runtime.cjs"], "string");
  assert.equal(typeof manifest["core/one-memory"], "string");
});
