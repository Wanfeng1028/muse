import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const script = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "verify-windows-support.mjs",
);

describe("Windows support matrix", () => {
  it("reports explicit blocked status until a Windows 11 x64 target is available", () => {
    const result = spawnSync(process.execPath, [script], { encoding: "utf8" });
    expect(result.error).toBeUndefined();
    const matrix = JSON.parse(result.stdout);
    expect(matrix.release_gate).toEqual({
      os: "Windows 11",
      arch: "x64",
      status: "blocked",
      blocked_reason: "windows_target_machine_required",
    });
    expect(matrix.explicit_matrix).toEqual({
      windows_11_x64: "blocked",
      windows_10_x64: "blocked",
      windows_arm64: "blocked",
    });
    expect(matrix.capabilities.app_cli_shared_runtime).toBe("implemented");
    expect(matrix.capabilities.current_user_sid_dacl).toBe("blocked");
    expect(matrix.conditions_to_unblock).toContain(
      "windows_11_x64_target_machine_or_runner",
    );
  });

  // Fail-closed gate: the process exit code must agree with the matrix, not be
  // a constant 0. A release job that only checks step success must fail while
  // the platform is blocked. Removing the `process.exitCode = ...` line in the
  // script makes this test go red.
  it("exits non-zero while the Windows release gate is blocked", () => {
    const result = spawnSync(process.execPath, [script], { encoding: "utf8" });
    const matrix = JSON.parse(result.stdout);
    expect(matrix.release_gate.status).toBe("blocked");
    expect(result.status).not.toBe(0);
  });
});
