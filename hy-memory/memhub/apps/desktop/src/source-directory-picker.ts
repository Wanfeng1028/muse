import path from "node:path";
import type {
  BrowserWindow,
  IpcMainInvokeEvent,
  OpenDialogOptions,
  OpenDialogReturnValue,
} from "electron";

export interface SourceDirectorySelection {
  cancelled: boolean;
  path: string | null;
}

export interface SourceDirectoryPickerOptions {
  requireWindow(event: IpcMainInvokeEvent): BrowserWindow;
  showOpenDialog(
    window: BrowserWindow,
    options: OpenDialogOptions,
  ): Promise<OpenDialogReturnValue>;
}

export class SourceDirectoryPicker {
  private readonly pending = new Map<BrowserWindow, () => void>();
  private disposed = false;

  constructor(private readonly options: SourceDirectoryPickerOptions) {}

  async pick(
    event: IpcMainInvokeEvent,
    sourceId: unknown,
  ): Promise<SourceDirectorySelection> {
    if (this.disposed) throw new Error("source_directory_picker_unavailable");
    if (typeof sourceId !== "string" || !Object.hasOwn(sourceLabels, sourceId))
      throw new Error("source_directory_picker_source_unsupported");
    const window = this.options.requireWindow(event);
    if (this.pending.has(window))
      throw new Error("source_directory_picker_busy");
    const contents = window.webContents;
    const frame = contents.mainFrame;
    const url = frame.url;
    let invalidated = false;
    let rejectChanged!: (error: Error) => void;
    const changed = new Promise<never>((_, reject) => {
      rejectChanged = reject;
    });
    const cleanup = () => {
      window.removeListener("closed", invalidate);
      contents.removeListener("destroyed", invalidate);
      contents.removeListener("render-process-gone", invalidate);
      contents.removeListener("did-start-navigation", navigation);
    };
    const invalidate = () => {
      if (invalidated) return;
      invalidated = true;
      cleanup();
      rejectChanged(new Error("source_directory_picker_context_changed"));
    };
    const navigation = (details: { isMainFrame: boolean }) => {
      if (details.isMainFrame) invalidate();
    };
    window.on("closed", invalidate);
    contents.on("destroyed", invalidate);
    contents.on("render-process-gone", invalidate);
    contents.on("did-start-navigation", navigation);
    this.pending.set(window, invalidate);

    let dialog: Promise<OpenDialogReturnValue>;
    try {
      dialog = this.options.showOpenDialog(window, {
        title: `Select ${sourceLabels[sourceId]} history directory`,
        properties: ["openDirectory"],
      });
    } catch {
      dialog = Promise.reject(new Error("source_directory_picker_unavailable"));
    }
    const native = dialog.catch(() => {
      throw new Error("source_directory_picker_unavailable");
    });
    const release = () => {
      if (this.pending.get(window) === invalidate) this.pending.delete(window);
    };
    // Navigation rejects promptly, but the native sheet may still be open.
    // Do not allow another picker until that original sheet actually settles.
    void native.then(release, release);
    try {
      const result = await Promise.race([native, changed]);
      try {
        if (
          invalidated ||
          this.disposed ||
          this.options.requireWindow(event) !== window ||
          contents.mainFrame !== frame ||
          frame.url !== url
        )
          throw new Error("changed");
      } catch {
        throw new Error("source_directory_picker_context_changed");
      }
      if (!result || typeof result !== "object")
        throw new Error("source_directory_picker_result_invalid");
      if (result.canceled === true) return { cancelled: true, path: null };
      if (
        result.canceled !== false ||
        !Array.isArray(result.filePaths) ||
        result.filePaths.length !== 1 ||
        typeof result.filePaths[0] !== "string" ||
        !path.isAbsolute(result.filePaths[0]) ||
        result.filePaths[0].includes("\0")
      )
        throw new Error("source_directory_picker_result_invalid");
      return { cancelled: false, path: result.filePaths[0] };
    } finally {
      cleanup();
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const invalidate of this.pending.values()) invalidate();
    this.pending.clear();
  }
}

const sourceLabels: Record<string, string> = {
  workbuddy: "WorkBuddy",
  cursor: "Cursor",
  "claude-code": "Claude Code",
  codex: "Codex",
};
