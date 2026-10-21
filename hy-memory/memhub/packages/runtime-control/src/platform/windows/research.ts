import path from "node:path";

/**
 * C7 Windows assessment for H08. Values are deliberately conservative:
 * capability is accepted only after target-machine evidence, so this module
 * reports the current fail-closed state rather than an aspirational plan.
 */
export const WINDOWS_RESEARCH_STATE = {
  schema_version: 1,
  product: "one-memory-runtime",
  minimum_release_gate: {
    os: "Windows 11",
    arch: "x64",
    status: "blocked",
    blocked_reason: "windows_target_machine_required",
  },
  explicit_matrix: {
    windows_11_x64: {
      support: "blocked",
      blocked_reason: "windows_target_machine_required",
    },
    windows_10_x64: {
      support: "blocked",
      blocked_reason: "windows_10_matrix_not_measured",
    },
    windows_arm64: {
      support: "blocked",
      blocked_reason: "windows_arm64_matrix_not_measured",
    },
  },
  capabilities: {
    x64_core_electron_cli_build: {
      status: "blocked",
      blocked_reason: "windows_toolchain_and_target_machine_required",
    },
    current_user_sid_dacl: {
      status: "blocked",
      blocked_reason: "target_machine_sid_dacl_verification_required",
    },
    credential_manager: {
      status: "blocked",
      blocked_reason: "target_machine_credential_manager_verification_required",
    },
    current_user_service: {
      status: "blocked",
      blocked_reason: "target_machine_service_verification_required",
    },
    path_launcher: {
      status: "blocked",
      blocked_reason: "target_machine_path_verification_required",
    },
    unicode_and_spaces: {
      status: "blocked",
      blocked_reason: "target_machine_unicode_path_verification_required",
    },
    junction_reparse: {
      status: "blocked",
      blocked_reason: "target_machine_reparse_point_verification_required",
    },
    open_file_replacement: {
      status: "blocked",
      blocked_reason: "target_machine_upgrade_transaction_required",
    },
    process_lifecycle: {
      status: "blocked",
      blocked_reason: "target_machine_process_identity_verification_required",
    },
    install_upgrade_rollback_uninstall: {
      status: "blocked",
      blocked_reason: "target_machine_lifecycle_verification_required",
    },
    app_cli_shared_runtime: {
      status: "implemented",
      evidence:
        "shared runtime-control layout and same install root are source-contract implemented",
    },
  },
} as const;

export interface WindowsSupportAssessment {
  isSupportedReleaseTarget(platform: NodeJS.Platform, arch: string): boolean;
  blockedReason(platform: NodeJS.Platform, arch: string): string | null;
  canUsePosixOwnerOnlyFallback(platform: NodeJS.Platform): boolean;
  containsReparseMarker(source: string): boolean;
  reparseLikePath(source: string): string | null;
}

/** Pure decision surface so tests can verify fail-closed behavior without Windows. */
export function createWindowsSupportAssessment(): WindowsSupportAssessment {
  return {
    isSupportedReleaseTarget(platform, arch) {
      return false;
    },
    blockedReason(platform, arch) {
      if (platform !== "win32") return null;
      if (arch !== "x64")
        return WINDOWS_RESEARCH_STATE.explicit_matrix.windows_arm64
          .blocked_reason;
      return WINDOWS_RESEARCH_STATE.minimum_release_gate.blocked_reason;
    },
    canUsePosixOwnerOnlyFallback(platform) {
      return platform !== "win32";
    },
    containsReparseMarker: (source) =>
      getNormalizedWindowsPath(source) !== null,
    reparseLikePath: (source) => getNormalizedWindowsPath(source),
  };
}

function getNormalizedWindowsPath(source: string): string | null {
  if (source === "") return null;
  const normalized = path.win32.normalize(source);
  return path.win32.isAbsolute(normalized) ? normalized : null;
}
