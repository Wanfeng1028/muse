// 来源：Botstalk 网关清单规范，设计思想移植自 OpenAgents mod_manifest.json（Apache-2.0）
// 格式规范属设计思想，不受版权约束；本实现代码以 MIT 许可证口径发布

import * as fs from "node:fs";
import * as nodePath from "node:path";

export interface BotstalkManifest {
  mod_name: string;
  version: string;
  description?: string;
  authors?: string[];
  license?: string;
  capabilities: string[];
  requires_adapter?: boolean;
  studio_interface?: boolean;
  dependencies?: string[];
  tools?: string[];
  process_events?: string[];
  generate_events?: string[];
  metadata?: Record<string, unknown>;
}

const MOD_NAME_RE = /^[a-z][a-z0-9_-]*$/;
const VERSION_RE = /^\d+\.\d+\.\d+$/;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function validateStringArray(
  obj: Record<string, unknown>,
  field: string,
  errors: string[],
  required: boolean,
): void {
  const value = obj[field];
  if (value === undefined) {
    if (required) {
      errors.push(`manifest.${field}: must be non-empty array`);
    }
    return;
  }
  if (!Array.isArray(value)) {
    errors.push(`manifest.${field}: must be ${required ? "non-empty array" : "array"}`);
    return;
  }
  if (required && value.length === 0) {
    errors.push(`manifest.${field}: must be non-empty array`);
    return;
  }
  for (const item of value) {
    if (!isNonEmptyString(item)) {
      errors.push(`manifest.${field}: items must be non-empty strings`);
      return;
    }
  }
  const seen = new Set<string>();
  for (const item of value as string[]) {
    if (seen.has(item)) {
      errors.push(`manifest.${field}: must not contain duplicates`);
      return;
    }
    seen.add(item);
  }
}

export function validateManifest(input: unknown): string[] {
  const errors: string[] = [];

  if (!isPlainObject(input)) {
    return ["manifest: expected object"];
  }

  const obj = input as Record<string, unknown>;

  if (!isNonEmptyString(obj.mod_name) || !MOD_NAME_RE.test(obj.mod_name as string)) {
    errors.push(`manifest.mod_name: must match /^${MOD_NAME_RE.source}$/`);
  }

  if (!isNonEmptyString(obj.version) || !VERSION_RE.test(obj.version as string)) {
    errors.push(`manifest.version: must match /^${VERSION_RE.source}$/`);
  }

  validateStringArray(obj, "capabilities", errors, true);

  if (obj.description !== undefined && !isNonEmptyString(obj.description)) {
    errors.push("manifest.description: must be non-empty string");
  }

  if (obj.license !== undefined && !isNonEmptyString(obj.license)) {
    errors.push("manifest.license: must be non-empty string");
  }

  validateStringArray(obj, "authors", errors, false);
  validateStringArray(obj, "dependencies", errors, false);
  validateStringArray(obj, "tools", errors, false);
  validateStringArray(obj, "process_events", errors, false);
  validateStringArray(obj, "generate_events", errors, false);

  if (obj.requires_adapter !== undefined && typeof obj.requires_adapter !== "boolean") {
    errors.push("manifest.requires_adapter: must be boolean");
  }

  if (obj.studio_interface !== undefined && typeof obj.studio_interface !== "boolean") {
    errors.push("manifest.studio_interface: must be boolean");
  }

  if (obj.metadata !== undefined && !isPlainObject(obj.metadata)) {
    errors.push("manifest.metadata: must be plain object");
  }

  return errors;
}

export function loadManifestFile(path: string): BotstalkManifest {
  let raw: string;
  try {
    raw = fs.readFileSync(path, "utf-8");
  } catch (readErr) {
    throw new Error(`Failed to read manifest file ${path}: ${(readErr as Error).message}`);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (parseErr) {
    throw new Error(`Failed to parse manifest file ${path}: ${(parseErr as Error).message}`);
  }

  const errors = validateManifest(parsed);
  if (errors.length > 0) {
    throw new Error(`Invalid manifest file ${path}: ${errors.join("; ")}`);
  }

  return parsed as BotstalkManifest;
}

export function loadManifestDir(dir: string): BotstalkManifest[] {
  const entries = fs.readdirSync(dir);
  const jsonFiles = entries
    .filter((name) => name.endsWith(".json"))
    .sort();

  const manifests: BotstalkManifest[] = [];
  for (const fileName of jsonFiles) {
    manifests.push(loadManifestFile(nodePath.join(dir, fileName)));
  }
  return manifests;
}
