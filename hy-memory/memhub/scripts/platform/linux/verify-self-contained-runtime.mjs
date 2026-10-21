#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import {
  access,
  chmod,
  mkdir,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TOOL_NAMES = ["python", "python3", "sqlite", "sqlite3", "pnpm", "uv"];

export async function verifySelfContainedRuntime(options) {
  if (process.platform !== "linux") {
    throw new Error("self_contained_runtime_requires_linux");
  }
  const distribution = path.resolve(options.distribution);
  const manifest = JSON.parse(
    await readFile(path.join(distribution, "manifest.json"), "utf8"),
  );
  if (
    manifest.product !== "one-memory-runtime" ||
    manifest.platform !== "linux" ||
    manifest.arch !== process.arch
  ) {
    throw new Error("self_contained_runtime_identity_invalid");
  }
  const verifyRoot = path.resolve(options.verifyRoot);
  await rm(verifyRoot, { recursive: true, force: true });
  const home = path.join(verifyRoot, "home");
  const dataDir = path.join(verifyRoot, "data with spaces");
  const poisonBin = path.join(verifyRoot, "poison-bin");
  const evidence = path.join(verifyRoot, "evidence");
  const poisonLog = path.join(evidence, "system-tool-invocations.log");
  for (const directory of [home, dataDir, poisonBin, evidence]) {
    await mkdir(directory, { recursive: true, mode: 0o700 });
  }
  for (const name of TOOL_NAMES) {
    const script = path.join(poisonBin, name);
    await writeFile(
      script,
      `#!/bin/sh\nprintf '%s\\n' ${JSON.stringify(name)} >> ${shellWord(poisonLog)}\nexit 97\n`,
      { mode: 0o700 },
    );
    await chmod(script, 0o700);
  }
  const corePort = options.corePort ?? 29585;
  const runtimePort = options.runtimePort ?? 29586;
  const environment = {
    ...process.env,
    PATH: `${poisonBin}:/usr/bin:/bin`,
    HOME: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    XDG_DATA_HOME: path.join(home, ".local", "share"),
    ONE_MEMORY_DATA_DIR: dataDir,
    ONE_MEMORY_CORE_PORT: String(corePort),
    ONE_MEMORY_RUNTIME_PORT: String(runtimePort),
    ONE_MEMORY_PORT: String(corePort),
    ONE_MEMORY_TEST_ISOLATED: "1",
    NO_COLOR: "1",
  };
  const cli = path.join(distribution, "bin", "one-memory");
  const runtimeStdout = path.join(evidence, "runtime.stdout.log");
  const runtimeStderr = path.join(evidence, "runtime.stderr.log");
  const child = spawn(cli, ["serve"], {
    cwd: verifyRoot,
    env: environment,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const receipt = {
    schema_version: 1,
    product: "memhub-self-contained-runtime-verification",
    version: manifest.version,
    build_number: manifest.build_number,
    platform: manifest.platform,
    arch: manifest.arch,
    distribution,
    verify_root: verifyRoot,
    poisoned_commands: TOOL_NAMES,
    status: {},
    observations: {},
  };
  try {
    const running = await waitForStatus({ cli, environment, evidence, child });
    receipt.observations.instance_id = findKey(running, "instance_id");
    receipt.status.runtime_start = "passed";
    const doctor = run(cli, ["doctor", "--json"], environment, verifyRoot);
    await writeFile(
      path.join(evidence, "doctor.json"),
      `${JSON.stringify(doctor, null, 2)}\n`,
    );
    if (doctor.status !== 0 && doctor.status !== 1) {
      throw new Error("self_contained_runtime_doctor_failed");
    }
    const doctorDocument = JSON.parse(doctor.stdout);
    const core = doctorDocument.checks?.find?.((check) => check?.id === "core");
    if (
      core?.state !== "pass" ||
      core.details?.version !== manifest.version ||
      core.details?.instance_verified !== true
    ) {
      throw new Error("self_contained_runtime_identity_unverified");
    }
    receipt.observations.core_version = core.details.version;
    receipt.status.doctor = "passed";
    const database = path.join(dataDir, "one-memory.sqlite3");
    await access(database);
    receipt.observations.sqlite_bytes = (await stat(database)).size;
    receipt.status.bundled_sqlite = "passed";
    const invocations = await readFile(poisonLog, "utf8").catch(() => "");
    receipt.observations.system_tool_invocations = invocations
      .split(/\r?\n/)
      .filter(Boolean);
    if (receipt.observations.system_tool_invocations.length !== 0) {
      throw new Error("self_contained_runtime_used_system_tool");
    }
    receipt.status.no_system_python_sqlite_build_tools = "passed";
    receipt.result = "passed";
  } catch (error) {
    receipt.result = "failed";
    receipt.error = error instanceof Error ? error.message : String(error);
  } finally {
    child.kill("SIGTERM");
    await Promise.race([
      new Promise((resolve) => child.once("close", resolve)),
      new Promise((resolve) => setTimeout(resolve, 10_000)),
    ]);
    if (child.exitCode === null) child.kill("SIGKILL");
    await writeFile(runtimeStdout, stdout);
    await writeFile(runtimeStderr, stderr);
    await writeFile(
      path.join(evidence, "self-contained-runtime-receipt.json"),
      `${JSON.stringify(receipt, null, 2)}\n`,
      { mode: 0o600 },
    );
  }
  if (receipt.result !== "passed") throw new Error(receipt.error);
  return receipt;
}

async function waitForStatus(options) {
  const deadline = Date.now() + 90_000;
  let attempt = 0;
  while (Date.now() < deadline) {
    if (options.child.exitCode !== null) {
      throw new Error(
        `self_contained_runtime_exited:${options.child.exitCode}`,
      );
    }
    attempt += 1;
    const result = run(
      options.cli,
      ["status", "--json"],
      options.environment,
      path.dirname(options.evidence),
    );
    await writeFile(
      path.join(options.evidence, `status-${attempt}.json`),
      `${JSON.stringify(result, null, 2)}\n`,
    );
    if (result.status === 0) return JSON.parse(result.stdout);
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("self_contained_runtime_not_ready");
}

function run(command, arguments_, environment, cwd) {
  const result = spawnSync(command, arguments_, {
    cwd,
    env: environment,
    encoding: "utf8",
    timeout: 30_000,
  });
  return {
    command,
    args: arguments_,
    status: result.status,
    signal: result.signal,
    stdout: result.stdout,
    stderr: result.stderr,
    error: result.error?.message ?? null,
  };
}

function findKey(value, key) {
  if (!value || typeof value !== "object") return null;
  if (Object.hasOwn(value, key)) return value[key];
  for (const nested of Object.values(value)) {
    const found = findKey(nested, key);
    if (found !== null && found !== undefined) return found;
  }
  return null;
}

function shellWord(value) {
  return `'${value.replaceAll("'", `'\\''`)}'`;
}

function parseArguments(arguments_) {
  const options = {};
  for (let index = 0; index < arguments_.length; index += 1) {
    const flag = arguments_[index];
    const value = arguments_[++index];
    if (!value) throw new Error(`missing value for ${flag}`);
    if (flag === "--distribution") options.distribution = value;
    else if (flag === "--verify-root") options.verifyRoot = value;
    else if (flag === "--core-port") options.corePort = Number(value);
    else if (flag === "--runtime-port") options.runtimePort = Number(value);
    else throw new Error(`invalid argument: ${flag}`);
  }
  if (!options.distribution || !options.verifyRoot) {
    throw new Error(
      "usage: verify-self-contained-runtime.mjs --distribution <dir> --verify-root <dir> [--core-port <port>] [--runtime-port <port>]",
    );
  }
  return options;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  verifySelfContainedRuntime(parseArguments(process.argv.slice(2)))
    .then((receipt) =>
      process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`),
    )
    .catch((error) => {
      process.stderr.write(
        `${error instanceof Error ? error.message : error}\n`,
      );
      process.exitCode = 1;
    });
}
