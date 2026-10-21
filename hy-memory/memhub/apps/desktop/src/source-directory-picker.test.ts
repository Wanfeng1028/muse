import { EventEmitter } from "node:events";
import path from "node:path";
import type {
  BrowserWindow,
  IpcMainInvokeEvent,
  OpenDialogOptions,
  OpenDialogReturnValue,
} from "electron";
import { describe, expect, it, vi } from "vitest";
import { SourceDirectoryPicker } from "./source-directory-picker";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function setup() {
  const parent = Object.assign(new EventEmitter(), {
    webContents: Object.assign(new EventEmitter(), {
      mainFrame: { url: "one-memory://app/index.html" },
    }),
  });
  const window = parent as unknown as BrowserWindow;
  const event = {
    sender: parent.webContents,
    senderFrame: parent.webContents.mainFrame,
  } as unknown as IpcMainInvokeEvent;
  const result = deferred<OpenDialogReturnValue>();
  const showOpenDialog = vi.fn(
    (_window: BrowserWindow, _options: OpenDialogOptions) => result.promise,
  );
  const requireWindow = vi.fn((_event: IpcMainInvokeEvent) => window);
  const picker = new SourceDirectoryPicker({ requireWindow, showOpenDialog });
  const selected = path.resolve("/unused/picker-only/with spaces");
  return {
    parent,
    window,
    event,
    result,
    showOpenDialog,
    requireWindow,
    picker,
    selected,
  };
}

describe("source directory picker", () => {
  it.each(["workbuddy", "cursor", "claude-code", "codex"])(
    "opens only one parented directory dialog for %s and returns the exact path",
    async (sourceId) => {
      const f = setup();
      const pending = f.picker.pick(f.event, sourceId);
      await Promise.resolve();
      expect(f.showOpenDialog).toHaveBeenCalledOnce();
      expect(f.showOpenDialog.mock.calls[0]).toEqual([
        f.window,
        expect.objectContaining({ properties: ["openDirectory"] }),
      ]);
      const options = f.showOpenDialog.mock.calls[0]?.[1];
      expect(options).not.toHaveProperty("defaultPath");
      expect(options).not.toHaveProperty("securityScopedBookmarks");
      f.result.resolve({ canceled: false, filePaths: [f.selected] });
      await expect(pending).resolves.toEqual({
        cancelled: false,
        path: f.selected,
      });
      expect(f.requireWindow).toHaveBeenCalledTimes(2);
      expect(f.parent.listenerCount("closed")).toBe(0);
      expect(f.parent.webContents.listenerCount("did-start-navigation")).toBe(
        0,
      );
    },
  );

  it.each(["openclaw", "chatgpt-export", "Cursor", "", null, {}, ["cursor"]])(
    "rejects an unsupported source without opening a dialog: %j",
    async (sourceId) => {
      const f = setup();
      await expect(f.picker.pick(f.event, sourceId)).rejects.toThrow(
        "source_directory_picker_source_unsupported",
      );
      expect(f.showOpenDialog).not.toHaveBeenCalled();
    },
  );

  it("returns cancellation with no path and releases the single-flight slot", async () => {
    const f = setup();
    f.result.resolve({ canceled: true, filePaths: [f.selected] });
    await expect(f.picker.pick(f.event, "cursor")).resolves.toEqual({
      cancelled: true,
      path: null,
    });
    await expect(f.picker.pick(f.event, "codex")).resolves.toEqual({
      cancelled: true,
      path: null,
    });
    expect(f.showOpenDialog).toHaveBeenCalledTimes(2);
  });

  it.each(
    [[], ["relative/path"], [""], ["/bad\0path"], ["/one", "/two"]].map(
      (filePaths) => ({ filePaths }),
    ),
  )(
    "rejects malformed or multiple selected paths: $filePaths",
    async ({ filePaths }) => {
      const f = setup();
      f.result.resolve({ canceled: false, filePaths });
      await expect(f.picker.pick(f.event, "cursor")).rejects.toThrow(
        "source_directory_picker_result_invalid",
      );
    },
  );

  it.each([null, undefined, {}, { canceled: "false", filePaths: ["/unused"] }])(
    "reports invalid native payload %j without exposing native data",
    async (value) => {
      const f = setup();
      f.result.resolve(value as unknown as OpenDialogReturnValue);
      await expect(f.picker.pick(f.event, "cursor")).rejects.toThrow(
        "source_directory_picker_result_invalid",
      );
      expect(f.parent.webContents.eventNames()).toEqual([]);
    },
  );

  it("keeps independent owned windows separate without opening twice in either", async () => {
    const first = setup(),
      second = setup();
    first.requireWindow.mockImplementation((event) =>
      event === first.event ? first.window : second.window,
    );
    first.showOpenDialog.mockImplementation((window) =>
      window === first.window ? first.result.promise : second.result.promise,
    );
    const left = first.picker.pick(first.event, "cursor");
    const right = first.picker.pick(second.event, "codex");
    await expect(first.picker.pick(second.event, "workbuddy")).rejects.toThrow(
      "source_directory_picker_busy",
    );
    first.result.resolve({ canceled: true, filePaths: [] });
    second.result.resolve({ canceled: true, filePaths: [] });
    await expect(left).resolves.toEqual({ cancelled: true, path: null });
    await expect(right).resolves.toEqual({ cancelled: true, path: null });
    expect(first.showOpenDialog).toHaveBeenCalledTimes(2);
  });

  it("cleans up a synchronous native dialog failure and allows retry", async () => {
    const f = setup();
    f.showOpenDialog.mockImplementationOnce(() => {
      throw new Error("native private failure");
    });
    await expect(f.picker.pick(f.event, "cursor")).rejects.toThrow(
      /^source_directory_picker_unavailable$/,
    );
    expect(f.parent.webContents.eventNames()).toEqual([]);
    f.result.resolve({ canceled: true, filePaths: [] });
    await expect(f.picker.pick(f.event, "cursor")).resolves.toEqual({
      cancelled: true,
      path: null,
    });
  });

  it("invalidates even if navigation occurs synchronously while showing the dialog", async () => {
    const f = setup();
    f.showOpenDialog.mockImplementation(() => {
      f.parent.webContents.emit("did-start-navigation", { isMainFrame: true });
      return f.result.promise;
    });
    const pending = f.picker.pick(f.event, "cursor");
    f.result.resolve({ canceled: false, filePaths: [f.selected] });
    await expect(pending).rejects.toThrow(
      "source_directory_picker_context_changed",
    );
  });

  it("rejects concurrent requests, including another source in the same window", async () => {
    const f = setup();
    const pending = f.picker.pick(f.event, "cursor");
    await expect(f.picker.pick(f.event, "workbuddy")).rejects.toThrow(
      "source_directory_picker_busy",
    );
    f.result.resolve({ canceled: true, filePaths: [] });
    await pending;
    expect(f.showOpenDialog).toHaveBeenCalledOnce();
  });

  it("does not open a dialog when the trusted window resolver rejects", async () => {
    const f = setup();
    f.requireWindow.mockImplementation(() => {
      throw new Error("untrusted");
    });
    await expect(f.picker.pick(f.event, "cursor")).rejects.toThrow();
    expect(f.showOpenDialog).not.toHaveBeenCalled();
  });

  it.each(["navigation", "closed", "destroyed", "crashed"])(
    "rejects promptly on %s, discards late results and removes listeners",
    async (kind) => {
      const f = setup();
      const pending = f.picker.pick(f.event, "cursor");
      const rejected = expect(pending).rejects.toThrow(
        "source_directory_picker_context_changed",
      );
      if (kind === "navigation")
        f.parent.webContents.emit("did-start-navigation", {
          isMainFrame: true,
        });
      else if (kind === "closed") f.parent.emit("closed");
      else
        f.parent.webContents.emit(
          kind === "crashed" ? "render-process-gone" : "destroyed",
        );
      await rejected;
      await expect(f.picker.pick(f.event, "codex")).rejects.toThrow(
        "source_directory_picker_busy",
      );
      expect(f.parent.listenerCount("closed")).toBe(0);
      expect(f.parent.webContents.eventNames()).toEqual([]);
      f.result.resolve({ canceled: false, filePaths: [f.selected] });
      await Promise.resolve();
      await Promise.resolve();
      f.picker.dispose();
    },
  );

  it("rejects an A-B-A main-frame navigation even when the URL returns unchanged", async () => {
    const f = setup();
    const pending = f.picker.pick(f.event, "cursor");
    const rejected = expect(pending).rejects.toThrow(
      "source_directory_picker_context_changed",
    );
    f.parent.webContents.emit("did-start-navigation", {
      isMainFrame: true,
      url: "one-memory://app/other",
    });
    f.parent.webContents.mainFrame.url = "one-memory://app/index.html";
    f.result.resolve({ canceled: false, filePaths: [f.selected] });
    await rejected;
  });

  it("does not invalidate a trusted top-frame selection for an unrelated child-frame navigation", async () => {
    const f = setup();
    const pending = f.picker.pick(f.event, "cursor");
    f.parent.webContents.emit("did-start-navigation", { isMainFrame: false });
    f.result.resolve({ canceled: false, filePaths: [f.selected] });
    await expect(pending).resolves.toEqual({
      cancelled: false,
      path: f.selected,
    });
  });

  it.each(["url", "frame", "owner", "trust"])(
    "revalidates %s after the native dialog resolves, even without a notification",
    async (kind) => {
      const f = setup();
      const pending = f.picker.pick(f.event, "cursor");
      if (kind === "url")
        f.parent.webContents.mainFrame.url = "one-memory://app/other";
      else if (kind === "frame")
        f.parent.webContents.mainFrame = { url: "one-memory://app/index.html" };
      else if (kind === "owner")
        f.requireWindow.mockReturnValue({} as BrowserWindow);
      else
        f.requireWindow.mockImplementation(() => {
          throw new Error("destroyed");
        });
      f.result.resolve({ canceled: false, filePaths: [f.selected] });
      await expect(pending).rejects.toThrow(
        "source_directory_picker_context_changed",
      );
    },
  );

  it("does not expose dialog errors or leave the window busy after rejection", async () => {
    const f = setup();
    f.result.reject(new Error("private native error /sensitive/path"));
    await expect(f.picker.pick(f.event, "cursor")).rejects.toThrow(
      /^source_directory_picker_unavailable$/,
    );
    f.showOpenDialog.mockResolvedValue({ canceled: true, filePaths: [] });
    await expect(f.picker.pick(f.event, "cursor")).resolves.toEqual({
      cancelled: true,
      path: null,
    });
    expect(f.parent.webContents.eventNames()).toEqual([]);
  });

  it("disposes pending requests and never reopens after shutdown", async () => {
    const f = setup();
    const pending = f.picker.pick(f.event, "cursor");
    const rejected = expect(pending).rejects.toThrow(
      "source_directory_picker_context_changed",
    );
    f.picker.dispose();
    f.picker.dispose();
    await rejected;
    await expect(f.picker.pick(f.event, "cursor")).rejects.toThrow(
      "source_directory_picker_unavailable",
    );
    expect(f.parent.webContents.eventNames()).toEqual([]);
    f.result.resolve({ canceled: false, filePaths: [f.selected] });
  });
});
