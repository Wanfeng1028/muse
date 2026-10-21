import {
  disableRuntimeService,
  enableRuntimeService,
  readRuntimeServiceOwner,
  runtimeServiceEnabled,
  setAppRuntimeStartAtLogin,
} from "@one-memory/runtime-control";

export interface ManagedServiceEnableSnapshot {
  managed: boolean;
  enabled: boolean;
  appStartAtLogin: boolean | null;
}

export async function setManagedServiceEnabled(
  dataDir: string,
  enabled: boolean,
): Promise<ManagedServiceEnableSnapshot> {
  const owner = await readRuntimeServiceOwner(dataDir).catch(() => null);
  if (owner === null) {
    return { managed: false, enabled: false, appStartAtLogin: null };
  }
  const snapshot: ManagedServiceEnableSnapshot = {
    managed: true,
    enabled: await runtimeServiceEnabled(dataDir),
    appStartAtLogin: owner.owner === "app" ? owner.start_at_login : null,
  };
  if (enabled) await enableRuntimeService(dataDir);
  else await disableRuntimeService(dataDir);
  if (owner.owner === "app") {
    await setAppRuntimeStartAtLogin(dataDir, enabled);
  }
  return snapshot;
}

export async function restoreManagedServiceEnabled(
  dataDir: string,
  snapshot: ManagedServiceEnableSnapshot,
): Promise<void> {
  if (!snapshot.managed) return;
  if (snapshot.enabled) await enableRuntimeService(dataDir);
  else await disableRuntimeService(dataDir);
  if (snapshot.appStartAtLogin !== null) {
    await setAppRuntimeStartAtLogin(dataDir, snapshot.appStartAtLogin);
  }
}
