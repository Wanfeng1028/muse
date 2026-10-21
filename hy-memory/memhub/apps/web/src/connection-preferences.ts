const KEY = "one-memory.connection-preferences.v1";

export interface ConnectionPreferences {
  syncSourceIds: string[];
  hostSourceIds: string[];
}

export function readConnectionPreferences(): ConnectionPreferences {
  try {
    const value = JSON.parse(window.localStorage.getItem(KEY) ?? "null");
    if (
      value?.version !== 1 ||
      !Array.isArray(value.syncSourceIds) ||
      !Array.isArray(value.hostSourceIds)
    )
      throw Error();
    return {
      syncSourceIds: value.syncSourceIds.filter(
        (id: unknown): id is string => typeof id === "string",
      ),
      hostSourceIds: value.hostSourceIds.filter(
        (id: unknown): id is string => typeof id === "string",
      ),
    };
  } catch {
    return { syncSourceIds: [], hostSourceIds: [] };
  }
}

export function saveConnectionPreferences(value: ConnectionPreferences) {
  try {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({
        version: 1,
        syncSourceIds: [...new Set(value.syncSourceIds)],
        hostSourceIds: [...new Set(value.hostSourceIds)],
      }),
    );
  } catch {
    // Private mode, quota, or a blocked store must not crash the setup flow.
  }
}

function withId(ids: string[], sourceId: string, enabled: boolean) {
  return enabled
    ? [...new Set([...ids, sourceId])]
    : ids.filter((id) => id !== sourceId);
}

export function writeConnectionPreference(
  kind: "sync" | "host",
  sourceId: string,
  enabled: boolean,
) {
  const current = readConnectionPreferences();
  saveConnectionPreferences({
    syncSourceIds:
      kind === "sync"
        ? withId(current.syncSourceIds, sourceId, enabled)
        : current.syncSourceIds,
    hostSourceIds:
      kind === "host"
        ? withId(current.hostSourceIds, sourceId, enabled)
        : current.hostSourceIds,
  });
}
