// @vitest-environment jsdom

import type { SourceResponse } from "@one-memory/contracts";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const { getSources, setSourceSync } = vi.hoisted(() => ({
  getSources: vi.fn(),
  setSourceSync: vi.fn(),
}));
vi.mock("./api", () => ({ getSources, setSourceSync }));

import { queryClient } from "./query-client";
import {
  cachedSources,
  prefetchSources,
  refreshSources,
  SOURCES_KEY,
  useSourceSync,
} from "./source-state";

const ROOT = "root:v2:cursor";

function cursor(grantRevision: number, syncEnabled = grantRevision % 2 === 1) {
  return {
    source_id: "cursor",
    display_name: "Cursor",
    storage_kinds: ["jsonl"],
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
      verification: "fixture_only",
    },
    root_id: ROOT,
    grant_revision: grantRevision,
    sync_enabled: syncEnabled,
  } satisfies SourceResponse;
}

function receipt(syncEnabled: boolean) {
  return {
    source_id: "cursor",
    sync_enabled: syncEnabled,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  getSources.mockReset();
  setSourceSync.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

it("ends on the newer read when an older forced read lands after it", async () => {
  getSources.mockResolvedValueOnce([cursor(0)]);
  await refreshSources();
  const older = deferred<SourceResponse[]>();
  const newer = deferred<SourceResponse[]>();
  getSources
    .mockReturnValueOnce(older.promise)
    .mockReturnValueOnce(newer.promise);
  const first = refreshSources();
  const second = refreshSources();
  newer.resolve([cursor(2)]);
  expect((await second)[0].grant_revision).toBe(2);
  older.resolve([cursor(1)]);
  expect((await first)[0].grant_revision).toBe(2);
  expect(cachedSources()?.[0].grant_revision).toBe(2);
});

it("keeps an older read's newer data when the read after it fails", async () => {
  getSources.mockResolvedValueOnce([cursor(0)]);
  await refreshSources();
  const older = deferred<SourceResponse[]>();
  getSources
    .mockReturnValueOnce(older.promise)
    .mockRejectedValueOnce(Error("timeout of 30000ms exceeded"));
  const first = refreshSources();
  await expect(refreshSources()).rejects.toThrow("timeout");
  older.resolve([cursor(1)]);
  await first;
  expect(cachedSources()?.[0].grant_revision).toBe(1);
});

it("does not let an older read bring back a source a newer read dropped", async () => {
  getSources.mockResolvedValueOnce([cursor(0)]);
  await refreshSources();
  const older = deferred<SourceResponse[]>();
  getSources.mockReturnValueOnce(older.promise).mockResolvedValueOnce([]);
  const first = refreshSources();
  await refreshSources();
  older.resolve([cursor(0)]);
  await first;
  expect(cachedSources()).toEqual([]);
});

it("keeps the last loaded sources when a refresh cannot reach Core", async () => {
  getSources.mockResolvedValueOnce([cursor(0)]);
  await refreshSources();
  getSources.mockRejectedValueOnce(Error("timeout of 30000ms exceeded"));
  await expect(refreshSources()).rejects.toThrow("timeout");
  expect(cachedSources()).toEqual([cursor(0)]);
});

it("replaces the sources when a refresh succeeds", async () => {
  getSources.mockResolvedValueOnce([cursor(0)]);
  await refreshSources();
  getSources.mockResolvedValueOnce([]);
  expect(await refreshSources()).toEqual([]);
  expect(cachedSources()).toEqual([]);
});

it("reuses a fresh read and reads again once it is stale", async () => {
  getSources.mockResolvedValue([cursor(0)]);
  await prefetchSources();
  await prefetchSources();
  expect(getSources).toHaveBeenCalledTimes(1);
  const later = Date.now() + 10 * 60_000;
  vi.spyOn(Date, "now").mockReturnValue(later);
  await prefetchSources();
  expect(getSources).toHaveBeenCalledTimes(2);
});

it("writes with the cached revision and lands the receipt in the cache", async () => {
  getSources.mockResolvedValueOnce([cursor(2, false)]);
  await refreshSources();
  setSourceSync.mockResolvedValueOnce(receipt(true));
  const { result } = renderHook(() => useSourceSync());
  await result.current.mutateAsync({ source: cursor(0), enabled: true });
  expect(setSourceSync).toHaveBeenCalledWith(cursor(2, false), true, undefined);
  await waitFor(() =>
    expect(cachedSources()?.[0]).toMatchObject({
      sync_enabled: true,
      grant_revision: 2,
    }),
  );
  expect(getSources).toHaveBeenCalledTimes(1);
});

it("a sync receipt changes only the sync flag on the cached source", async () => {
  getSources.mockResolvedValueOnce([cursor(4, false)]);
  await refreshSources();
  setSourceSync.mockResolvedValueOnce(receipt(true));
  const { result } = renderHook(() => useSourceSync());
  await result.current.mutateAsync({
    source: cursor(4, false),
    enabled: true,
  });
  expect(cachedSources()?.[0]).toMatchObject({
    grant_revision: 4,
    root_id: ROOT,
    sync_enabled: true,
  });
});

it("hands the query's abort signal to the request so a cancelled read is cancelled", async () => {
  let signal: AbortSignal | undefined;
  getSources.mockImplementationOnce((options?: { signal?: AbortSignal }) => {
    signal = options?.signal;
    return new Promise(() => {});
  });
  void prefetchSources();
  await waitFor(() => expect(getSources).toHaveBeenCalled());
  await queryClient.cancelQueries({ queryKey: SOURCES_KEY });
  expect(signal?.aborted).toBe(true);
});
