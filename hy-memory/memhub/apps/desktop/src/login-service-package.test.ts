import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { runInNewContext } from "node:vm";
import { expect, it, vi } from "vitest";

it.skipIf(process.platform !== "darwin")(
  "does not ship a bundled LaunchAgent and still strips unused permissions before signing",
  async () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "om-login-package-"));
    try {
      const bundle = path.join(root, "One Memory Preview.app");
      const contents = path.join(bundle, "Contents");
      mkdirSync(contents, { recursive: true });
      const info = path.join(contents, "Info.plist");
      execFileSync("/usr/libexec/PlistBuddy", [
        "-c",
        "Clear dict",
        "-c",
        "Add :CFBundleExecutable string 'One Memory Preview'",
        "-c",
        "Add :CFBundleIdentifier string com.tencent.onememory.preview",
        info,
      ]);
      const service = path.join(
        contents,
        "Library",
        "LaunchAgents",
        "one-memory-background.plist",
      );
      // The runtime service is the only startup owner. A
      // bundled `Contents/Library/LaunchAgents/...plist` with `RunAtLoad` must
      // not ship; launchd never scans that directory anyway, so it was dead
      // weight that also looked like a second startup registration.
      const sign = vi.fn(() => expect(existsSync(service)).toBe(false));
      const module = {
        exports: undefined as undefined | ((context: unknown) => Promise<void>),
      };
      runInNewContext(
        readFileSync(
          path.join(process.cwd(), "scripts/after-pack.cjs"),
          "utf8",
        ),
        {
          module,
          process: { env: {} },
          require(name: string) {
            if (name === "node:crypto")
              return {
                randomUUID: () => "00000000-0000-4000-8000-000000000000",
              };
            if (name === "node:path") return path;
            if (name === "node:child_process")
              return {
                execFileSync(
                  command: string,
                  args: string[],
                  options?: object,
                ) {
                  if (command === "/usr/bin/codesign") return sign();
                  if (command !== "/usr/libexec/PlistBuddy")
                    throw new Error("Unexpected subprocess");
                  return execFileSync(command, args, {
                    ...options,
                    stdio: ["ignore", "pipe", "pipe"],
                  });
                },
              };
            throw new Error("Unexpected dependency");
          },
        },
      );
      await module.exports?.({
        electronPlatformName: "darwin",
        appOutDir: root,
        packager: { appInfo: { productFilename: "One Memory Preview" } },
      });
      expect(existsSync(service)).toBe(false);
      // The unused-usage-string cleanup is the script's real job and must stay.
      const keys = execFileSync(
        "/usr/libexec/PlistBuddy",
        ["-c", "Print", info],
        { encoding: "utf8" },
      );
      expect(keys).not.toContain("BluetoothAlwaysUsageDescription");
      expect(sign).toHaveBeenCalledTimes(1);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  },
);
