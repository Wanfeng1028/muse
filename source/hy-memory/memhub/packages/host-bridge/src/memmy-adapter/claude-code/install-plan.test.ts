import { createHash } from "node:crypto";
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { hookCommand } from "./hook-template.js";
import { verifiedAssets } from "./install-plan.js";
import {
  createClaudeCodeRemovalTarget,
  createClaudeCodeTarget,
} from "./target.js";

const roots: string[] = [];
afterEach(async () => {
  for (const root of roots.splice(0))
    await rm(root, { recursive: true, force: true });
});
const digest = (text: string) =>
  createHash("sha256").update(text).digest("hex");
function assets() {
  const runtime =
    'export const CLAUDE_RUNTIME_CAPABILITY = "mh-c01-runtime-v1";\nexport async function runClaudeHook() {}\n';
  const notification =
    'export const capability = "source-change-v1";\nexport function createNotificationTransport() { throw new Error("test-only"); }\n';
  return verifiedAssets({
    runtime,
    notification,
    proof: {
      runtimeSha256: digest(runtime),
      notificationSha256: digest(notification),
      integrationTestsPassed: true,
    },
  });
}
async function fixture() {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "mh-c01-install-")),
  );
  roots.push(root);
  const claudeDir = path.join(root, "claude");
  await mkdir(claudeDir);
  const credentials = path.join(root, "private");
  await mkdir(credentials, { mode: 0o700 });
  const credentialFile = path.join(credentials, "credential");
  await writeFile(credentialFile, `omhg_v1_${"a".repeat(43)}`, { mode: 0o600 });
  const config = {
    schemaVersion: 1 as const,
    mode: "recall-and-sync" as const,
    installationId: "00000000-0000-4000-8000-000000000001",
    discoveryPath: path.join(root, "discovery.json"),
    credentialFile,
    stateDirectory: path.join(claudeDir, ".one-memory/mh-c01/state"),
  };
  const options = {
    claudeDirectory: claudeDir,
    nodeExecutable: process.execPath,
    config,
    assets: assets(),
  };
  const target = createClaudeCodeTarget(options);
  return { root, claudeDir, credentialFile, config, options, target };
}
describe("MH-C01 complete candidate target", () => {
  it("refuses missing or unmatched asset capability proof", () => {
    expect(() =>
      verifiedAssets({ runtime: "", notification: "", proof: null } as never),
    ).toThrow();
    expect(() =>
      verifiedAssets({
        runtime: "code",
        notification: "code",
        proof: {
          runtimeSha256: "a".repeat(64),
          notificationSha256: "b".repeat(64),
          integrationTestsPassed: true,
        },
      }),
    ).toThrow("runtime_assets_unverified");
  });
  it("previews all owned artifacts without writes, installs, verifies and reverses exactly", async () => {
    const f = await fixture();
    const settingsPath = path.join(f.claudeDir, "settings.json");
    const original = JSON.stringify(
      {
        permissions: { allow: ["Read"] },
        env: { KEEP: "unchanged" },
        hooks: {
          Stop: [
            {
              matcher: "foreign",
              hooks: [
                { type: "command", command: "foreign --memmy-resume-hook.mjs" },
              ],
            },
          ],
        },
        custom: true,
      },
      null,
      2,
    );
    await writeFile(settingsPath, original);
    await chmod(settingsPath, 0o640);
    await writeFile(
      path.join(f.claudeDir, "CLAUDE.md"),
      "Keep user instructions.\n",
    );
    const plan = await f.target.planInstall();
    expect(plan.files.length).toBe(9);
    expect(await readFile(settingsPath, "utf8")).toBe(original);
    await expect(f.target.applyInstall(plan, "wrong")).rejects.toThrow(
      "preview_stale",
    );
    await f.target.applyInstall(plan, plan.fingerprint);
    expect((await f.target.verify()).state).toBe("candidate-installed");
    const installed = JSON.parse(await readFile(settingsPath, "utf8"));
    expect(installed.permissions).toEqual({ allow: ["Read"] });
    expect(installed.env).toEqual({ KEEP: "unchanged" });
    expect(installed.hooks.Stop[0].hooks[0].command).toBe(
      "foreign --memmy-resume-hook.mjs",
    );
    for (const event of [
      "SessionStart",
      "PostCompact",
      "SessionEnd",
      "Stop",
      "UserPromptSubmit",
    ])
      expect(installed.hooks[event].at(-1).hooks[0].timeout).toBe(60);
    const again = await f.target.planInstall();
    await f.target.applyInstall(again, again.fingerprint);
    expect(
      JSON.parse(await readFile(settingsPath, "utf8")).hooks.Stop,
    ).toHaveLength(2);
    const removal = await f.target.planUninstall();
    await f.target.applyUninstall(removal, removal.fingerprint);
    expect(await readFile(settingsPath, "utf8")).toBe(original);
    expect(await readFile(path.join(f.claudeDir, "CLAUDE.md"), "utf8")).toBe(
      "Keep user instructions.\n",
    );
    expect((await f.target.verify()).state).toBe("not-installed");
  });
  it("preserves unrelated hook edits made after installation on uninstall", async () => {
    const f = await fixture();
    const plan = await f.target.planInstall();
    await f.target.applyInstall(plan, plan.fingerprint);
    const settingsPath = path.join(f.claudeDir, "settings.json");
    const config = JSON.parse(await readFile(settingsPath, "utf8"));
    config.hooks.Stop.push({
      matcher: "",
      hooks: [{ type: "command", command: "later-foreign-hook" }],
    });
    config.permissions = { allow: [] };
    await writeFile(settingsPath, JSON.stringify(config));
    const removal = await f.target.planUninstall();
    await f.target.applyUninstall(removal, removal.fingerprint);
    expect(JSON.parse(await readFile(settingsPath, "utf8"))).toEqual({
      hooks: {
        Stop: [
          {
            matcher: "",
            hooks: [{ type: "command", command: "later-foreign-hook" }],
          },
        ],
      },
      permissions: { allow: [] },
    });
  });
  it("refuses stale preview and edited owned files without overwriting either", async () => {
    const f = await fixture();
    const plan = await f.target.planInstall();
    const settingsPath = path.join(f.claudeDir, "settings.json");
    await writeFile(settingsPath, '{"newForeign":true}');
    await expect(f.target.applyInstall(plan, plan.fingerprint)).rejects.toThrow(
      "preview_stale",
    );
    expect(await readFile(settingsPath, "utf8")).toBe('{"newForeign":true}');
    const next = await f.target.planInstall();
    await f.target.applyInstall(next, next.fingerprint);
    const skill = path.join(
      f.claudeDir,
      "skills/one-memory-lifecycle/SKILL.md",
    );
    await writeFile(skill, "User edited this file");
    await expect(f.target.planUninstall()).rejects.toThrow(
      "owned_file_changed",
    );
    expect(await readFile(skill, "utf8")).toBe("User edited this file");
  });
  it("refuses malformed settings and an unmanaged candidate artifact", async () => {
    const f = await fixture();
    await writeFile(
      path.join(f.claudeDir, "settings.json"),
      '{"hooks":{"Stop":"not-an-array"}}',
    );
    await expect(f.target.planInstall()).rejects.toThrow(
      "invalid_hook_settings",
    );
    await writeFile(path.join(f.claudeDir, "settings.json"), "{}");
    await mkdir(path.join(f.claudeDir, "commands"));
    await writeFile(
      path.join(f.claudeDir, "commands/one-memory-resume.md"),
      "Unmanaged command",
    );
    await expect(f.target.planInstall()).rejects.toThrow(
      "unmanaged_file_conflict",
    );
  });
  it("refuses missing or unsafe credential metadata without reading credential content", async () => {
    const f = await fixture();
    await chmod(f.credentialFile, 0o644);
    await expect(f.target.planInstall()).rejects.toThrow(
      "credential_unavailable",
    );
    await rm(f.credentialFile);
    await expect(f.target.planInstall()).rejects.toThrow(
      "credential_unavailable",
    );
  });

  it("preserves the legacy node command and pins Electron-as-node in the preview", async () => {
    const f = await fixture();
    const legacy = await f.target.planInstall();
    const explicit = await createClaudeCodeTarget({
      ...f.options,
      runtimeKind: "node",
    }).planInstall();
    expect(explicit).toEqual(legacy);
    const electron = await createClaudeCodeTarget({
      ...f.options,
      runtimeKind: "electron",
    }).planInstall();
    expect(electron.fingerprint).not.toBe(legacy.fingerprint);
    expect(electron.journalAfter?.command).toBe(
      `/usr/bin/env ELECTRON_RUN_AS_NODE=1 ${legacy.journalAfter?.command}`,
    );
    expect(electron.permissionEffect).toBe("none");
    expect(
      electron.files.find((file) => file.path.endsWith("config.json"))?.after,
    ).toBe(
      legacy.files.find((file) => file.path.endsWith("config.json"))?.after,
    );
  });

  it("quotes the trusted Electron path and refuses unknown runtime kinds", async () => {
    const executable = "/opt/My App's.app/Contents/MacOS/My App";
    const hook = "/private/a ' $(touch nope)/hook.mjs";
    expect(hookCommand(executable, hook, "electron")).toBe(
      "/usr/bin/env ELECTRON_RUN_AS_NODE=1 '/opt/My App'\\''s.app/Contents/MacOS/My App' '/private/a '\\'' $(touch nope)/hook.mjs'",
    );
    expect(() => hookCommand(executable, hook, "browser" as never)).toThrow(
      "invalid_runtime_kind",
    );
    const f = await fixture();
    await expect(
      createClaudeCodeTarget({
        ...f.options,
        runtimeKind: "browser" as never,
      }).planInstall(),
    ).rejects.toThrow("invalid_runtime_kind");
  });

  it("refuses applying a preview for another runtime kind without writing", async () => {
    const f = await fixture();
    const nodePlan = await f.target.planInstall();
    const electron = createClaudeCodeTarget({
      ...f.options,
      runtimeKind: "electron",
    });
    await expect(
      electron.applyInstall(nodePlan, nodePlan.fingerprint),
    ).rejects.toThrow("preview_stale");
    await expect(
      readFile(path.join(f.claudeDir, "settings.json")),
    ).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("removes using only the owned journal after the credential and build assets are unavailable", async () => {
    const f = await fixture();
    const settingsPath = path.join(f.claudeDir, "settings.json");
    await writeFile(settingsPath, '{"foreign":true}');
    const plan = await f.target.planInstall();
    await f.target.applyInstall(plan, plan.fingerprint);
    await rm(f.credentialFile);
    const removal = createClaudeCodeRemovalTarget(f.claudeDir);
    expect(Object.keys(removal).sort()).toEqual([
      "applyUninstall",
      "planUninstall",
      "verify",
    ]);
    expect(await removal.verify()).toEqual({
      state: "candidate-installed",
      permissionEffect: "none",
    });
    const preview = await removal.planUninstall();
    await removal.applyUninstall(preview, preview.fingerprint);
    expect(await readFile(settingsPath, "utf8")).toBe('{"foreign":true}');
    expect(await removal.verify()).toEqual({
      state: "not-installed",
      permissionEffect: "none",
    });
  });

  it("keeps removal fail-closed for modified owned files and stale previews", async () => {
    const f = await fixture();
    const plan = await f.target.planInstall();
    await f.target.applyInstall(plan, plan.fingerprint);
    const removal = createClaudeCodeRemovalTarget(f.claudeDir);
    const preview = await removal.planUninstall();
    const hook = path.join(f.claudeDir, ".one-memory/mh-c01/hook.mjs");
    await writeFile(hook, "user edited hook");
    await expect(removal.verify()).rejects.toThrow("owned_file_changed");
    await expect(
      removal.applyUninstall(preview, preview.fingerprint),
    ).rejects.toThrow("owned_file_changed");
    expect(await readFile(hook, "utf8")).toBe("user edited hook");
  });
});
