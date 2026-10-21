import type { MemoryLibraryPage, MemoryStatus } from "@one-memory/contracts";
import { useCallback, useEffect, useRef, useState } from "react";
import { getMemoryLibrary } from "./api";

export function useMemoryLibrary({
  enabled,
  stale,
  sourceKey,
  query,
  status,
  source,
  activeOnly = false,
  keepPreviousOnRefresh = activeOnly,
}: {
  enabled: boolean;
  stale: boolean;
  sourceKey: string;
  query: string;
  status: MemoryStatus;
  source?: string;
  activeOnly?: boolean;
  keepPreviousOnRefresh?: boolean;
}) {
  const scope = JSON.stringify([query, status, sourceKey, source, activeOnly]);
  const [position, setPosition] = useState({ scope, offset: 0 });
  const offset = position.scope === scope ? position.offset : 0;
  const key = JSON.stringify([scope, offset]);
  const [result, setResult] = useState<{
    key: string;
    authority: string;
    page: MemoryLibraryPage | null;
    failed: boolean;
    refreshing: boolean;
    // Which filter the page on screen answers. It lags the inputs on purpose:
    // while a new read is open the numbers are still the previous filter's.
    query: string;
    source?: string;
  }>({
    key: "",
    authority: "",
    page: null,
    failed: false,
    refreshing: false,
    query: "",
    source: undefined,
  });
  const epoch = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const current = useRef({ key, enabled, stale });
  current.current = { key, enabled, stale };
  const invalidate = useCallback(() => {
    ++epoch.current;
    controller.current?.abort();
    controller.current = null;
    setResult({
      key: "",
      authority: "",
      page: null,
      failed: false,
      refreshing: false,
      query: "",
      source: undefined,
    });
  }, []);
  const refresh = useCallback(async () => {
    if (
      !enabled ||
      stale ||
      !current.current.enabled ||
      current.current.stale ||
      current.current.key !== key
    )
      return;
    const ticket = ++epoch.current;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setResult((previous) => ({
      key,
      authority: sourceKey,
      page:
        keepPreviousOnRefresh &&
        previous.authority === sourceKey &&
        previous.page &&
        !previous.failed
          ? previous.page
          : previous.key === key && previous.page && !previous.failed
            ? previous.page
            : null,
      failed: false,
      refreshing: true,
      query: previous.query,
      source: previous.source,
    }));
    const valid = () =>
      ticket === epoch.current &&
      !request.signal.aborted &&
      current.current.key === key &&
      current.current.enabled &&
      !current.current.stale;
    try {
      const page = await getMemoryLibrary(
        {
          query,
          ...(activeOnly ? { active_only: true } : { status }),
          ...(source ? { source } : {}),
          offset,
          limit: 100,
        },
        request.signal,
      );
      if (!valid()) return;
      if (
        activeOnly &&
        (!page ||
          page.offset !== offset ||
          page.limit !== 100 ||
          !Number.isSafeInteger(page.total) ||
          page.total < 0 ||
          !Array.isArray(page.items) ||
          page.items.length > page.limit ||
          new Set(page.items.map((item) => item.memory_id)).size !==
            page.items.length ||
          page.items.some((item) => item.status !== "confirmed"))
      )
        throw Error("invalid_map_page");
      if (page.source_ids_by_memory !== undefined) {
        const mapping = page.source_ids_by_memory;
        const ids = new Set(page.items.map((item) => item.memory_id));
        if (
          !mapping ||
          typeof mapping !== "object" ||
          Array.isArray(mapping) ||
          Object.keys(mapping).length !== ids.size ||
          Object.entries(mapping).some(
            ([id, sourceIds]) =>
              !ids.has(id) ||
              !Array.isArray(sourceIds) ||
              new Set(sourceIds).size !== sourceIds.length ||
              sourceIds.some(
                (sourceId) =>
                  typeof sourceId !== "string" ||
                  sourceId.length < 1 ||
                  sourceId.length > 128,
              ),
          )
        )
          throw Error("invalid_memory_sources");
      }
      // Offset pages are independent snapshots; deletion can move the last page.
      if (offset > 0 && offset >= page.total) {
        setPosition({
          scope,
          offset: Math.max(
            0,
            Math.floor((page.total - 1) / page.limit) * page.limit,
          ),
        });
        return;
      }
      setResult((previous) => ({
        key,
        authority: sourceKey,
        page:
          previous.key === key &&
          previous.page &&
          JSON.stringify(previous.page) === JSON.stringify(page)
            ? previous.page
            : page,
        failed: false,
        refreshing: false,
        query,
        source,
      }));
    } catch (error) {
      if (!valid()) return;
      setResult({
        key,
        authority: sourceKey,
        page: null,
        failed: true,
        refreshing: false,
        query,
        source,
      });
      throw error;
    }
  }, [
    enabled,
    stale,
    key,
    query,
    status,
    offset,
    scope,
    source,
    sourceKey,
    activeOnly,
    keepPreviousOnRefresh,
  ]);
  useEffect(() => {
    if (!enabled) {
      invalidate();
      return;
    }
    // Preserve a verified page while source metadata is being refreshed.
    // A real authority change changes sourceKey and still invalidates the page;
    // stale continues to block writes until the refresh is authoritative.
    if (stale) return;
    void refresh().catch(() => {});
    return () => {
      ++epoch.current;
      controller.current?.abort();
    };
  }, [enabled, stale, refresh, invalidate]);
  const page =
    enabled && result.key === key
      ? result.page
      : enabled &&
          keepPreviousOnRefresh &&
          result.authority === sourceKey &&
          result.page
        ? result.page
        : null;
  const failed = enabled && !stale && result.key === key && result.failed;
  const stalePage = !failed && !!page && page.stale === true;
  const refreshing =
    enabled && !stale && !failed && (result.key !== key || result.refreshing);
  // While the backend reports a partial snapshot (read budget exhausted under
  // a history import) keep polling gently instead of leaving a dead end; the
  // import finishes on its own and the next poll shows the full page.
  const retryTick = stalePage ? (page?.total ?? 0) : -1;
  useEffect(() => {
    if (!stalePage) return;
    void retryTick;
    const timer = setTimeout(() => {
      void refresh().catch(() => {});
    }, 5000);
    return () => clearTimeout(timer);
  }, [stalePage, retryTick, refresh]);
  return {
    page,
    failed,
    stale: stalePage,
    settledQuery: result.query,
    settledSource: result.source,
    loading: enabled && !stale && !failed && (!page || refreshing),
    refreshing: !!page && refreshing,
    writeBlocked:
      !page || refreshing || failed || stalePage || stale || !enabled,
    writable:
      enabled && !stale && !!page && !failed && !refreshing && !stalePage,
    offset,
    scope,
    key,
    go: (nextOffset: number) =>
      setPosition({
        scope,
        offset: Math.max(0, nextOffset),
      }),
    refresh,
    invalidate,
  };
}
