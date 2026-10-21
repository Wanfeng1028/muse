// @vitest-environment jsdom

import type { ImportJob, ImportStatus } from "@one-memory/contracts";
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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  SourceJobActions,
  type SourceJobActionsProps,
} from "./SourceJobActions";

function job(overrides: Partial<ImportJob> = {}): ImportJob {
  return {
    job_id: "job-a",
    user_id: "local",
    source_id: "cursor",
    status: "running",
    phase: "read",
    checkpoint: "byte:42",
    discovered: 12,
    discovered_targets: 3,
    emitted: 8,
    stored: 8,
    revised: 0,
    merged: 0,
    skipped: 0,
    errors: 0,
    created_at: "2026-09-14T00:00:00Z",
    updated_at: "2026-09-14T00:00:01Z",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function setup(overrides: Partial<SourceJobActionsProps> = {}) {
  const onAction = vi.fn<SourceJobActionsProps["onAction"]>();
  let props: SourceJobActionsProps = {
    job: job(),
    sourceLabel: "Cursor",
    syncEnabled: false,
    onAction,
    ...overrides,
  };
  const view = render(<SourceJobActions {...props} />);
  return {
    ...view,
    onAction,
    update(change: Partial<SourceJobActionsProps>) {
      props = { ...props, ...change };
      view.rerender(<SourceJobActions {...props} />);
    },
  };
}

function button(name: string) {
  return screen.getByRole<HTMLButtonElement>("button", { name });
}

beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(prefers-reduced-motion: reduce)",
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("SourceJobActions COLD-12 / A10", () => {
  it.each([
    ["pending", "等待检查新增", "暂停新增同步"],
    ["running", "正在检查新增", "暂停新增同步"],
    ["paused", "新增同步已暂停", "继续新增同步"],
    ["interrupted", "新增同步已中断", "继续新增同步"],
    ["failed", "新增同步失败", "重试新增同步"],
    ["completed", "本次新增检查已完成", null],
    ["cancelled", "本次新增同步已取消", null],
  ] satisfies [ImportStatus, string, string | null][])(
    "sync %s has operation-specific state and tools without changing counts",
    (status, label, action) => {
      const { onAction } = setup({
        job: job({ status, operation: "sync", stored: 0, merged: 81614 }),
      });
      expect(
        screen.getByRole("group", { name: "Cursor 新增同步任务操作" }),
      ).toBeTruthy();
      expect(screen.getByRole("status").textContent).toContain(label);
      expect(screen.getByRole("status").textContent).toContain("本次新增 0 条");
      expect(screen.getByRole("status").textContent).not.toMatch(/导入|81,614/);
      if (action) {
        expect(button(action).title).toBe(action);
        expect(button("取消本次新增同步")).toBeTruthy();
      } else expect(screen.queryByRole("button")).toBeNull();
      expect(onAction).not.toHaveBeenCalled();
    },
  );

  it("sync cancellation keeps the same job action and does not claim a history reset", async () => {
    const { onAction } = setup({
      job: job({ operation: "sync", stored: 0 }),
      syncEnabled: true,
    });
    onAction.mockResolvedValue(
      job({
        operation: "sync",
        status: "cancelled",
        stored: 0,
        updated_at: "2026-09-14T00:00:03Z",
      }),
    );
    await userEvent.click(button("取消本次新增同步"));
    const dialog = screen.getByRole("dialog", {
      name: "取消 Cursor 的本次新增同步？",
    });
    expect(dialog.textContent).toContain("仅停止本次新增同步");
    expect(dialog.textContent).toContain("本次取消不会关闭持续同步");
    expect(within(dialog).getByText("本次新增")).toBeTruthy();
    expect(onAction).not.toHaveBeenCalled();
    await userEvent.click(button("确认取消"));
    expect(onAction.mock.calls).toEqual([["job-a", "cancel"]]);
    expect(screen.getByRole("status").textContent).toContain(
      "本次新增同步已取消",
    );
  });

  it("sync pause/resume use unchanged controller commands and actual completed race status", async () => {
    const { onAction } = setup({ job: job({ operation: "sync", stored: 0 }) });
    onAction.mockResolvedValueOnce(
      job({
        operation: "sync",
        status: "paused",
        stored: 0,
        updated_at: "2026-09-14T00:00:02Z",
      }),
    );
    onAction.mockResolvedValueOnce(
      job({
        operation: "sync",
        status: "completed",
        stored: 1,
        updated_at: "2026-09-14T00:00:03Z",
      }),
    );
    await userEvent.click(button("暂停新增同步"));
    await userEvent.click(button("继续新增同步"));
    expect(onAction.mock.calls).toEqual([
      ["job-a", "pause"],
      ["job-a", "resume"],
    ]);
    expect(screen.getByRole("status").textContent).toContain(
      "本次新增检查已完成 · 本次新增 1 条",
    );
  });

  it("stale sync status remains a last receipt and operation change invalidates confirmation", async () => {
    const { update, onAction } = setup({
      job: job({ operation: "sync", stored: 0 }),
      snapshotStale: true,
    });
    expect(screen.getByRole("status").textContent).toContain(
      "最近回执：正在检查新增",
    );
    await userEvent.click(button("取消本次新增同步"));
    update({ job: job({ operation: "history" }) });
    expect(button("确认取消").disabled).toBe(true);
    expect(onAction).not.toHaveBeenCalled();
  });

  it.each([
    ["pending", "暂停导入"],
    ["running", "暂停导入"],
    ["paused", "继续导入"],
    ["interrupted", "继续导入"],
    ["failed", "重试未完成部分"],
  ] satisfies [ImportStatus, string][])(
    "%s exposes only the appropriate action and cancel with named icon tooltips",
    (status, label) => {
      const { onAction } = setup({ job: job({ status }) });
      expect(button(label).querySelector("svg")).toBeTruthy();
      expect(button(label).title).toBe(label);
      expect(button("取消本次导入").querySelector("svg")).toBeTruthy();
      expect(button("取消本次导入").title).toBe("取消本次导入");
      expect(screen.getAllByRole("button")).toHaveLength(2);
      expect(onAction).not.toHaveBeenCalled();
    },
  );

  it.each(["completed", "cancelled"] satisfies ImportStatus[])(
    "%s never exposes resume or cancel",
    (status) => {
      setup({ job: job({ status }) });
      expect(screen.queryByRole("button")).toBeNull();
      expect(screen.getByRole("status").textContent).toContain(
        status === "completed" ? "已完成" : "已取消",
      );
      expect(screen.getByRole("status").textContent).toContain("8");
    },
  );

  it("waits for the authoritative pause receipt and ignores a stale poll", async () => {
    const { onAction, update } = setup();
    const pending = deferred<ImportJob>();
    onAction.mockReturnValue(pending.promise);
    fireEvent.click(button("暂停导入"));
    expect(onAction).toHaveBeenCalledWith("job-a", "pause");
    expect(screen.getByRole("status").textContent).toContain("正在暂停");
    expect(screen.queryByText(/已暂停/)).toBeNull();
    expect(button("取消本次导入").disabled).toBe(true);
    await act(async () =>
      pending.resolve(
        job({ status: "paused", updated_at: "2026-09-14T00:00:03Z" }),
      ),
    );
    expect(button("继续导入")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("已暂停");
    update({ job: job({ updated_at: "2026-09-14T00:00:02Z" }) });
    expect(button("继续导入")).toBeTruthy();
    update({
      job: job({
        status: "completed",
        stored: 11,
        updated_at: "2026-09-14T00:00:04Z",
      }),
    });
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("11");
  });

  it.each(["paused", "interrupted", "failed"] satisfies ImportStatus[])(
    "%s resumes the exact existing job without creating one",
    async (status) => {
      const { onAction } = setup({ job: job({ status }) });
      onAction.mockResolvedValue(job({ updated_at: "2026-09-14T00:00:02Z" }));
      await userEvent.click(
        button(status === "failed" ? "重试未完成部分" : "继续导入"),
      );
      expect(onAction.mock.calls).toEqual([["job-a", "resume"]]);
      expect(screen.getByRole("status").textContent).toContain("正在导入");
    },
  );

  it.each([true, false])(
    "requires explicit cancel confirmation and preserves sync=%s",
    async (syncEnabled) => {
      const { onAction } = setup({ syncEnabled });
      await userEvent.click(button("取消本次导入"));
      const dialog = screen.getByRole("dialog", {
        name: "取消 Cursor 的本次导入？",
      });
      expect(onAction).not.toHaveBeenCalled();
      expect(dialog.textContent).toContain("已保存的本机副本会保留");
      expect(dialog.textContent).toContain("不会撤回来源读取授权");
      expect(dialog.textContent).toContain("不会修改或删除原文件");
      expect(
        dialog.textContent?.includes("未来新增对话仍可能触发新的同步任务"),
      ).toBe(syncEnabled);
      expect(within(dialog).getByText("job-a")).toBeTruthy();
      expect(within(dialog).getByText("cursor")).toBeTruthy();
      expect(button("确认取消")).toBeTruthy();
    },
  );

  it.each(["escape", "back", "close"])(
    "%s dismisses without any request and restores focus",
    async (method) => {
      const { onAction } = setup();
      const trigger = button("取消本次导入");
      await userEvent.click(trigger);
      if (method === "escape") await userEvent.keyboard("{Escape}");
      else
        await userEvent.click(
          button(method === "back" ? "返回" : "关闭取消确认"),
        );
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(onAction).not.toHaveBeenCalled();
      expect(document.activeElement).toBe(trigger);
    },
  );

  it("keeps cancel single-flight, busy, focus-locked and open through Escape until receipt", async () => {
    const { onAction } = setup();
    const pending = deferred<ImportJob>();
    onAction.mockReturnValue(pending.promise);
    await userEvent.click(button("取消本次导入"));
    const confirm = button("确认取消");
    act(() => {
      fireEvent.click(confirm);
      fireEvent.click(confirm);
    });
    expect(onAction.mock.calls).toEqual([["job-a", "cancel"]]);
    expect(screen.getByRole("dialog").getAttribute("aria-busy")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
    await userEvent.keyboard("{Escape}{Tab}{Shift>}{Tab}{/Shift}");
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
    expect(button("返回").disabled).toBe(true);
    expect(screen.queryByText(/本次导入已取消/)).toBeNull();
    await act(async () =>
      pending.resolve(
        job({ status: "cancelled", updated_at: "2026-09-14T00:00:02Z" }),
      ),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("本次导入已取消");
  });

  it.each(["pause", "cancel"] as const)(
    "%s displays completed when completion wins the race",
    async (action) => {
      const { onAction } = setup();
      onAction.mockResolvedValue(
        job({
          status: "completed",
          stored: 15,
          updated_at: "2026-09-14T00:00:02Z",
        }),
      );
      if (action === "cancel") {
        await userEvent.click(button("取消本次导入"));
        await userEvent.click(button("确认取消"));
      } else await userEvent.click(button("暂停导入"));
      expect(screen.getByRole("status").textContent).toContain(
        "本次导入已完成",
      );
      expect(screen.getByRole("status").textContent).toContain("15");
      expect(screen.queryByText(/本次导入已取消|导入已暂停/)).toBeNull();
      expect(screen.queryByRole("dialog")).toBeNull();
    },
  );

  it("keeps cancellation failure close to the confirmation and retries through the controller", async () => {
    const { onAction } = setup({ syncEnabled: true });
    onAction.mockRejectedValueOnce(new Error("连接中断，状态需核对"));
    onAction.mockResolvedValueOnce(
      job({ status: "cancelled", updated_at: "2026-09-14T00:00:03Z" }),
    );
    await userEvent.click(button("取消本次导入"));
    await userEvent.click(button("确认取消"));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("alert").textContent).toContain(
      "状态待核对",
    );
    expect(within(dialog).getByRole("alert").textContent).toContain("连接中断");
    expect(screen.queryByText(/本次导入已取消/)).toBeNull();
    await userEvent.click(button("核对并重试取消"));
    expect(onAction.mock.calls).toEqual([
      ["job-a", "cancel"],
      ["job-a", "cancel"],
    ]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("leaves an inline retry for a failed pause without claiming it stopped", async () => {
    const { onAction } = setup();
    onAction.mockRejectedValueOnce("unknown");
    onAction.mockResolvedValueOnce(
      job({ status: "paused", updated_at: "2026-09-14T00:00:02Z" }),
    );
    await userEvent.click(button("暂停导入"));
    expect(screen.getByRole("alert").textContent).toContain("状态待核对");
    expect(screen.getByRole("status").textContent).not.toContain("已暂停");
    await userEvent.click(button("核对并重试暂停"));
    expect(onAction).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status").textContent).toContain("已暂停");
  });

  it.each([
    ["job", { job: job({ job_id: "job-b" }) }],
    ["source", { job: job({ source_id: "workbuddy" }) }],
    ["owner", { job: job({ user_id: "other" }) }],
    ["creation", { job: job({ created_at: "2026-09-14T01:00:00Z" }) }],
    ["label", { sourceLabel: "Other source" }],
    ["sync", { syncEnabled: true }],
    ["terminal", { job: job({ status: "completed" }) }],
  ] satisfies [string, Partial<SourceJobActionsProps>][])(
    "latches an invalid confirmation when %s changes",
    async (_name, change) => {
      const { onAction, update } = setup();
      await userEvent.click(button("取消本次导入"));
      update(change);
      expect(button("确认取消").disabled).toBe(true);
      expect(
        within(screen.getByRole("dialog")).getByRole("alert").textContent,
      ).toContain("重新确认");
      expect(screen.getByRole("dialog").textContent).toContain("job-a");
      update({ job: job(), sourceLabel: "Cursor", syncEnabled: false });
      expect(button("确认取消").disabled).toBe(true);
      fireEvent.click(button("确认取消"));
      expect(onAction).not.toHaveBeenCalled();
    },
  );

  it("keeps progress-only polling from invalidating the frozen job", async () => {
    const { onAction, update } = setup();
    onAction.mockResolvedValue(
      job({
        status: "cancelled",
        stored: 19,
        updated_at: "2026-09-14T00:00:03Z",
      }),
    );
    await userEvent.click(button("取消本次导入"));
    update({
      job: job({
        stored: 19,
        checkpoint: "byte:900",
        updated_at: "2026-09-14T00:00:02Z",
      }),
    });
    expect(button("确认取消").disabled).toBe(false);
    await userEvent.click(button("确认取消"));
    expect(onAction.mock.calls).toEqual([["job-a", "cancel"]]);
    expect(screen.getByRole("status").textContent).toContain("19");
  });

  it("ignores late results after replacement, retaining the flight lock until settlement", async () => {
    const pending = deferred<ImportJob>();
    const { onAction, update } = setup();
    onAction.mockReturnValue(pending.promise);
    fireEvent.click(button("暂停导入"));
    update({ job: job({ job_id: "job-b" }) });
    fireEvent.click(button("暂停导入"));
    expect(onAction).toHaveBeenCalledTimes(1);
    await act(async () =>
      pending.resolve(
        job({ status: "paused", updated_at: "2026-09-14T00:00:02Z" }),
      ),
    );
    expect(button("暂停导入").disabled).toBe(false);
    expect(screen.queryByRole("button", { name: "继续导入" })).toBeNull();
  });

  it.each([
    undefined,
    job({ job_id: "wrong" }),
    job({ source_id: "wrong" }),
    job({ status: "unknown" as ImportStatus }),
  ])(
    "does not interpret an invalid receipt as cancellation: %j",
    async (response) => {
      const { onAction } = setup();
      onAction.mockResolvedValue(response as ImportJob);
      await userEvent.click(button("取消本次导入"));
      await userEvent.click(button("确认取消"));
      expect(screen.getByRole("dialog")).toBeTruthy();
      expect(screen.getByRole("alert").textContent).toContain("状态待核对");
      expect(screen.queryByText(/本次导入已取消/)).toBeNull();
    },
  );

  it("keeps a cancel response that is still running unresolved", async () => {
    const { onAction } = setup();
    onAction.mockResolvedValue(job({ updated_at: "2026-09-14T00:00:02Z" }));
    await userEvent.click(button("取消本次导入"));
    await userEvent.click(button("确认取消"));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("状态待核对");
    expect(button("核对并重试取消")).toBeTruthy();
  });

  it("makes siblings inert, traps both Tab directions and restores prior inert states", async () => {
    const outside = document.createElement("button");
    outside.textContent = "outside";
    const previous = document.createElement("div");
    previous.inert = true;
    previous.setAttribute("inert", "");
    document.body.append(outside, previous);
    setup();
    const trigger = button("取消本次导入");
    await userEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(outside.inert).toBe(true);
    expect(outside.hasAttribute("inert")).toBe(true);
    const controls = within(dialog).getAllByRole("button");
    controls[0].focus();
    await userEvent.tab({ shift: true });
    expect(document.activeElement).toBe(controls.at(-1));
    await userEvent.tab();
    expect(document.activeElement).toBe(controls[0]);
    outside.focus();
    expect(dialog.contains(document.activeElement)).toBe(true);
    const added = document.createElement("button");
    document.body.append(added);
    await waitFor(() => expect(added.inert).toBe(true));
    await userEvent.keyboard("{Escape}");
    expect(outside.inert).toBe(false);
    expect(outside.hasAttribute("inert")).toBe(false);
    expect(previous.inert).toBe(true);
    expect(previous.hasAttribute("inert")).toBe(true);
    expect(document.activeElement).toBe(trigger);
  });

  it("does not steal focus on row polling and releases a modal on unmount without cancelling", async () => {
    const { onAction, update, unmount } = setup();
    const unrelated = document.createElement("input");
    document.body.append(unrelated);
    unrelated.focus();
    update({ job: job({ stored: 20 }) });
    expect(document.activeElement).toBe(unrelated);
    await userEvent.click(button("取消本次导入"));
    unmount();
    expect(onAction).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(unrelated.inert).toBe(false);
  });

  it("prevents rapid pause/cancel activation from creating a second operation", async () => {
    const { onAction } = setup();
    const pending = deferred<ImportJob>();
    onAction.mockReturnValue(pending.promise);
    const pause = button("暂停导入"),
      cancel = button("取消本次导入");
    act(() => {
      fireEvent.click(pause);
      fireEvent.click(pause);
      fireEvent.click(cancel);
    });
    expect(onAction.mock.calls).toEqual([["job-a", "pause"]]);
    expect(screen.queryByRole("dialog")).toBeNull();
    await act(async () => pending.resolve(job({ status: "paused" })));
  });

  it("blocks new writes when disabled, including a dialog already open", async () => {
    const { onAction, update } = setup({ disabled: true });
    expect(button("暂停导入").disabled).toBe(true);
    expect(button("取消本次导入").disabled).toBe(true);
    update({ disabled: false });
    await userEvent.click(button("取消本次导入"));
    update({ disabled: true });
    expect(button("确认取消").disabled).toBe(true);
    await userEvent.click(button("返回"));
    expect(onAction).not.toHaveBeenCalled();
  });

  it("does not open a second business modal", () => {
    setup();
    const existing = document.createElement("section");
    existing.setAttribute("role", "dialog");
    existing.setAttribute("aria-modal", "true");
    document.body.append(existing);
    fireEvent.click(button("取消本次导入"));
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  it("registers the business dialog immediately, but waits for a tour to relinquish focus", async () => {
    setup();
    const tour = document.createElement("div");
    tour.className = "om-spotlight";
    tour.setAttribute("role", "dialog");
    tour.setAttribute("aria-modal", "true");
    const tourButton = document.createElement("button");
    tourButton.textContent = "tour control";
    tour.append(tourButton);
    document.body.append(tour);
    tourButton.focus();
    fireEvent.click(button("取消本次导入"));
    const dialog = screen.getByRole("dialog", {
      name: "取消 Cursor 的本次导入？",
    });
    expect(dialog).toBeTruthy();
    expect(document.activeElement).toBe(tourButton);
    expect(button("确认取消").disabled).toBe(true);
    await act(async () => tour.remove());
    await waitFor(() =>
      expect(dialog.contains(document.activeElement)).toBe(true),
    );
    expect(button("确认取消").disabled).toBe(false);
  });

  it("keeps closing mounted for 160ms without allowing late submits", async () => {
    vi.stubGlobal("matchMedia", () => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    vi.useFakeTimers();
    const { onAction } = setup();
    fireEvent.click(button("取消本次导入"));
    expect(screen.getByRole("dialog").getAttribute("data-motion")).toBe("full");
    fireEvent.click(button("返回"));
    expect(screen.getByRole("dialog").getAttribute("data-closing")).toBe(
      "true",
    );
    fireEvent.click(button("确认取消"));
    act(() => vi.advanceTimersByTime(159));
    expect(screen.getByRole("dialog")).toBeTruthy();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(onAction).not.toHaveBeenCalled();
  });
});
