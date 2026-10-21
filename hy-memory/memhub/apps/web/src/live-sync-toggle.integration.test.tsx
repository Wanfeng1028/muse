// @vitest-environment jsdom

import { webcrypto } from "node:crypto";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Posted = {
  enabled: boolean;
};

// A Core stand-in for the direct `{ enabled } -> SourceSyncState` endpoint.
const core = vi.hoisted(() => {
  const ROOT = `root:v2:${"a".repeat(64)}`;
  const state = {
    grantRevision: 1,
    syncEnabled: false,
    posts: [] as Posted[],
    /** GET /sources calls that fail, as they do while Core is busy importing. */
    failSourceReads: 0,
    /** GET /sources calls read now but answered only when released. */
    holdSourceReads: 0,
    heldSourceReads: [] as Array<() => void>,
  };
  const source = () => ({
    source_id: "cursor",
    display_name: "Cursor",
    storage_kinds: ["sqlite"],
    available: true,
    authorized: true,
    detected: true,
    root_label: ".cursor",
    candidate_path: "~/.cursor",
    candidate_kind: "default",
    imported_messages: 0,
    imported_conversations: 0,
    sync_completeness: "additions_only",
    capabilities: {
      historical_import: "implemented",
      incremental_import: "implemented",
      live_sync: "implemented",
      recall: "implemented",
      installer: "implemented",
      verification: "real_replayed",
    },
    grant_revision: state.grantRevision,
    root_id: ROOT,
    candidate_root_id: ROOT,
    sync_enabled: state.syncEnabled,
  });
  const receipt = () => ({
    source_id: "cursor",
    sync_enabled: state.syncEnabled,
  });
  const get = vi.fn(async (url: string) => {
    if (url === "/api/v1/health")
      return {
        data: {
          status: "ok",
          service: "one-memory-core",
          version: "test",
          instance_id: "instance-1",
        },
      };
    if (url === "/api/v1/import-jobs") return { data: [] };
    if (url === "/api/v1/sources") {
      if (state.failSourceReads > 0) {
        state.failSourceReads -= 1;
        throw new Error("timeout of 30000ms exceeded");
      }
      const snapshot = [source()];
      if (state.holdSourceReads > 0) {
        state.holdSourceReads -= 1;
        return new Promise((resolve) =>
          state.heldSourceReads.push(() => resolve({ data: snapshot })),
        );
      }
      return { data: snapshot };
    }
    throw new Error(`unexpected GET ${url}`);
  });
  const post = vi.fn(async (url: string, body: Posted) => {
    if (url !== "/api/v1/sources/cursor/sync-permission")
      throw new Error(`unexpected POST ${url}`);
    state.syncEnabled = body.enabled;
    state.posts.push(body);
    return { data: receipt() };
  });
  return { state, get, post };
});

vi.mock("axios", () => ({
  default: {
    create: () => ({
      get: core.get,
      post: core.post,
      interceptors: { request: { use: vi.fn() } },
    }),
    isAxiosError: (value: { isAxiosError?: boolean }) =>
      value?.isAxiosError === true,
  },
}));

vi.mock("./ModelSettings", () => ({
  ModelSettings: () => <input aria-label="模型配置输入" />,
}));

import { ApplicationDetail } from "./ApplicationDetail";
import { resetConnectionReconcile } from "./connection-reconcile";
import { resetClient } from "./query-client";
import { useImportSources } from "./use-import-sources";

function DetailHarness() {
  const imports = useImportSources({ automaticSync: false });
  const cursor = imports.sources.find((item) => item.source_id === "cursor");
  if (!cursor) return <p>loading</p>;
  return (
    <ApplicationDetail
      source={cursor}
      sources={imports.sources}
      stale={imports.sourceSnapshot?.stale === true}
      syncWriteConfirmed={imports.sourceSyncWriteConfirmed?.has(
        cursor.source_id,
      )}
      setSync={imports.setSync}
      refresh={imports.refresh}
      onBack={() => {}}
    />
  );
}

function posted() {
  return core.state.posts;
}

async function click(sync: HTMLElement) {
  const before = core.state.posts.length;
  fireEvent.click(sync);
  await waitFor(() => expect(core.state.posts.length).toBe(before + 1));
  await waitFor(() => expect(sync.getAttribute("aria-busy")).toBeNull());
}

async function toggle(sync: HTMLElement, expected: "true" | "false") {
  await click(sync);
  await waitFor(() => expect(sync.getAttribute("aria-checked")).toBe(expected));
}

async function openDetail() {
  render(<DetailHarness />);
  const sync = await screen.findByRole("switch", { name: "同步开关" });
  await waitFor(() => expect(sync.getAttribute("aria-checked")).toBe("false"));
  await waitFor(() => expect(sync.getAttribute("aria-busy")).toBeNull());
  return sync;
}

const settled = [{ enabled: true }, { enabled: false }, { enabled: true }];

beforeEach(() => {
  resetClient();
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value: webcrypto,
  });
  resetConnectionReconcile();
  Object.assign(core.state, {
    grantRevision: 1,
    syncEnabled: false,
    posts: [],
    failSourceReads: 0,
    holdSourceReads: 0,
    heldSourceReads: [],
  });
});

afterEach(() => {
  cleanup();
  window.oneMemory = undefined;
  vi.clearAllMocks();
});

describe("application detail continuous sync against Core", () => {
  it("posts only enabled and uses direct receipts when follow-up reads fail", async () => {
    const sync = await openDetail();
    core.state.failSourceReads = 3;
    await toggle(sync, "true");
    await toggle(sync, "false");
    await toggle(sync, "true");
    expect(posted()).toEqual(settled);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
