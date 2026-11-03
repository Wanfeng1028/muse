#!/usr/bin/env node

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

async function hasWindowsPowerShell() {
  try {
    await execFileAsync("powershell.exe", [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      "$PSVersionTable.PSVersion.Major",
    ]);
    return true;
  } catch {
    return false;
  }
}

async function isWindowsHost() {
  return process.platform === "win32";
}

const windowsHost = await isWindowsHost();
const capabilities = {
  windows_power_shell:
    windowsHost && (await hasWindowsPowerShell()) ? "available" : "unavailable",
};

const matrix = {
  schema_version: 1,
  product: "one-memory-windows-support-matrix",
  platform: "win32",
  architectures: ["x64"],
  host: {
    is_windows: windowsHost,
    capabilities,
    host_is_not_windows_note:
      "On non-Windows hosts every real-machine outcome stays blocked. This is evidence of the blocking condition, not a substitute for Windows verification.",
  },
  release_gate: {
    os: "Windows 11",
    arch: "x64",
    status: "blocked",
    blocked_reason: "windows_target_machine_required",
  },
  explicit_matrix: {
    windows_11_x64: "blocked",
    windows_10_x64: "blocked",
    windows_arm64: "blocked",
  },
  capabilities: {
    ...capabilities,
    x64_core_electron_cli_build: "blocked",
    current_user_sid_dacl: "blocked",
    credential_manager: "blocked",
    current_user_service: "blocked",
    path_launcher: "blocked",
    unicode_and_spaces: "blocked",
    junction_reparse: "blocked",
    open_file_replacement: "blocked",
    process_lifecycle: "blocked",
    install_upgrade_rollback_uninstall: "blocked",
    app_cli_shared_runtime: "implemented",
  },
  blocked_reason: "windows_runtime_and_runner_unavailable",
  conditions_to_unblock: [
    "windows_11_x64_target_machine_or_runner",
    "same_source_runtime_hash",
    "non_admin_current_user_install_session",
    "sid_dacl_owner_only_verification",
    "credential_manager_roundtrip",
    "current_user_service_install_start_stop_restart",
    "unicode_space_junction_long_path_matrix",
    "open_file_upgrade_and_rollback_uninstall_preserves_data",
  ],
};

process.stdout.write(`${JSON.stringify(matrix, null, 2)}\n`);

// Fail closed: the matrix is machine-readable evidence for a release gate, so
// the exit code must agree with `release_gate.status`. Until a Windows 11 x64
// target has actually run the blocked capabilities, `status` is "blocked" and
// this process must exit non-zero. Exiting 0 here let a CI step that only
// checks success read "blocked" as "platform supported" — the exact failure
// two independent reviewers flagged. "accepted" is the only passing status.
process.exitCode = matrix.release_gate.status === "accepted" ? 0 : 1;
