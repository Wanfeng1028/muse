// Adapted from MemTensor memmy-agent, MIT. See PROVENANCE.md and LICENSE.memmy.
import path from "node:path";

export type ClaudeRuntimeKind = "node" | "electron";

export function runtimeKind(value: unknown = "node"): ClaudeRuntimeKind {
  if (value !== "node" && value !== "electron")
    throw new ClaudeAdapterError("invalid_runtime_kind");
  return value;
}

export interface ClaudeRuntimeConfig {
  schemaVersion: 1;
  mode: "sync-only" | "recall-and-sync";
  installationId: string;
  discoveryPath: string;
  credentialFile: string;
  stateDirectory: string;
}

export class ClaudeAdapterError extends Error {
  constructor(readonly code: string) {
    super(code);
    this.name = "ClaudeAdapterError";
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function exactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  return (
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

export function absolutePath(value: unknown): string {
  if (
    typeof value !== "string" ||
    !path.isAbsolute(value) ||
    /\p{Cc}/u.test(value) ||
    value !== path.normalize(value)
  ) {
    throw new ClaudeAdapterError("invalid_runtime_path");
  }
  return value;
}

export function runtimeConfig(value: unknown): Readonly<ClaudeRuntimeConfig> {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      "schemaVersion",
      "mode",
      "installationId",
      "discoveryPath",
      "credentialFile",
      "stateDirectory",
    ]) ||
    value.schemaVersion !== 1 ||
    (value.mode !== "sync-only" && value.mode !== "recall-and-sync") ||
    typeof value.installationId !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      value.installationId,
    )
  ) {
    throw new ClaudeAdapterError("invalid_runtime_config");
  }
  return Object.freeze({
    schemaVersion: 1,
    mode: value.mode,
    installationId: value.installationId,
    discoveryPath: absolutePath(value.discoveryPath),
    credentialFile: absolutePath(value.credentialFile),
    stateDirectory: absolutePath(value.stateDirectory),
  });
}

export function sessionIdentity(value: unknown): string {
  if (
    typeof value !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)
  ) {
    throw new ClaudeAdapterError("invalid_session_identity");
  }
  return value;
}
