import { EventEmitter } from "node:events";
import type { ConnectionClient } from "@one-memory/runtime-control";
import type { IpcMainInvokeEvent } from "electron";
import { afterEach, expect, it, vi } from "vitest";
import { installConnectionSetupIpc } from "./connection-setup-ipc";

const local = vi.hoisted(() => {
  const forbidden = () =>
    vi.fn(() => {
      throw Error("LOCAL_IO_FORBIDDEN");
    });
  return {
    lstat: forbidden(),
    realpath: forbidden(),
    axios: forbidden(),
    open: forbidden(),
    initialize: forbidden(),
  };
});
vi.mock("node:fs/promises", async (original) => ({
  ...(await original<typeof import("node:fs/promises")>()),
  lstat: local.lstat,
  realpath: local.realpath,
}));
vi.mock("axios", () => ({ default: { create: local.axios } }));
vi.mock(
  "../../../packages/runtime-control/src/connection-controller.js",
  () => ({
    ConnectionController: { open: local.open, initialize: local.initialize },
  }),
);

type Options = Parameters<typeof installConnectionSetupIpc>[0];
type Preview = Awaited<ReturnType<ConnectionClient["preview"]>>;
type Result = Awaited<ReturnType<ConnectionClient["execute"]>>;
const selection = { syncSourceIds: ["codex"], hostSourceIds: ["codex"] };
const preview: Preview = {
  planId: "plan-one",
  operationId: "operation-one",
  digest: "a".repeat(64),
  items: [
    {
      id: "sync:codex",
      kind: "sync",
      sourceIds: ["codex"],
      restoresRevoked: false,
    },
  ],
};
const execution = {
  planId: preview.planId,
  digest: preview.digest,
  userConfirmed: true as const,
};
const owner = {
  userId: "local",
  runtimeId: "private-runtime",
  operationId: preview.operationId,
  intentDigest: "b".repeat(64),
};
const host = {
  hostId: "codex",
  installationId: "installation-one",
  permissionRevision: 2,
  layoutDigest: "c".repeat(64),
  installationDigest: "d".repeat(64),
};
const directSyncItem = {
  id: "sync:codex",
  kind: "sync",
  state: "succeeded",
  intentDigest: owner.intentDigest,
  receipt: null,
} as const;
const persistentItems: Result["items"] = [
  {
    id: "install:codex",
    kind: "install",
    state: "succeeded",
    intentDigest: owner.intentDigest,
    receipt: { ...owner, itemId: "install:codex", kind: "install", host },
  },
  {
    id: "grant:codex",
    kind: "readGrant",
    state: "succeeded",
    intentDigest: owner.intentDigest,
    receipt: {
      ...owner,
      itemId: "grant:codex",
      kind: "readGrant",
      host,
      allowedTools: ["om_recall"],
      allowedScopes: ["source:codex"],
    },
  },
];
const result: Result = {
  mode: "execute",
  operationId: preview.operationId,
  planDigest: preview.digest,
  state: "completed",
  recovery: "persistent",
  cancelled: false,
  items: [directSyncItem, ...persistentItems],
  skipped: [{ id: "sync:claude", state: "unchanged" }],
} as unknown as Result;
const journal = {
  schemaVersion: 1 as const,
  userId: owner.userId,
  runtimeId: owner.runtimeId,
  operationId: result.operationId,
  planDigest: "e".repeat(64),
  revision: 3,
  items: persistentItems,
};
const publicItems = [
  {
    id: "install:codex",
    kind: "install",
    state: "succeeded",
    receipt: {
      kind: "install",
      hostId: "codex",
      installationId: "installation-one",
      permissionRevision: 2,
    },
  },
  {
    id: "grant:codex",
    kind: "readGrant",
    state: "succeeded",
    receipt: {
      kind: "readGrant",
      hostId: "codex",
      installationId: "installation-one",
      permissionRevision: 2,
      allowedTools: ["om_recall"],
      allowedScopes: ["source:codex"],
    },
  },
];
const publicExecutionItems = [
  {
    id: "sync:codex",
    kind: "sync",
    state: "succeeded",
    receipt: null,
  },
  ...publicItems,
];

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
const fixtures: Array<{
  bridge: ReturnType<typeof installConnectionSetupIpc>;
  forbidden: ReturnType<typeof vi.fn>;
  window: EventEmitter & { webContents: EventEmitter };
}> = [];
function fixture(platform: NodeJS.Platform = "darwin") {
  const handlers = new Map<
    string,
    (event: IpcMainInvokeEvent, ...args: unknown[]) => Promise<unknown>
  >();
  const windows = new Map<
    IpcMainInvokeEvent,
    ReturnType<typeof newWindow>["window"]
  >();
  function newWindow() {
    const frame = { url: "one-memory://app/index.html" };
    const sender = Object.assign(new EventEmitter(), { mainFrame: frame });
    const window = Object.assign(new EventEmitter(), { webContents: sender });
    const event = {
      sender,
      senderFrame: frame,
    } as unknown as IpcMainInvokeEvent;
    windows.set(event, window);
    return {
      window,
      event,
      frame,
      call: (channel: string, ...args: unknown[]) => {
        const handler = handlers.get(`one-memory:connection-setup-${channel}`);
        if (!handler) throw Error("missing handler");
        return handler(event, ...args);
      },
    };
  }
  const remote = {
    capability: vi
      .fn<ConnectionClient["capability"]>()
      .mockResolvedValue({ available: true }),
    preview: vi
      .fn<ConnectionClient["preview"]>()
      .mockImplementation(async () => structuredClone(preview)),
    execute: vi
      .fn<ConnectionClient["execute"]>()
      .mockImplementation(async () => structuredClone(result)),
    receipt: vi
      .fn<ConnectionClient["receipt"]>()
      .mockImplementation(async () => structuredClone(journal)),
  };
  const forbidden = vi.fn(() => {
    throw Error("LOCAL_HOST_OR_CORE_IO");
  });
  const trusted = vi.fn((event: IpcMainInvokeEvent) => {
    const window = windows.get(event);
    if (!window || event.senderFrame?.url !== "one-memory://app/index.html")
      throw Error("PRIVATE_TRUST_ERROR");
    return window;
  });
  const options: Options = {
    ipc: {
      handle: (name, handler) => {
        handlers.set(name, handler);
      },
      removeHandler: (name) => {
        handlers.delete(name);
      },
    },
    dataDir: "/must-not-open-desktop-storage",
    getCore: forbidden,
    hostPermissions: {
      getPermission: forbidden,
      previewInstall: forbidden,
      install: forbidden,
      setPermission: forbidden,
    },
    hosts: [],
    requireTrustedWindow: trusted,
    platform,
    remote,
  };
  const bridge = installConnectionSetupIpc(options);
  const first = newWindow();
  const f = {
    ...first,
    bridge,
    remote,
    forbidden,
    trusted,
    handlers,
    windows,
    newWindow,
  };
  fixtures.push(f);
  return f;
}
afterEach(async () => {
  for (const f of fixtures.splice(0)) {
    await f.bridge.drain();
    f.bridge.dispose();
    expect(f.forbidden).not.toHaveBeenCalled();
    expect(f.window.listenerCount("closed")).toBe(0);
    expect(f.window.webContents.listenerCount("destroyed")).toBe(0);
    expect(f.window.webContents.listenerCount("did-start-navigation")).toBe(0);
  }
  for (const spy of Object.values(local)) expect(spy).not.toHaveBeenCalled();
  vi.clearAllMocks();
});

it("uses remote capability, preview, execute and receipt with public-only projection and zero local I/O", async () => {
  const f = fixture();
  expect(await f.call("capability")).toEqual({ available: true, reason: null });
  expect(await f.call("preview", selection)).toEqual(preview);
  expect(await f.call("execute", execution)).toEqual({
    operationId: result.operationId,
    planDigest: result.planDigest,
    state: "completed",
    recovery: "persistent",
    cancelled: false,
    items: publicExecutionItems,
    skipped: result.skipped,
  });
  expect(await f.call("receipt", preview.operationId)).toEqual({
    operationId: journal.operationId,
    planDigest: journal.planDigest,
    revision: 3,
    state: "completed",
    items: publicItems,
  });
  expect(f.remote.preview).toHaveBeenCalledExactlyOnceWith(selection);
  expect(f.remote.execute).toHaveBeenCalledExactlyOnceWith(
    execution,
    expect.any(AbortSignal),
  );
  expect(f.remote.receipt).toHaveBeenCalledExactlyOnceWith(preview.operationId);
});

it("remote capability failure returns a fixed reason without leaking transport errors or falling back", async () => {
  const f = fixture();
  f.remote.capability.mockRejectedValue(Error("private-path/token"));
  expect(await f.call("capability")).toEqual({
    available: false,
    reason: "runtime_unavailable",
  });
});

it.each(["capability", "preview", "execute", "receipt"])(
  "rejects untrusted %s before remote calls",
  async (channel) => {
    const f = fixture();
    f.windows.delete(f.event);
    await expect(f.call(channel)).rejects.toThrow(
      "connection_setup_untrusted_window",
    );
    for (const fn of Object.values(f.remote)) expect(fn).not.toHaveBeenCalled();
  },
);

it("validates payloads and explicit confirmation before remote calls", async () => {
  const f = fixture();
  await expect(f.call("capability", {})).rejects.toThrow("invalid_input");
  await expect(
    f.call("preview", { ...selection, path: "/private" }),
  ).rejects.toThrow("invalid_input");
  await expect(
    f.call("preview", { syncSourceIds: ["openclaw"], hostSourceIds: [] }),
  ).rejects.toThrow("invalid_input");
  await expect(
    f.call("execute", { ...execution, userConfirmed: false }),
  ).rejects.toThrow("invalid_input");
  await expect(f.call("receipt", "../escape")).rejects.toThrow("invalid_input");
  for (const fn of Object.values(f.remote)) expect(fn).not.toHaveBeenCalled();
});

it("keeps unsupported-platform guards without local I/O", async () => {
  const f = fixture("win32");
  expect(await f.call("capability")).toEqual({
    available: false,
    reason: "unsupported_platform",
  });
  await expect(f.call("preview", selection)).rejects.toThrow(
    "unsupported_platform",
  );
  expect(f.remote.capability).not.toHaveBeenCalled();
  expect(f.remote.preview).not.toHaveBeenCalled();
});

it("binds plans to one trusted window but allows GET-only receipt recovery in another", async () => {
  const f = fixture();
  await f.call("preview", selection);
  const other = f.newWindow();
  await expect(other.call("execute", execution)).rejects.toThrow(
    "plan_missing",
  );
  expect(f.remote.execute).not.toHaveBeenCalled();
  expect(await other.call("receipt", preview.operationId)).toMatchObject({
    items: publicItems,
  });
});

it("revalidates trust immediately before remote execute invocation", async () => {
  const f = fixture();
  await f.call("preview", selection);
  f.trusted.mockReturnValueOnce(f.window).mockImplementationOnce(() => {
    throw Error("late loss");
  });
  await expect(f.call("execute", execution)).rejects.toThrow("context_changed");
  expect(f.remote.execute).not.toHaveBeenCalled();
});

it.each(["navigation", "closed", "destroyed", "frame"])(
  "rejects delivery after %s during execute and retains receipt recovery",
  async (loss) => {
    const f = fixture();
    await f.call("preview", selection);
    const gate = deferred<Result>();
    f.remote.execute.mockReturnValueOnce(gate.promise);
    const pending = f.call("execute", execution);
    const rejected = expect(pending).rejects.toThrow("context_changed");
    await vi.waitFor(() => expect(f.remote.execute).toHaveBeenCalledTimes(1));
    if (loss === "navigation")
      f.window.webContents.emit("did-start-navigation");
    else if (loss === "closed") f.window.emit("closed");
    else if (loss === "destroyed") f.window.webContents.emit("destroyed");
    else Object.assign(f.event, { senderFrame: { url: f.frame.url } });
    gate.resolve(structuredClone(result));
    await rejected;
    expect(
      await f.newWindow().call("receipt", preview.operationId),
    ).toMatchObject({ state: "completed", items: publicItems });
    expect(f.remote.execute).toHaveBeenCalledExactlyOnceWith(
      execution,
      expect.any(AbortSignal),
    );
  },
);

it.each(["capability", "preview", "receipt"] as const)(
  "rejects late navigation for remote %s",
  async (channel) => {
    const f = fixture();
    const gate = deferred<never>();
    f.remote[channel].mockReturnValueOnce(gate.promise);
    const args =
      channel === "preview"
        ? [selection]
        : channel === "receipt"
          ? [preview.operationId]
          : [];
    const pending = f.call(channel, ...args);
    const rejected = expect(pending).rejects.toThrow("context_changed");
    await vi.waitFor(() => expect(f.remote[channel]).toHaveBeenCalledTimes(1));
    f.window.webContents.emit("did-start-navigation");
    gate.resolve(
      (channel === "preview"
        ? preview
        : channel === "receipt"
          ? journal
          : { available: true }) as never,
    );
    await rejected;
    await expect(f.call("execute", execution)).rejects.toThrow("plan_missing");
  },
);

it("drain waits for remote dispatch without pretending to cancel it and closes admission", async () => {
  const f = fixture();
  await f.call("preview", selection);
  const gate = deferred<Result>();
  f.remote.execute.mockReturnValueOnce(gate.promise);
  const pending = f.call("execute", execution);
  await vi.waitFor(() => expect(f.remote.execute).toHaveBeenCalledTimes(1));
  let drained = false;
  const drain = f.bridge.drain().then(() => {
    drained = true;
  });
  await Promise.resolve();
  expect(drained).toBe(false);
  expect(f.remote.execute.mock.calls[0]?.[1]?.aborted).toBe(true);
  await expect(f.call("capability")).rejects.toThrow("closing");
  gate.resolve(structuredClone(result));
  expect(await pending).toMatchObject({ cancelled: false, state: "completed" });
  await drain;
  expect(drained).toBe(true);
});

it("context loss during drain still prevents execute delivery", async () => {
  const f = fixture();
  await f.call("preview", selection);
  const gate = deferred<Result>();
  f.remote.execute.mockReturnValueOnce(gate.promise);
  const pending = f.call("execute", execution);
  const rejected = expect(pending).rejects.toThrow("context_changed");
  await vi.waitFor(() => expect(f.remote.execute).toHaveBeenCalledTimes(1));
  const drain = f.bridge.drain();
  f.windows.delete(f.event);
  gate.resolve(structuredClone(result));
  await rejected;
  await drain;
});

it("remote errors are sanitized and unknown operations are not replayed or routed locally", async () => {
  const f = fixture();
  await f.call("preview", selection);
  f.remote.execute.mockRejectedValueOnce(
    Error("connection_client_operation_unknown private-token"),
  );
  await expect(f.call("execute", execution)).rejects.toThrow(
    /^connection_setup_unavailable$/,
  );
  expect(await f.call("receipt", preview.operationId)).toMatchObject({
    state: "completed",
  });
  expect(f.remote.execute).toHaveBeenCalledTimes(1);
  f.remote.receipt.mockResolvedValueOnce(null);
  expect(await f.call("receipt", "missing")).toBeNull();
});

it("unknown journal items stay partial and invalid execution states are never projected", async () => {
  const f = fixture();
  f.remote.receipt.mockResolvedValueOnce({
    ...journal,
    items: [{ ...persistentItems[0], state: "unknown", receipt: null }],
  });
  expect(await f.call("receipt", preview.operationId)).toMatchObject({
    state: "partial",
    items: [{ id: "install:codex", state: "unknown", receipt: null }],
  });
  await f.call("preview", selection);
  f.remote.execute.mockResolvedValueOnce({
    ...result,
    state: "invalid",
  } as unknown as Result);
  await expect(f.call("execute", execution)).rejects.toThrow(
    /^connection_setup_unavailable$/,
  );
});

it.each(["capability", "preview"] as const)(
  "drain waits for pending %s and blocks its late delivery",
  async (channel) => {
    const f = fixture();
    const gate = deferred<never>();
    f.remote[channel].mockReturnValueOnce(gate.promise);
    const pending = f.call(
      channel,
      ...(channel === "preview" ? [selection] : []),
    );
    const rejected = expect(pending).rejects.toThrow("context_changed");
    await vi.waitFor(() => expect(f.remote[channel]).toHaveBeenCalledTimes(1));
    let drained = false;
    const drain = f.bridge.drain().then(() => {
      drained = true;
    });
    await Promise.resolve();
    expect(drained).toBe(false);
    gate.resolve(
      (channel === "preview" ? preview : { available: true }) as never,
    );
    await rejected;
    await drain;
    expect(drained).toBe(true);
  },
);

it("dispose removes every handler and prevents late preview from authorizing a plan", async () => {
  const f = fixture();
  const gate = deferred<Preview>();
  f.remote.preview.mockReturnValueOnce(gate.promise);
  const oldExecute = f.handlers.get("one-memory:connection-setup-execute");
  if (!oldExecute) throw Error("missing execute handler");
  const pending = f.call("preview", selection);
  const rejected = expect(pending).rejects.toThrow("context_changed");
  await vi.waitFor(() => expect(f.remote.preview).toHaveBeenCalledTimes(1));
  f.bridge.dispose();
  expect(f.handlers.size).toBe(0);
  gate.resolve(preview);
  await rejected;
  await expect(oldExecute(f.event, execution)).rejects.toThrow("closing");
  expect(f.remote.execute).not.toHaveBeenCalled();
});

it.each(["navigation", "closed", "destroyed"])(
  "propagates abort during remote discovery so %s prevents dispatch",
  async (loss) => {
    const f = fixture();
    await f.call("preview", selection);
    const discovery = deferred<void>();
    const dispatch = vi.fn(() => structuredClone(result));
    let receivedSignal: AbortSignal | undefined;
    f.remote.execute.mockImplementationOnce(async (_input, signal) => {
      receivedSignal = signal;
      await discovery.promise;
      if (signal?.aborted) throw Error("connection_client_cancelled");
      return dispatch();
    });
    const pending = f.call("execute", execution);
    const rejected = expect(pending).rejects.toThrow(
      /^connection_setup_unavailable$/,
    );
    await vi.waitFor(() => expect(f.remote.execute).toHaveBeenCalledTimes(1));
    const before = receivedSignal?.aborted;
    if (loss === "navigation")
      f.window.webContents.emit("did-start-navigation");
    else if (loss === "closed") f.window.emit("closed");
    else f.window.webContents.emit("destroyed");
    const after = receivedSignal?.aborted;
    discovery.resolve();
    await rejected;
    expect(before).toBe(false);
    expect(after).toBe(true);
    expect(dispatch).not.toHaveBeenCalled();
  },
);
