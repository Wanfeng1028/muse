#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import {
  chmod,
  copyFile,
  cp,
  lstat,
  mkdir,
  readdir,
  readFile,
  readlink,
  realpath,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

export async function verifyLinuxUpgradeRollback(options) {
  if (process.platform !== "linux") {
    throw new Error("linux_upgrade_rollback_requires_linux");
  }
  if (!["x64", "arm64"].includes(process.arch)) {
    throw new Error("linux_upgrade_rollback_arch_unsupported");
  }
  const previousDistribution = await distributionIdentity(
    options.previousDistribution,
  );
  const currentDistribution = await distributionIdentity(
    options.currentDistribution,
  );
  if (
    previousDistribution.manifest.platform !== "linux" ||
    currentDistribution.manifest.platform !== "linux" ||
    previousDistribution.manifest.arch !== process.arch ||
    currentDistribution.manifest.arch !== process.arch ||
    !Number.isSafeInteger(previousDistribution.manifest.build_number) ||
    !Number.isSafeInteger(currentDistribution.manifest.build_number) ||
    currentDistribution.manifest.build_number <=
      previousDistribution.manifest.build_number
  ) {
    throw new Error("linux_upgrade_rollback_distribution_order_invalid");
  }

  const verifyRoot = path.resolve(options.verifyRoot);
  await assertAbsent(verifyRoot, "linux_upgrade_rollback_root_exists");
  const home = path.join(verifyRoot, "home");
  const dataDir = path.join(verifyRoot, "data with spaces");
  const installRoot = path.join(verifyRoot, "install");
  const binDir = path.join(verifyRoot, "bin");
  const evidenceDir = path.join(verifyRoot, "evidence");
  const sourceDir = path.join(
    home,
    ".claude",
    "projects",
    "-tmp-memhub-upgrade-rollback",
  );
  const failingDistribution = path.join(
    verifyRoot,
    "failing distribution with spaces",
  );
  for (const directory of [home, dataDir, binDir, evidenceDir, sourceDir]) {
    await mkdir(directory, { recursive: true, mode: 0o700 });
  }

  const environment = {
    ...process.env,
    HOME: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    XDG_DATA_HOME: path.join(home, ".local", "share"),
    ONE_MEMORY_DATA_DIR: dataDir,
    ONE_MEMORY_CORE_PORT: String(options.corePort),
    ONE_MEMORY_RUNTIME_PORT: String(options.runtimePort),
    ONE_MEMORY_PORT: String(options.corePort),
    ONE_MEMORY_TEST_ISOLATED: "1",
    NO_COLOR: "1",
  };
  let cli = path.join(previousDistribution.path, "bin", "one-memory");
  const serviceId = "one-memory.service";
  const status = {};
  const observations = {};
  const receipt = {
    schema_version: 1,
    product: "memhub-linux-upgrade-rollback",
    platform: "linux",
    arch: process.arch,
    previous_distribution: previousDistribution.path,
    current_distribution: currentDistribution.path,
    previous_version: previousDistribution.manifest.version,
    previous_build_number: previousDistribution.manifest.build_number,
    current_version: currentDistribution.manifest.version,
    current_build_number: currentDistribution.manifest.build_number,
    verify_root: verifyRoot,
    status,
    observations,
  };

  try {
    systemctl("systemd-probe", ["show-environment"], environment, evidenceDir);
    systemctl(
      "preflight-disabled",
      ["is-enabled", serviceId],
      environment,
      evidenceDir,
      [1, 4],
    );
    systemctl(
      "preflight-inactive",
      ["is-active", serviceId],
      environment,
      evidenceDir,
      [3, 4],
    );

    const install = parseJson(
      run(
        "install-previous",
        cli,
        installArguments({
          command: "install",
          source: previousDistribution.path,
          installRoot,
          home,
          binDir,
          dataDir,
          xdgConfigHome: environment.XDG_CONFIG_HOME,
        }),
        environment,
        evidenceDir,
      ).stdout,
      "install-previous",
    );
    const installedCorePort = findKey(install, "core_port");
    if (
      !Number.isSafeInteger(installedCorePort) ||
      installedCorePort < 1024 ||
      installedCorePort > 65535
    ) {
      throw new Error("linux_upgrade_rollback_core_port_invalid");
    }
    environment.ONE_MEMORY_CORE_PORT = String(installedCorePort);
    environment.ONE_MEMORY_PORT = String(installedCorePort);
    observations.installed_core_port = installedCorePort;
    cli = path.join(binDir, "memhub");
    systemctl(
      "previous-active",
      ["is-active", serviceId],
      environment,
      evidenceDir,
    );
    const previousStatus = await waitForRunningStatus({
      prefix: "status-previous",
      cli,
      environment,
      evidenceDir,
    });
    observations.previous_instance_id = findKey(previousStatus, "instance_id");
    status.install_previous = "passed";

    const phrase = "MemHub N minus one upgrade persistence phrase";
    const conversation = path.join(
      sourceDir,
      "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee.jsonl",
    );
    await writeFile(
      conversation,
      `${conversationRow("user", "u1", phrase, "01")}\n${conversationRow("assistant", "a1", "Upgrade phrase received", "02")}\n`,
    );
    const imported = run(
      "import-before-upgrade",
      cli,
      ["init", "--source", "claude-code", "--import", "--json"],
      environment,
      evidenceDir,
      [0],
      60_000,
    );
    if (imported.status !== 0) {
      throw commandFailure("import-before-upgrade", imported);
    }
    observations.recalled_before_upgrade = await waitForRecall({
      prefix: "recall-before-upgrade",
      cli,
      phrase,
      environment,
      evidenceDir,
    });
    if (!observations.recalled_before_upgrade) {
      throw new Error("linux_upgrade_rollback_initial_recall_failed");
    }
    status.data_before_upgrade = "passed";

    const database = path.join(dataDir, "one-memory.sqlite3");
    const databaseBeforeUpgrade = await databaseIdentity(database);
    observations.database_before_upgrade = databaseBeforeUpgrade;
    const currentBeforeUpgrade = await selectedManifest(installRoot);
    if (
      currentBeforeUpgrade.version !== previousDistribution.manifest.version ||
      currentBeforeUpgrade.build_number !==
        previousDistribution.manifest.build_number
    ) {
      throw new Error("linux_upgrade_rollback_previous_selection_mismatch");
    }

    const upgrade = run(
      "upgrade-to-current",
      cli,
      installArguments({
        command: "upgrade",
        source: currentDistribution.path,
        installRoot,
        home,
        binDir,
        dataDir,
        xdgConfigHome: environment.XDG_CONFIG_HOME,
      }),
      environment,
      evidenceDir,
      [0],
      120_000,
    );
    if (upgrade.status !== 0)
      throw commandFailure("upgrade-to-current", upgrade);
    systemctl(
      "current-active",
      ["is-active", serviceId],
      environment,
      evidenceDir,
    );
    const currentStatus = await waitForRunningStatus({
      prefix: "status-current",
      cli,
      environment,
      evidenceDir,
      previousInstanceId: observations.previous_instance_id,
    });
    observations.current_instance_id = findKey(currentStatus, "instance_id");
    const doctor = doctorDocument(
      run(
        "doctor-current",
        cli,
        ["doctor", "--json"],
        environment,
        evidenceDir,
        [0, 1],
        30_000,
      ),
      "doctor-current",
    );
    if (
      doctor.core.details?.version !== currentDistribution.manifest.version ||
      doctor.core.details?.instance_verified !== true ||
      doctor.broker.state !== "pass"
    ) {
      throw new Error("linux_upgrade_rollback_current_identity_mismatch");
    }
    observations.current_core_version = doctor.core.details.version;
    observations.recalled_after_upgrade = await waitForRecall({
      prefix: "recall-after-upgrade",
      cli,
      phrase,
      environment,
      evidenceDir,
    });
    if (!observations.recalled_after_upgrade) {
      throw new Error("linux_upgrade_rollback_data_lost_after_upgrade");
    }
    const selectedCurrent = await selectedManifest(installRoot);
    if (
      selectedCurrent.version !== currentDistribution.manifest.version ||
      selectedCurrent.build_number !== currentDistribution.manifest.build_number
    ) {
      throw new Error("linux_upgrade_rollback_current_selection_mismatch");
    }
    observations.database_after_upgrade = await databaseIdentity(database);
    status.upgrade_n_minus_one_to_n = "passed";

    const failing = await makeFailingDistribution({
      source: currentDistribution.path,
      target: failingDistribution,
      version: nextInternalVersion(currentDistribution.manifest.version),
      buildNumber: currentDistribution.manifest.build_number + 1,
    });
    receipt.failing_distribution = failing.path;
    receipt.failing_version = failing.manifest.version;
    receipt.failing_build_number = failing.manifest.build_number;
    observations.current_link_before_failed_upgrade = await readlink(
      path.join(installRoot, "current"),
    );
    const databaseBeforeFailure = await databaseIdentity(database);
    const failedUpgrade = run(
      "upgrade-to-crashing-build",
      cli,
      installArguments({
        command: "upgrade",
        source: failing.path,
        installRoot,
        home,
        binDir,
        dataDir,
        xdgConfigHome: environment.XDG_CONFIG_HOME,
      }),
      environment,
      evidenceDir,
      [1],
      // The product may spend one 45s readiness window proving the crashing
      // build is unhealthy and another 45s window proving the restored build
      // is healthy. Leave room for copying the large distribution and both
      // service transitions; an outer timeout must not kill a valid rollback.
      180_000,
    );
    if (failedUpgrade.status !== 1) {
      throw commandFailure("upgrade-to-crashing-build", failedUpgrade);
    }
    const failedDocument = parseJson(
      failedUpgrade.stderr,
      "upgrade-to-crashing-build",
    );
    if (failedDocument.code !== "upgrade_health_check_failed") {
      throw new Error("linux_upgrade_rollback_wrong_failure_code");
    }
    observations.failed_upgrade_code = failedDocument.code;

    systemctl(
      "rollback-active",
      ["is-active", serviceId],
      environment,
      evidenceDir,
    );
    const rollbackStatus = await waitForRunningStatus({
      prefix: "status-after-rollback",
      cli,
      environment,
      evidenceDir,
      previousInstanceId: observations.current_instance_id,
    });
    observations.rollback_instance_id = findKey(rollbackStatus, "instance_id");
    const selectedAfterRollback = await selectedManifest(installRoot);
    if (
      selectedAfterRollback.version !== currentDistribution.manifest.version ||
      selectedAfterRollback.build_number !==
        currentDistribution.manifest.build_number
    ) {
      throw new Error("linux_upgrade_rollback_selection_not_restored");
    }
    observations.current_link_after_failed_upgrade = await readlink(
      path.join(installRoot, "current"),
    );
    if (
      observations.current_link_after_failed_upgrade !==
      observations.current_link_before_failed_upgrade
    ) {
      throw new Error("linux_upgrade_rollback_current_link_changed");
    }
    const failedVersionDirectory = path.join(
      installRoot,
      "versions",
      `${failing.manifest.version}-b${failing.manifest.build_number}-linux-${process.arch}`,
    );
    if (await exists(failedVersionDirectory)) {
      throw new Error("linux_upgrade_rollback_failed_version_retained");
    }
    const rollbackDoctor = doctorDocument(
      run(
        "doctor-after-rollback",
        cli,
        ["doctor", "--json"],
        environment,
        evidenceDir,
        [0, 1],
        30_000,
      ),
      "doctor-after-rollback",
    );
    if (
      rollbackDoctor.core.details?.version !==
        currentDistribution.manifest.version ||
      rollbackDoctor.core.details?.instance_verified !== true ||
      rollbackDoctor.broker.state !== "pass"
    ) {
      throw new Error("linux_upgrade_rollback_restored_identity_mismatch");
    }
    observations.rollback_core_version = rollbackDoctor.core.details.version;
    observations.recalled_after_rollback = await waitForRecall({
      prefix: "recall-after-rollback",
      cli,
      phrase,
      environment,
      evidenceDir,
    });
    if (!observations.recalled_after_rollback) {
      throw new Error("linux_upgrade_rollback_data_lost_after_rollback");
    }
    const databaseAfterFailure = await databaseIdentity(database);
    observations.database_before_failed_upgrade = databaseBeforeFailure;
    observations.database_after_failed_upgrade = databaseAfterFailure;
    observations.database_file_changed_during_failed_upgrade =
      databaseBeforeFailure.bytes !== databaseAfterFailure.bytes ||
      databaseBeforeFailure.sha256 !== databaseAfterFailure.sha256;
    status.crash_loop_rollback = "passed";

    systemctl(
      "stop-before-uninstall",
      ["stop", serviceId],
      environment,
      evidenceDir,
    );
    systemctl(
      "inactive-before-uninstall",
      ["is-active", serviceId],
      environment,
      evidenceDir,
      [3],
    );
    // Stopping Core may checkpoint SQLite WAL into the main database. That is
    // a legitimate database write performed by Core, not by uninstall. Take
    // the byte-for-byte preservation snapshot only after the service is
    // confirmed inactive, then require uninstall itself to leave it unchanged.
    const databaseBeforeUninstall = await databaseIdentity(database);
    observations.database_before_uninstall = databaseBeforeUninstall;
    const uninstall = run(
      "uninstall",
      cli,
      installArguments({
        command: "uninstall",
        source: currentDistribution.path,
        installRoot,
        home,
        binDir,
        dataDir,
        xdgConfigHome: environment.XDG_CONFIG_HOME,
      }),
      environment,
      evidenceDir,
      [0],
      120_000,
    );
    if (uninstall.status !== 0) throw commandFailure("uninstall", uninstall);
    systemctl(
      "uninstalled-disabled",
      ["is-enabled", serviceId],
      environment,
      evidenceDir,
      [1, 4],
    );
    systemctl(
      "uninstalled-inactive",
      ["is-active", serviceId],
      environment,
      evidenceDir,
      [3, 4],
    );
    const databaseAfterUninstall = await databaseIdentity(database);
    observations.database_after_uninstall = databaseAfterUninstall;
    if (
      databaseAfterUninstall.bytes !== databaseBeforeUninstall.bytes ||
      databaseAfterUninstall.sha256 !== databaseBeforeUninstall.sha256
    ) {
      throw new Error("linux_upgrade_rollback_uninstall_changed_data");
    }
    status.uninstall_preserve_data = "passed";
    receipt.result = "passed";
  } catch (error) {
    receipt.result = "failed";
    receipt.error = error instanceof Error ? error.message : String(error);
    systemctl(
      "cleanup-stop",
      ["stop", serviceId],
      environment,
      evidenceDir,
      [0, 5],
    );
    const cleanupCli = (await exists(path.join(binDir, "memhub")))
      ? path.join(binDir, "memhub")
      : path.join(currentDistribution.path, "bin", "one-memory");
    run(
      "cleanup-uninstall",
      cleanupCli,
      installArguments({
        command: "uninstall",
        source: currentDistribution.path,
        installRoot,
        home,
        binDir,
        dataDir,
        xdgConfigHome: environment.XDG_CONFIG_HOME,
      }),
      environment,
      evidenceDir,
      [0, 1],
      120_000,
    );
  }
  await writeFile(
    path.join(evidenceDir, "linux-upgrade-rollback-receipt.json"),
    `${JSON.stringify(receipt, null, 2)}\n`,
  );
  if (receipt.result !== "passed") throw new Error(receipt.error);
  return receipt;
}

function run(
  name,
  command,
  arguments_,
  environment,
  evidenceDir,
  accepted = [0],
  timeout = 120_000,
) {
  const result = spawnSync(command, arguments_, {
    cwd: root,
    env: environment,
    encoding: "utf8",
    timeout,
  });
  const document = {
    command,
    args: arguments_,
    exit_code: result.status,
    signal: result.signal,
    stdout: result.stdout,
    stderr: result.stderr,
    error: result.error?.message ?? null,
  };
  writeFile(
    path.join(evidenceDir, `${name}.json`),
    `${JSON.stringify(document, null, 2)}\n`,
  ).catch(() => undefined);
  if (!accepted.includes(result.status)) {
    throw commandFailure(name, { ...document, status: result.status });
  }
  return { ...document, status: result.status };
}

function systemctl(name, arguments_, environment, evidenceDir, accepted = [0]) {
  return run(
    name,
    "systemctl",
    ["--user", ...arguments_],
    environment,
    evidenceDir,
    accepted,
    30_000,
  );
}

function installArguments(options) {
  return [
    options.command,
    "--source",
    options.source,
    "--install-root",
    options.installRoot,
    "--home",
    options.home,
    "--bin-dir",
    options.binDir,
    "--data-dir",
    options.dataDir,
    "--xdg-config-home",
    options.xdgConfigHome,
    "--no-shell-path",
    "--yes",
    "--json",
  ];
}

async function distributionIdentity(value) {
  const resolved = await realpath(value);
  const manifest = JSON.parse(
    await readFile(path.join(resolved, "manifest.json"), "utf8"),
  );
  return { path: resolved, manifest };
}

async function selectedManifest(installRoot) {
  const current = path.join(installRoot, "current");
  const target = await realpath(current);
  return JSON.parse(await readFile(path.join(target, "manifest.json"), "utf8"));
}

async function makeFailingDistribution(options) {
  await assertAbsent(options.target, "failing_distribution_exists");
  await cp(options.source, options.target, {
    recursive: true,
    dereference: false,
    verbatimSymlinks: true,
  });
  const core = path.join(options.target, "core", "one-memory");
  const crashingExecutable = "/bin/false";
  await copyFile(crashingExecutable, core);
  await chmod(core, 0o700);
  const manifestPath = path.join(options.target, "manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  manifest.version = options.version;
  manifest.build_number = options.buildNumber;
  manifest.package_id = `simulated-crash-${options.buildNumber}`;
  manifest.files["core/one-memory"] = await sha256File(core);
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  return { path: options.target, manifest };
}

function nextInternalVersion(version) {
  const match = /^(\d+\.\d+\.\d+)-internal\.(\d+)$/.exec(version);
  if (!match) return `${version}-crash.1`;
  return `${match[1]}-internal.${Number(match[2]) + 1}`;
}

async function waitForRunningStatus(options) {
  const deadline = Date.now() + 60_000;
  let attempt = 0;
  while (Date.now() < deadline) {
    attempt += 1;
    const result = run(
      `${options.prefix}-${attempt}`,
      options.cli,
      ["status", "--json"],
      options.environment,
      options.evidenceDir,
      // During a crash/restart transition status may truthfully return 1 with
      // `runtime_service_not_ready` or 3 while stopped. Both are observations,
      // not verifier failures; only a later exit 0 with a new verified instance
      // satisfies the readiness condition below.
      [0, 1, 3],
      10_000,
    );
    if (result.status === 0) {
      const document = parseJson(result.stdout, options.prefix);
      const instanceId = findKey(document, "instance_id");
      if (
        typeof instanceId === "string" &&
        instanceId.length > 0 &&
        (options.previousInstanceId === undefined ||
          instanceId !== options.previousInstanceId)
      ) {
        return document;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`${options.prefix}_runtime_not_ready`);
}

async function waitForRecall(options) {
  const deadline = Date.now() + 90_000;
  let attempt = 0;
  while (Date.now() < deadline) {
    attempt += 1;
    const result = run(
      `${options.prefix}-${attempt}`,
      options.cli,
      ["recall", options.phrase, "--json"],
      options.environment,
      options.evidenceDir,
      [0, 1, 3],
      15_000,
    );
    if (result.stdout.includes(options.phrase)) return true;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  return false;
}

function doctorDocument(result, label) {
  const document = parseJson(result.stdout, label);
  const core = document?.checks?.find?.((check) => check?.id === "core");
  const broker = document?.checks?.find?.((check) => check?.id === "broker");
  if (!core || !broker || core.state !== "pass") {
    throw new Error(`${label}_checks_invalid`);
  }
  return { document, core, broker };
}

function conversationRow(type, uuid, content, minute) {
  return JSON.stringify({
    type,
    sessionId: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    uuid,
    timestamp: `2026-10-13T09:${minute}:00+08:00`,
    cwd: "/tmp/memhub-upgrade-rollback",
    message: {
      role: type,
      content:
        type === "assistant" ? [{ type: "text", text: content }] : content,
    },
  });
}

async function databaseIdentity(file) {
  return { bytes: (await stat(file)).size, sha256: await sha256File(file) };
}

async function sha256File(file) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
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

function parseJson(value, label) {
  try {
    return JSON.parse(value);
  } catch {
    throw new Error(`${label}_json_invalid`);
  }
}

function commandFailure(name, result) {
  return new Error(
    `${name} failed with exit ${result.status}: ${result.stderr || result.stdout}`,
  );
}

async function exists(target) {
  return lstat(target).then(
    () => true,
    () => false,
  );
}

async function assertAbsent(target, code) {
  if (await exists(target)) throw new Error(code);
}

function parseArguments(arguments_) {
  const options = { corePort: 29285, runtimePort: 29286 };
  for (let index = 0; index < arguments_.length; index += 1) {
    const flag = arguments_[index];
    const value = arguments_[++index];
    if (!value) throw new Error(`missing value for ${flag}`);
    if (flag === "--previous-distribution")
      options.previousDistribution = value;
    else if (flag === "--current-distribution")
      options.currentDistribution = value;
    else if (flag === "--verify-root") options.verifyRoot = value;
    else if (flag === "--core-port") options.corePort = Number(value);
    else if (flag === "--runtime-port") options.runtimePort = Number(value);
    else throw new Error(`invalid argument: ${flag}`);
  }
  if (
    !options.previousDistribution ||
    !options.currentDistribution ||
    !options.verifyRoot
  ) {
    throw new Error(
      "usage: verify-linux-upgrade-rollback.mjs --previous-distribution <dir> --current-distribution <dir> --verify-root <dir> [--core-port <port>] [--runtime-port <port>]",
    );
  }
  for (const port of [options.corePort, options.runtimePort]) {
    if (!Number.isSafeInteger(port) || port < 1024 || port > 65535) {
      throw new Error("linux_upgrade_rollback_port_invalid");
    }
  }
  return options;
}

async function main() {
  const receipt = await verifyLinuxUpgradeRollback(
    parseArguments(process.argv.slice(2)),
  );
  process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`);
    process.exitCode = 1;
  });
}
