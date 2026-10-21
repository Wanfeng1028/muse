import { describe, expect, it, vi } from "vitest";

import { run } from "./cli.js";
import type { WizardPrompter } from "./init-wizard.js";

const runtime = vi.hoisted(() => ({
  inspectRuntimeStatus: vi.fn(),
  discoverRuntimeAttachment: vi.fn(),
}));
const setup = vi.hoisted(() => ({ runInteractiveModelSetup: vi.fn() }));

vi.mock("@one-memory/runtime-control", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@one-memory/runtime-control")>()),
  ...runtime,
}));
vi.mock("./interactive-model-setup.js", () => setup);

const prompt: WizardPrompter = {
  async ask() {
    return "";
  },
  async askSecret() {
    return "secret";
  },
  write() {},
};

describe("models setup command", () => {
  it("runs only on a TTY and reuses the attached Core clients", async () => {
    runtime.inspectRuntimeStatus.mockResolvedValue({
      state: "running",
      code: "runtime_verified",
      instanceId: "instance-1",
      host: "127.0.0.1",
      port: 29123,
      version: "1.2.3",
    });
    runtime.discoverRuntimeAttachment.mockResolvedValue({
      instanceId: "instance-1",
      apiToken: "test-token",
      host: "127.0.0.1",
      port: 29123,
      servicePid: 4242,
      health: {
        status: "ok",
        service: "one-memory-core",
        version: "1.2.3",
        instance_id: "instance-1",
      },
    });
    setup.runInteractiveModelSetup.mockResolvedValue({ state: "configured" });

    await expect(
      run(
        ["models", "setup"],
        {
          ONE_MEMORY_DATA_DIR: "/private/tmp/model-setup-command/data",
          ONE_MEMORY_HOST_HOME: "/private/tmp/model-setup-command/home",
        },
        { stdinIsTTY: true, wizardPrompter: prompt },
      ),
    ).resolves.toBe(0);
    expect(setup.runInteractiveModelSetup).toHaveBeenCalledOnce();
    expect(setup.runInteractiveModelSetup.mock.calls[0]?.[2]).toEqual({
      dataDir: "/private/tmp/model-setup-command/data",
      hostHome: "/private/tmp/model-setup-command/home",
      installHosts: false,
    });
  });

  it("does not prompt or touch Runtime in non-TTY or JSON mode", async () => {
    setup.runInteractiveModelSetup.mockClear();
    runtime.inspectRuntimeStatus.mockClear();
    const stdout = vi
      .spyOn(process.stdout, "write")
      .mockImplementation(() => true);
    const stderr = vi
      .spyOn(process.stderr, "write")
      .mockImplementation(() => true);
    try {
      await expect(
        run(["models", "setup"], {}, { stdinIsTTY: false }),
      ).resolves.toBe(2);
      await expect(
        run(["models", "setup", "--json"], {}, { stdinIsTTY: true }),
      ).resolves.toBe(2);
    } finally {
      stdout.mockRestore();
      stderr.mockRestore();
    }
    expect(setup.runInteractiveModelSetup).not.toHaveBeenCalled();
    expect(runtime.inspectRuntimeStatus).not.toHaveBeenCalled();
  });
});
