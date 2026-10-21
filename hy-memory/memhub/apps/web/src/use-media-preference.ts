import { useCallback, useSyncExternalStore } from "react";
import {
  readDisplayPreference,
  subscribeDisplayPreference,
} from "./display-preferences";

export function useMediaPreference(query: string) {
  const subscribe = useCallback(
    (notify: () => void) => subscribeDisplayPreference(query, notify),
    [query],
  );
  const snapshot = useCallback(() => readDisplayPreference(query), [query]);
  return useSyncExternalStore(subscribe, snapshot, () => false);
}
