import { describe, expect, it, vi } from "vitest";
import { installBackgroundHealthIpc } from "./background-health-ipc";

function fixture() {
  let handler:
    | ((event: unknown, ...args: unknown[]) => Promise<unknown>)
    | undefined;
  const owner = {};
  const requireTrustedWindow = vi.fn((event: unknown) => {
    if (event !== owner) throw Error("untrusted");
    return owner;
  });
  const inspect = vi.fn(async (_options: { dataDir: string }) => ({
    state: "healthy" as const,
    code: "background_verified",
    core: "running" as const,
    broker: "running" as const,
    instanceId: "same",
  }));
  const ipc = {
    handle: vi.fn((_name: string, callback: typeof handler) => {
      handler = callback;
    }),
    removeHandler: vi.fn(),
  };
  const dispose = installBackgroundHealthIpc({
    ipc,
    dataDir: "/tmp/selected",
    requireTrustedWindow,
    inspect,
  });
  return {
    invoke: (event: unknown, ...args: unknown[]) => {
      if (!handler) throw Error("missing");
      return handler(event, ...args);
    },
    owner,
    inspect,
    ipc,
    requireTrustedWindow,
    dispose,
  };
}
describe("background health IPC", () => {
  it("revalidates the sender after an asynchronous read finishes", async () => {
    const f = fixture();
    let release: () => void = () => {};
    f.inspect.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = () =>
            resolve({
              state: "healthy",
              code: "background_verified",
              core: "running",
              broker: "running",
              instanceId: "same",
            });
        }),
    );
    const result = f.invoke(f.owner);
    f.requireTrustedWindow.mockImplementation(() => {
      throw Error("navigated");
    });
    release();
    await expect(result).rejects.toThrow("navigated");
  });
  it("reads only the main-selected data directory with no renderer options", async () => {
    const f = fixture();
    expect(f.inspect).not.toHaveBeenCalled();
    expect(await f.invoke(f.owner)).toMatchObject({ state: "healthy" });
    expect(f.inspect).toHaveBeenCalledExactlyOnceWith({
      dataDir: "/tmp/selected",
    });
    expect(f.requireTrustedWindow).toHaveBeenCalledTimes(2);
  });
  it("rejects foreign callers before inspection", async () => {
    const f = fixture();
    await expect(f.invoke({})).rejects.toThrow();
    expect(f.inspect).not.toHaveBeenCalled();
  });
  it("rejects supplied paths or command arguments", async () => {
    const f = fixture();
    await expect(f.invoke(f.owner, { dataDir: "/other" })).rejects.toThrow(
      "arguments",
    );
    expect(f.inspect).not.toHaveBeenCalled();
  });
  it("rejects late result after navigation or disposal", async () => {
    const f = fixture();
    let release: () => void = () => {};
    f.inspect.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = () =>
            resolve({
              state: "healthy",
              code: "background_verified",
              core: "running",
              broker: "running",
              instanceId: "same",
            });
        }),
    );
    const result = f.invoke(f.owner);
    f.dispose();
    release();
    await expect(result).rejects.toThrow("closed");
    expect(f.ipc.removeHandler).toHaveBeenCalledTimes(1);
  });
  it("coalesces simultaneous trusted reads and clears the completed flight", async () => {
    const f = fixture();
    let release: () => void = () => {};
    f.inspect.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = () =>
            resolve({
              state: "healthy",
              code: "background_verified",
              core: "running",
              broker: "running",
              instanceId: "same",
            });
        }),
    );
    const first = f.invoke(f.owner),
      second = f.invoke(f.owner);
    release();
    await Promise.all([first, second]);
    expect(f.inspect).toHaveBeenCalledTimes(1);
    await f.invoke(f.owner);
    expect(f.inspect).toHaveBeenCalledTimes(2);
  });
});
