import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackgroundPlanRegistry } from "./background-plan.js";
import { inspectPlannedBackgroundRegistration } from "./background-registration.js";
import { runtimeInstallLayout } from "./service-plan.js";

const dirs: string[] = [];
afterEach(async () => {
  for (const dir of dirs.splice(0))
    await rm(dir, { recursive: true, force: true });
});
async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-bg-registration-"));
  dirs.push(root);
  await mkdir(path.join(root, "runtime"));
  await writeFile(path.join(root, "runtime/service-observer"), "fixture");
  await chmod(path.join(root, "runtime/service-observer"), 0o700);
  const layout = runtimeInstallLayout({
    platform: "darwin",
    home: "/Users/example",
    installRoot: "/Users/example/runtime/current",
  });
  const artifact = { digest: "a".repeat(64), version: "1.0.0", root };
  const plans = new BackgroundPlanRegistry(
    { userId: "local", runtimeId: "stable" },
    layout,
    501,
  );
  const plan = plans.resolve(plans.create("enable", 0, artifact).intent);
  const observe = vi.fn(async () => ({
    schemaVersion: 1 as const,
    systemEligibility: "registered" as const,
    code: "system_eligibility_observed",
  }));
  const verifyArtifact = vi.fn(async () => artifact);
  return { plan, observe, verifyArtifact };
}
describe("planned system registration", () => {
  it("checks artifact and declaration around the limited OS observation", async () => {
    const f = await fixture();
    const inspectDeclaration = vi.fn(async (_layout, options) => ({
      serviceId: "com.tencent.onememory.runtime",
      file: "managed" as const,
      registration: await options.observe(),
      runtime: "not_checked" as const,
      reason: null,
    }));
    expect(
      await inspectPlannedBackgroundRegistration(f.plan, {
        legacy: "not_registered",
        ...f,
        inspectDeclaration,
      }),
    ).toMatchObject({ registration: "registered", runtime: "not_checked" });
    expect(f.observe).toHaveBeenCalledTimes(1);
    expect(f.verifyArtifact).toHaveBeenCalledTimes(2);
    expect(inspectDeclaration).toHaveBeenCalledTimes(2);
  });
  it("artifact change after observation invalidates the result", async () => {
    const f = await fixture();
    f.verifyArtifact
      .mockResolvedValueOnce(f.plan.artifact)
      .mockResolvedValueOnce({ ...f.plan.artifact, digest: "b".repeat(64) });
    const inspectDeclaration = vi.fn(async (_layout, options) => ({
      serviceId: "com.tencent.onememory.runtime",
      file: "managed" as const,
      registration: await options.observe(),
      runtime: "not_checked" as const,
      reason: null,
    }));
    expect(
      (
        await inspectPlannedBackgroundRegistration(f.plan, {
          legacy: "not_registered",
          ...f,
          inspectDeclaration,
        })
      ).registration,
    ).toBe("unknown");
  });
  it("never invokes helper if artifact or legacy registration is unverifiable", async () => {
    const f = await fixture();
    f.verifyArtifact.mockRejectedValueOnce(Error("private path"));
    const result = await inspectPlannedBackgroundRegistration(f.plan, {
      legacy: "unknown",
      ...f,
    });
    expect(result.registration).toBe("unknown");
    expect(f.observe).not.toHaveBeenCalled();
    expect(JSON.stringify(result)).not.toContain("private");
  });
});
