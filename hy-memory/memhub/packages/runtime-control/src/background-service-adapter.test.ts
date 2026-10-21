import { describe, expect, it, vi } from "vitest";
import { BackgroundPlanRegistry } from "./background-plan.js";
import { BackgroundServiceAdapter } from "./background-service-adapter.js";
import { runtimeInstallLayout } from "./service-plan.js";

function fixture(action: "enable" | "disable" = "enable") {
  const owner = { userId: "local", runtimeId: "stable" };
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
  const plans = new BackgroundPlanRegistry(owner, layout, 501);
  const preview = plans.create(action, 0, artifact);
  const serviceId = plans.resolve(preview.intent).service.service_id;
  const verifyArtifact = vi.fn(async () => artifact);
  const registration = vi.fn(async () => ({
    serviceId,
    file: action === "enable" ? ("absent" as const) : ("managed" as const),
    registration:
      action === "enable" ? ("absent" as const) : ("registered" as const),
    runtime: "not_checked" as const,
    reason: null,
  }));
  const install = vi.fn(async () => plans.resolve(preview.intent).service);
  const uninstall = vi.fn(async () => "removed" as const);
  const health = vi.fn(async () => ({
    state: "stopped" as const,
    code: "background_runtime_not_healthy",
    core: "stopped" as const,
    broker: "not_checked" as const,
  }));
  const options = { verifyArtifact, registration, install, uninstall, health };
  const adapter = new BackgroundServiceAdapter(plans, options);
  return { plans, preview, artifact, adapter, options };
}
describe("background service adapter", () => {
  it("requires absent registration and stopped Runtime before a new install", async () => {
    const f = fixture();
    expect(await f.adapter.check(f.preview.intent)).toBe(true);
    expect(f.options.install).not.toHaveBeenCalled();
  });
  it.each([
    "unknown",
    "requires_approval",
    "disabled_by_system",
    "registered",
    "conflict",
  ] as const)("does not bootstrap over %s", async (registration) => {
    const f = fixture();
    f.options.registration.mockResolvedValue({
      serviceId: "com.tencent.onememory.runtime",
      file: "absent",
      registration,
      runtime: "not_checked",
      reason: null,
    } as never);
    expect(await f.adapter.check(f.preview.intent)).toBe(false);
    expect(f.options.install).not.toHaveBeenCalled();
  });
  it("rechecks artifact and registration immediately before mutation", async () => {
    const f = fixture();
    expect(await f.adapter.check(f.preview.intent)).toBe(true);
    f.options.verifyArtifact.mockResolvedValue({
      ...f.artifact,
      digest: "b".repeat(64),
    });
    await expect(f.adapter.apply(f.preview.intent)).rejects.toThrow("changed");
    expect(f.options.install).not.toHaveBeenCalled();
  });
  it("consumes a plan before invoking the shared installer and never auto-repeats", async () => {
    const f = fixture();
    f.options.install.mockImplementation(async () => {
      throw Error("lost response");
    });
    await expect(f.adapter.apply(f.preview.intent)).rejects.toThrow();
    await expect(f.adapter.apply(f.preview.intent)).rejects.toThrow("consumed");
    expect(f.options.install).toHaveBeenCalledTimes(1);
    expect(await f.adapter.inspect(f.preview.intent)).toBe("unknown");
  });
  it("system eligibility alone cannot attest an exact job or operation", async () => {
    const f = fixture();
    f.options.install.mockResolvedValue(
      f.plans.resolve(f.preview.intent).service,
    );
    await f.adapter.apply(f.preview.intent);
    f.options.registration.mockResolvedValue({
      serviceId: "com.tencent.onememory.runtime",
      file: "managed",
      registration: "registered",
      runtime: "not_checked",
      reason: null,
    } as never);
    expect(await f.adapter.inspect(f.preview.intent)).toBe("unknown");
  });
  it("disable requires the exact managed declaration and uses shared uninstall", async () => {
    const f = fixture("disable");
    expect(await f.adapter.check(f.preview.intent)).toBe(true);
    await f.adapter.apply(f.preview.intent);
    expect(f.options.uninstall).toHaveBeenCalledTimes(1);
    expect(f.options.install).not.toHaveBeenCalled();
  });
  it("will not infer not_applied from absence after an unknown result", async () => {
    const f = fixture();
    expect(await f.adapter.inspect(f.preview.intent)).toBe("unknown");
    expect(f.options.install).not.toHaveBeenCalled();
    expect(f.options.uninstall).not.toHaveBeenCalled();
  });
});
