#!/usr/bin/env node

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

async function hasSystemdUser() {
  try {
    await execFileAsync("systemctl", ["--user", "show-environment"]);
    return true;
  } catch {
    return false;
  }
}

async function hasPortables() {
  try {
    await execFileAsync("systemctl", [
      "--user",
      "show",
      "--property=Portables",
    ]);
    return true;
  } catch {
    return false;
  }
}

async function hasTmpfilesD() {
  try {
    await execFileAsync("test", ["-d", "/usr/lib/tmpfiles.d"]);
    return true;
  } catch {
    return false;
  }
}

const capabilities = {
  systemd_user: (await hasSystemdUser()) ? "available" : "unavailable",
  portable_service: (await hasPortables()) ? "available" : "unavailable",
  tmpfiles_d: (await hasTmpfilesD()) ? "available" : "unavailable",
};

const matrix = {
  schema_version: 1,
  product: "one-memory-linux-support-matrix",
  platform: "linux",
  architectures: ["x64", "arm64"],
  build_entrypoint: "scripts/platform/linux/build-linux-runtime.mjs",
  capabilities,
  status: {
    x64_build: "blocked",
    arm64_build: "blocked",
    x64_systemd_user:
      capabilities.systemd_user === "available" ? "blocked" : "blocked",
    arm64_systemd_user:
      capabilities.systemd_user === "available" ? "blocked" : "blocked",
    no_systemd_serve:
      capabilities.systemd_user === "available" ? "blocked" : "blocked",
  },
  blocked_reason: "linux_runtime_and_runner_unavailable",
  conditions_to_unblock: [
    "linux_x64_arm64_runtime_or_runner",
    "same_source_runtime_hash",
    "systemd_user_session_for_install_start_stop_restart_upgrade_rollback_uninstall",
    "no_systemd_host_for_serve_only_claim",
  ],
};

process.stdout.write(`${JSON.stringify(matrix, null, 2)}\n`);
