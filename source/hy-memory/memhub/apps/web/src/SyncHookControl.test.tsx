// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RecallHostStatus } from "./global";
import {
  SyncHookControl,
  type SyncHookPreview,
  type SyncHookStatus,
} from "./SyncHookControl";

const installationId = "00000000-0000-4000-8000-000000000001";
const fingerprint = "a".repeat(64);
function permission() {
  return {
    hostId: "claude-code",
    state: "install-only" as const,
    reason: null,
    receipt: {
      hostId: "claude-code",
      installationId,
      revision: 1,
      status: "install-only" as const,
      allowedTools: [],
      allowedScopes: [],
    },
  };
}
const host = (change: Partial<RecallHostStatus> = {}): RecallHostStatus => ({
  hostId: "claude-code",
  label: "Claude Code",
  present: true,
  installed: true,
  selfCheck: null,
  skillDrift: null,
  permission: {
    hostId: "claude-code",
    state: "install-only",
    reason: null,
    receipt: {
      hostId: "claude-code",
      installationId,
      revision: 1,
      status: "install-only",
      allowedTools: [],
      allowedScopes: [],
    },
  },
  ...change,
});
const status = (
  state: SyncHookStatus["state"] = "not-installed",
): SyncHookStatus => ({ hostId: "claude-code", state, reason: null });
const preview = (
  operation: "install" | "uninstall" = "install",
): SyncHookPreview => ({
  hostId: "claude-code",
  operation,
  installationId,
  revision: 1,
  fingerprint,
  files: [
    {
      path: "/synthetic/claude/settings.json",
      action: "update",
      owner: "host",
    },
    {
      path: "/synthetic/claude/.one-memory/hook.mjs",
      action: operation === "install" ? "create" : "remove",
      owner: "one-memory",
    },
  ],
});
const button = (name: string) =>
  screen.getByRole<HTMLButtonElement>("button", { name });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function setup(
  initial: SyncHookStatus["state"] = "not-installed",
  initialHost = host(),
) {
  const getSyncHookStatus = vi.fn().mockResolvedValue(status(initial));
  const previewSyncHook = vi
    .fn()
    .mockImplementation(
      async (_host: string, operation: "install" | "uninstall") =>
        preview(operation),
    );
  const applySyncHook = vi
    .fn()
    .mockImplementation(async (_host: string, input: { operation: string }) =>
      status(input.operation === "install" ? "installed" : "not-installed"),
    );
  window.oneMemory = {
    getSyncHookStatus,
    previewSyncHook,
    applySyncHook,
  } as unknown as NonNullable<Window["oneMemory"]>;
  const view = render(<SyncHookControl host={initialHost} />);
  return {
    ...view,
    getSyncHookStatus,
    previewSyncHook,
    applySyncHook,
    update: (value = initialHost, disabled = false) =>
      view.rerender(<SyncHookControl host={value} disabled={disabled} />),
  };
}
async function open(name = "安装同步 Hook") {
  await userEvent.click(await screen.findByRole("button", { name }));
  return screen.findByRole("dialog");
}
afterEach(() => {
  cleanup();
  delete window.oneMemory;
});

describe("SyncHookControl", () => {
  it.each(["all", "getSyncHookStatus", "previewSyncHook", "applySyncHook"])(
    "hides older shells missing %s",
    (missing) => {
      const api = setup();
      if (missing === "all") delete window.oneMemory;
      else
        delete (window.oneMemory as unknown as Record<string, unknown>)[
          missing
        ];
      api.update();
      expect(
        screen.queryByRole("region", { name: "Claude Code 同步 Hook" }),
      ).toBeNull();
      expect(api.applySyncHook).not.toHaveBeenCalled();
    },
  );
  it.each([
    host({ hostId: "cursor", label: "Cursor" }),
    host({ installed: false }),
    host({ present: false }),
  ])("does not offer an unlinked or other host", (value) => {
    const api = setup("not-installed", value);
    expect(api.container.textContent).toBe("");
    expect(api.getSyncHookStatus).not.toHaveBeenCalled();
  });
  it("shows display-only hook state, without claiming sync or calling a write", async () => {
    const api = setup("installed");
    expect(await screen.findByText("同步 Hook 已安装")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "同步 Hook 已安装" }),
    ).toBeNull();
    expect(screen.queryByText("持续同步已开启")).toBeNull();
    expect(api.applySyncHook).not.toHaveBeenCalled();
    expect(api.previewSyncHook).not.toHaveBeenCalled();
  });
  it("previews files and requires explicit confirmation before exactly one install", async () => {
    const api = setup();
    const dialog = await open();
    expect(api.previewSyncHook).toHaveBeenCalledExactlyOnceWith(
      "claude-code",
      "install",
    );
    expect(
      within(dialog).getByText("/synthetic/claude/settings.json"),
    ).toBeTruthy();
    expect(
      within(dialog).getByText("/synthetic/claude/.one-memory/hook.mjs"),
    ).toBeTruthy();
    expect(dialog.textContent).toContain("读取与持续同步仍由来源权限控制");
    expect(button("确认安装").disabled).toBe(true);
    expect(api.applySyncHook).not.toHaveBeenCalled();
    api.getSyncHookStatus.mockResolvedValue(status("installed"));
    await userEvent.click(
      screen.getByRole("checkbox", { name: "我确认以上文件变更" }),
    );
    await userEvent.click(button("确认安装"));
    expect(api.applySyncHook).toHaveBeenCalledExactlyOnceWith("claude-code", {
      operation: "install",
      installationId,
      revision: 1,
      fingerprint,
      userConfirmed: true,
    });
    expect(
      await screen.findByText("同步 Hook 已安装。来源持续同步设置未改变。"),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "确认安装" })).toBeNull();
  });
  it("uninstalls only the hook, with separate confirmation and no MCP or sync mutation", async () => {
    const api = setup("installed");
    const dialog = await open("卸载同步 Hook");
    expect(dialog.textContent).toContain(
      "不会关闭独立持续同步，也不会断开 MCP 记忆连接",
    );
    expect(api.applySyncHook).not.toHaveBeenCalled();
    api.getSyncHookStatus.mockResolvedValue(status());
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(button("确认卸载"));
    expect(api.applySyncHook.mock.calls[0][1]).toEqual({
      operation: "uninstall",
      installationId,
      revision: 1,
      fingerprint,
      userConfirmed: true,
    });
    expect(
      await screen.findByText(
        "同步 Hook 已卸载。独立持续同步和 MCP 连接未改变。",
      ),
    ).toBeTruthy();
  });
  it.each(["installed", "modified"] as const)(
    "permits removal, not installation, for a revoked connection with %s hook",
    async (state) => {
      const api = setup(
        state,
        host({
          permission: {
            ...permission(),
            state: "revoked",
            receipt: {
              ...permission().receipt,
              status: "revoked",
              revision: 2,
            },
          },
        }),
      );
      api.getSyncHookStatus.mockResolvedValue({
        ...status(state),
        reason: "connection-revoked",
      });
      await userEvent.click(
        await screen.findByRole("button", { name: "刷新同步 Hook 状态" }),
      );
      await screen.findByText("MCP 连接需要核对；仍可移除已有同步 Hook。");
      expect(
        screen.queryByRole("button", { name: "更新同步 Hook" }),
      ).toBeNull();
      api.previewSyncHook.mockResolvedValueOnce({
        ...preview("uninstall"),
        revision: 2,
      });
      await open("卸载同步 Hook");
      api.applySyncHook.mockResolvedValueOnce(status("connection-required"));
      api.getSyncHookStatus.mockResolvedValue(status("connection-required"));
      await userEvent.click(screen.getByRole("checkbox"));
      await userEvent.click(button("确认卸载"));
      expect(api.applySyncHook).toHaveBeenCalledExactlyOnceWith(
        "claude-code",
        expect.objectContaining({ operation: "uninstall", revision: 2 }),
      );
      expect(
        await screen.findByText(
          "同步 Hook 已卸载。独立持续同步和 MCP 连接未改变。",
        ),
      ).toBeTruthy();
      await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
      await userEvent.click(button("完成"));
      expect(screen.getByText("需要重新关联 MCP 连接")).toBeTruthy();
      expect(
        screen.queryByRole("button", { name: "卸载同步 Hook" }),
      ).toBeNull();
    },
  );
  it("treats an empty installed update preview as current without submitting a write", async () => {
    const api = setup("installed");
    api.previewSyncHook.mockResolvedValueOnce({ ...preview(), files: [] });
    await open("更新同步 Hook");
    expect(
      await screen.findByText("同步 Hook 已是当前版本，无需修改。"),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "确认更新" })).toBeNull();
    await userEvent.click(button("完成"));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("同步 Hook 已安装")).toBeTruthy();
    expect(api.applySyncHook).not.toHaveBeenCalled();
  });
  it("uses install operation for an explicit update and never treats modified as sync enabled", async () => {
    const api = setup("modified");
    await open("更新同步 Hook");
    expect(api.previewSyncHook).toHaveBeenCalledExactlyOnceWith(
      "claude-code",
      "install",
    );
    expect(screen.queryByText("持续同步已开启")).toBeNull();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(button("确认更新"));
    expect(api.applySyncHook).toHaveBeenCalledTimes(1);
    expect(
      await screen.findByText("同步 Hook 已更新。来源持续同步设置未改变。"),
    ).toBeTruthy();
  });
  it("cancel and Escape during a pending preview discard late results without any write", async () => {
    const api = setup();
    const late = deferred<SyncHookPreview>();
    api.previewSyncHook.mockReturnValueOnce(late.promise);
    await userEvent.click(
      await screen.findByRole("button", { name: "安装同步 Hook" }),
    );
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await act(async () => late.resolve(preview()));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.applySyncHook).not.toHaveBeenCalled();
    await open();
    await userEvent.click(button("取消"));
    expect(api.applySyncHook).not.toHaveBeenCalled();
  });
  it("retains failed preview and sanitizes raw errors while allowing explicit retry", async () => {
    const api = setup();
    api.previewSyncHook.mockRejectedValueOnce(
      new Error("secret-token /private/file"),
    );
    await open();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(document.body.textContent).not.toContain("secret-token");
    expect(screen.getByRole("dialog")).toBeTruthy();
    await userEvent.click(button("重新预览"));
    await waitFor(() =>
      expect(screen.getByText("/synthetic/claude/settings.json")).toBeTruthy(),
    );
    expect(api.applySyncHook).not.toHaveBeenCalled();
  });
  it("retains apply failure and requires a new preview and confirmation before retry", async () => {
    const api = setup();
    api.applySyncHook.mockRejectedValueOnce(new Error("raw-secret failure"));
    await open();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(button("确认安装"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(button("确认安装").disabled).toBe(true);
    expect(document.body.textContent).not.toContain("raw-secret");
    await userEvent.click(button("重新预览"));
    expect(api.applySyncHook).toHaveBeenCalledTimes(1);
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(
      false,
    );
    expect(button("确认安装").disabled).toBe(true);
  });
  it("keeps a successful mutation receipt when refresh fails and retries only GET", async () => {
    const api = setup();
    await open();
    api.getSyncHookStatus.mockRejectedValueOnce(new Error("offline"));
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(button("确认安装"));
    expect(
      await screen.findByText("同步 Hook 已安装。来源持续同步设置未改变。"),
    ).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain(
      "安装已成功，但状态刷新失败",
    );
    const previews = api.previewSyncHook.mock.calls.length;
    api.getSyncHookStatus.mockResolvedValue(status("installed"));
    await userEvent.click(button("刷新状态"));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(api.applySyncHook).toHaveBeenCalledTimes(1);
    expect(api.previewSyncHook).toHaveBeenCalledTimes(previews);
  });
  it("suppresses duplicate submit and close while the confirmed write is pending", async () => {
    const api = setup();
    const late = deferred<SyncHookStatus>();
    api.applySyncHook.mockReturnValueOnce(late.promise);
    await open();
    await userEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(button("确认安装"));
    fireEvent.click(button("确认安装"));
    expect(button("取消").disabled).toBe(true);
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeTruthy();
    await act(async () => late.resolve(status("installed")));
    expect(api.applySyncHook).toHaveBeenCalledTimes(1);
  });
  it("invalidates an open confirmation when installation identity or revision changes", async () => {
    const api = setup();
    await open();
    await userEvent.click(screen.getByRole("checkbox"));
    api.update(
      host({
        permission: {
          ...permission(),
          receipt: { ...permission().receipt, revision: 2 },
        },
      }),
    );
    expect(button("确认安装").disabled).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("连接已变化");
    fireEvent.click(button("确认安装"));
    expect(api.applySyncHook).not.toHaveBeenCalled();
  });
  it("ignores late status from a previous installation", async () => {
    const api = setup();
    const late = deferred<SyncHookStatus>();
    await screen.findByText("同步 Hook 未安装");
    api.getSyncHookStatus.mockReturnValueOnce(late.promise);
    await userEvent.click(button("刷新同步 Hook 状态"));
    api.getSyncHookStatus.mockResolvedValue(status("connection-required"));
    api.update(
      host({
        permission: {
          ...permission(),
          receipt: {
            ...permission().receipt,
            installationId: "00000000-0000-4000-8000-000000000002",
          },
        },
      }),
    );
    await screen.findByText("需要重新关联 MCP 连接");
    await act(async () => late.resolve(status("installed")));
    expect(screen.queryByText("同步 Hook 已安装")).toBeNull();
  });
  it.each(["host", "operation", "installation", "revision", "file"])(
    "rejects mismatched preview %s without authorizing",
    async (kind) => {
      const api = setup();
      const value = preview();
      if (kind === "host") value.hostId = "cursor";
      if (kind === "operation") value.operation = "uninstall";
      if (kind === "installation")
        value.installationId = "another-installation";
      if (kind === "revision") value.revision = 2;
      if (kind === "file")
        value.files = [{ ...value.files[0], path: "bad\npath" }];
      api.previewSyncHook.mockResolvedValueOnce(value);
      await open();
      expect(await screen.findByRole("alert")).toBeTruthy();
      expect(screen.queryByRole("checkbox")).toBeNull();
      expect(api.applySyncHook).not.toHaveBeenCalled();
    },
  );
  it("contains focus, restores previous inert state and returns focus after close", async () => {
    const background = document.createElement("button");
    const alreadyInert = document.createElement("div");
    alreadyInert.inert = true;
    document.body.append(background, alreadyInert);
    try {
      const api = setup();
      const dialog = await open();
      expect(api.container.contains(dialog)).toBe(false);
      expect(background.inert).toBe(true);
      expect(document.activeElement).toBe(button("关闭"));
      await userEvent.tab({ shift: true });
      expect(document.activeElement).toBe(button("取消"));
      background.focus();
      expect(dialog.contains(document.activeElement)).toBe(true);
      await userEvent.click(button("取消"));
      expect(background.inert).toBeFalsy();
      expect(alreadyInert.inert).toBe(true);
      expect(document.activeElement).toBe(button("安装同步 Hook"));
    } finally {
      background.remove();
      alreadyInert.remove();
    }
  });
});
