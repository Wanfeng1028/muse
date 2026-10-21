const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { createReadStream } = require("node:fs");
const { readdir, readlink, realpath } = require("node:fs/promises");
const path = require("node:path");

async function hashFile(file) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

async function treeManifest(directory) {
  const root = await realpath(directory);
  const result = {};
  async function walk(current, prefix) {
    const entries = await readdir(current, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const file = path.join(current, entry.name),
        name = `${prefix}${entry.name}`;
      if (entry.isSymbolicLink()) {
        const resolved = await realpath(file);
        const relative = path.relative(root, resolved);
        assert(
          !relative.startsWith("..") && !path.isAbsolute(relative),
          "Resource link escapes its runtime",
        );
        result[name] = { symlink: await readlink(file) };
      } else if (entry.isDirectory()) await walk(file, `${name}/`);
      else if (entry.isFile()) result[name] = await hashFile(file);
      else throw new Error("Unsupported runtime resource type");
    }
  }
  await walk(root, "");
  return result;
}

async function packageResourceManifest(resourcesPath) {
  const result = {};
  for (const file of [
    "app.asar",
    "web/index.html",
    "cli/one-memory.cjs",
    "runtime/runtime.cjs",
    "host-bridge/mcp.cjs",
    "host-bridge/recall-cli.cjs",
    "host-bridge/installer-cli.cjs",
  ])
    result[file] = await hashFile(path.join(resourcesPath, file));
  for (const folder of ["core", "web/assets"])
    for (const [file, value] of Object.entries(
      await treeManifest(path.join(resourcesPath, folder)),
    ))
      result[`${folder}/${file}`] = value;
  return result;
}

module.exports = { packageResourceManifest, treeManifest };
