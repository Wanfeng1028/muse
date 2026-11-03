#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import {
  access,
  chmod,
  cp,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  readlink,
  realpath,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import https from "node:https";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildReleaseAssets } from "../../build-release-assets.mjs";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);
const require = createRequire(import.meta.url);
const { readReleaseContract } = require("../../release-contract.cjs");
const releaseContract = readReleaseContract(root);

export async function verifyFakeReleaseBootstrap(options) {
  if (process.platform !== "linux") {
    throw new Error("fake_release_bootstrap_requires_linux");
  }
  if (!["x64", "arm64"].includes(process.arch)) {
    throw new Error("fake_release_bootstrap_arch_unsupported");
  }
  const distribution = await realpath(options.distribution);
  const sourceRoot = await realpath(options.sourceRoot ?? root);
  assertTrackedGitTreeClean(sourceRoot);
  let distributionManifest = JSON.parse(
    await readFile(path.join(distribution, "manifest.json"), "utf8"),
  );
  if (
    distributionManifest?.product !== "one-memory-runtime" ||
    distributionManifest.platform !== "linux" ||
    distributionManifest.arch !== process.arch ||
    typeof distributionManifest.version !== "string" ||
    !Number.isSafeInteger(distributionManifest.build_number)
  ) {
    throw new Error("fake_release_distribution_identity_invalid");
  }

  const output = path.resolve(options.output);
  const verifyRoot = path.resolve(options.verifyRoot);
  await assertAbsent(output, "fake_release_output_exists");
  await assertAbsent(verifyRoot, "fake_release_verify_root_exists");
  const home = path.join(verifyRoot, "home");
  const dataDir = path.join(verifyRoot, "data with spaces");
  const installRoot = path.join(verifyRoot, "install");
  const binDir = path.join(verifyRoot, "bin");
  const evidenceDir = path.join(verifyRoot, "evidence");
  const temporaryDirectory = path.join(verifyRoot, "tmp");
  const npmPrefix = path.join(verifyRoot, "npm-prefix");
  for (const directory of [
    home,
    dataDir,
    binDir,
    evidenceDir,
    temporaryDirectory,
    npmPrefix,
  ]) {
    await mkdir(directory, { recursive: true, mode: 0o700 });
  }

  const releaseDistribution = await prepareReleaseDistribution({
    distribution,
    verifyRoot,
    sourceRoot: options.distributionSourceRoot,
    sourceCommit: options.distributionSourceCommit,
  });
  distributionManifest = releaseDistribution.manifest;

  const tlsRoot = await mkdtemp(
    path.join(os.tmpdir(), "memhub-fake-release-tls-"),
  );
  await chmod(tlsRoot, 0o700);
  const receipt = {
    schema_version: 1,
    product: "memhub-fake-release-bootstrap",
    distribution,
    release_distribution: releaseDistribution.path,
    runtime_source_commit: distributionManifest.git_commit,
    verifier_source_commit: gitCommit(sourceRoot),
    cli_source_commit: null,
    source_root: sourceRoot,
    output,
    verify_root: verifyRoot,
    version: distributionManifest.version,
    build_number: distributionManifest.build_number,
    platform: distributionManifest.platform,
    arch: distributionManifest.arch,
    npm_package: options.packageName,
    status: {},
    observations: {},
    requests: [],
  };

  let server;
  const managedCli = path.join(binDir, "memhub");
  let environment;
  try {
    const tls = generateTlsFixture(tlsRoot);
    server = await startReleaseServer({
      key: await readFile(tls.serverKey),
      cert: await readFile(tls.serverCertificate),
      output,
      requests: receipt.requests,
    });
    const address = server.address();
    if (!address || typeof address === "string") {
      throw new Error("fake_release_server_address_unavailable");
    }
    const assetBaseUrl = `https://127.0.0.1:${address.port}/downloads/`;
    const manifestUrl = `${assetBaseUrl}release-manifest.json`;
    receipt.manifest_url = manifestUrl;

    const release = await buildReleaseAssets({
      output,
      version: distributionManifest.version,
      channel: distributionManifest.version.includes("-")
        ? "prerelease"
        : "stable",
      assetBaseUrl,
      publishedAt: new Date().toISOString(),
      distributions: [releaseDistribution.path],
    });
    receipt.release = release;
    receipt.status.release_assets = "passed";

    const expectedInstallSpec = `${options.packageName}@${distributionManifest.version}`;
    let npmInstallTarget;
    if (options.npmInstallSpec !== undefined) {
      if (options.npmInstallSpec !== expectedInstallSpec) {
        throw new Error("fake_release_npm_install_spec_mismatch");
      }
      npmInstallTarget = options.npmInstallSpec;
      receipt.npm_install_source = "registry";
      receipt.npm_install_spec = options.npmInstallSpec;
      receipt.npm_registry = options.npmRegistry;
      receipt.expected_cli_bundle_sha256 = options.expectedCliSha256;
      receipt.status.npm_pack = "not_applicable";
    } else {
      const pack = await run(
        "pack-cli",
        "pnpm",
        ["--filter", "@one-memory/cli", "pack:publish"],
        {
          cwd: sourceRoot,
          env: {
            ...process.env,
            ONE_MEMORY_VERSION: distributionManifest.version,
            ONE_MEMORY_BUILD_NUMBER: String(distributionManifest.build_number),
            ONE_MEMORY_COMMIT: receipt.verifier_source_commit,
            MEMHUB_NPM_PACKAGE: options.packageName,
            MEMHUB_DEFAULT_RELEASE_MANIFEST_URL_TEMPLATE: manifestUrl,
          },
          evidenceDir,
          timeout: 5 * 60_000,
        },
      );
      if (pack.status !== 0) throw commandFailure("pack-cli", pack);
      const tarball = path.join(
        sourceRoot,
        "apps",
        "cli",
        "dist-cli",
        npmTarballName(options.packageName, distributionManifest.version),
      );
      const tarballInfo = await stat(tarball);
      receipt.npm_tarball = tarball;
      receipt.npm_tarball_bytes = tarballInfo.size;
      receipt.npm_install_source = "tarball";
      receipt.cli_source_commit = receipt.verifier_source_commit;
      receipt.status.npm_pack = "passed";
      npmInstallTarget = tarball;
    }

    const npmInstallArguments = [
      "install",
      "--prefix",
      npmPrefix,
      npmInstallTarget,
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
    ];
    if (options.npmRegistry !== undefined) {
      npmInstallArguments.push("--registry", options.npmRegistry);
    }
    const npmInstall = await run("npm-install", "npm", npmInstallArguments, {
      cwd: sourceRoot,
      env: process.env,
      evidenceDir,
      timeout: 120_000,
    });
    if (npmInstall.status !== 0) {
      throw commandFailure("npm-install", npmInstall);
    }
    const thinCli = path.join(npmPrefix, "node_modules", ".bin", "memhub");
    await access(thinCli);
    const installedCliBundle = await realpath(thinCli);
    const installedCliSha256 = await sha256File(installedCliBundle);
    receipt.cli_bundle_sha256 = installedCliSha256;
    if (
      options.expectedCliSha256 !== undefined &&
      installedCliSha256 !== options.expectedCliSha256
    ) {
      throw new Error("fake_release_registry_cli_digest_mismatch");
    }
    const version = await run("thin-cli-version", thinCli, ["--version"], {
      cwd: sourceRoot,
      env: process.env,
      evidenceDir,
    });
    if (
      version.status !== 0 ||
      version.stdout.trim() !== `memhub ${distributionManifest.version}`
    ) {
      throw new Error("fake_release_thin_cli_version_mismatch");
    }
    receipt.status.npm_install = "passed";

    environment = {
      ...process.env,
      HOME: home,
      XDG_CONFIG_HOME: path.join(home, ".config"),
      XDG_DATA_HOME: path.join(home, ".local", "share"),
      ONE_MEMORY_DATA_DIR: dataDir,
      ONE_MEMORY_CORE_PORT: String(options.corePort),
      ONE_MEMORY_RUNTIME_PORT: String(options.runtimePort),
      ONE_MEMORY_PORT: String(options.corePort),
      ONE_MEMORY_TEST_ISOLATED: "1",
      NODE_EXTRA_CA_CERTS: tls.caCertificate,
      MEMHUB_RELEASE_ALLOWED_HOSTS: "127.0.0.1",
      TMPDIR: temporaryDirectory,
      NO_COLOR: "1",
    };
    const installArguments = [
      "install",
      ...(options.npmInstallSpec === undefined
        ? []
        : ["--release-manifest-url", manifestUrl]),
      "--install-root",
      installRoot,
      "--home",
      home,
      "--bin-dir",
      binDir,
      "--data-dir",
      dataDir,
      "--xdg-config-home",
      environment.XDG_CONFIG_HOME,
      "--no-shell-path",
      "--json",
    ];

    const beforePreview = requestSummary(receipt.requests);
    const preview = await run("install-preview", thinCli, installArguments, {
      cwd: sourceRoot,
      env: environment,
      evidenceDir,
      timeout: 120_000,
    });
    if (preview.status !== 0) throw commandFailure("install-preview", preview);
    const previewDocument = parseJson(preview.stdout, "install-preview");
    const afterPreview = requestSummary(receipt.requests);
    if (
      afterPreview.manifest !== beforePreview.manifest + 1 ||
      afterPreview.artifact !== beforePreview.artifact
    ) {
      throw new Error("fake_release_preview_downloaded_artifact");
    }
    if (
      previewDocument?.release?.version !== distributionManifest.version ||
      previewDocument?.apply !== false
    ) {
      throw new Error("fake_release_preview_identity_mismatch");
    }
    receipt.status.preview_manifest_only = "passed";

    const beforeApply = requestSummary(receipt.requests);
    const apply = await run(
      "install-apply",
      thinCli,
      [...installArguments, "--yes"],
      {
        cwd: sourceRoot,
        env: environment,
        evidenceDir,
        timeout: 15 * 60_000,
      },
    );
    if (apply.status !== 0) throw commandFailure("install-apply", apply);
    const installDocument = parseJson(apply.stdout, "install-apply");
    const afterApply = requestSummary(receipt.requests);
    if (
      afterApply.manifest !== beforeApply.manifest + 1 ||
      afterApply.artifact !== beforeApply.artifact + 1
    ) {
      throw new Error("fake_release_apply_request_sequence_invalid");
    }
    const artifact = release.artifacts.find(
      (candidate) =>
        candidate.kind === "runtime" &&
        candidate.platform === "linux" &&
        candidate.arch === process.arch,
    );
    if (!artifact) throw new Error("fake_release_runtime_artifact_missing");
    const servedArtifact = receipt.requests
      .filter((request) => request.kind === "artifact")
      .at(-1);
    if (
      !servedArtifact ||
      servedArtifact.status !== 200 ||
      servedArtifact.bytes_sent !== artifact.bytes
    ) {
      throw new Error("fake_release_artifact_stream_incomplete");
    }
    const installedCorePort = findKey(installDocument, "core_port");
    if (
      !Number.isSafeInteger(installedCorePort) ||
      installedCorePort < 1024 ||
      installedCorePort > 65535
    ) {
      throw new Error("fake_release_install_core_port_invalid");
    }
    environment.ONE_MEMORY_CORE_PORT = String(installedCorePort);
    environment.ONE_MEMORY_PORT = String(installedCorePort);
    receipt.observations.installed_core_port = installedCorePort;
    receipt.status.remote_download_install = "passed";

    const temporaryEntries = await readdir(temporaryDirectory);
    if (temporaryEntries.some((entry) => entry.startsWith("memhub-runtime-"))) {
      throw new Error("fake_release_download_temporary_state_leaked");
    }
    receipt.status.download_cleanup = "passed";

    const running = await waitForRunningStatus({
      cli: managedCli,
      env: environment,
      evidenceDir,
    });
    const instanceId = findKey(running, "instance_id");
    if (typeof instanceId !== "string" || instanceId.length === 0) {
      throw new Error("fake_release_runtime_identity_missing");
    }
    receipt.observations.instance_id = instanceId;
    receipt.status.status = "passed";

    const doctor = await run("doctor", managedCli, ["doctor", "--json"], {
      cwd: sourceRoot,
      env: environment,
      evidenceDir,
      accepted: [0, 1],
      timeout: 30_000,
    });
    if (![0, 1].includes(doctor.status)) throw commandFailure("doctor", doctor);
    const doctorDocument = parseJson(doctor.stdout, "doctor");
    const coreCheck = doctorCheck(doctorDocument, "core");
    const brokerCheck = doctorCheck(doctorDocument, "broker");
    if (
      coreCheck.state !== "pass" ||
      coreCheck.details?.version !== distributionManifest.version ||
      coreCheck.details?.instance_verified !== true ||
      brokerCheck.state !== "pass"
    ) {
      throw new Error("fake_release_doctor_identity_mismatch");
    }
    receipt.observations.doctor_state = doctorDocument.state;
    receipt.observations.doctor_core_version = coreCheck.details.version;
    receipt.status.doctor = "passed";

    const database = path.join(dataDir, "one-memory.sqlite3");
    await access(database);
    const currentBeforeNpmUninstall = await readlink(
      path.join(installRoot, "current"),
    );
    const requestsBeforeNpmUninstall = receipt.requests.length;
    const npmUninstall = await run(
      "npm-uninstall",
      "npm",
      [
        "uninstall",
        "--prefix",
        npmPrefix,
        options.packageName,
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
      ],
      {
        cwd: sourceRoot,
        env: process.env,
        evidenceDir,
        timeout: 120_000,
      },
    );
    if (npmUninstall.status !== 0) {
      throw commandFailure("npm-uninstall", npmUninstall);
    }
    if (await exists(thinCli)) {
      throw new Error("fake_release_npm_uninstall_left_thin_cli");
    }
    await access(managedCli);
    await access(database);
    if (
      (await readlink(path.join(installRoot, "current"))) !==
      currentBeforeNpmUninstall
    ) {
      throw new Error("fake_release_npm_uninstall_changed_current");
    }
    const activeAfterNpmUninstall = await run(
      "active-after-npm-uninstall",
      "systemctl",
      ["--user", "is-active", "one-memory.service"],
      { cwd: sourceRoot, env: environment, evidenceDir, timeout: 30_000 },
    );
    if (activeAfterNpmUninstall.status !== 0) {
      throw commandFailure(
        "active-after-npm-uninstall",
        activeAfterNpmUninstall,
      );
    }
    const runningAfterNpmUninstall = await waitForRunningStatus({
      cli: managedCli,
      env: environment,
      evidenceDir,
    });
    if (findKey(runningAfterNpmUninstall, "instance_id") !== instanceId) {
      throw new Error("fake_release_npm_uninstall_changed_runtime_identity");
    }
    const doctorAfterNpmUninstall = await run(
      "doctor-after-npm-uninstall",
      managedCli,
      ["doctor", "--json"],
      {
        cwd: sourceRoot,
        env: environment,
        evidenceDir,
        accepted: [0, 1],
        timeout: 30_000,
      },
    );
    const doctorAfterNpmDocument = parseJson(
      doctorAfterNpmUninstall.stdout,
      "doctor-after-npm-uninstall",
    );
    if (
      doctorCheck(doctorAfterNpmDocument, "core").state !== "pass" ||
      doctorCheck(doctorAfterNpmDocument, "broker").state !== "pass"
    ) {
      throw new Error("fake_release_npm_uninstall_changed_runtime_health");
    }
    if (receipt.requests.length !== requestsBeforeNpmUninstall) {
      throw new Error("fake_release_npm_uninstall_accessed_release_network");
    }
    receipt.observations.current_after_npm_uninstall =
      currentBeforeNpmUninstall;
    receipt.observations.runtime_after_npm_uninstall = instanceId;
    receipt.status.npm_uninstall_preserve_runtime_data = "passed";

    const stop = await run(
      "stop-service",
      "systemctl",
      ["--user", "stop", "one-memory.service"],
      { cwd: sourceRoot, env: environment, evidenceDir, timeout: 30_000 },
    );
    if (stop.status !== 0) throw commandFailure("stop-service", stop);
    await access(database);
    const databaseBefore = {
      bytes: (await stat(database)).size,
      sha256: await sha256File(database),
    };
    receipt.observations.database_before_uninstall = databaseBefore;

    const requestsBeforeUninstall = receipt.requests.length;
    const uninstall = await run(
      "uninstall",
      managedCli,
      [
        "uninstall",
        "--source",
        distribution,
        "--install-root",
        installRoot,
        "--home",
        home,
        "--bin-dir",
        binDir,
        "--data-dir",
        dataDir,
        "--xdg-config-home",
        environment.XDG_CONFIG_HOME,
        "--no-shell-path",
        "--yes",
        "--json",
      ],
      {
        cwd: sourceRoot,
        env: environment,
        evidenceDir,
        timeout: 120_000,
      },
    );
    if (uninstall.status !== 0) throw commandFailure("uninstall", uninstall);
    if (receipt.requests.length !== requestsBeforeUninstall) {
      throw new Error("fake_release_uninstall_accessed_network");
    }
    const databaseAfter = {
      bytes: (await stat(database)).size,
      sha256: await sha256File(database),
    };
    receipt.observations.database_after_uninstall = databaseAfter;
    if (
      databaseAfter.bytes !== databaseBefore.bytes ||
      databaseAfter.sha256 !== databaseBefore.sha256
    ) {
      throw new Error("fake_release_uninstall_changed_data");
    }
    if (
      (await exists(path.join(installRoot, "current"))) ||
      (await readdir(binDir)).length !== 0
    ) {
      throw new Error("fake_release_uninstall_left_managed_program");
    }
    receipt.status.uninstall_preserve_data = "passed";
    receipt.result = "passed";
  } catch (error) {
    receipt.result = "failed";
    receipt.error = error instanceof Error ? error.message : String(error);
    if (environment) {
      await run(
        "cleanup-stop",
        "systemctl",
        ["--user", "stop", "one-memory.service"],
        {
          cwd: sourceRoot,
          env: environment,
          evidenceDir,
          accepted: [0, 5],
          timeout: 30_000,
        },
      );
      await run(
        "cleanup-uninstall",
        path.join(distribution, "bin", "one-memory"),
        [
          "uninstall",
          "--source",
          distribution,
          "--install-root",
          installRoot,
          "--home",
          home,
          "--bin-dir",
          binDir,
          "--data-dir",
          dataDir,
          "--xdg-config-home",
          environment.XDG_CONFIG_HOME,
          "--no-shell-path",
          "--yes",
          "--json",
        ],
        {
          cwd: sourceRoot,
          env: environment,
          evidenceDir,
          accepted: [0, 1],
          timeout: 120_000,
        },
      );
    }
  } finally {
    if (server) await closeServer(server);
    await rm(tlsRoot, { recursive: true, force: true });
    await writeFile(
      path.join(evidenceDir, "fake-release-bootstrap-receipt.json"),
      `${JSON.stringify(receipt, null, 2)}\n`,
    );
  }
  if (receipt.result !== "passed") throw new Error(receipt.error);
  return receipt;
}

async function prepareReleaseDistribution(options) {
  const manifestPath = path.join(options.distribution, "manifest.json");
  const original = JSON.parse(await readFile(manifestPath, "utf8"));
  const complete =
    typeof original.git_commit === "string" &&
    /^[0-9a-f]{40}$/.test(original.git_commit) &&
    original.runtime_protocol === releaseContract.runtimeProtocol &&
    original.supported_cli_protocol?.min ===
      releaseContract.runtimeSupportedCliProtocol.min &&
    original.supported_cli_protocol?.max ===
      releaseContract.runtimeSupportedCliProtocol.max;
  if (complete) return { path: options.distribution, manifest: original };
  if (!options.sourceRoot || !options.sourceCommit) {
    throw new Error("fake_release_distribution_contract_missing");
  }
  const sourceRoot = await realpath(options.sourceRoot);
  const commit = gitCommit(sourceRoot);
  if (commit !== options.sourceCommit || !/^[0-9a-f]{40}$/.test(commit)) {
    throw new Error("fake_release_distribution_commit_unproven");
  }
  assertTrackedGitTreeClean(sourceRoot);
  const relative = path.relative(sourceRoot, options.distribution);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("fake_release_distribution_source_unrelated");
  }
  const staged = path.join(options.verifyRoot, "release-distribution");
  await cp(options.distribution, staged, {
    recursive: true,
    dereference: false,
    verbatimSymlinks: true,
    errorOnExist: true,
    force: false,
  });
  const manifest = {
    ...original,
    git_commit: commit,
    runtime_protocol: releaseContract.runtimeProtocol,
    supported_cli_protocol: releaseContract.runtimeSupportedCliProtocol,
  };
  await writeFile(
    path.join(staged, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    { mode: 0o600 },
  );
  return { path: staged, manifest };
}

function gitCommit(directory) {
  const result = spawnSync("git", ["rev-parse", "HEAD"], {
    cwd: directory,
    encoding: "utf8",
  });
  const commit = result.stdout?.trim();
  if (result.status !== 0 || !/^[0-9a-f]{40}$/.test(commit)) {
    throw new Error("fake_release_source_commit_unavailable");
  }
  return commit;
}

function assertTrackedGitTreeClean(directory) {
  for (const arguments_ of [
    ["diff", "--quiet", "--"],
    ["diff", "--cached", "--quiet", "--"],
  ]) {
    const result = spawnSync("git", arguments_, { cwd: directory });
    if (result.status !== 0) {
      throw new Error("fake_release_distribution_source_modified");
    }
  }
}

async function run(name, command, arguments_, options) {
  const result = await new Promise((resolve) => {
    const child = spawn(command, arguments_, {
      cwd: options.cwd,
      env: options.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 2_000).unref();
    }, options.timeout ?? 120_000);
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", (error) => {
      clearTimeout(timeout);
      resolve({
        status: null,
        signal: null,
        stdout,
        stderr,
        error: error.message,
      });
    });
    child.on("close", (status, signal) => {
      clearTimeout(timeout);
      resolve({
        status,
        signal,
        stdout,
        stderr,
        error: timedOut ? "command timed out" : null,
      });
    });
  });
  const document = {
    command,
    args: arguments_,
    exit_code: result.status,
    signal: result.signal,
    stdout: result.stdout,
    stderr: result.stderr,
    error: result.error,
  };
  await writeFile(
    path.join(options.evidenceDir, `${name}.json`),
    `${JSON.stringify(document, null, 2)}\n`,
  );
  return { ...document, status: result.status };
}

function commandFailure(name, result) {
  return new Error(
    `${name} failed with exit ${result.status}: ${result.stderr || result.stdout}`,
  );
}

function generateTlsFixture(directory) {
  const caKey = path.join(directory, "ca-key.pem");
  const caCertificate = path.join(directory, "ca-cert.pem");
  const serverKey = path.join(directory, "server-key.pem");
  const serverRequest = path.join(directory, "server.csr");
  const serverCertificate = path.join(directory, "server-cert.pem");
  const extension = path.join(directory, "server.ext");
  const serial = path.join(directory, "ca-cert.srl");
  const extensionText = [
    "basicConstraints=critical,CA:FALSE",
    "keyUsage=critical,digitalSignature,keyEncipherment",
    "extendedKeyUsage=serverAuth",
    "subjectAltName=IP:127.0.0.1,DNS:localhost",
    "",
  ].join("\n");
  const extensionWrite = spawnSync(process.execPath, [
    "-e",
    "require('fs').writeFileSync(process.argv[1], process.argv[2], {mode:0o600})",
    extension,
    extensionText,
  ]);
  if (extensionWrite.status !== 0) throw new Error("fake_release_tls_failed");
  openssl([
    "req",
    "-x509",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-days",
    "1",
    "-subj",
    "/CN=MemHub Fake Release CA",
    "-addext",
    "basicConstraints=critical,CA:TRUE",
    "-addext",
    "keyUsage=critical,keyCertSign,cRLSign",
    "-keyout",
    caKey,
    "-out",
    caCertificate,
  ]);
  openssl([
    "req",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-subj",
    "/CN=127.0.0.1",
    "-keyout",
    serverKey,
    "-out",
    serverRequest,
  ]);
  openssl([
    "x509",
    "-req",
    "-days",
    "1",
    "-CA",
    caCertificate,
    "-CAkey",
    caKey,
    "-CAcreateserial",
    "-in",
    serverRequest,
    "-out",
    serverCertificate,
    "-extfile",
    extension,
  ]);
  return { caCertificate, serverCertificate, serverKey, serial };
}

function openssl(arguments_) {
  const result = spawnSync("openssl", arguments_, {
    encoding: "utf8",
    timeout: 30_000,
  });
  if (result.status !== 0) {
    throw new Error(
      `fake_release_tls_failed:${result.stderr || result.stdout}`,
    );
  }
}

async function startReleaseServer(options) {
  const server = https.createServer(
    { key: options.key, cert: options.cert },
    async (request, response) => {
      const record = {
        method: request.method,
        path: request.url,
        kind: "unknown",
        status: 0,
        bytes_sent: 0,
      };
      options.requests.push(record);
      try {
        if (request.method !== "GET" || !request.url) {
          record.status = 405;
          response.writeHead(405).end();
          return;
        }
        const url = new URL(request.url, "https://127.0.0.1");
        const match = /^\/downloads\/([0-9A-Za-z][0-9A-Za-z._-]{0,255})$/.exec(
          url.pathname,
        );
        if (!match) {
          record.status = 404;
          response.writeHead(404).end();
          return;
        }
        const filename = match[1];
        const file = path.join(options.output, filename);
        const info = await stat(file).catch(() => null);
        if (!info?.isFile()) {
          record.status = 404;
          response.writeHead(404).end();
          return;
        }
        record.kind =
          filename === "release-manifest.json" ? "manifest" : "artifact";
        record.status = 200;
        response.writeHead(200, {
          "content-length": String(info.size),
          "content-type": filename.endsWith(".json")
            ? "application/json"
            : "application/octet-stream",
        });
        const stream = createReadStream(file);
        stream.on("data", (chunk) => {
          record.bytes_sent += chunk.length;
        });
        stream.on("error", () => response.destroy());
        stream.pipe(response);
      } catch {
        record.status = 500;
        if (!response.headersSent) response.writeHead(500);
        response.end();
      }
    },
  );
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve());
  });
  return server;
}

function closeServer(server) {
  return new Promise((resolve) => server.close(() => resolve()));
}

function requestSummary(requests) {
  return {
    manifest: requests.filter((request) => request.kind === "manifest").length,
    artifact: requests.filter((request) => request.kind === "artifact").length,
  };
}

async function waitForRunningStatus(options) {
  const deadline = Date.now() + 60_000;
  let attempt = 0;
  while (Date.now() < deadline) {
    attempt += 1;
    const result = await run(
      `status-${attempt}`,
      options.cli,
      ["status", "--json"],
      {
        cwd: options.cwd,
        env: options.env,
        evidenceDir: options.evidenceDir,
        accepted: [0, 3],
        timeout: 10_000,
      },
    );
    if (result.status === 0) return parseJson(result.stdout, "status");
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("fake_release_runtime_not_ready");
}

function doctorCheck(document, id) {
  const check = document?.checks?.find?.((candidate) => candidate?.id === id);
  if (!check || typeof check !== "object") {
    throw new Error(`fake_release_doctor_check_missing:${id}`);
  }
  return check;
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
    throw new Error(`fake_release_${label}_json_invalid`);
  }
}

function npmTarballName(name, version) {
  return `${name.replace(/^@/, "").replaceAll("/", "-")}-${version}.tgz`;
}

async function sha256File(file) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
}

async function exists(target) {
  return access(target).then(
    () => true,
    () => false,
  );
}

async function assertAbsent(target, code) {
  if (await exists(target)) throw new Error(code);
}

function parseArguments(arguments_) {
  const options = {
    packageName: "@example/memhub-bootstrap-smoke",
    corePort: 29085,
    runtimePort: 29086,
  };
  for (let index = 0; index < arguments_.length; index += 1) {
    const flag = arguments_[index];
    const value = arguments_[++index];
    if (!value) throw new Error(`missing value for ${flag}`);
    if (flag === "--distribution") options.distribution = value;
    else if (flag === "--source-root") options.sourceRoot = value;
    else if (flag === "--distribution-source-root")
      options.distributionSourceRoot = value;
    else if (flag === "--distribution-source-commit")
      options.distributionSourceCommit = value;
    else if (flag === "--output") options.output = value;
    else if (flag === "--verify-root") options.verifyRoot = value;
    else if (flag === "--package-name") options.packageName = value;
    else if (flag === "--npm-install-spec") options.npmInstallSpec = value;
    else if (flag === "--npm-registry") options.npmRegistry = value;
    else if (flag === "--expected-cli-sha256")
      options.expectedCliSha256 = value;
    else if (flag === "--core-port") options.corePort = Number(value);
    else if (flag === "--runtime-port") options.runtimePort = Number(value);
    else throw new Error(`invalid argument: ${flag}`);
  }
  if (!options.distribution || !options.output || !options.verifyRoot) {
    throw new Error(
      "usage: verify-fake-release-bootstrap.mjs --distribution <dir> --output <dir> --verify-root <dir> [--source-root <repo>] [--distribution-source-root <repo> --distribution-source-commit <sha>] [--package-name <name>] [--npm-install-spec <name@version> --npm-registry <https-url> --expected-cli-sha256 <digest>] [--core-port <port>] [--runtime-port <port>]",
    );
  }
  for (const port of [options.corePort, options.runtimePort]) {
    if (!Number.isSafeInteger(port) || port < 1024 || port > 65535) {
      throw new Error("fake_release_port_invalid");
    }
  }
  if (!/^(?:@[a-z0-9._-]+\/)?[a-z0-9._-]+$/.test(options.packageName)) {
    throw new Error("fake_release_package_name_invalid");
  }
  if (
    new Set([
      options.npmInstallSpec !== undefined,
      options.npmRegistry !== undefined,
      options.expectedCliSha256 !== undefined,
    ]).size !== 1
  ) {
    throw new Error("fake_release_npm_registry_incomplete");
  }
  if (
    options.expectedCliSha256 !== undefined &&
    !/^[a-f0-9]{64}$/.test(options.expectedCliSha256)
  ) {
    throw new Error("fake_release_cli_digest_invalid");
  }
  if (options.npmRegistry !== undefined) {
    let registry;
    try {
      registry = new URL(options.npmRegistry);
    } catch {
      throw new Error("fake_release_npm_registry_invalid");
    }
    if (
      registry.protocol !== "https:" ||
      registry.username !== "" ||
      registry.password !== ""
    ) {
      throw new Error("fake_release_npm_registry_invalid");
    }
  }
  if (
    (options.distributionSourceRoot === undefined) !==
    (options.distributionSourceCommit === undefined)
  ) {
    throw new Error("fake_release_distribution_source_incomplete");
  }
  return options;
}

async function main() {
  const receipt = await verifyFakeReleaseBootstrap(
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
