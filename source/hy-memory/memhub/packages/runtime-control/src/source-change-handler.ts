/** Shared bridge from authenticated host notifications to the current Core. */
import {
  SourceNotificationError,
  type SourceNotificationHandler,
} from "@one-memory/host-bridge";
import axios from "axios";

interface SourceIdentity {
  root: string;
  revision: number;
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function createSourceChangeHandler(options: {
  coreBaseUrl: string;
  coreApiToken: string;
  instanceId: string;
}): SourceNotificationHandler {
  const base = new URL(options.coreBaseUrl);
  if (
    base.protocol !== "http:" ||
    base.hostname !== "127.0.0.1" ||
    !base.port ||
    base.username ||
    base.password ||
    base.pathname !== "/" ||
    base.search ||
    base.hash ||
    !options.coreApiToken ||
    !options.instanceId
  )
    throw new Error("invalid_source_notification_core");
  const instanceId = options.instanceId;
  const client = axios.create({
    baseURL: base.origin,
    headers: { Authorization: `Bearer ${options.coreApiToken}` },
    proxy: false,
    maxRedirects: 0,
    timeout: 15_000,
    maxContentLength: 1024 * 1024,
    maxBodyLength: 1024,
  });

  const checkCancelled = (signal?: AbortSignal) => {
    if (signal?.aborted)
      throw new SourceNotificationError("source_notification_cancelled", 409);
  };
  const translate = (error: unknown): never => {
    if (error instanceof SourceNotificationError) throw error;
    if (axios.isAxiosError(error) && error.response?.status === 409)
      throw new SourceNotificationError("source_work_unavailable", 409);
    throw new SourceNotificationError("source_notification_unavailable", 503);
  };
  const inspect = async (
    sourceId: string,
    signal?: AbortSignal,
  ): Promise<SourceIdentity> => {
    checkCancelled(signal);
    if (sourceId !== "claude-code")
      throw new SourceNotificationError("source_host_unsupported", 403);
    try {
      const health = (await client.get<unknown>("/api/v1/health", { signal }))
        .data;
      if (
        !object(health) ||
        health.status !== "ok" ||
        health.service !== "one-memory-core" ||
        health.instance_id !== instanceId
      )
        throw new SourceNotificationError(
          "source_notification_core_changed",
          503,
        );
      const sources = (await client.get<unknown>("/api/v1/sources", { signal }))
        .data;
      if (!Array.isArray(sources))
        throw new SourceNotificationError(
          "source_notification_unavailable",
          503,
        );
      const selected = sources.filter(
        (source) => object(source) && source.source_id === sourceId,
      );
      const source: unknown = selected[0];
      if (
        selected.length !== 1 ||
        !object(source) ||
        source.authorized !== true ||
        source.sync_enabled !== true ||
        typeof source.root_id !== "string" ||
        !/^root:v2:[a-f0-9]{64}$/.test(source.root_id) ||
        source.candidate_root_id !== source.root_id ||
        !Number.isSafeInteger(source.grant_revision) ||
        Number(source.grant_revision) < 1
      )
        throw new SourceNotificationError(
          "source_notification_permission_required",
          403,
        );
      if (
        source.sync_completeness === "one_time_snapshot" ||
        !object(source.capabilities) ||
        source.capabilities.live_sync !== "implemented"
      )
        throw new SourceNotificationError("source_work_unavailable", 409);
      checkCancelled(signal);
      return {
        root: source.root_id,
        revision: Number(source.grant_revision),
      };
    } catch (error) {
      return translate(error);
    }
  };

  return {
    async checkSource(sourceId) {
      await inspect(sourceId, AbortSignal.timeout(5000));
    },
    async synchronize(sourceId, signal) {
      const bounded = AbortSignal.any([signal, AbortSignal.timeout(15_000)]);
      const before = await inspect(sourceId, bounded);
      checkCancelled(bounded);
      try {
        // The Core owns the adapter, cursor, job and model consent. This trigger
        // carries neither host transcript content nor a new processing grant.
        const job = (
          await client.post<unknown>(
            `/api/v1/sources/${sourceId}/sync`,
            undefined,
            { signal: bounded },
          )
        ).data;
        if (
          !object(job) ||
          job.source_id !== sourceId ||
          job.operation !== "sync" ||
          job.status !== "completed" ||
          job.errors !== 0
        )
          throw new SourceNotificationError("source_work_unavailable", 409);
        const after = await inspect(sourceId, bounded);
        if (after.root !== before.root || after.revision !== before.revision)
          throw new SourceNotificationError(
            "source_notification_permission_changed",
            403,
          );
      } catch (error) {
        translate(error);
      }
    },
  };
}
