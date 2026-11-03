import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";

describe("desktop packaging resources", () => {
  it("writes the required build number into the macOS bundle version", () => {
    const pkg = JSON.parse(
      readFileSync(path.join(process.cwd(), "package.json"), "utf8"),
    ) as { scripts: Record<string, string> };
    expect(pkg.scripts["package:mac:dir"]).toContain(
      "-c.buildVersion=$ONE_MEMORY_BUILD_NUMBER",
    );
    expect(pkg.scripts["package:mac:dir"]).toContain(
      'test -n "$ONE_MEMORY_BUILD_NUMBER"',
    );
    expect(pkg.scripts["package:mac:dir"]).toContain(
      "pnpm --dir ../.. build:core:mac &&",
    );
    expect(pkg.scripts["package:mac:dir"]).toContain(
      "pnpm --dir ../.. --filter @one-memory/web build &&",
    );
    expect(pkg.scripts["package:mac:dir"]).toContain("pnpm build &&");
  });

  it("ships the executable and its complete native runtime at the launch path", () => {
    const pkg = JSON.parse(
      readFileSync(path.join(process.cwd(), "package.json"), "utf8"),
    ) as {
      build: {
        extraResources: Array<{ from: string; to: string }>;
        mac: {
          minimumSystemVersion: string;
          hardenedRuntime: boolean;
          gatekeeperAssess: boolean;
          entitlements: string;
          entitlementsInherit: string;
        };
      };
    };

    const core = pkg.build.extraResources.filter((entry) =>
      entry.from.includes("core/dist/"),
    );
    // Folder builds contain the OS-native executable beside _internal. Copying
    // that folder to core/one-memory would nest the path and break every launch.
    expect(core).toEqual([
      { from: "../core/dist/one-memory-runtime", to: "core" },
    ]);
    expect(pkg.build.extraResources).toContainEqual({
      from: "../../packages/runtime-control/dist",
      to: "runtime",
    });
    expect(pkg.build.extraResources).toContainEqual({
      from: "../cli/dist",
      to: "cli",
    });
    expect(pkg.build.mac).toMatchObject({
      minimumSystemVersion: "13.0",
      hardenedRuntime: true,
      gatekeeperAssess: false,
      entitlements: "entitlements/entitlements.mac.plist",
      entitlementsInherit: "entitlements/entitlements.mac.inherit.plist",
    });
  });

  it("uses the reviewed specification without an embedded private preset", () => {
    const pkg = JSON.parse(
      readFileSync(path.resolve(process.cwd(), "../../package.json"), "utf8"),
    ) as { scripts: Record<string, string> };
    const build = pkg.scripts["build:core:mac"];
    expect(build).toContain("one-memory.spec");
    expect(build).not.toContain("--onefile");
    expect(build).not.toContain("preset:internal");

    const desktop = JSON.parse(
      readFileSync(path.join(process.cwd(), "package.json"), "utf8"),
    ) as { scripts: Record<string, string> };
    expect(desktop.scripts.build).toContain("@one-memory/runtime-control");
    expect(desktop.scripts.build).toContain("@one-memory/cli");
  });
});

const unusedPermissionKeys = [
  ["NS", "BluetoothAlwaysUsageDescription"].join(""),
  ["NS", "BluetoothPeripheralUsageDescription"].join(""),
  ["NS", "CameraUsageDescription"].join(""),
  ["NS", "MicrophoneUsageDescription"].join(""),
  ["NS", "AudioCaptureUsageDescription"].join(""),
];
const audioCaptureKey = unusedPermissionKeys[4];
const bundle = path.join(
  "/private/packaging fixture",
  "One Memory Preview.app",
);
const plistPath = path.join(bundle, "Contents", "Info.plist");
const macContext = {
  electronPlatformName: "darwin",
  appOutDir: path.dirname(bundle),
  packager: { appInfo: { productFilename: "One Memory Preview" } },
};
type AfterPackHook = (context: typeof macContext) => Promise<void>;

function hookFixture(
  keys: readonly string[],
  environment: Record<string, string> = {},
) {
  const plist = new Map([
    ["CFBundleIdentifier", "com.tencent.onememory.preview"],
    ["CFBundleExecutable", "One Memory Preview"],
    ["NSHighResolutionCapable", "true"],
    ...keys.map((key): [string, string] => [
      key,
      "Inherited Electron usage text",
    ]),
  ]);
  const signedSnapshots: Map<string, string>[] = [];
  const execFileSync = vi.fn((command: string, args: string[]) => {
    if (command === "/usr/libexec/PlistBuddy") {
      // The hook must never write a bundled LaunchAgent: the runtime service is
      // the only startup owner. Any path outside Info.plist is a bug.
      expect(args.at(-1)).toBe(plistPath);
      expect(args).toHaveLength(3);
      expect(args[0]).toBe("-c");
      expect(args[2]).toBe(plistPath);
      if (args[1].startsWith("Print :"))
        return plist.get(args[1].slice("Print :".length));
      if (args[1] === "Add :LSEnvironment dict") return;
      if (args[1].startsWith("Add :LSEnvironment:")) {
        const match = /^Add :(.+) string (.+)$/.exec(args[1]);
        if (!match) throw new Error(`Invalid Add command: ${args[1]}`);
        plist.set(match[1], match[2]);
        return;
      }
      if (args[1].startsWith("Set :")) {
        const match = /^Set :(.+) (.+)$/.exec(args[1]);
        if (!match) throw new Error(`Invalid Set command: ${args[1]}`);
        plist.set(match[1], match[2]);
        return;
      }
      expect(args[1]).toMatch(/^Delete :/);
      if (!plist.delete(args[1].slice("Delete :".length))) {
        throw new Error("Entry does not exist");
      }
      return;
    }
    if (command === "/usr/bin/codesign") {
      expect(args).toEqual(["--force", "--deep", "--sign", "-", bundle]);
      signedSnapshots.push(new Map(plist));
      return;
    }
    throw new Error(`Unexpected subprocess: ${command}`);
  });
  const module = { exports: undefined as AfterPackHook | undefined };
  const filename = path.join(process.cwd(), "scripts/after-pack.cjs");
  runInNewContext(
    readFileSync(filename, "utf8"),
    {
      module,
      process: { env: environment },
      require(name: string) {
        if (name === "node:crypto")
          return { randomUUID: () => "00000000-0000-4000-8000-000000000000" };
        if (name === "node:path") return path;
        if (name === "node:child_process") return { execFileSync };
        throw new Error(`Unexpected hook dependency: ${name}`);
      },
    },
    { filename },
  );
  if (typeof module.exports !== "function")
    throw new Error("Missing afterPack hook");
  return {
    hook: module.exports,
    plist,
    execFileSync,
    signedSnapshots,
  };
}

describe("packaged macOS permission metadata", () => {
  it("stamps SemVer separately from the monotonic build number", async () => {
    const fixture = hookFixture([], {
      ONE_MEMORY_VERSION: "1.2.3",
      ONE_MEMORY_BUILD_NUMBER: "3903",
      ONE_MEMORY_COMMIT: "a".repeat(40),
    });

    await fixture.hook(macContext);

    expect(fixture.plist.get("CFBundleShortVersionString")).toBe("1.2.3");
    expect(fixture.plist.get("CFBundleVersion")).toBe("3903");
    expect(fixture.plist.get("LSEnvironment:ONE_MEMORY_VERSION")).toBe("1.2.3");
    expect(fixture.plist.get("LSEnvironment:ONE_MEMORY_BUILD_NUMBER")).toBe(
      "3903",
    );
  });

  it("removes inherited audio capture and existing unused keys before signing", async () => {
    const fixture = hookFixture(unusedPermissionKeys);
    expect(fixture.plist.has(audioCaptureKey)).toBe(true);

    await fixture.hook(macContext);

    expect(fixture.plist.has(audioCaptureKey)).toBe(false);
    expect([...fixture.plist]).toEqual([
      ["CFBundleIdentifier", "com.tencent.onememory.preview"],
      ["CFBundleExecutable", "One Memory Preview"],
      ["NSHighResolutionCapable", "true"],
    ]);
    // Production clears any stale build marker before removing unused usage
    // strings and signing. No LaunchAgent plist is written.
    expect(fixture.execFileSync.mock.calls).toEqual([
      ["/usr/libexec/PlistBuddy", ["-c", "Add :LSEnvironment dict", plistPath]],
      [
        "/usr/libexec/PlistBuddy",
        ["-c", "Delete :LSEnvironment:ONE_MEMORY_VERSION", plistPath],
      ],
      [
        "/usr/libexec/PlistBuddy",
        ["-c", "Delete :LSEnvironment:ONE_MEMORY_BUILD_NUMBER", plistPath],
      ],
      ...unusedPermissionKeys.map((key) => [
        "/usr/libexec/PlistBuddy",
        ["-c", `Delete :${key}`, plistPath],
      ]),
      ["/usr/bin/codesign", ["--force", "--deep", "--sign", "-", bundle]],
    ]);
    expect(fixture.signedSnapshots).toEqual([fixture.plist]);
  });

  it("still removes audio capture when older permission entries are absent", async () => {
    const fixture = hookFixture([audioCaptureKey]);

    await fixture.hook(macContext);

    expect(fixture.plist.has(audioCaptureKey)).toBe(false);
    expect(fixture.signedSnapshots).toEqual([fixture.plist]);
  });

  it("signs older Electron bundles without any of the unused keys", async () => {
    const fixture = hookFixture([]);

    await fixture.hook(macContext);

    expect(fixture.signedSnapshots).toEqual([fixture.plist]);
    expect(fixture.execFileSync).toHaveBeenCalledTimes(
      unusedPermissionKeys.length + 4,
    );
  });

  it("leaves public Developer ID signing to electron-builder", async () => {
    const fixture = hookFixture([], {
      MEMHUB_MAC_SIGNING_MODE: "public",
      ONE_MEMORY_VERSION: "1.2.3",
      ONE_MEMORY_BUILD_NUMBER: "3903",
    });

    await fixture.hook(macContext);

    expect(fixture.signedSnapshots).toEqual([]);
    expect(
      fixture.execFileSync.mock.calls.some(
        ([command]) => command === "/usr/bin/codesign",
      ),
    ).toBe(false);
    expect(fixture.plist.get("CFBundleShortVersionString")).toBe("1.2.3");
    expect(fixture.plist.get("CFBundleVersion")).toBe("3903");
  });

  it.each(["win32", "linux"])(
    "does not invoke macOS commands on %s",
    async (platform) => {
      const fixture = hookFixture(unusedPermissionKeys);
      const original = new Map(fixture.plist);

      await fixture.hook({ ...macContext, electronPlatformName: platform });

      expect(fixture.execFileSync).not.toHaveBeenCalled();
      expect(fixture.plist).toEqual(original);
    },
  );
});

// These are package-shape guards, not Windows installation acceptance. Windows
// still requires a native build and an installed-app verification on Windows.
