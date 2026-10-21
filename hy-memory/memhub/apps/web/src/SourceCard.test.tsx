// @vitest-environment jsdom

import type { ImportJob, SourceResponse } from "@one-memory/contracts";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceCard } from "./SourceCard";

const source: SourceResponse = {
  source_id: "claude-code",
  display_name: "Claude Code",
  storage_kinds: ["jsonl"],
  available: true,
  authorized: false,
  detected: null,
  root_label: null,
  candidate_path: "~/.claude/projects",
  candidate_kind: "default",
  imported_messages: 0,
  imported_conversations: 0,
  capabilities: {
    historical_import: "implemented",
    incremental_import: "implemented",
    live_sync: "not_implemented",
    recall: "not_implemented",
    installer: "not_implemented",
    verification: "real_replayed",
  },
  sync_enabled: false,
  sync_completeness: "additions_only",
};

const job: ImportJob = {
  job_id: "job-1",
  user_id: "local",
  source_id: "claude-code",
  status: "running",
  phase: "read",
  checkpoint: "byte:10",
  discovered: 9,
  discovered_targets: 2,
  emitted: 7,
  stored: 5,
  revised: 0,
  merged: 2,
  skipped: 1,
  errors: 1,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:01Z",
};

function callbacks() {
  return {
    onAuthorize: vi.fn(),
    onDetect: vi.fn(),
    onImport: vi.fn(),
    onChangeJob: vi.fn(),
    onRevoke: vi.fn(),
  };
}

describe("SourceCard", () => {
  it("describes an export as a snapshot without promising source changes", () => {
    render(
      <SourceCard
        source={{ ...source, sync_completeness: "one_time_snapshot" }}
        busyKey={null}
        {...callbacks()}
      />,
    );
    expect(screen.getByText(/一次性快照，不跟随原应用变化/)).toBeTruthy();
    expect(screen.queryByText(/仅新增同步，源头删除不跟随/)).toBeNull();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("requires an explicit keyboard-accessible authorization action", async () => {
    const user = userEvent.setup();
    const actions = callbacks();
    render(<SourceCard source={source} busyKey={null} {...actions} />);

    await user.tab();
    await user.keyboard("{Enter}");

    expect(actions.onAuthorize).toHaveBeenCalledWith(source, false);
  });

  it("shows real counters without inventing a completion percentage", () => {
    const actions = callbacks();
    const { container } = render(
      <SourceCard
        source={{ ...source, authorized: true, detected: true }}
        job={job}
        busyKey={null}
        {...actions}
      />,
    );

    expect(screen.getByText("正在后台导入")).toBeTruthy();
    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByRole("button", { name: "暂停" })).toBeTruthy();
    expect(container.textContent).not.toContain("%");
  });

  it("states recall support without claiming this machine is connected", () => {
    const actions = callbacks();
    const { container } = render(
      <SourceCard
        source={{
          ...source,
          capabilities: { ...source.capabilities, recall: "implemented" },
        }}
        busyKey={null}
        {...actions}
      />,
    );

    // Whether recall is installed here is the recall section's fact, not ours.
    expect(container.textContent).toContain("支持应用内召回");
    expect(container.textContent).not.toContain("应用内召回已接入");
  });

  it("does not call an additions-only connection real-time sync", () => {
    const actions = callbacks();
    const { container } = render(
      <SourceCard
        source={{
          ...source,
          capabilities: { ...source.capabilities, live_sync: "implemented" },
          sync_completeness: "additions_only",
        }}
        busyKey={null}
        {...actions}
      />,
    );

    // We poll on a server-side interval and cannot see upstream deletions, so
    // a memory can outlive the sentence it came from. Saying "实时同步" would
    // tell the user their copy tracks the source.
    expect(container.textContent).toContain("仅新增同步");
    expect(container.textContent).not.toContain("实时同步");
  });

  it("requires a second explicit confirmation for environment paths", async () => {
    const user = userEvent.setup();
    const actions = callbacks();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    const custom = {
      ...source,
      candidate_kind: "environment_override" as const,
      candidate_path: "/custom/agent/history",
    };
    render(<SourceCard source={custom} busyKey={null} {...actions} />);

    await user.click(
      screen.getByRole("button", { name: "确认并授权自定义目录" }),
    );
    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining(custom.candidate_path),
    );
    expect(actions.onAuthorize).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    await user.click(
      screen.getByRole("button", { name: "确认并授权自定义目录" }),
    );
    expect(actions.onAuthorize).toHaveBeenCalledWith(custom, true);
  });

  it("tells the person how many sessions were found before they grant", () => {
    const actions = callbacks();
    render(
      <SourceCard
        source={{ ...source, detected: true, session_count: 128 }}
        busyKey={null}
        {...actions}
      />,
    );

    expect(screen.getByText("找到 128 个会话")).toBeTruthy();
  });

  it("says the host is installed but empty rather than showing a bare zero", () => {
    const actions = callbacks();
    render(
      <SourceCard
        source={{ ...source, detected: true, session_count: 0 }}
        busyKey={null}
        {...actions}
      />,
    );

    expect(screen.getByText("已安装，暂未发现会话")).toBeTruthy();
    expect(screen.queryByText("找到 0 个会话")).toBeNull();
  });

  it("shows no session count when the core has not reported one", () => {
    const actions = callbacks();
    const { container } = render(
      <SourceCard
        source={{ ...source, detected: true }}
        busyKey={null}
        {...actions}
      />,
    );

    expect(container.textContent).not.toContain("个会话");
    expect(container.textContent).not.toContain("已安装，暂未发现会话");
  });
});
