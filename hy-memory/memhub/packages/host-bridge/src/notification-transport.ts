import axios from "axios";
import { readDiscovery } from "./discovery.js";
import type { SourceChangeNotification } from "./memmy-adapter/claude-code/event-adapter.js";
import type {
  NotificationBinding,
  NotifySourceChanged,
} from "./memmy-adapter/claude-code/runtime.js";
import {
  exactKeys,
  isRecord,
  runtimeConfig,
} from "./memmy-adapter/claude-code/runtime-config.js";

export const capability = "source-change-v1";
type ErrorCode =
  | "invalid_notification"
  | "host_credential_unavailable"
  | "host_authorization_required"
  | "source_not_authorized"
  | "source_work_unavailable"
  | "source_notification_rate_limited"
  | "notification_unavailable";

const errors: Record<ErrorCode, { status: number; message: string }> = {
  invalid_notification: {
    status: 400,
    message: "MemHub source notification is invalid.",
  },
  host_credential_unavailable: {
    status: 401,
    message: "MemHub installation credential is unavailable.",
  },
  host_authorization_required: {
    status: 401,
    message: "MemHub installation authorization is required or has changed.",
  },
  source_not_authorized: {
    status: 403,
    message: "MemHub source read and sync permission are required.",
  },
  source_work_unavailable: {
    status: 409,
    message: "MemHub source work is paused or unavailable.",
  },
  source_notification_rate_limited: {
    status: 429,
    message: "MemHub source notification capacity is temporarily limited.",
  },
  notification_unavailable: {
    status: 503,
    message: "MemHub source notification service is unavailable.",
  },
};
export class NotificationTransportError extends Error {
  readonly status: number;
  constructor(readonly code: ErrorCode) {
    super(errors[code].message);
    this.name = "NotificationTransportError";
    this.status = errors[code].status;
  }
}

function notification(value: unknown): SourceChangeNotification {
  if (
    !isRecord(value) ||
    !exactKeys(value, ["version", "event_id", "session_id", "event_kind"]) ||
    value.version !== 1 ||
    value.event_kind !== "source-changed" ||
    typeof value.event_id !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.event_id) ||
    typeof value.session_id !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value.session_id)
  ) {
    throw new NotificationTransportError("invalid_notification");
  }
  return {
    version: 1,
    event_id: value.event_id,
    session_id: value.session_id,
    event_kind: "source-changed",
  };
}
function jsonResponse(contentType: unknown, data: unknown): unknown {
  if (
    typeof contentType !== "string" ||
    !/^application\/json(?:\s*;|$)/i.test(contentType) ||
    typeof data !== "string"
  )
    throw new NotificationTransportError("notification_unavailable");
  return JSON.parse(data);
}
function statusError(status: number): NotificationTransportError {
  const code: ErrorCode =
    status === 400
      ? "invalid_notification"
      : status === 401
        ? "host_authorization_required"
        : status === 403
          ? "source_not_authorized"
          : status === 409
            ? "source_work_unavailable"
            : status === 429
              ? "source_notification_rate_limited"
              : "notification_unavailable";
  return new NotificationTransportError(code);
}

export function createNotificationTransport(
  binding: NotificationBinding,
): NotifySourceChanged {
  let config: ReturnType<typeof runtimeConfig>;
  try {
    config = runtimeConfig(binding.config);
    if (typeof binding.credentialProvider !== "function") throw new Error();
  } catch {
    throw new NotificationTransportError("notification_unavailable");
  }
  const credentialProvider = binding.credentialProvider;
  // Separate Axios instance: no global retry/interceptor or environment proxy inheritance.
  const client = axios.create({
    proxy: false,
    maxRedirects: 0,
    maxContentLength: 8192,
    maxBodyLength: 4096,
    responseType: "text",
    transformResponse: [(value: unknown) => value],
    validateStatus: () => true,
  });
  return async (input) => {
    const payload = notification(input);
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const expired = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new NotificationTransportError("notification_unavailable"));
      }, 25_000);
    });
    const send = async () => {
      try {
        const discovery = await readDiscovery(config.discoveryPath);
        controller.signal.throwIfAborted();
        if (
          discovery.status !== "running" ||
          discovery.port === null ||
          !discovery.instance_id ||
          discovery.instance_id.length > 128
        )
          throw new NotificationTransportError("notification_unavailable");
        const base = `http://${discovery.host}:${discovery.port}`;
        const health = await client.get(`${base}/health`, {
          timeout: 1000,
          signal: controller.signal,
        });
        if (health.status !== 200)
          throw new NotificationTransportError("notification_unavailable");
        const identity = jsonResponse(
          health.headers["content-type"],
          health.data,
        );
        if (
          !isRecord(identity) ||
          identity.status !== "ok" ||
          identity.service !== "one-memory-recall-broker" ||
          identity.instance_id !== discovery.instance_id
        )
          throw new NotificationTransportError("notification_unavailable");
        let credential: string;
        try {
          credential = await credentialProvider();
          if (
            typeof credential !== "string" ||
            !/^omhg_v1_[A-Za-z0-9_-]{43}$/.test(credential)
          )
            throw new Error();
        } catch {
          throw new NotificationTransportError("host_credential_unavailable");
        }
        controller.signal.throwIfAborted();
        const current = await readDiscovery(config.discoveryPath);
        controller.signal.throwIfAborted();
        if (
          current.status !== "running" ||
          current.host !== discovery.host ||
          current.port !== discovery.port ||
          current.instance_id !== discovery.instance_id
        )
          throw new NotificationTransportError("notification_unavailable");
        const response = await client.post(`${base}/source-changed`, payload, {
          timeout: 25_000,
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${credential}`,
          },
        });
        if (response.status !== 200) throw statusError(response.status);
        const result = jsonResponse(
          response.headers["content-type"],
          response.data,
        );
        if (
          !isRecord(result) ||
          !exactKeys(result, ["accepted"]) ||
          result.accepted !== true
        )
          throw new NotificationTransportError("notification_unavailable");
        return { accepted: true as const };
      } catch (error) {
        if (error instanceof NotificationTransportError) throw error;
        // Never retain Axios config/headers or discovery/parser causes containing private paths.
        throw new NotificationTransportError("notification_unavailable");
      }
    };
    try {
      return await Promise.race([send(), expired]);
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      controller.abort();
    }
  };
}
