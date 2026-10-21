import { readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { describe, expect, it, vi } from "vitest";

/**
 * A Finder double-click carries no shell environment, so the hourly package's
 * diagnostic identity has to be baked into `LSEnvironment` at pack time. The
 * shipped dist launcher stamps these for CLI/LaunchAgent starts, but the App
 * spawns its Runtime directly and never runs that launcher: without this the
 * four-level chain reports `unknown:no-identity` (C6/C8 EXEC-1914).
 *
 * This fixture drives the real `after-pack.cjs` in its hourly branch with a
 * PlistBuddy stand-in that understands the multi-`-c` invocation the hook uses.
 */
const BUNDLE = path.join("/tmp", "hook-fixture", "MemHub.app");
const PLIST = path.join(BUNDLE, "Contents", "Info.plist");
const context = {
  electronPlatformName: "darwin",
  appOutDir: path.dirname(BUNDLE),
  packager: { appInfo: { productFilename: "MemHub", version: "0.0.0" } },
};

function runHook(env: Record<string, string>) {
  const plist = new Map<string, string>([
    ["CFBundleIdentifier", "com.tencent.onememory"],
    ["MallocNanoZone", "0"],
  ]);
  const execFileSync = vi.fn((command: string, args: string[]) => {
    if (command === "/usr/libexec/PlistBuddy") {
      expect(args.at(-1)).toBe(PLIST);
      for (let index = 0; index < args.length - 1; index += 2) {
        expect(args[index]).toBe("-c");
        const command_ = args[index + 1];
        if (command_ === "Delete :LSEnvironment") {
          // Absent on a fresh pack.
          continue;
        }
        if (command_ === "Add :LSEnvironment dict") continue;
        const add = /^Add :LSEnvironment:(\w+) string (.+)$/.exec(command_);
        if (add) {
          plist.set(add[1], add[2]);
          continue;
        }
        if (command_.startsWith("Delete :")) {
          plist.delete(command_.slice("Delete :".length));
          continue;
        }
        const set = /^Set :(.+) (.+)$/.exec(command_);
        if (set) {
          plist.set(set[1], set[2]);
          continue;
        }
        throw new Error(`Unexpected PlistBuddy command: ${command_}`);
      }
      return;
    }
    if (command === "/usr/bin/codesign") return;
    throw new Error(`Unexpected subprocess: ${command}`);
  });
  const module_ = {
    exports: undefined as ((c: typeof context) => Promise<void>) | undefined,
  };

  // The hook reads `process.env`; give the VM the env under test.
  const previous = process.env;
  const sandboxProcess = { env: { ...previous, ...env } };
  vm.runInNewContext(
    readFileSync(path.join(process.cwd(), "scripts/after-pack.cjs"), "utf8"),
    {
      module: module_,
      process: sandboxProcess,
      require(name: string) {
        if (name === "node:path") return path;
        if (name === "node:crypto")
          return {
            randomUUID: () => "11111111-2222-4333-8444-555555555555",
          };
        if (name === "node:child_process") return { execFileSync };
        throw new Error(`Unexpected hook dependency: ${name}`);
      },
    },
    { filename: "after-pack.cjs" },
  );
  if (!module_.exports) throw new Error("after-pack hook was not exported");
  return { hook: module_.exports, plist, execFileSync };
}

describe("hourly diagnostic identity stamping", () => {
  it("stamps a numeric build number into production without hourly identity", async () => {
    const fixture = runHook({ ONE_MEMORY_BUILD_NUMBER: "3762" });

    await fixture.hook(context);

    expect(fixture.plist.get("ONE_MEMORY_BUILD_NUMBER")).toBe("3762");
    expect(fixture.plist.get("CFBundleShortVersionString")).toBe("0.0.0");
    expect(fixture.plist.get("CFBundleVersion")).toBe("3762");
    expect(fixture.plist.get("MallocNanoZone")).toBe("0");
    expect(fixture.plist.has("ONE_MEMORY_HOURLY_INSTANCE_ID")).toBe(false);
    expect(fixture.plist.has("ONE_MEMORY_HOURLY_PACKAGE_ID")).toBe(false);
    expect(fixture.plist.has("ONE_MEMORY_PACKAGE_ID")).toBe(false);
    expect(fixture.plist.has("ONE_MEMORY_ROUND")).toBe(false);
  });

  it.each([undefined, "", "v3762"])(
    "leaves a production build number absent for %j",
    async (buildNumber) => {
      const fixture = runHook({
        ...(buildNumber === undefined
          ? {}
          : { ONE_MEMORY_BUILD_NUMBER: buildNumber }),
      });

      await fixture.hook(context);

      expect(fixture.plist.has("ONE_MEMORY_BUILD_NUMBER")).toBe(false);
      expect(fixture.plist.get("MallocNanoZone")).toBe("0");
      expect(fixture.plist.has("ONE_MEMORY_HOURLY_PACKAGE_ID")).toBe(false);
    },
  );

  it("bakes build/package/round together with the isolation markers", async () => {
    const fixture = runHook({
      ONE_MEMORY_HOURLY_PACKAGE: "1",
      ONE_MEMORY_HOURLY_PACKAGE_ID: "One-Memory-HAPP1R4-c8qa-73d593d-candidate",
      ONE_MEMORY_ROUND: "101",
    });

    await fixture.hook(context);

    expect(fixture.plist.get("ONE_MEMORY_HOURLY_PACKAGE_ID")).toBe(
      "One-Memory-HAPP1R4-c8qa-73d593d-candidate",
    );
    // The three fields the shared DiagnosticLogger copies onto every event.
    expect(fixture.plist.get("ONE_MEMORY_BUILD_ID")).toBe(
      "One-Memory-HAPP1R4-c8qa-73d593d-candidate",
    );
    expect(fixture.plist.get("ONE_MEMORY_PACKAGE_ID")).toBe(
      "One-Memory-HAPP1R4-c8qa-73d593d-candidate",
    );
    expect(fixture.plist.get("ONE_MEMORY_ROUND")).toBe("101");
  });

  it("leaves round absent rather than inventing one", async () => {
    const fixture = runHook({
      ONE_MEMORY_HOURLY_PACKAGE: "1",
      ONE_MEMORY_HOURLY_PACKAGE_ID: "One-Memory-HAPP1R4-c8qa-73d593d-candidate",
    });

    await fixture.hook(context);

    expect(fixture.plist.get("ONE_MEMORY_PACKAGE_ID")).toBe(
      "One-Memory-HAPP1R4-c8qa-73d593d-candidate",
    );
    expect(fixture.plist.has("ONE_MEMORY_ROUND")).toBe(false);
    // A build number must never be invented either: absent means the App keeps
    // the installer's default rather than fabricating an ordering claim.
    expect(fixture.plist.has("ONE_MEMORY_BUILD_NUMBER")).toBe(false);
  });

  it("bakes the monotonic build number into the isolated environment", async () => {
    // Anti-downgrade compares `build_number` alone; without it baked the
    // Finder-launched isolated App installs at 0 and R->R.1 is refused.
    const fixture = runHook({
      ONE_MEMORY_HOURLY_PACKAGE: "1",
      ONE_MEMORY_HOURLY_PACKAGE_ID: "One-Memory-HAPP1R5.1-c10f9c8-candidate",
      ONE_MEMORY_ROUND: "101",
      ONE_MEMORY_BUILD_NUMBER: "3653",
    });

    await fixture.hook(context);

    expect(fixture.plist.get("ONE_MEMORY_BUILD_NUMBER")).toBe("3653");
  });

  it("refuses a non-numeric build number instead of baking it", async () => {
    const fixture = runHook({
      ONE_MEMORY_HOURLY_PACKAGE: "1",
      ONE_MEMORY_HOURLY_PACKAGE_ID: "One-Memory-HAPP1R5.1-c10f9c8-candidate",
      ONE_MEMORY_BUILD_NUMBER: "v3653",
    });

    await fixture.hook(context);

    expect(fixture.plist.has("ONE_MEMORY_BUILD_NUMBER")).toBe(false);
  });
});
