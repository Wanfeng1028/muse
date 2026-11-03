import { describe, expect, it } from "vitest";

import {
  canonicalManagedServiceRoot,
  defaultManagedInstallRoot,
  hourlyIsolationFromEnvironment,
  isIsolatedHourlyInstall,
  planUserService,
  priorLaunchAgentDeclarations,
  runtimeInstallLayout,
  stableRuntimeInstallRoot,
} from "./service-plan.js";

describe("user service plans", () => {
  it("keeps the host install root at current for every platform", () => {
    expect(stableRuntimeInstallRoot("darwin", "/Users/example")).toBe(
      "/Users/example/Library/Application Support/One Memory/current",
    );
    expect(stableRuntimeInstallRoot("linux", "/home/example")).toBe(
      "/home/example/.local/share/one-memory/current",
    );
    expect(stableRuntimeInstallRoot("win32", "C:\\Users\\Example")).toBe(
      "C:\\Users\\Example\\AppData\\Local\\One Memory\\current",
    );
    expect(defaultManagedInstallRoot("linux", "/home/example")).toBe(
      "/home/example/.local/share/one-memory",
    );
  });

  it("preserves an explicitly selected data instance independently from login home", () => {
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home: "/Users/example",
      installRoot: "/opt/one-memory/current",
      dataDir: "/Users/example/Private Memory",
    });
    expect(layout.dataDir).toBe("/Users/example/Private Memory");
    const plan = planUserService(layout, { uid: 501 });
    expect(plan.service_file?.content).toContain(
      "<key>ONE_MEMORY_DATA_DIR</key><string>/Users/example/Private Memory</string>",
    );
    // A login start must have a real place to write, and it must belong to the
    // same data instance rather than the daily home. The Runtime -- not launchd
    // -- owns that file so it can bound and rotate it; see the H34 ruling. A
    // launchd-held descriptor cannot be rotated.
    expect(plan.log_directory).toBe("/Users/example/Private Memory/logs");
    expect(plan.service_file?.content).not.toContain(
      "<key>StandardOutPath</key>",
    );
    expect(plan.service_file?.content).not.toContain(
      "<key>StandardErrorPath</key>",
    );
  });

  it.each(["", "relative/path", "/tmp/bad\npath", "/tmp/bad\0path"])(
    "rejects ambiguous explicit data paths %j",
    (dataDir) => {
      expect(() =>
        runtimeInstallLayout({
          platform: "darwin",
          home: "/Users/example",
          installRoot: "/opt/one-memory/current",
          dataDir,
        }),
      ).toThrow("runtime_service_data_directory_invalid");
    },
  );
  it("carries an isolated Broker port into the service environment", () => {
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home: "/Users/example",
      installRoot: "/tmp/memhub-test/current",
      corePort: 9301,
      brokerPort: 19301,
    });
    const content = planUserService(layout, { uid: 501 }).service_file?.content;
    expect(content).toContain(
      "<key>ONE_MEMORY_BROKER_PORT</key><string>19301</string>",
    );
  });
  it("keeps the canonical label for the daily install root", () => {
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home: "/Users/example",
      installRoot:
        "/Users/example/Library/Application Support/One Memory/current",
    });
    const plan = planUserService(layout, { uid: 501 });

    expect(plan.status).toBe("ready");
    expect(plan.service_file?.path).toBe(
      "/Users/example/Library/LaunchAgents/com.tencent.onememory.runtime.plist",
    );
    expect(plan.service_id).toBe("com.tencent.onememory.runtime");
    expect(plan.commands.restart[0]).toEqual([
      "launchctl",
      "kickstart",
      "-k",
      "gui/501/com.tencent.onememory.runtime",
    ]);
    expect(plan.service_file?.content).toContain(
      "<key>KeepAlive</key><dict><key>PathState</key>",
    );
    expect(plan.service_file?.content).toContain(
      "<key>/Users/example/.one-memory/runtime-service.enabled</key><true/>",
    );
  });

  it("keeps the durable Runtime out of launchd Background QoS", () => {
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home: "/Users/example",
      installRoot:
        "/Users/example/Library/Application Support/One Memory/current",
    });
    const content = planUserService(layout, { uid: 501 }).service_file?.content;
    // A frozen Core marked Background can be throttled before it binds its
    // loopback port; the Runtime then never reaches ready even though the Core
    // process is alive. Keep this service at normal user priority.
    expect(content).toContain(
      "<key>ProcessType</key><string>Interactive</string>",
    );
    expect(content).not.toContain(
      "<key>ProcessType</key><string>Background</string>",
    );
  });

  it("scopes an isolated install root to its own label so it cannot collide", () => {
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home: "/Users/A & B",
      installRoot: "/Users/A & B/.local/share/one-memory/current",
    });
    const plan = planUserService(layout, { uid: 501 });

    expect(plan.status).toBe("ready");
    expect(plan.service_id).toMatch(
      /^com\.tencent\.onememory\.runtime\.[a-f0-9]{16}$/,
    );
    expect(plan.service_file?.path).toBe(
      `/Users/A & B/Library/LaunchAgents/${plan.service_id}.plist`,
    );
    expect(plan.service_file?.content).toContain("&amp;");
    expect(plan.service_file?.content).not.toContain("<key>RunAtLoad</key>");
    expect(plan.commands.install[0]).toEqual([
      "launchctl",
      "bootstrap",
      "gui/501",
      plan.service_file?.path,
    ]);
    expect(plan.commands.stop[0]).toEqual([
      "launchctl",
      "bootout",
      "gui/501",
      plan.service_file?.path,
    ]);
    expect(plan.commands.restart[0]).toEqual([
      "launchctl",
      "kickstart",
      "-k",
      `gui/501/${plan.service_id}`,
    ]);
  });

  it("derives one label whether the caller names the root or its current link", () => {
    const root =
      "/Users/example/Library/Application Support/One Memory Hourly/managed-runtime";
    const fromRoot = planUserService(
      runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: root,
      }),
      { uid: 501 },
    );
    const fromCurrent = planUserService(
      runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: `${root}/current`,
      }),
      { uid: 501 },
    );
    // `install` passes the `current` link; `uninstall`/`upgrade` pass the root.
    // If these disagreed, an install would be invisible to its own uninstall.
    expect(fromCurrent.service_id).toBe(fromRoot.service_id);
    expect(fromCurrent.service_file?.path).toBe(fromRoot.service_file?.path);
  });

  it("canonicalizes macOS filesystem aliases before deriving a service identity", () => {
    if (process.platform !== "darwin") return;
    const lexicalRoot = "/tmp/one-memory-missing-service-root";
    const physicalRoot = "/private/tmp/one-memory-missing-service-root";

    expect(canonicalManagedServiceRoot("darwin", lexicalRoot)).toBe(
      `${physicalRoot}/current`,
    );
    const lexical = planUserService(
      runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: lexicalRoot,
      }),
      { uid: 501 },
    );
    const physical = planUserService(
      runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: `${physicalRoot}/current`,
      }),
      { uid: 501 },
    );

    expect(lexical.service_id).toBe(physical.service_id);
    expect(lexical.service_file?.content).toBe(physical.service_file?.content);
  });

  it("renders a user-scoped Linux systemd service with exact resource paths", () => {
    const layout = runtimeInstallLayout({
      platform: "linux",
      home: "/home/example",
      installRoot: "/home/example/.local/share/one memory/current",
    });
    const plan = planUserService(layout);

    expect(plan.status).toBe("ready");
    expect(plan.service_file?.path).toBe(
      "/home/example/.config/systemd/user/one-memory.service",
    );
    expect(plan.service_file?.content).toContain("UMask=0077");
    expect(plan.service_file?.content).toContain(
      'ExecStart="/home/example/.local/share/one memory/current/bin/node"',
    );
    expect(plan.commands.install).toEqual([
      ["systemctl", "--user", "daemon-reload"],
      [
        "systemctl",
        "--user",
        "enable",
        "--now",
        "/home/example/.config/systemd/user/one-memory.service",
      ],
    ]);
    expect(plan.commands.restart).toEqual([
      ["systemctl", "--user", "restart", "one-memory.service"],
    ]);
    expect(plan.service_file?.content).toContain(
      'Environment="ONE_MEMORY_DATA_DIR=/home/example/.one-memory"',
    );
    expect(plan.service_file?.content).toContain(
      'Environment="HOME=/home/example"',
    );
  });

  it("keeps Windows blocked until user ACL and service semantics are verified", () => {
    const plan = planUserService(
      runtimeInstallLayout({
        platform: "win32",
        home: "C:\\Users\\Example",
        installRoot: "C:\\Users\\Example\\One Memory",
      }),
    );

    expect(plan).toMatchObject({
      status: "blocked",
      blocked_reason: "windows_acl_and_user_service_not_verified",
      service_file: null,
    });
    expect(plan.commands.install).toEqual([]);
  });

  it("requires an explicit uid before producing launchctl commands", () => {
    const plan = planUserService(
      runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: "/opt/one-memory",
      }),
    );

    expect(plan.status).toBe("blocked");
    expect(plan.blocked_reason).toBe("macos_user_id_required");
  });

  describe("isolated hourly installs", () => {
    const INSTANCE = "3f1c2b4a-5d6e-4f70-8a9b-0c1d2e3f4a5b";

    it("partitions the managed install root by package id", () => {
      const a = stableRuntimeInstallRoot(
        "darwin",
        "/Users/example",
        undefined,
        true,
        "One-Memory-H08-aaaaaaa-c7-isolated",
      );
      const b = stableRuntimeInstallRoot(
        "darwin",
        "/Users/example",
        undefined,
        true,
        "One-Memory-H09-bbbbbbb-c7-isolated",
      );
      // Two hourly packages must never share one `current` link.
      expect(a).not.toBe(b);
      expect(a).toBe(
        "/Users/example/Library/Application Support/One Memory Hourly/One-Memory-H08-aaaaaaa-c7-isolated/managed-runtime/current",
      );
      // The daily path is unchanged.
      expect(stableRuntimeInstallRoot("darwin", "/Users/example")).toBe(
        "/Users/example/Library/Application Support/One Memory/current",
      );
    });

    it("derives a distinct LaunchAgent label per package root", () => {
      const planA = planUserService(
        runtimeInstallLayout({
          platform: "darwin",
          home: "/Users/example",
          installRoot: stableRuntimeInstallRoot(
            "darwin",
            "/Users/example",
            undefined,
            true,
            "One-Memory-H08-aaaaaaa-c7-isolated",
          ),
          hourlyInstanceId: INSTANCE,
          hourlyPackageId: "One-Memory-H08-aaaaaaa-c7-isolated",
        }),
        { uid: 501 },
      );
      const planB = planUserService(
        runtimeInstallLayout({
          platform: "darwin",
          home: "/Users/example",
          installRoot: stableRuntimeInstallRoot(
            "darwin",
            "/Users/example",
            undefined,
            true,
            "One-Memory-H09-bbbbbbb-c7-isolated",
          ),
          hourlyInstanceId: INSTANCE,
          hourlyPackageId: "One-Memory-H09-bbbbbbb-c7-isolated",
        }),
        { uid: 501 },
      );
      expect(planA.service_id).not.toBe(planB.service_id);
      expect(planA.service_id).not.toBe("com.tencent.onememory.runtime");
    });

    it("writes the three isolation keys into the plist only for hourly installs", () => {
      const hourly = planUserService(
        runtimeInstallLayout({
          platform: "darwin",
          home: "/Users/example",
          installRoot: "/opt/hourly/current",
          hourlyInstanceId: INSTANCE,
          hourlyPackageId: "One-Memory-H08-aaaaaaa-c7-isolated",
          corePort: 9311,
        }),
        { uid: 501 },
      );
      const content = hourly.service_file?.content ?? "";
      // Without these three keys launchd's Runtime never sees the markers, so
      // the port override silently does nothing for an installed service.
      expect(content).toContain(
        "<key>ONE_MEMORY_CORE_PORT</key><string>9311</string>",
      );
      expect(content).toContain(
        `<key>ONE_MEMORY_HOURLY_INSTANCE_ID</key><string>${INSTANCE}</string>`,
      );
      expect(content).toContain(
        "<key>ONE_MEMORY_HOURLY_PACKAGE_ID</key><string>One-Memory-H08-aaaaaaa-c7-isolated</string>",
      );
    });

    it("leaves the daily plist with no hourly keys and no port override", () => {
      const daily = planUserService(
        runtimeInstallLayout({
          platform: "darwin",
          home: "/Users/example",
          installRoot:
            "/Users/example/Library/Application Support/One Memory/current",
        }),
        { uid: 501 },
      );
      const content = daily.service_file?.content ?? "";
      expect(content).not.toContain("ONE_MEMORY_CORE_PORT");
      expect(content).not.toContain("ONE_MEMORY_HOURLY_INSTANCE_ID");
      expect(content).not.toContain("ONE_MEMORY_HOURLY_PACKAGE_ID");
    });

    it("ignores partial or forged markers and falls back to the daily shape", () => {
      // A UUID alone, or a package id with the wrong suffix, is not isolation.
      expect(
        isIsolatedHourlyInstall({ instanceId: INSTANCE, packageId: undefined }),
      ).toBe(false);
      expect(
        isIsolatedHourlyInstall({
          instanceId: "not-a-uuid",
          packageId: "One-Memory-H08-aaaaaaa-c7-isolated",
        }),
      ).toBe(false);
      expect(
        isIsolatedHourlyInstall({
          instanceId: INSTANCE,
          packageId: "One-Memory-H08-aaaaaaa-candidate",
        }),
      ).toBe(false);
      const layout = runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: "/opt/daily/current",
        hourlyInstanceId: INSTANCE,
        hourlyPackageId: "guessed",
      });
      expect(layout.hourlyIsolation).toBeUndefined();
    });

    it("rejects a package id that would escape the managed root", () => {
      expect(() =>
        defaultManagedInstallRoot(
          "darwin",
          "/Users/example",
          undefined,
          true,
          "../../escape",
        ),
      ).toThrow("runtime_service_hourly_package_id_invalid");
    });

    it("rejects an out-of-range core port", () => {
      expect(() =>
        runtimeInstallLayout({
          platform: "darwin",
          home: "/Users/example",
          installRoot: "/opt/hourly/current",
          hourlyInstanceId: INSTANCE,
          hourlyPackageId: "One-Memory-H08-aaaaaaa-c7-isolated",
          corePort: 70000,
        }),
      ).toThrow("runtime_service_core_port_invalid");
    });

    it("accepts the new declaration as migratable so an upgrade is not read as a user edit", () => {
      const layout = runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: "/opt/hourly/current",
        hourlyInstanceId: INSTANCE,
        hourlyPackageId: "One-Memory-H08-aaaaaaa-c7-isolated",
        corePort: 9311,
      });
      const plan = planUserService(layout, { uid: 501 });
      const prior = priorLaunchAgentDeclarations(layout);
      // The migration check compares the on-disk bytes against these shapes.
      // Adding plist keys changes the current bytes, so the current shape must
      // be in the accepted set or every existing install fails closed on
      // upgrade with `runtime_service_file_modified`.
      expect(prior).toContain(plan.service_file?.content);
      expect(prior[0]).toBe(plan.service_file?.content);
      expect(prior[1]).toContain(
        "<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>",
      );
    });

    it("reads the two markers out of the installer environment", () => {
      const both = hourlyIsolationFromEnvironment({
        ONE_MEMORY_HOURLY_INSTANCE_ID: INSTANCE,
        ONE_MEMORY_HOURLY_PACKAGE_ID: "One-Memory-H08-aaaaaaa-c7-isolated",
      });
      expect(both).toEqual({
        hourlyInstanceId: INSTANCE,
        hourlyPackageId: "One-Memory-H08-aaaaaaa-c7-isolated",
      });
      // Partial or malformed pairs must not move the daily install.
      expect(
        hourlyIsolationFromEnvironment({
          ONE_MEMORY_HOURLY_INSTANCE_ID: INSTANCE,
        }),
      ).toEqual({});
      expect(
        hourlyIsolationFromEnvironment({
          ONE_MEMORY_HOURLY_PACKAGE_ID: "One-Memory-H08-aaaaaaa-c7-isolated",
        }),
      ).toEqual({});
      expect(
        hourlyIsolationFromEnvironment({
          ONE_MEMORY_HOURLY_INSTANCE_ID: INSTANCE,
          ONE_MEMORY_HOURLY_PACKAGE_ID: "One-Memory-H08-aaaaaaa-candidate",
        }),
      ).toEqual({});
      expect(hourlyIsolationFromEnvironment({})).toEqual({});
    });

    it("gives each hourly package its own data directory", () => {
      const a = runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: "/opt/hourly/A/current",
        hourlyInstanceId: INSTANCE,
        hourlyPackageId: "One-Memory-H08-aaaaaaa-c7-isolated",
      });
      const b = runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: "/opt/hourly/B/current",
        hourlyInstanceId: INSTANCE,
        hourlyPackageId: "One-Memory-H09-bbbbbbb-c7-isolated",
      });
      // Two hourly packages must not share `runtime-token` / `runtime.json`.
      expect(a.dataDir).not.toBe(b.dataDir);
      expect(a.dataDir).toBe(
        "/Users/example/.one-memory-hourly/One-Memory-H08-aaaaaaa-c7-isolated",
      );
      // The daily install keeps the historical data directory.
      const daily = runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot:
          "/Users/example/Library/Application Support/One Memory/current",
      });
      expect(daily.dataDir).toBe("/Users/example/.one-memory");
    });

    it("puts the derived port and both markers into the isolated plist", () => {
      const layout = runtimeInstallLayout({
        platform: "darwin",
        home: "/Users/example",
        installRoot: stableRuntimeInstallRoot(
          "darwin",
          "/Users/example",
          undefined,
          true,
          "One-Memory-H08-aaaaaaa-c7-isolated",
        ),
        hourlyInstanceId: INSTANCE,
        hourlyPackageId: "One-Memory-H08-aaaaaaa-c7-isolated",
      });
      const content =
        planUserService(layout, { uid: 501 }).service_file?.content ?? "";
      expect(content).toContain("<key>ONE_MEMORY_HOURLY_INSTANCE_ID</key>");
      expect(content).toContain(
        "<key>ONE_MEMORY_HOURLY_PACKAGE_ID</key><string>One-Memory-H08-aaaaaaa-c7-isolated</string>",
      );
      expect(content).toContain("<key>ONE_MEMORY_CORE_PORT</key>");
      // The derived port must match the one the plan reports for this root.
      const plan = planUserService(layout, { uid: 501 });
      expect(plan.service_id).not.toBe("com.tencent.onememory.runtime");
    });
  });
});
