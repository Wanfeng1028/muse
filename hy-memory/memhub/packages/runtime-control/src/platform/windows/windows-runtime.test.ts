import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  planWindowsRuntime,
  planWindowsRuntimeControl,
} from "./windows-runtime.js";

function layout(home: string) {
  return {
    platform: "win32" as const,
    home,
    installRoot: "C:\\Users\\Example\\AppData\\Local\\One Memory\\current",
    dataDir: "C:\\Users\\Example\\.one-memory",
    nodeCommand:
      "C:\\Users\\Example\\AppData\\Local\\One Memory\\current\\bin\\node.exe",
    runtimeEntry:
      "C:\\Users\\Example\\AppData\\Local\\One Memory\\current\\runtime\\runtime.cjs",
    coreCommand:
      "C:\\Users\\Example\\AppData\\Local\\One Memory\\current\\core\\one-memory.exe",
    mcpEntryPath:
      "C:\\Users\\Example\\AppData\\Local\\One Memory\\current\\host-bridge\\mcp.cjs",
    recallCliPath:
      "C:\\Users\\Example\\AppData\\Local\\One Memory\\current\\host-bridge\\recall-cli.cjs",
    syncHookAssetsDirectory:
      "C:\\Users\\Example\\AppData\\Local\\One Memory\\current\\host-bridge\\sync-hook",
  };
}

describe("Windows runtime control matrix", () => {
  it("never publishes a service plan before the real-machine ACL matrix passes", () => {
    const plan = planWindowsRuntime(layout("C:\\Users\\Example"));
    expect(plan).toMatchObject({
      status: "blocked",
      blocked_reason: "windows_acl_and_user_service_not_verified",
      service_file: null,
    });
    expect(Object.values(plan.commands).flat()).toEqual([]);
  });

  it("reports the target-machine capabilities that gate every Windows action", () => {
    const plan = planWindowsRuntimeControl({
      home: "C:\\Users\\Example",
      installRoot: "C:\\Users\\Example\\AppData\\Local\\One Memory\\current",
      host: { windowsPowerShell: true, currentUserDataRoot: true },
    });
    expect(plan.platform).toBe("win32");
    expect(plan.capabilities).toEqual({
      windows_power_shell: "available",
      current_user_data_root: "available",
    });
    expect(plan.blocked_reason).toBe(
      "windows_acl_and_user_service_not_verified",
    );
  });

  it("builds a Windows layout with spaced install roots without changing semantics", () => {
    const plan = planWindowsRuntimeControl({
      home: "C:\\Users\\张三",
      installRoot:
        "C:\\Users\\张三\\AppData\\Local\\One Memory With Spaces\\current",
      host: { windowsPowerShell: false, currentUserDataRoot: false },
    });
    expect(path.win32.isAbsolute(plan.current_user_service.service_id)).toBe(
      false,
    );
    expect(plan.capabilities.current_user_data_root).toBe("unavailable");
  });
});
