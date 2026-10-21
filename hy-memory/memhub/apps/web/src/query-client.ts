import { QueryClient, type QueryKey } from "@tanstack/react-query";

/** The one client holding server state for every page. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    },
    mutations: { retry: false },
  },
});

const resets = new Set<() => void>();

/** Module state that orders reads and writes goes away together with the cache. */
export function onClientReset(reset: () => void) {
  resets.add(reset);
}

export function resetClient() {
  void queryClient.cancelQueries();
  queryClient.clear();
  for (const reset of resets) reset();
}

// Forced reads always go out; only a read newer than the last one to land is kept.
export function latestReads<T>(key: QueryKey, read: () => Promise<T>) {
  let started = 0;
  let landed = 0;
  onClientReset(() => {
    started = 0;
    landed = 0;
  });
  return async (): Promise<T> => {
    const order = ++started;
    const next = await read();
    if (order < landed) return queryClient.getQueryData<T>(key) ?? next;
    landed = order;
    queryClient.setQueryData<T>(key, next);
    return next;
  };
}
