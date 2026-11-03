
import { describe, it, expect } from "vitest";
import { validateManifest, loadManifestFile } from "../src/manifest.js";
import { join } from "path";

describe("validateManifest", () => {
  it("valid manifest returns empty array", () => {
    const result = validateManifest({
      mod_name: "deepseek",
      version: "1.0.0",
      capabilities: ["llm"],
    });
    expect(result).toEqual([]);
  });

  it("unknown fields are ignored, still returns empty array", () => {
    const result = validateManifest({
      mod_name: "deepseek",
      version: "1.0.0",
      capabilities: ["llm"],
      extra_field: "whatever",
    });
    expect(result).toEqual([]);
  });

  it("invalid mod_name with uppercase start returns at least 1 error", () => {
    const result = validateManifest({
      mod_name: "Deepseek",
      version: "1.0.0",
      capabilities: ["llm"],
    });
    expect(result.length).toBeGreaterThanOrEqual(1);
  });

  it("invalid mod_name with space returns at least 1 error", () => {
    const result = validateManifest({
      mod_name: "deep seek",
      version: "1.0.0",
      capabilities: ["llm"],
    });
    expect(result.length).toBeGreaterThanOrEqual(1);
  });

  it("invalid version '1.0' returns at least 1 error", () => {
    const result = validateManifest({
      mod_name: "deepseek",
      version: "1.0",
      capabilities: ["llm"],
    });
    expect(result.length).toBeGreaterThanOrEqual(1);
  });

  it("empty capabilities array returns at least 1 error", () => {
    const result = validateManifest({
      mod_name: "deepseek",
      version: "1.0.0",
      capabilities: [],
    });
    expect(result.length).toBeGreaterThanOrEqual(1);
  });

  it("duplicate capabilities returns at least 1 error", () => {
    const result = validateManifest({
      mod_name: "deepseek",
      version: "1.0.0",
      capabilities: ["llm", "llm"],
    });
    expect(result.length).toBeGreaterThanOrEqual(1);
  });

  it("requires_adapter non-boolean returns at least 1 error", () => {
    const result = validateManifest({
      mod_name: "deepseek",
      version: "1.0.0",
      capabilities: ["llm"],
      requires_adapter: "yes",
    });
    expect(result.length).toBeGreaterThanOrEqual(1);
  });

  it("non-object input returns ['manifest: expected object']", () => {
    expect(validateManifest(null)).toEqual(["manifest: expected object"]);
    expect(validateManifest(undefined)).toEqual(["manifest: expected object"]);
    expect(validateManifest("string")).toEqual(["manifest: expected object"]);
  });
});

describe("loadManifestFile", () => {
  it("loads deepseek manifest and validates successfully", () => {
    const dir = import.meta.dirname ?? __dirname;
    const path = join(dir, "..", "..", "adapters", "deepseek", "manifest.json");
    const manifest = loadManifestFile(path);
    expect(manifest.mod_name).toBe("deepseek");
    expect(validateManifest(manifest)).toEqual([]);
  });

  it("throws for non-existent file", () => {
    expect(() => loadManifestFile("/nonexistent/path/manifest.json")).toThrow();
  });
});
