import type { HealthResponse } from "@one-memory/contracts";
import { describe, expect, it, vi } from "vitest";

import type { DiagnosticInput } from "./diagnostic-log.js";
import {
  type RuntimeConnection,
  RuntimeSupervisor,
} from "./runtime-supervisor.js";

const health: HealthResponse = {
  status: "ok",
  service: "one-memory-core",
  version: "1.0.0",
  instance_id: "runtime-test",
};

function fixture(options: { sidecarStartFails?: boolean } = {}) {
  const events: string[] = [];
  const core = {
    instanceId: "runtime-test",
    apiToken: "runtime-token",
    port: 8765,
    start: vi.fn(async () => {
      events.push("core:start");
      return health;
    }),
    stop: vi.fn(async () => {
      events.push("core:stop");
    }),
  };
  const connections: RuntimeConnection[] = [];
  const sidecar = {
    start: vi.fn(async () => {
      events.push("sidecar:start");
      if (options.sidecarStartFails) throw new Error("sidecar failed");
    }),
    stop: vi.fn(async () => {
      events.push("sidecar:stop");
    }),
  };
  let reportFault: (code: string) => void = () => undefined;
  const supervisor = new RuntimeSupervisor({
    core,
    createSidecar(connection, fault) {
      connections.push(connection);
      reportFault = fault;
      return sidecar;
    },
  });
  return {
    supervisor,
    core,
    sidecar,
    events,
    connections,
    reportFault: (code: string) => reportFault(code),
  };
}

it("records a Core startup failure without leaking its message", async () => {
  const logged: DiagnosticInput[] = [];
  const core = {
    instanceId: "runtime-test",
    apiToken: "secret-token",
    port: 8765,
    start: vi.fn(async () => {
      throw new Error("private provider response");
    }),
    stop: vi.fn(async () => undefined),
  };
  const supervisor = new RuntimeSupervisor({
    core,
    createSidecar: vi.fn(),
    diagnostics: { log: async (event) => void logged.push(event) },
  });
  await expect(supervisor.start()).rejects.toThrow("private provider response");
  expect(logged.at(-1)).toMatchObject({
    event: "runtime.start_failed",
    error_code: "runtime_start_failed",
    error_type: "Error",
  });
  expect(JSON.stringify(logged)).not.toContain("private provider response");
  expect(core.stop).not.toHaveBeenCalled();
});

describe("RuntimeSupervisor", () => {
  it("drains sidecar operations before stopping their Core", async () => {
    const value = fixture();
    let finish!: () => void;
    value.sidecar.stop.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    await value.supervisor.start();
    const stopping = value.supervisor.stop();
    await Promise.resolve();
    expect(value.core.stop).not.toHaveBeenCalled();
    finish();
    await stopping;
    expect(value.core.stop).toHaveBeenCalledOnce();
  });
  it("starts Core before the sidecar and publishes one connection", async () => {
    const value = fixture();

    await expect(value.supervisor.start()).resolves.toEqual(health);

    expect(value.events).toEqual(["core:start", "sidecar:start"]);
    expect(value.connections).toEqual([
      {
        coreBaseUrl: "http://127.0.0.1:8765",
        coreApiToken: "runtime-token",
        instanceId: "runtime-test",
      },
    ]);
    expect(value.supervisor.connection).toEqual(value.connections[0]);
  });

  it("retains the sidecar and Core after a failed drain so stop can retry", async () => {
    const value = fixture();
    await value.supervisor.start();
    value.sidecar.stop.mockRejectedValueOnce(Error("drain failed"));
    await expect(value.supervisor.stop()).rejects.toThrow("drain failed");
    expect(value.core.stop).not.toHaveBeenCalled();
    await expect(value.supervisor.start()).rejects.toThrow("already started");
    await value.supervisor.stop();
    expect(value.sidecar.stop).toHaveBeenCalledTimes(2);
    expect(value.core.stop).toHaveBeenCalledOnce();
  });

  it("shares concurrent stops and rejects start while Core is stopping", async () => {
    const value = fixture();
    let finish!: () => void;
    value.core.stop.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    const first = value.supervisor.stop();
    const second = value.supervisor.stop();
    await Promise.resolve();
    await expect(value.supervisor.start()).rejects.toThrow("already started");
    expect(value.core.stop).toHaveBeenCalledOnce();
    finish();
    await Promise.all([first, second]);
  });

  it("keeps Core alive when failed startup cannot drain the sidecar", async () => {
    const value = fixture({ sidecarStartFails: true });
    value.sidecar.stop.mockRejectedValueOnce(Error("drain failed"));
    await expect(value.supervisor.start()).rejects.toThrow("drain failed");
    expect(value.core.stop).not.toHaveBeenCalled();
    await value.supervisor.stop();
    expect(value.core.stop).toHaveBeenCalledOnce();
  });

  it("stops the sidecar and releases the Core together", async () => {
    const value = fixture();
    await value.supervisor.start();

    await value.supervisor.stop();

    expect(value.events).toEqual([
      "core:start",
      "sidecar:start",
      "sidecar:stop",
      "core:stop",
    ]);
    expect(() => value.supervisor.connection).toThrow("not running");
  });

  it("restarts the same Core and sidecar instead of creating a second runtime", async () => {
    const value = fixture();
    await value.supervisor.start();

    await expect(value.supervisor.restart()).resolves.toEqual(health);

    expect(value.events).toEqual([
      "core:start",
      "sidecar:start",
      "sidecar:stop",
      "core:stop",
      "core:start",
      "sidecar:start",
    ]);
    expect(value.connections).toHaveLength(2);
    expect(value.connections[1]).toEqual(value.connections[0]);
  });

  it("releases an attached or owned Core when the sidecar cannot start", async () => {
    const value = fixture({ sidecarStartFails: true });

    await expect(value.supervisor.start()).rejects.toThrow("sidecar failed");

    expect(value.events).toEqual([
      "core:start",
      "sidecar:start",
      "sidecar:stop",
      "core:stop",
    ]);
    expect(() => value.supervisor.connection).toThrow("not running");
  });

  it("does not start twice", async () => {
    const value = fixture();
    await value.supervisor.start();

    await expect(value.supervisor.start()).rejects.toThrow("already started");
  });

  // Contract: a sidecar fault after startup
  // must NOT kill the Runtime. It is captured as a sidecar failure state so
  // background-health can report `broker=unhealthy` + overall `degraded`
  // instead of the daemon simply vanishing and reporting `stopped`.
  it("captures a post-start sidecar fault instead of letting it escape", async () => {
    const value = fixture();
    await value.supervisor.start();
    expect(value.supervisor.sidecarState).toBe("running");

    // The sidecar reporting its own fault is the in-process capture point.
    value.reportFault("broker_request_handler_failed");

    expect(value.supervisor.sidecarState).toBe("failed");
    expect(value.supervisor.sidecarFaultState).toMatchObject({
      code: "broker_request_handler_failed",
    });
    // The Runtime must still be usable: connection stays published and Core
    // is untouched, because `degraded` means "outer alive, capability lost".
    expect(value.supervisor.connection.instanceId).toBe("runtime-test");
    expect(value.core.stop).not.toHaveBeenCalled();
  });

  it("keeps only the first sidecar fault so a fault loop cannot grow state", async () => {
    const value = fixture();
    await value.supervisor.start();
    value.reportFault("first");
    value.reportFault("second");
    expect(value.supervisor.sidecarFaultState).toMatchObject({ code: "first" });
  });

  it("does not report a sidecar fault for a clean drain", async () => {
    const value = fixture();
    await value.supervisor.start();
    await value.supervisor.stop();
    expect(value.supervisor.sidecarState).toBe("stopped");
    expect(value.supervisor.sidecarFaultState).toBeNull();
  });
});
