import { createHash } from "node:crypto";
import {
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readHostCredentialFile } from "@one-memory/host-bridge";
import {
  claudeCodeLayout,
  cursorLayout,
} from "@one-memory/host-bridge/installer";
import { afterEach, describe, expect, expectTypeOf, it, vi } from "vitest";
import type {
  ApplySyncHookInput as WebInput,
  SyncHookPreview as WebPreview,
  SyncHookStatus as WebStatus,
} from "../../web/src/global";
import { HostPermissions } from "./host-permissions";
import type {
  ApplySyncHookInput,
  SyncHookPreview,
  SyncHookStatus,
} from "./sync-hook";

vi.mock("../../../packages/host-bridge/src/recall-probe.js", () => ({
  probeRecallInstall: vi.fn(async () => ({
    state: "reachable_but_blind",
    detail: "isolated fixture",
    probedAt: new Date(0).toISOString(),
  })),
}));
const roots: string[] = [];
function required<T>(value: T | null | undefined): T {
  if (value === null || value === undefined)
    throw new Error("missing_fixture_value");
  return value;
}
const hash = (v: string) => createHash("sha256").update(v).digest("hex");
afterEach(async () => {
  for (const root of roots.splice(0))
    await rm(root, { recursive: true, force: true });
});
async function fixture() {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "om-host-hook-")),
  );
  roots.push(root);
  const data = path.join(root, "data"),
    host = path.join(root, "claude"),
    assets = path.join(root, "assets");
  for (const dir of [data, host, assets]) await mkdir(dir, { mode: 0o700 });
  const runtimeCommand = path.join(
    root,
    "One Memory Preview.app/Contents/MacOS/One Memory Preview",
  );
  await mkdir(path.dirname(runtimeCommand), { recursive: true });
  await writeFile(runtimeCommand, "synthetic executable", { mode: 0o700 });
  const runtime = {
    runtimeCommand,
    mcpEntryPath: path.join(root, "mcp.cjs"),
    discoveryPath: path.join(data, "broker.json"),
  };
  const contents = {
    "runtime.mjs": 'export const capability="mh-c01-runtime-v1";',
    "notification.mjs": 'export const capability="source-change-v1";',
  };
  for (const [name, value] of Object.entries(contents))
    await writeFile(path.join(assets, name), value);
  await writeFile(
    path.join(assets, "manifest.json"),
    JSON.stringify({
      schemaVersion: 1,
      runtimeCapability: "mh-c01-runtime-v1",
      notificationCapability: "source-change-v1",
      runtimeTarget: "node24",
      files: Object.fromEntries(
        Object.entries(contents).map(([n, v]) => [
          n,
          { sha256: hash(v), bytes: Buffer.byteLength(v) },
        ]),
      ),
    }),
  );
  const layout = claudeCodeLayout({
    claudeDir: host,
    configPath: path.join(root, ".claude.json"),
  });
  await writeFile(
    required(layout.configPath),
    JSON.stringify({ mcpServers: { neighbor: { command: "keep" } } }),
  );
  await writeFile(
    path.join(host, "settings.json"),
    JSON.stringify({
      permissions: { allow: ["Read"] },
      hooks: {
        Stop: [
          {
            matcher: "foreign",
            hooks: [{ type: "command", command: "leave-me" }],
          },
        ],
      },
    }),
  );
  const permissions = await HostPermissions.open(data, runtime, {
    syncHookAssetsDirectory: assets,
  });
  const install = async () =>
    permissions.install(
      layout,
      (await permissions.previewInstall(layout)).fingerprint,
    );
  const apply = async (operation: "install" | "uninstall") => {
    const p = await permissions.previewSyncHook(layout, operation);
    return permissions.applySyncHook(layout, {
      operation,
      installationId: p.installationId,
      revision: p.revision,
      fingerprint: p.fingerprint,
      userConfirmed: true,
    });
  };
  return {
    root,
    data,
    host,
    assets,
    layout,
    runtime,
    permissions,
    install,
    apply,
  };
}

describe("same-identity supplementary sync hook", () => {
  it("keeps IPC contracts identical", () => {
    expectTypeOf<SyncHookStatus>().toEqualTypeOf<WebStatus>();
    expectTypeOf<SyncHookPreview>().toEqualTypeOf<WebPreview>();
    expectTypeOf<ApplySyncHookInput>().toEqualTypeOf<WebInput>();
  });
  it("requires a normal MCP connection and rejects unsupported hosts", async () => {
    const f = await fixture();
    expect(await f.permissions.getSyncHookStatus(f.layout)).toMatchObject({
      state: "connection-required",
    });
    await expect(
      f.permissions.previewSyncHook(f.layout, "install"),
    ).rejects.toThrow("sync_hook_connection_required");
    expect(
      await f.permissions.getSyncHookStatus(cursorLayout(f.host)),
    ).toMatchObject({ state: "unsupported" });
    expect(await f.permissions.hostGrantStore.listInstallations()).toEqual([]);
  });
  it("adds and removes only the sync hook while preserving the MCP identity, credential and rights", async () => {
    const f = await fixture();
    const installed = await f.install();
    const r = required(installed.permission.receipt);
    await f.permissions.setPermission(f.layout, {
      installationId: r.installationId,
      expectedRevision: r.revision,
      allowedTools: ["om_recall"],
      allowedScopes: ["all-apps"],
      userConfirmed: true,
    });
    const permission = await f.permissions.getPermission(f.layout);
    const beforeMcp = await readFile(required(f.layout.configPath), "utf8"),
      beforeSkill = await readFile(required(f.layout.skillPath), "utf8"),
      beforeSettings = await readFile(
        path.join(f.host, "settings.json"),
        "utf8",
      );
    const credential = await readHostCredentialFile(
      f.permissions.runtimeFor(f.layout).credentialFile,
    );
    const preview = await f.permissions.previewSyncHook(f.layout, "install");
    expect(
      preview.files.every((file) => file.path.startsWith(f.host + path.sep)),
    ).toBe(true);
    expect(JSON.stringify(preview)).not.toContain(credential);
    await f.apply("install");
    expect(await f.permissions.getSyncHookStatus(f.layout)).toMatchObject({
      state: "installed",
    });
    expect(await f.permissions.getPermission(f.layout)).toEqual(permission);
    expect(
      await readHostCredentialFile(
        f.permissions.runtimeFor(f.layout).credentialFile,
      ),
    ).toBe(credential);
    expect(await readFile(required(f.layout.configPath), "utf8")).toBe(
      beforeMcp,
    );
    expect(await readFile(required(f.layout.skillPath), "utf8")).toBe(
      beforeSkill,
    );
    const config = JSON.parse(
      await readFile(
        path.join(f.host, ".one-memory/mh-c01/config.json"),
        "utf8",
      ),
    );
    expect(config).toMatchObject({
      mode: "sync-only",
      installationId: r.installationId,
      credentialFile: f.permissions.runtimeFor(f.layout).credentialFile,
    });
    await expect(f.permissions.previewUninstall(f.layout)).rejects.toThrow(
      "sync_hook_remove_first",
    );
    await expect(f.permissions.previewInstall(f.layout)).rejects.toThrow(
      "sync_hook_remove_first",
    );
    await f.apply("uninstall");
    expect(await f.permissions.getSyncHookStatus(f.layout)).toMatchObject({
      state: "not-installed",
    });
    expect(await readFile(path.join(f.host, "settings.json"), "utf8")).toBe(
      beforeSettings,
    );
    expect(await f.permissions.getPermission(f.layout)).toEqual(permission);
    expect(await f.permissions.hostGrantStore.listInstallations()).toHaveLength(
      1,
    );
    await expect(
      f.permissions.previewUninstall(f.layout),
    ).resolves.toBeDefined();
  });
  it("does not grant reads when supplementing an install-only identity", async () => {
    const f = await fixture();
    await f.install();
    await f.apply("install");
    const secret = await readHostCredentialFile(
      f.permissions.runtimeFor(f.layout).credentialFile,
    );
    await expect(
      f.permissions.hostGrantStore.authenticate(secret),
    ).rejects.toMatchObject({ code: "host_grant_not_approved" });
    expect((await f.permissions.getPermission(f.layout)).state).toBe(
      "install-only",
    );
  });
  it.each(["consent", "fingerprint", "revision", "foreign-field"])(
    "rejects invalid %s before writing",
    async (kind) => {
      const f = await fixture();
      await f.install();
      const preview = await f.permissions.previewSyncHook(f.layout, "install");
      const input: Record<string, unknown> = {
        operation: "install",
        installationId: preview.installationId,
        revision: preview.revision,
        fingerprint: preview.fingerprint,
        userConfirmed: true,
      };
      if (kind === "consent") input.userConfirmed = false;
      if (kind === "fingerprint") input.fingerprint = "0".repeat(64);
      if (kind === "revision") input.revision = 2;
      if (kind === "foreign-field") input.path = f.host;
      await expect(
        f.permissions.applySyncHook(f.layout, input),
      ).rejects.toThrow();
      expect((await f.permissions.getSyncHookStatus(f.layout)).state).toBe(
        "not-installed",
      );
    },
  );
  it.each(["file", "asset", "revoke"])(
    "rejects %s changes after preview",
    async (kind) => {
      const f = await fixture();
      await f.install();
      const p = await f.permissions.previewSyncHook(f.layout, "install");
      if (kind === "file")
        await writeFile(path.join(f.host, "settings.json"), "{}");
      if (kind === "asset")
        await writeFile(path.join(f.assets, "runtime.mjs"), "changed");
      if (kind === "revoke")
        await f.permissions.revokePermission(f.layout, {
          installationId: p.installationId,
          expectedRevision: p.revision,
          userConfirmed: true,
        });
      await expect(
        f.permissions.applySyncHook(f.layout, {
          operation: "install",
          installationId: p.installationId,
          revision: p.revision,
          fingerprint: p.fingerprint,
          userConfirmed: true,
        }),
      ).rejects.toThrow();
      await expect(
        readFile(path.join(f.host, ".one-memory/mh-c01/hook.mjs"), "utf8"),
      ).rejects.toMatchObject({ code: "ENOENT" });
    },
  );
  it("allows safe removal after recall revocation and loss of packaged assets", async () => {
    const f = await fixture();
    await f.install();
    await f.apply("install");
    const p = required((await f.permissions.getPermission(f.layout)).receipt);
    await f.permissions.revokePermission(f.layout, {
      installationId: p.installationId,
      expectedRevision: p.revision,
      userConfirmed: true,
    });
    await rm(f.assets, { recursive: true });
    expect(await f.permissions.getSyncHookStatus(f.layout)).toMatchObject({
      state: "installed",
      reason: "connection-revoked",
    });
    await f.apply("uninstall");
    expect((await f.permissions.getPermission(f.layout)).state).toBe("revoked");
    expect((await f.permissions.getSyncHookStatus(f.layout)).state).toBe(
      "connection-required",
    );
  });
});
