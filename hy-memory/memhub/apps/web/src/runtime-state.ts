import { useQuery } from "@tanstack/react-query";
import { prefetchRecallHosts } from "./host-state";
import { latestReads, queryClient } from "./query-client";
import { prefetchSources } from "./source-state";

export type LoginPreference = {
  supported: boolean;
  enabled: boolean;
  status: string;
};

const LOGIN_KEY = ["login-preference"] as const;
const FRESH_MS = 5_000;

queryClient.setQueryDefaults(LOGIN_KEY, {
  gcTime: Number.POSITIVE_INFINITY,
  staleTime: FRESH_MS,
});

async function readLogin(): Promise<LoginPreference | null> {
  return (await window.oneMemory?.getLoginPreference?.()) ?? null;
}

export const refreshLoginPreference = latestReads(LOGIN_KEY, readLogin);

export function setLoginPreference(value: LoginPreference) {
  queryClient.setQueryData(LOGIN_KEY, value);
}

export function useLoginPreference() {
  return useQuery(
    { queryKey: LOGIN_KEY, queryFn: refreshLoginPreference, enabled: false },
    queryClient,
  ).data;
}

/** Warms what the settings page shows first; fresh data is reused. */
export function prefetchDataRuntime() {
  return Promise.all([
    prefetchSources(),
    prefetchRecallHosts(),
    queryClient.prefetchQuery({
      queryKey: LOGIN_KEY,
      queryFn: refreshLoginPreference,
    }),
  ]);
}
