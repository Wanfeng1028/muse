import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const script = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "verify-linux-support.mjs",
);

describe("Linux support matrix", () => {
  it("reports explicit blocked status until a Linux runtime is available", () => {
    const result = spawnSync(process.execPath, [script], { encoding: "utf8" });
    expect(result.error).toBeUndefined();
    const matrix = JSON.parse(result.stdout);
    expect(matrix.status).toMatchObject({
      x64_build: "blocked",
      arm64_build: "blocked",
      x64_systemd_user: "blocked",
      arm64_systemd_user: "blocked",
      no_systemd_serve: "blocked",
    });
    expect(matrix.capabilities).toHaveProperty("systemd_user");
    expect(matrix.conditions_to_unblock).toContain(
      "linux_x64_arm64_runtime_or_runner",
    );
  });
});
