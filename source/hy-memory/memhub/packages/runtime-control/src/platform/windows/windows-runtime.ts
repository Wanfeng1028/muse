import {
  type RuntimeInstallLayout,
  type RuntimeServicePlan,
  runtimeInstallLayout,
} from "../../service-plan.js";

export type WindowsCapabilityStatus = "available" | "unavailable" | "unknown";

export interface WindowsHostCapabilities {
  /** Windows PowerShell 5.1 is present on every supported desktop release. */
  windowsPowerShell: boolean;
  /** The process can read and write the current user's SID-secured data root. */
  currentUserDataRoot: boolean;
}

export interface WindowsRuntimeControlPlan {
  schema_version: 1;
  platform: "win32";
  capabilities: {
    windows_power_shell: WindowsCapabilityStatus;
    current_user_data_root: WindowsCapabilityStatus;
  };
  blocked_reason: string | null;
  /**
   * Windows remains blocked until the real-machine SID/DACL and service
   * matrix passes. This planner may only describe the task that would run;
   * it never claims the mechanism is verified.
   */
  current_user_service: RuntimeServicePlan;
}

export function planWindowsRuntimeControl(input: {
  home: string;
  installRoot: string;
  dataDir?: string;
  localAppData?: string;
  host: WindowsHostCapabilities;
}): WindowsRuntimeControlPlan {
  const layout = runtimeInstallLayout({
    platform: "win32",
    home: input.home,
    installRoot: input.installRoot,
    dataDir: input.dataDir,
  });
  const runtime = planWindowsRuntime(layout);
  const capabilities = {
    windows_power_shell: input.host.windowsPowerShell
      ? ("available" as const)
      : ("unavailable" as const),
    current_user_data_root: input.host.currentUserDataRoot
      ? ("available" as const)
      : ("unavailable" as const),
  };
  return {
    schema_version: 1,
    platform: "win32",
    capabilities,
    blocked_reason: runtime.blocked_reason,
    current_user_service: runtime,
  };
}

export function planWindowsRuntime(
  layout: RuntimeInstallLayout,
): RuntimeServicePlan {
  if (layout.platform !== "win32")
    throw new Error("windows_plan_platform_mismatch");
  return {
    schema_version: 1,
    platform: "win32",
    scope: "user",
    service_id: "One Memory Runtime",
    status: "blocked",
    blocked_reason: "windows_acl_and_user_service_not_verified",
    core_port: null,
    service_file: null,
    log_directory: null,
    commands: {
      install: [],
      start: [],
      restart: [],
      stop: [],
      uninstall: [],
    },
  };
}

export type { RuntimeInstallLayout };
