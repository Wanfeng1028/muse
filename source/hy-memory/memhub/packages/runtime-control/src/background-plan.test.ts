import { randomUUID } from "node:crypto";
import { describe, expect, it } from "vitest";
import { BackgroundPlanRegistry } from "./background-plan.js";
import { runtimeInstallLayout } from "./service-plan.js";

const owner = { userId: "local", runtimeId: "stable-data" };
const layout = runtimeInstallLayout({
  platform: "darwin",
  home: "/Users/example",
  installRoot: "/Users/example/runtime/current",
  dataDir: "/Users/example/data",
});
const artifact = {
  digest: "a".repeat(64),
  version: "1.0.0",
  root: "/Users/example/runtime/versions/1.0.0-darwin-arm64",
};
function registry(clock = () => 100) {
  return new BackgroundPlanRegistry(owner, layout, 501, { clock });
}
describe("trusted background plans", () => {
  it("public preview has no executable path and resolves exactly the trusted layout", () => {
    const plans = registry(),
      preview = plans.create("enable", 0, artifact);
    expect(JSON.stringify(preview)).not.toContain("/Users");
    expect(preview.intent.operationId).toMatch(/^[a-f0-9-]+$/);
    expect(plans.resolve(preview.intent).layout).toEqual(layout);
    // A non-daily install root gets its own scoped label so it cannot collide
    // with the canonical daily LaunchAgent.
    expect(plans.resolve(preview.intent).service.service_id).toMatch(
      /^com\.tencent\.onememory\.runtime\.[a-f0-9]{16}$/,
    );
  });
  it("rejects a forged operation or modified intent despite a valid digest", () => {
    const plans = registry(),
      preview = plans.create("enable", 0, artifact);
    for (const patch of [
      { operationId: randomUUID() },
      { action: "disable" },
      { expectedRevision: 1 },
      { artifactDigest: "b".repeat(64) },
      { planDigest: "b".repeat(64) },
    ]) {
      expect(() =>
        plans.resolve({ ...preview.intent, ...patch } as typeof preview.intent),
      ).toThrow();
    }
  });
  it("ties digests to data directory artifact uid and action", () => {
    const first = registry().create("enable", 0, artifact);
    const changed = new BackgroundPlanRegistry(
      owner,
      { ...layout, dataDir: "/Users/example/other" },
      501,
    ).create("enable", 0, artifact);
    expect(changed.intent.planDigest).not.toBe(first.intent.planDigest);
    expect(
      registry().create("disable", 0, artifact).intent.planDigest,
    ).not.toBe(first.intent.planDigest);
  });
  it("defensively copies trusted inputs and resolved plans", () => {
    const original = { ...layout };
    const plans = new BackgroundPlanRegistry(owner, original, 501);
    original.dataDir = "/wrong";
    const preview = plans.create("enable", 0, artifact);
    const plan = plans.resolve(preview.intent);
    plan.layout.dataDir = "/mutated";
    plan.service.commands.install.length = 0;
    expect(plans.resolve(preview.intent).layout.dataDir).toBe(layout.dataDir);
    expect(plans.resolve(preview.intent).service.commands.install.length).toBe(
      1,
    );
  });
  it("expires plans, never revives them on backward clock, and limits retained entries", () => {
    let now = 100;
    const plans = registry(() => now);
    const first = plans.create("enable", 0, artifact);
    now = 99;
    expect(() => plans.resolve(first.intent)).toThrow("clock");
    now = 401;
    expect(() => plans.resolve(first.intent)).toThrow("expired");
    now = 500;
    for (let i = 0; i < 16; i++) plans.create("enable", i, artifact);
    expect(() => plans.create("enable", 17, artifact)).toThrow("capacity");
  });
  it("cannot reuse a consumed plan for another effect but can inspect its immutable intent", () => {
    const plans = registry(),
      preview = plans.create("enable", 0, artifact);
    plans.markApplying(preview.intent);
    expect(() => plans.markApplying(preview.intent)).toThrow("consumed");
    expect(() => plans.resolve(preview.intent)).toThrow("consumed");
    expect(plans.inspect(preview.intent)?.intent).toEqual(preview.intent);
  });
  it("rejects unsupported or malformed layout before creating a plan", () => {
    expect(
      () =>
        new BackgroundPlanRegistry(
          owner,
          { ...layout, dataDir: "relative" },
          501,
        ),
    ).toThrow();
    expect(
      () =>
        new BackgroundPlanRegistry(
          owner,
          { ...layout, runtimeEntry: "/other/program" },
          501,
        ),
    ).toThrow();
    expect(
      () =>
        new BackgroundPlanRegistry(
          owner,
          { ...layout, platform: "win32" },
          501,
        ),
    ).toThrow();
  });
});
