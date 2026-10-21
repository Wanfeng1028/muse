import { describe, expect, it, vi } from "vitest";
import { inspectBackgroundHealth } from "./background-health.js";

const runtime = {
  state: "running" as const,
  code: "runtime_verified",
  instanceId: "instance-a",
  port: 8123,
};
const broker = {
  state: "running" as const,
  code: "broker_verified",
  instanceId: "instance-a",
  port: 9123,
};
function setup() {
  return {
    inspectRuntime: vi.fn(async () => ({ ...runtime })),
    inspectBroker: vi.fn(async () => ({ ...broker })),
  };
}
describe("joint background health", () => {
  it("verifies Core and Broker then rechecks the same Runtime", async () => {
    const checks = setup();
    expect(
      await inspectBackgroundHealth({ dataDir: "/tmp/isolated", ...checks }),
    ).toMatchObject({ state: "healthy", instanceId: "instance-a" });
    expect(checks.inspectRuntime).toHaveBeenCalledTimes(2);
    expect(checks.inspectBroker).toHaveBeenCalledExactlyOnceWith({
      dataDir: "/tmp/isolated",
      expectedInstanceId: "instance-a",
    });
  });
  it.each(["stopped", "unhealthy", "untrusted"] as const)(
    "Core running and Broker %s is never healthy",
    async (state) => {
      const checks = setup();
      const result = await inspectBackgroundHealth({
        dataDir: "/tmp/isolated",
        ...checks,
        inspectBroker: async () => ({ state, code: "bounded" }),
      });
      expect(result.state).toBe(
        state === "untrusted" ? "untrusted" : "degraded",
      );
    },
  );
  it.each(["stopped", "unhealthy", "untrusted"] as const)(
    "does not query Broker for Runtime %s",
    async (state) => {
      const checks = setup();
      const result = await inspectBackgroundHealth({
        dataDir: "/tmp/isolated",
        ...checks,
        inspectRuntime: async () => ({ state, code: "bounded" }),
      });
      expect(result.state).not.toBe("healthy");
      expect(checks.inspectBroker).not.toHaveBeenCalled();
    },
  );
  it("drops a broker result if Runtime restarted while checking it", async () => {
    const checks = setup();
    checks.inspectRuntime
      .mockResolvedValueOnce(runtime)
      .mockResolvedValueOnce({ ...runtime, instanceId: "instance-b" });
    const result = await inspectBackgroundHealth({
      dataDir: "/tmp/isolated",
      ...checks,
    });
    expect(result).toMatchObject({
      state: "unknown",
      code: "background_identity_changed",
    });
    expect(result.instanceId).toBeUndefined();
  });
  it("rejects an unexpected Broker instance even from injected inspection", async () => {
    const checks = setup();
    const result = await inspectBackgroundHealth({
      dataDir: "/tmp/isolated",
      ...checks,
      inspectBroker: async () => ({ ...broker, instanceId: "other" }),
    });
    expect(result.state).toBe("untrusted");
  });
  it("does not expose arbitrary exception messages", async () => {
    const result = await inspectBackgroundHealth({
      dataDir: "/tmp/isolated",
      inspectRuntime: async () => {
        throw Error("credential=private");
      },
    });
    expect(result.state).toBe("unknown");
    expect(JSON.stringify(result)).not.toContain("private");
  });
  it("does not call a running status with no identity healthy", async () => {
    const checks = setup();
    const result = await inspectBackgroundHealth({
      dataDir: "/tmp/isolated",
      ...checks,
      inspectRuntime: async () => ({ state: "running", code: "incomplete" }),
    });
    expect(result.state).toBe("untrusted");
    expect(checks.inspectBroker).not.toHaveBeenCalled();
  });

  // A sidecar (Broker) fault captured by the Runtime must be
  // reported as `degraded` with `broker=unhealthy`, never healthy and never a
  // generic `stopped` -- the outer Runtime is still alive.
  it("reports a captured sidecar failure as degraded, not healthy", async () => {
    const checks = setup();
    const result = await inspectBackgroundHealth({
      dataDir: "/tmp/isolated",
      ...checks,
      inspectRuntime: async () => ({
        ...runtime,
        sidecar: "failed" as const,
      }),
    });
    expect(result.state).toBe("degraded");
    expect(result).toMatchObject({
      code: "background_broker_failed",
      core: "running",
      broker: "unhealthy",
    });
    // No probe needed: the Runtime already attested the failure.
    expect(checks.inspectBroker).not.toHaveBeenCalled();
  });

  it("still verifies a healthy sidecar through the Broker probe", async () => {
    const checks = setup();
    const result = await inspectBackgroundHealth({
      dataDir: "/tmp/isolated",
      ...checks,
      inspectRuntime: async () => ({
        ...runtime,
        sidecar: "running" as const,
      }),
    });
    expect(result.state).toBe("healthy");
    expect(checks.inspectBroker).toHaveBeenCalledOnce();
  });
  it("holds the caller's data directory and requires service receipt", async () => {
    const checks = setup();
    await inspectBackgroundHealth({ dataDir: "/tmp/custom data ", ...checks });
    expect(checks.inspectRuntime).toHaveBeenCalledWith(
      expect.objectContaining({
        dataDir: "/tmp/custom data ",
        requireServiceReceipt: true,
      }),
    );
  });
});
