export interface NativeDisplayPreferences {
  readonly reduceMotion: boolean;
  readonly reduceTransparency: boolean;
  readonly revision: number;
}

type NativeSession = {
  owners: number;
  unsubscribe: (() => void) | null;
};

const motionQuery = "(prefers-reduced-motion: reduce)";
const transparencyQuery = "(prefers-reduced-transparency: reduce)";
const nativeListeners = new Set<() => void>();
let nativeSnapshot: NativeDisplayPreferences | null = null;
let nativeSession: NativeSession | null = null;

export function getNativeDisplayPreferences(): NativeDisplayPreferences | null {
  return nativeSnapshot;
}

export function subscribeNativeDisplayPreferences(
  notify: () => void,
): () => void {
  // Each subscription owns an entry, including callers sharing one callback.
  const listener = () => notify();
  nativeListeners.add(listener);
  return () => {
    nativeListeners.delete(listener);
  };
}

export function startNativeDisplayPreferences(): () => void {
  let session = nativeSession;
  const firstOwner = session === null;
  if (!session) {
    session = { owners: 0, unsubscribe: null };
    nativeSession = session;
  }
  session.owners += 1;
  if (firstOwner) connect(session);
  let released = false;
  return () => {
    if (released) return;
    released = true;
    session.owners -= 1;
    if (session.owners !== 0 || nativeSession !== session) return;
    // Invalidate the session before cleanup, which may synchronously emit.
    nativeSession = null;
    try {
      session.unsubscribe?.();
    } catch {
      // A disposed shell must not retain renderer state or break media fallback.
    }
    publish(null);
  };
}

export function readDisplayPreference(query: string): boolean {
  const media = mediaQuery(query)?.matches === true;
  return media || nativeValue(query);
}

export function subscribeDisplayPreference(
  query: string,
  notify: () => void,
): () => void {
  const media = mediaQuery(query);
  let active = true;
  let value = readDisplayPreference(query);
  const changed = () => {
    if (!active) return;
    const next = readDisplayPreference(query);
    if (next === value) return;
    value = next;
    notify();
  };
  const stopNative = isReductionQuery(query)
    ? subscribeNativeDisplayPreferences(changed)
    : null;
  if (typeof media?.addEventListener === "function") {
    media.addEventListener("change", changed);
  } else {
    media?.addListener?.(changed);
  }
  return () => {
    if (!active) return;
    active = false;
    stopNative?.();
    if (typeof media?.removeEventListener === "function") {
      media.removeEventListener("change", changed);
    } else {
      media?.removeListener?.(changed);
    }
  };
}

function connect(session: NativeSession) {
  const bridge = typeof window === "undefined" ? undefined : window.oneMemory;
  if (!bridge) return;
  // Subscribe first so a notification cannot be lost while the initial IPC is pending.
  try {
    if (typeof bridge.onDisplayPreferencesChanged === "function") {
      const unsubscribe = bridge.onDisplayPreferencesChanged((value) =>
        accept(session, value),
      );
      if (typeof unsubscribe === "function") session.unsubscribe = unsubscribe;
    }
  } catch {
    // Old or unavailable subscription methods do not prevent the initial read.
  }
  try {
    if (typeof bridge.getDisplayPreferences === "function") {
      void Promise.resolve(bridge.getDisplayPreferences()).then(
        (value) => accept(session, value),
        () => {},
      );
    }
  } catch {
    // Retain any known native flags; a failed read is not a false preference.
  }
}

function accept(session: NativeSession, value: unknown) {
  if (nativeSession !== session || session.owners === 0) return;
  if (!value || typeof value !== "object" || Array.isArray(value)) return;
  const candidate = value as Record<string, unknown>;
  const { reduceMotion, reduceTransparency, revision } = candidate;
  if (
    typeof reduceMotion !== "boolean" ||
    typeof reduceTransparency !== "boolean" ||
    typeof revision !== "number" ||
    !Number.isSafeInteger(revision) ||
    revision < 0 ||
    (nativeSnapshot !== null && revision <= nativeSnapshot.revision)
  )
    return;
  publish(Object.freeze({ reduceMotion, reduceTransparency, revision }));
}

function publish(value: NativeDisplayPreferences | null) {
  if (nativeSnapshot === value) return;
  nativeSnapshot = value;
  for (const listener of [...nativeListeners]) listener();
}

function nativeValue(query: string) {
  if (query === motionQuery) return nativeSnapshot?.reduceMotion === true;
  if (query === transparencyQuery)
    return nativeSnapshot?.reduceTransparency === true;
  return false;
}

function isReductionQuery(query: string) {
  return query === motionQuery || query === transparencyQuery;
}

function mediaQuery(query: string): MediaQueryList | undefined {
  try {
    return typeof window === "undefined"
      ? undefined
      : window.matchMedia?.(query);
  } catch {
    return undefined;
  }
}
