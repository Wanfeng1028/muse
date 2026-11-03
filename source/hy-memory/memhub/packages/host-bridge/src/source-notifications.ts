import {
  HostGrantError,
  type HostGrantStore,
  type VerifiedInstallationIdentity,
} from "./host-grants.js";

export interface SourceChangeNotification {
  readonly version: 1;
  readonly event_id: string;
  readonly session_id: string;
  readonly event_kind: "source-changed";
}
export type SourceChangeAcceptance = { accepted: true };
export interface SourceNotificationHandler {
  checkSource(sourceId: string): Promise<void>;
  synchronize(sourceId: string, signal: AbortSignal): Promise<void>;
}

const FAILURES = {
  source_notification_invalid: [400, "Invalid source notification."],
  host_grant_authentication_failed: [
    401,
    "Installation authentication is required.",
  ],
  source_not_authorized: [403, "Source notification permission is required."],
  source_host_unmapped: [403, "This installation cannot notify a source."],
  source_host_unsupported: [403, "This installation cannot notify a source."],
  source_notification_permission_required: [
    403,
    "Source notification permission is required.",
  ],
  source_notification_permission_changed: [
    403,
    "Source notification permission has changed.",
  ],
  source_work_unavailable: [
    409,
    "Source synchronization is not complete or is unavailable.",
  ],
  source_notification_conflict: [
    409,
    "The event identity conflicts with an earlier notification.",
  ],
  source_notification_cancelled: [409, "Source notification was cancelled."],
  source_notification_rate_limited: [
    429,
    "Source notification rate limit reached.",
  ],
  source_notification_capacity: [429, "Source notification capacity reached."],
  source_notification_core_changed: [
    503,
    "The source service identity has changed.",
  ],
  source_notification_unavailable: [
    503,
    "Source notifications are unavailable.",
  ],
} as const;
export type SourceNotificationErrorCode = keyof typeof FAILURES;
export type SourceNotificationStatus = 400 | 401 | 403 | 409 | 429 | 503;

export class SourceNotificationError extends Error {
  readonly code: SourceNotificationErrorCode;
  readonly status: SourceNotificationStatus;

  constructor(
    code: SourceNotificationErrorCode,
    status: SourceNotificationStatus,
  ) {
    const valid = Object.hasOwn(FAILURES, code) && FAILURES[code][0] === status;
    const safeCode = valid ? code : "source_notification_unavailable";
    super(FAILURES[safeCode][1]);
    this.name = "SourceNotificationError";
    this.code = safeCode;
    this.status = FAILURES[safeCode][0];
  }
}

const MINUTE_MS = 60_000;
const MAX_EVENTS_PER_MINUTE = 12;
const MAX_DISPATCHES = 4;
const MAX_RECEIPTS = 256;
// Bound preflight requests and duplicate waiters as well as actual sync work.
const MAX_REQUESTS = 16;
const MAX_RATE_INSTALLATIONS = 1024;
const WORK_DEADLINE_MS = 15_000;

interface EventEntry {
  sessionId: string;
  promise: Promise<void>;
}
interface CachedEvent {
  sessionId: string;
  expiresAt: number;
}

function failure(code: SourceNotificationErrorCode): SourceNotificationError {
  return new SourceNotificationError(code, FAILURES[code][0]);
}
function normalizeError(error: unknown): SourceNotificationError {
  if (error instanceof SourceNotificationError)
    return new SourceNotificationError(error.code, error.status);
  if (
    error instanceof HostGrantError &&
    error.code === "host_grant_authentication_failed"
  )
    return failure("host_grant_authentication_failed");
  return failure("source_notification_unavailable");
}
function notification(input: unknown): SourceChangeNotification {
  if (!input || typeof input !== "object" || Array.isArray(input))
    throw failure("source_notification_invalid");
  const value = input as Record<string, unknown>;
  if (
    Object.keys(value).length !== 4 ||
    !["version", "event_id", "session_id", "event_kind"].every((key) =>
      Object.hasOwn(value, key),
    ) ||
    value.version !== 1 ||
    value.event_kind !== "source-changed" ||
    typeof value.event_id !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.event_id) ||
    typeof value.session_id !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value.session_id)
  )
    throw failure("source_notification_invalid");
  return {
    version: 1,
    event_id: value.event_id,
    session_id: value.session_id,
    event_kind: "source-changed",
  };
}

/** One broker instance owns this dispatcher. No content, credentials or paths are cached. */
export class SourceNotificationDispatcher {
  readonly #store: HostGrantStore;
  readonly #handler: SourceNotificationHandler;
  readonly #now: () => number;
  readonly #observe: (event: {
    outcome: string;
    reason?: string;
  }) => void | Promise<void>;
  readonly #inflight = new Map<string, EventEntry>();
  readonly #cache = new Map<string, CachedEvent>();
  readonly #rates = new Map<
    string,
    Array<{ id: string; sessionId: string; at: number }>
  >();
  readonly #controllers = new Set<AbortController>();
  readonly #requests = new Set<Promise<SourceChangeAcceptance>>();
  #stopping = false;

  constructor(
    store: HostGrantStore,
    handler: SourceNotificationHandler,
    options: {
      now?: () => number;
      observe?: (event: {
        outcome: string;
        reason?: string;
      }) => void | Promise<void>;
    } = {},
  ) {
    this.#store = store;
    this.#handler = handler;
    this.#now = options.now ?? (() => performance.now());
    this.#observe = options.observe ?? (() => {});
  }

  dispatch(secret: string, input: unknown): Promise<SourceChangeAcceptance> {
    if (this.#stopping)
      return Promise.reject(failure("source_notification_unavailable"));
    if (this.#requests.size >= MAX_REQUESTS)
      return Promise.reject(failure("source_notification_capacity"));
    const controller = new AbortController();
    this.#controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), WORK_DEADLINE_MS);
    timer.unref();
    const pending = this.#dispatch(secret, input, controller.signal).catch(
      (error: unknown) => {
        throw normalizeError(error);
      },
    );
    this.#requests.add(pending);
    const cleanup = () => {
      clearTimeout(timer);
      this.#controllers.delete(controller);
      this.#requests.delete(pending);
    };
    void pending.then(cleanup, cleanup);
    return pending;
  }

  async shutdown(): Promise<void> {
    this.#stopping = true;
    for (const controller of this.#controllers) controller.abort();
    await Promise.allSettled([...this.#requests]);
    this.#cache.clear();
    this.#rates.clear();
  }

  #checkActive(signal: AbortSignal): void {
    if (this.#stopping) throw failure("source_notification_unavailable");
    if (signal.aborted) throw failure("source_notification_cancelled");
  }

  async #identity(
    secret: string,
    expected?: VerifiedInstallationIdentity,
  ): Promise<VerifiedInstallationIdentity> {
    const identity = await this.#store.authenticateInstallation(secret);
    if (
      expected &&
      (identity.installationId !== expected.installationId ||
        identity.hostId !== expected.hostId ||
        identity.revision !== expected.revision)
    )
      throw failure("host_grant_authentication_failed");
    return identity;
  }

  async #verify(
    secret: string,
    expected: VerifiedInstallationIdentity,
    signal: AbortSignal,
  ): Promise<void> {
    this.#checkActive(signal);
    await this.#handler.checkSource("claude-code");
    await this.#identity(secret, expected);
    this.#checkActive(signal);
  }

  #prune(): void {
    const now = this.#now();
    for (const [key, item] of this.#cache)
      if (item.expiresAt <= now) this.#cache.delete(key);
    for (const [key, entries] of this.#rates) {
      const recent = entries.filter((entry) => entry.at > now - MINUTE_MS);
      if (recent.length) this.#rates.set(key, recent);
      else this.#rates.delete(key);
    }
  }

  #takeRate(installationId: string, event: SourceChangeNotification): void {
    const entries = this.#rates.get(installationId) ?? [];
    const prior = entries.find((entry) => entry.id === event.event_id);
    if (prior) {
      if (prior.sessionId !== event.session_id)
        throw failure("source_notification_conflict");
      return;
    }
    if (entries.length >= MAX_EVENTS_PER_MINUTE)
      throw failure("source_notification_rate_limited");
    if (
      !this.#rates.has(installationId) &&
      this.#rates.size >= MAX_RATE_INSTALLATIONS
    )
      throw failure("source_notification_capacity");
    this.#rates.set(installationId, [
      ...entries,
      { id: event.event_id, sessionId: event.session_id, at: this.#now() },
    ]);
  }

  async #dispatch(
    secret: string,
    input: unknown,
    signal: AbortSignal,
  ): Promise<SourceChangeAcceptance> {
    const event = notification(input);
    const identity = await this.#identity(secret);
    if (identity.hostId !== "claude-code")
      throw failure("source_host_unmapped");
    await this.#verify(secret, identity, signal);
    this.#prune();
    const key = JSON.stringify([
      identity.installationId,
      identity.revision,
      event.event_id,
    ]);
    const cached = this.#cache.get(key);
    const existing = this.#inflight.get(key);
    if (
      (cached && cached.sessionId !== event.session_id) ||
      (existing && existing.sessionId !== event.session_id)
    )
      throw failure("source_notification_conflict");
    if (cached) {
      await this.#observe({ outcome: "skipped", reason: "duplicate" });
      return { accepted: true };
    }
    if (existing) {
      await existing.promise;
      await this.#verify(secret, identity, signal);
      await this.#observe({ outcome: "skipped", reason: "coalesced" });
      return { accepted: true };
    }
    if (this.#inflight.size >= MAX_DISPATCHES)
      throw failure("source_notification_capacity");
    this.#takeRate(identity.installationId, event);
    // Register synchronously before invoking an async handler; all joins use this one operation.
    const work = Promise.resolve().then(async () => {
      this.#checkActive(signal);
      await this.#handler.synchronize("claude-code", signal);
      await this.#verify(secret, identity, signal);
      while (this.#cache.size >= MAX_RECEIPTS) {
        const oldest = this.#cache.keys().next().value;
        if (oldest !== undefined) this.#cache.delete(oldest);
      }
      this.#cache.set(key, {
        sessionId: event.session_id,
        expiresAt: this.#now() + MINUTE_MS,
      });
      await this.#observe({ outcome: "written" });
    });
    this.#inflight.set(key, { sessionId: event.session_id, promise: work });
    try {
      await work;
      return { accepted: true };
    } finally {
      this.#inflight.delete(key);
    }
  }
}
