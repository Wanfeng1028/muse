import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";
import {
  HARNESS_VERSION,
  CreativeEpisodeEventSchema,
  CreativeEpisodeSchema,
  EpisodeStatusSchema,
  HarnessIdSchema,
  WorkResourceIdSchema,
  type CreativeEpisode,
  type CreativeEpisodeEvent,
  type EpisodeStatus,
} from "./contracts.js";

function isLiveProcess(pid: number): boolean {
  try { process.kill(pid, 0); return true; }
  catch (error) { return (error as NodeJS.ErrnoException).code !== "ESRCH"; }
}

export class CreativeEpisodeStore {
  private readonly db: DatabaseSync;

  constructor(path: string) {
    if (path !== ":memory:") mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    this.db.exec("PRAGMA journal_mode = WAL");
    this.db.exec("PRAGMA foreign_keys = ON");
    this.db.exec("PRAGMA busy_timeout = 5000");
    this.initializeSchema();
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const columns = this.db.prepare("PRAGMA table_info(creative_episodes)").all();
      if (!columns.some((column) => column.name === "owner_pid")) this.db.exec("ALTER TABLE creative_episodes ADD COLUMN owner_pid INTEGER");
      this.db.exec("CREATE INDEX IF NOT EXISTS creative_episode_event_work ON creative_episode_events(work_id, episode_id)");
      this.db.exec("COMMIT");
    } catch (error) { this.db.exec("ROLLBACK"); throw error; }
  }

  create(input: CreativeEpisode): CreativeEpisode {
    const episode = CreativeEpisodeSchema.parse(input);
    this.db.prepare(`
      INSERT INTO creative_episodes (
        episode_id, work_id, profile_id, status, started_at, completed_at, owner_pid
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      episode.id,
      episode.workId,
      episode.profileId,
      episode.status,
      episode.startedAt,
      episode.completedAt,
      process.pid,
    );
    return episode;
  }

  append(
    input: Omit<CreativeEpisodeEvent, "version" | "seq" | "timestamp">,
    timestamp = new Date().toISOString(),
  ): CreativeEpisodeEvent {
    const episodeId = HarnessIdSchema.parse(input.episodeId);
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const episode = this.db.prepare(
        "SELECT episode_id FROM creative_episodes WHERE episode_id = ?",
      ).get(episodeId);
      if (!episode) throw new Error(`Unknown creative episode: ${episodeId}`);
      const row = this.db.prepare(
        "SELECT COALESCE(MAX(seq), -1) + 1 AS seq FROM creative_episode_events WHERE episode_id = ?",
      ).get(episodeId) as unknown as { readonly seq: number };
      const event = CreativeEpisodeEventSchema.parse({
        version: HARNESS_VERSION,
        ...input,
        episodeId,
        seq: row.seq,
        timestamp,
      });
      this.db.prepare(`
        INSERT INTO creative_episode_events (
          episode_id, seq, timestamp, type, work_id,
          capability_id, action_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        event.episodeId,
        event.seq,
        event.timestamp,
        event.type,
        event.workId,
        event.capabilityId ?? null,
        event.actionId ?? null,
        JSON.stringify(event.payload),
      );
      this.db.exec("COMMIT");
      return event;
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  finish(
    episodeId: string,
    status: Exclude<EpisodeStatus, "running">,
    completedAt = new Date().toISOString(),
  ): CreativeEpisode {
    const id = HarnessIdSchema.parse(episodeId);
    EpisodeStatusSchema.parse(status);
    const result = this.db.prepare(`
      UPDATE creative_episodes
      SET status = ?, completed_at = ?
      WHERE episode_id = ? AND status = 'running'
    `).run(status, completedAt, id);
    if (Number(result.changes) !== 1) {
      throw new Error(`Creative episode is missing or already terminal: ${id}`);
    }
    return this.requireEpisode(id);
  }

  getEpisode(episodeId: string): CreativeEpisode | undefined {
    const id = HarnessIdSchema.parse(episodeId);
    const row = this.db.prepare(`
      SELECT episode_id AS id, work_id AS workId, profile_id AS profileId,
             status, started_at AS startedAt, completed_at AS completedAt
      FROM creative_episodes
      WHERE episode_id = ?
    `).get(id) as unknown as Record<string, unknown> | undefined;
    return row ? CreativeEpisodeSchema.parse({ version: HARNESS_VERSION, ...row }) : undefined;
  }

  requireEpisode(episodeId: string): CreativeEpisode {
    const episode = this.getEpisode(episodeId);
    if (!episode) throw new Error(`Unknown creative episode: ${episodeId}`);
    return episode;
  }

  bindWork(
    episodeId: string,
    workId: string,
    timestamp = new Date().toISOString(),
  ): CreativeEpisode {
    const id = HarnessIdSchema.parse(episodeId);
    const boundWorkId = WorkResourceIdSchema.parse(workId);
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const row = this.db.prepare(`
        SELECT work_id AS workId, status
        FROM creative_episodes
        WHERE episode_id = ?
      `).get(id) as unknown as { readonly workId: string | null; readonly status: EpisodeStatus } | undefined;
      if (!row) throw new Error(`Unknown creative episode: ${id}`);
      if (row.workId !== null && row.workId !== boundWorkId) {
        throw new Error(`Creative episode "${id}" is already bound to Work "${row.workId}"`);
      }
      if (row.workId === boundWorkId) {
        this.db.exec("COMMIT");
        return this.requireEpisode(id);
      }
      if (row.status !== "running") {
        throw new Error(`Cannot bind terminal creative episode: ${id}`);
      }

      const seqRow = this.db.prepare(
        "SELECT COALESCE(MAX(seq), -1) + 1 AS seq FROM creative_episode_events WHERE episode_id = ?",
      ).get(id) as unknown as { readonly seq: number };
      const event = CreativeEpisodeEventSchema.parse({
        version: HARNESS_VERSION,
        episodeId: id,
        seq: seqRow.seq,
        timestamp,
        type: "episode-work-bound",
        workId: boundWorkId,
        payload: {},
      });
      this.db.prepare(`
        UPDATE creative_episodes
        SET work_id = ?
        WHERE episode_id = ? AND work_id IS NULL AND status = 'running'
      `).run(boundWorkId, id);
      this.db.prepare(`
        INSERT INTO creative_episode_events (
          episode_id, seq, timestamp, type, work_id,
          capability_id, action_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        event.episodeId,
        event.seq,
        event.timestamp,
        event.type,
        event.workId,
        null,
        null,
        JSON.stringify(event.payload),
      );
      this.db.exec("COMMIT");
      return this.requireEpisode(id);
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  listEpisodes(options: {
    readonly workId?: string;
    readonly profileId?: string;
    readonly status?: EpisodeStatus;
    readonly limit?: number;
  } = {}): CreativeEpisode[] {
    const workId = options.workId === undefined ? null : WorkResourceIdSchema.parse(options.workId);
    const profileId = options.profileId === undefined ? null : HarnessIdSchema.parse(options.profileId);
    const status = options.status === undefined ? null : EpisodeStatusSchema.parse(options.status);
    const limit = Math.max(1, Math.min(500, Math.trunc(options.limit ?? 100)));
    const rows = this.db.prepare(`
      SELECT episode_id AS id, work_id AS workId, profile_id AS profileId,
             status, started_at AS startedAt, completed_at AS completedAt
      FROM creative_episodes
      WHERE (? IS NULL OR work_id = ? OR EXISTS (
        SELECT 1 FROM creative_episode_events e WHERE e.episode_id=creative_episodes.episode_id
          AND (e.work_id=? OR (e.type='action-started' AND (
            json_extract(e.payload_json,'$.parameters.workId')=?
            OR json_extract(e.payload_json,'$.parameters.projectId')=?
            OR json_extract(e.payload_json,'$.parameters.bookId')=?
          )))
      ))
        AND (? IS NULL OR profile_id = ?)
        AND (? IS NULL OR status = ?)
      ORDER BY started_at DESC, episode_id DESC
      LIMIT ?
    `).all(workId, workId, workId, workId, workId, workId, profileId, profileId, status, status, limit) as unknown as ReadonlyArray<Record<string, unknown>>;
    return rows.map((row) => CreativeEpisodeSchema.parse({ version: HARNESS_VERSION, ...row }));
  }

  listEvents(episodeId: string): CreativeEpisodeEvent[] {
    const id = HarnessIdSchema.parse(episodeId);
    const rows = this.db.prepare(`
      SELECT episode_id AS episodeId, seq, timestamp, type, work_id AS workId,
             capability_id AS capabilityId, action_id AS actionId, payload_json AS payloadJson
      FROM creative_episode_events
      WHERE episode_id = ?
      ORDER BY seq ASC
    `).all(id) as unknown as ReadonlyArray<Record<string, unknown> & { readonly payloadJson: string }>;
    return rows.map(({ payloadJson, capabilityId, actionId, ...row }) => CreativeEpisodeEventSchema.parse({
      version: HARNESS_VERSION,
      ...row,
      ...(typeof capabilityId === "string" ? { capabilityId } : {}),
      ...(typeof actionId === "string" ? { actionId } : {}),
      payload: JSON.parse(payloadJson),
    }));
  }

  recoverInterruptedEpisodes(
    completedAt = new Date().toISOString(),
    reason = "studio-process-restarted",
  ): number {
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const rows = this.db.prepare(`
        SELECT episode_id AS episodeId, work_id AS workId, owner_pid AS ownerPid
        FROM creative_episodes
        WHERE status = 'running'
        ORDER BY started_at ASC, episode_id ASC
      `).all() as unknown as ReadonlyArray<{ readonly episodeId: string; readonly workId: string | null; readonly ownerPid: number | null }>;
      let recovered = 0;
      for (const row of rows) {
        if (row.ownerPid && isLiveProcess(row.ownerPid)) continue;
        const seqRow = this.db.prepare(
          "SELECT COALESCE(MAX(seq), -1) + 1 AS seq FROM creative_episode_events WHERE episode_id = ?",
        ).get(row.episodeId) as unknown as { readonly seq: number };
        const event = CreativeEpisodeEventSchema.parse({
          version: HARNESS_VERSION,
          episodeId: row.episodeId,
          seq: seqRow.seq,
          timestamp: completedAt,
          type: "episode-failed",
          workId: row.workId,
          payload: { reason },
        });
        this.db.prepare(`
          INSERT INTO creative_episode_events (
            episode_id, seq, timestamp, type, work_id,
            capability_id, action_id, payload_json
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
          event.episodeId,
          event.seq,
          event.timestamp,
          event.type,
          event.workId,
          null,
          null,
          JSON.stringify(event.payload),
        );
        this.db.prepare(`
          UPDATE creative_episodes
          SET status = 'failed', completed_at = ?
          WHERE episode_id = ? AND status = 'running'
        `).run(completedAt, row.episodeId);
        recovered++;
      }
      this.db.exec("COMMIT");
      return recovered;
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  close(): void {
    this.db.close();
  }

  private initializeSchema(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS creative_episodes (
        episode_id TEXT PRIMARY KEY,
        work_id TEXT,
        profile_id TEXT,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT
      );

      CREATE TABLE IF NOT EXISTS creative_episode_events (
        episode_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        type TEXT NOT NULL,
        work_id TEXT,
        capability_id TEXT,
        action_id TEXT,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (episode_id, seq),
        FOREIGN KEY (episode_id) REFERENCES creative_episodes(episode_id) ON DELETE CASCADE
      );

      CREATE INDEX IF NOT EXISTS idx_creative_episode_events_type
        ON creative_episode_events(type);
      CREATE INDEX IF NOT EXISTS idx_creative_episodes_work
        ON creative_episodes(work_id, started_at);
    `);
  }
}
