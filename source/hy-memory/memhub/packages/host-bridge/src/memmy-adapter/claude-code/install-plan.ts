// Claude settings/skill installation adapted from MemTensor memmy-agent (MIT).
import { createHash } from "node:crypto";
import path from "node:path";
import { CLAUDE_EVENTS } from "./event-adapter.js";
import {
  END_MARKER,
  hookCommand,
  INSTRUCTION_BLOCK,
  renderHookScript,
  renderResumeCommand,
  renderSkill,
  START_MARKER,
} from "./hook-template.js";
import { MEMMY_LICENSE } from "./license.js";
import {
  absolutePath,
  ClaudeAdapterError,
  type ClaudeRuntimeConfig,
  type ClaudeRuntimeKind,
  exactKeys,
  isRecord,
  runtimeConfig,
  runtimeKind,
} from "./runtime-config.js";

export const ARTIFACT_ROOT = ".one-memory/mh-c01";
export const JOURNAL = `${ARTIFACT_ROOT}/install.json`;
export const MANAGED_FILES = [
  "settings.json",
  "CLAUDE.md",
  `${ARTIFACT_ROOT}/hook.mjs`,
  `${ARTIFACT_ROOT}/runtime.mjs`,
  `${ARTIFACT_ROOT}/notification.mjs`,
  `${ARTIFACT_ROOT}/config.json`,
  `${ARTIFACT_ROOT}/LICENSE.memmy`,
  "commands/one-memory-resume.md",
  "skills/one-memory-lifecycle/SKILL.md",
] as const;
export type ManagedFile = (typeof MANAGED_FILES)[number];
export const digest = (value: string) =>
  createHash("sha256").update(value).digest("hex");
const proofBrand = Symbol("verified-claude-assets");
export interface VerifiedClaudeAssets {
  readonly runtime: string;
  readonly notification: string;
  readonly [proofBrand]: true;
}

/** Trusted packaging owner attests the exact tested, self-contained asset bytes. */
export function verifiedAssets(input: {
  runtime: string;
  notification: string;
  proof: {
    runtimeSha256: string;
    notificationSha256: string;
    integrationTestsPassed: true;
  };
}): VerifiedClaudeAssets {
  if (
    !input ||
    typeof input.runtime !== "string" ||
    !input.runtime.trim() ||
    typeof input.notification !== "string" ||
    !input.notification.trim() ||
    !input.proof ||
    input.proof.integrationTestsPassed !== true ||
    input.proof.runtimeSha256 !== digest(input.runtime) ||
    input.proof.notificationSha256 !== digest(input.notification) ||
    !input.runtime.includes("mh-c01-runtime-v1") ||
    !input.notification.includes("source-change-v1") ||
    Buffer.byteLength(input.runtime) > 2 * 1024 * 1024 ||
    Buffer.byteLength(input.notification) > 2 * 1024 * 1024
  )
    throw new ClaudeAdapterError("runtime_assets_unverified");
  return Object.freeze({
    runtime: input.runtime,
    notification: input.notification,
    [proofBrand]: true as const,
  });
}

export interface ClaudeTargetOptions {
  claudeDirectory: string;
  nodeExecutable: string;
  /** Omitted only for legacy Node callers; Desktop explicitly selects Electron. */
  runtimeKind?: ClaudeRuntimeKind;
  config: ClaudeRuntimeConfig;
  assets: VerifiedClaudeAssets;
}
export interface FileSnapshot {
  path: ManagedFile;
  content: string | null;
  mode: number;
}
export interface PlannedFile extends FileSnapshot {
  after: string | null;
}
export interface InstallationJournal {
  schemaVersion: 1;
  owner: "one-memory-mh-c01";
  phase: "applying" | "installed";
  command: string;
  files: Array<{
    path: ManagedFile;
    original: string | null;
    originalMode: number;
    installed: string;
  }>;
}
export interface ClaudeInstallPlan {
  operation: "install" | "uninstall";
  fingerprint: string;
  files: PlannedFile[];
  journalBefore: string | null;
  journalAfter: InstallationJournal | null;
  permissionEffect: "none";
}

function parseSettings(raw: string | null): Record<string, unknown> {
  let value: unknown;
  try {
    value = raw === null ? {} : JSON.parse(raw);
  } catch {
    throw new ClaudeAdapterError("invalid_hook_settings");
  }
  if (!isRecord(value) || (value.hooks !== undefined && !isRecord(value.hooks)))
    throw new ClaudeAdapterError("invalid_hook_settings");
  const result = structuredClone(value);
  const hooks = result.hooks as Record<string, unknown> | undefined;
  for (const event of CLAUDE_EVENTS) {
    const entries = hooks?.[event];
    if (
      entries !== undefined &&
      (!Array.isArray(entries) ||
        !entries.every(
          (entry) =>
            isRecord(entry) &&
            Array.isArray(entry.hooks) &&
            entry.hooks.every(isRecord),
        ))
    )
      throw new ClaudeAdapterError("invalid_hook_settings");
  }
  return result;
}
const hookEntry = (command: string) => ({
  matcher: "",
  hooks: [{ type: "command", command, timeout: 60 }],
});
const same = (a: unknown, b: unknown) =>
  JSON.stringify(a) === JSON.stringify(b);

function removeHooks(config: Record<string, unknown>, command: string): void {
  if (!isRecord(config.hooks))
    throw new ClaudeAdapterError("owned_file_changed");
  for (const event of CLAUDE_EVENTS) {
    const entries = config.hooks[event];
    if (!Array.isArray(entries))
      throw new ClaudeAdapterError("owned_file_changed");
    const owned = entries.filter((entry) => same(entry, hookEntry(command)));
    if (owned.length !== 1) throw new ClaudeAdapterError("owned_file_changed");
    const others = entries.filter((entry) => !same(entry, hookEntry(command)));
    if (others.length) config.hooks[event] = others;
    else delete config.hooks[event];
  }
  if (!Object.keys(config.hooks).length) delete config.hooks;
}

function addHooks(config: Record<string, unknown>, command: string): void {
  const hooks = isRecord(config.hooks) ? config.hooks : {};
  for (const event of CLAUDE_EVENTS) {
    const entries = (hooks[event] ?? []) as Array<Record<string, unknown>>;
    if (
      entries.some(
        (entry) =>
          Array.isArray(entry.hooks) &&
          entry.hooks.some(
            (hook) =>
              isRecord(hook) &&
              typeof hook.command === "string" &&
              hook.command.includes(`${ARTIFACT_ROOT}/hook.mjs`),
          ),
      )
    )
      throw new ClaudeAdapterError("unmanaged_hook_conflict");
    hooks[event] = [...entries, hookEntry(command)];
  }
  config.hooks = hooks;
}

function removeBlock(raw: string): string {
  if (
    raw.split(START_MARKER).length !== 2 ||
    raw.split(END_MARKER).length !== 2 ||
    !raw.includes(INSTRUCTION_BLOCK)
  )
    throw new ClaudeAdapterError("owned_file_changed");
  return raw.replace(INSTRUCTION_BLOCK, "");
}

export function parseJournal(raw: string | null): InstallationJournal | null {
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (
      !isRecord(value) ||
      !exactKeys(value, [
        "schemaVersion",
        "owner",
        "phase",
        "command",
        "files",
      ]) ||
      value.schemaVersion !== 1 ||
      value.owner !== "one-memory-mh-c01" ||
      !["applying", "installed"].includes(String(value.phase)) ||
      typeof value.command !== "string" ||
      !Array.isArray(value.files) ||
      value.files.length !== MANAGED_FILES.length
    )
      throw new Error();
    for (const file of value.files) {
      if (
        !isRecord(file) ||
        !exactKeys(file, ["path", "original", "originalMode", "installed"]) ||
        !MANAGED_FILES.includes(file.path as ManagedFile) ||
        (file.original !== null && typeof file.original !== "string") ||
        typeof file.installed !== "string" ||
        !Number.isInteger(file.originalMode) ||
        (file.originalMode as number) < 0 ||
        (file.originalMode as number) > 0o777
      )
        throw new Error();
    }
    if (
      new Set(value.files.map((file) => file.path)).size !==
      MANAGED_FILES.length
    )
      throw new Error();
    return value as unknown as InstallationJournal;
  } catch {
    throw new ClaudeAdapterError("invalid_installation_journal");
  }
}

export function planFingerprint(
  plan: Omit<ClaudeInstallPlan, "fingerprint">,
): string {
  return digest(JSON.stringify(plan));
}

export function renderInstallPlan(
  options: ClaudeTargetOptions,
  observed: FileSnapshot[],
  journalBefore: string | null,
): ClaudeInstallPlan {
  const root = absolutePath(options.claudeDirectory);
  absolutePath(options.nodeExecutable);
  const kind = runtimeKind(options.runtimeKind);
  if (
    (kind === "node" && path.basename(options.nodeExecutable) !== "node") ||
    !options.assets?.[proofBrand]
  )
    throw new ClaudeAdapterError("runtime_assets_unverified");
  const config = runtimeConfig(options.config);
  if (config.stateDirectory !== path.join(root, ARTIFACT_ROOT, "state"))
    throw new ClaudeAdapterError("invalid_state_directory");
  const prior = parseJournal(journalBefore);
  if (prior && prior.phase !== "installed")
    throw new ClaudeAdapterError("installation_recovery_required");
  const command = hookCommand(
    options.nodeExecutable,
    path.join(root, ARTIFACT_ROOT, "hook.mjs"),
    kind,
  );
  const contents: Record<ManagedFile, string> = {
    "settings.json": "",
    "CLAUDE.md": "",
    [`${ARTIFACT_ROOT}/hook.mjs`]: renderHookScript(),
    [`${ARTIFACT_ROOT}/runtime.mjs`]: options.assets.runtime,
    [`${ARTIFACT_ROOT}/notification.mjs`]: options.assets.notification,
    [`${ARTIFACT_ROOT}/config.json`]: `${JSON.stringify(config, null, 2)}\n`,
    [`${ARTIFACT_ROOT}/LICENSE.memmy`]: MEMMY_LICENSE,
    "commands/one-memory-resume.md": renderResumeCommand(config.mode),
    "skills/one-memory-lifecycle/SKILL.md": renderSkill(config.mode),
  };
  const get = (name: ManagedFile) => {
    const value = observed.find((file) => file.path === name);
    if (!value) throw new ClaudeAdapterError("invalid_install_snapshot");
    return value;
  };
  const settings = parseSettings(get("settings.json").content);
  if (prior) removeHooks(settings, prior.command);
  addHooks(settings, command);
  contents["settings.json"] = `${JSON.stringify(settings, null, 2)}\n`;
  let instructions = get("CLAUDE.md").content ?? "";
  if (prior) instructions = removeBlock(instructions);
  else if (
    instructions.includes(START_MARKER) ||
    instructions.includes(END_MARKER)
  )
    throw new ClaudeAdapterError("unmanaged_file_conflict");
  contents["CLAUDE.md"] =
    `${instructions}${instructions && !instructions.endsWith("\n") ? "\n" : ""}${INSTRUCTION_BLOCK}`;
  const files = MANAGED_FILES.map((name) => {
    const file = get(name),
      old = prior?.files.find((item) => item.path === name);
    if (
      name !== "settings.json" &&
      name !== "CLAUDE.md" &&
      file.content !== null &&
      (!old || old.installed !== file.content)
    )
      throw new ClaudeAdapterError(
        old ? "owned_file_changed" : "unmanaged_file_conflict",
      );
    if (old && file.content === null)
      throw new ClaudeAdapterError("owned_file_changed");
    return { ...file, after: contents[name] };
  });
  const journalAfter: InstallationJournal = {
    schemaVersion: 1,
    owner: "one-memory-mh-c01",
    phase: "installed",
    command,
    files: files.map((file) => {
      const old = prior?.files.find((item) => item.path === file.path);
      return {
        path: file.path,
        original: old ? old.original : file.content,
        originalMode: old?.originalMode ?? file.mode,
        installed: file.after,
      };
    }),
  };
  const plan = {
    operation: "install" as const,
    files,
    journalBefore,
    journalAfter,
    permissionEffect: "none" as const,
  };
  return { ...plan, fingerprint: planFingerprint(plan) };
}

export function renderUninstallPlan(
  observed: FileSnapshot[],
  journalBefore: string,
): ClaudeInstallPlan {
  const prior = parseJournal(journalBefore);
  if (prior?.phase !== "installed")
    throw new ClaudeAdapterError("installation_recovery_required");
  const files = prior.files.map((old) => {
    const file = observed.find((item) => item.path === old.path);
    if (!file || file.content === null)
      throw new ClaudeAdapterError("owned_file_changed");
    let after = old.original;
    if (file.content !== old.installed) {
      if (file.path === "settings.json") {
        const settings = parseSettings(file.content);
        removeHooks(settings, prior.command);
        after = `${JSON.stringify(settings, null, 2)}\n`;
      } else if (file.path === "CLAUDE.md") after = removeBlock(file.content);
      else throw new ClaudeAdapterError("owned_file_changed");
    }
    return { ...file, after };
  });
  const plan = {
    operation: "uninstall" as const,
    files,
    journalBefore,
    journalAfter: null,
    permissionEffect: "none" as const,
  };
  return { ...plan, fingerprint: planFingerprint(plan) };
}
