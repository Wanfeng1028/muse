#!/usr/bin/env node
const { execFile } = require("node:child_process");
const fs = require("node:fs/promises");
const path = require("node:path");
const { promisify } = require("node:util");

const SOURCE = path.resolve(
  __dirname,
  "../packages/runtime-control/native/service-observer.m",
);
const DEFAULT_OUTPUT = path.resolve(
  __dirname,
  "../packages/runtime-control/dist/service-observer",
);

function validOutput(output) {
  return (
    typeof output === "string" &&
    path.isAbsolute(output) &&
    path.normalize(output) === output &&
    !output.endsWith("/") &&
    !/[\0\r\n]/.test(output) &&
    output !== SOURCE
  );
}

function parseArguments(args) {
  if (args.length === 0) return { output: DEFAULT_OUTPUT };
  if (args.length === 2 && args[0] === "--output" && validOutput(args[1]))
    return { output: args[1] };
  throw Error(
    "Usage: build_service_observer.cjs [--output /absolute/new/service-observer]",
  );
}

async function buildServiceObserver({
  output = DEFAULT_OUTPUT,
  platform = process.platform,
  arch = process.arch,
  run = promisify(execFile),
} = {}) {
  if (platform !== "darwin" || !["arm64", "x64"].includes(arch))
    throw Error("service_observer_build_unsupported");
  if (!validOutput(output)) throw Error("service_observer_output_invalid");
  try {
    await fs.lstat(output);
    throw Error("service_observer_output_exists");
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  await fs.mkdir(path.dirname(output), { recursive: true });
  const stage = await fs.mkdtemp(
    path.join(path.dirname(output), ".service-observer-build-"),
  );
  const binary = path.join(stage, "service-observer");
  try {
    await run(
      "/usr/bin/xcrun",
      [
        "--sdk",
        "macosx",
        "clang",
        "-fobjc-arc",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-mmacosx-version-min=13.0",
        "-arch",
        arch === "x64" ? "x86_64" : "arm64",
        SOURCE,
        "-framework",
        "Foundation",
        "-framework",
        "ServiceManagement",
        "-o",
        binary,
      ],
      {
        timeout: 120000,
        maxBuffer: 1024 * 1024,
        env: { PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" },
      },
    );
    const info = await fs.lstat(binary);
    if (!info.isFile() || info.isSymbolicLink() || info.size === 0)
      throw Error("service_observer_build_invalid");
    await fs.chmod(binary, 0o755);
    // Publish only into a new output path, never replace a concurrent candidate.
    await fs.link(binary, output);
    return { output, source: SOURCE, platform, arch };
  } finally {
    await fs.rm(stage, { recursive: true, force: true });
  }
}

if (require.main === module) {
  Promise.resolve()
    .then(() => buildServiceObserver(parseArguments(process.argv.slice(2))))
    .then((result) => process.stdout.write(`${JSON.stringify(result)}\n`))
    .catch(() => {
      process.stderr.write("service_observer_build_failed\n");
      process.exitCode = 1;
    });
}
module.exports = {
  buildServiceObserver,
  parseArguments,
  SOURCE,
  DEFAULT_OUTPUT,
};
