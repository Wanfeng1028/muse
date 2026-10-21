import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import {
  byoHomeDir,
  listProfiles,
  loadProfile,
  saveProfile,
  type ByoProfile,
} from "../src/profile.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = join(__dirname, "..");

function sampleProfile(agentId: string): ByoProfile {
  return {
    agentId,
    gatewayUrl: "ws://127.0.0.1:8765",
    room: "lobby",
    provider: { command: "claude", args: ["--acp"], cwd: "/work" },
    createdAtMs: 111,
    updatedAtMs: 222,
  };
}

describe("byoHomeDir", () => {
  it("prefers BOTSTALK_BYO_DIR", () => {
    expect(byoHomeDir({ BOTSTALK_BYO_DIR: "/custom/byo" })).toBe("/custom/byo");
  });

  it("uses XDG_CONFIG_HOME/botstalk/byo when set", () => {
    expect(byoHomeDir({ XDG_CONFIG_HOME: "/xdg" })).toBe(join("/xdg", "botstalk", "byo"));
  });

  it("falls back to ~/.botstalk/byo", () => {
    const dir = byoHomeDir({});
    expect(dir.endsWith(join(".botstalk", "byo"))).toBe(true);
  });
});

describe("profile persistence", () => {
  let home = "";

  beforeEach(() => {
    home = join(PKG_ROOT, "test-tmp", `profiles-${Math.random().toString(36).slice(2)}`);
    mkdirSync(home, { recursive: true });
  });

  afterEach(() => {
    rmSync(home, { recursive: true, force: true });
  });

  it("round-trips a saved profile", () => {
    const profile = sampleProfile("agent-a");
    saveProfile(home, profile);
    expect(loadProfile(home, "agent-a")).toEqual(profile);
  });

  it("returns null for a missing profile", () => {
    expect(loadProfile(home, "nope")).toBeNull();
  });

  it("returns null for corrupt profile content", () => {
    const dir = join(home, "agent-bad");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "profile.json"), "{not json", "utf8");
    expect(loadProfile(home, "agent-bad")).toBeNull();
  });

  it("returns null for a profile with the wrong shape", () => {
    const dir = join(home, "agent-shape");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "profile.json"), JSON.stringify({ agentId: 42 }), "utf8");
    expect(loadProfile(home, "agent-shape")).toBeNull();
  });

  it("lists saved profiles and skips corrupt ones", () => {
    saveProfile(home, sampleProfile("agent-a"));
    saveProfile(home, sampleProfile("agent-b"));
    const dir = join(home, "agent-bad");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "profile.json"), "garbage", "utf8");
    const listed = listProfiles(home);
    expect(listed.map((p) => p.agentId).sort()).toEqual(["agent-a", "agent-b"]);
  });
});
