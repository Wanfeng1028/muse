import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { join } from "node:path";
import type { StudioChatRequestSnapshot } from "../shared/session-request.js";

/** Studio transport state, separate from the transcript's model/tool history. */
export class ChatRequestStore {
  private readonly queues = new Map<string, Promise<void>>();
  constructor(private readonly root: string) {}

  private path(sessionId: string): string {
    return join(this.root, ".inkos", "chat-requests", `${encodeURIComponent(sessionId)}.json`);
  }

  private async enqueue(sessionId: string, write: () => Promise<void>): Promise<void> {
    const previous = this.queues.get(sessionId) ?? Promise.resolve();
    const next = previous.catch(() => undefined).then(write);
    this.queues.set(sessionId, next);
    try { await next; } finally {
      if (this.queues.get(sessionId) === next) this.queues.delete(sessionId);
    }
  }

  async save(snapshot: StudioChatRequestSnapshot): Promise<void> {
    const serialized = JSON.stringify(snapshot);
    await this.enqueue(snapshot.sessionId, async () => {
      await mkdir(join(this.root, ".inkos", "chat-requests"), { recursive: true });
      const path = this.path(snapshot.sessionId), temporary = `${path}.${randomUUID()}.tmp`;
      try {
        await writeFile(temporary, serialized, { mode: 0o600 });
        await rename(temporary, path);
      } finally { await rm(temporary, { force: true }); }
    });
  }

  async load(sessionId: string): Promise<StudioChatRequestSnapshot | null> {
    await this.queues.get(sessionId);
    try {
      const snapshot = JSON.parse(await readFile(this.path(sessionId), "utf8")) as StudioChatRequestSnapshot;
      if (snapshot.sessionId !== sessionId || typeof snapshot.requestId !== "string"
        || typeof snapshot.startedAt !== "number"
        || !["running", "completed", "failed", "cancelled"].includes(snapshot.status)) {
        throw new Error("Invalid Studio chat request snapshot.");
      }
      return snapshot;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }
  }

  async delete(sessionId: string): Promise<void> {
    await this.enqueue(sessionId, () => rm(this.path(sessionId), { force: true }));
  }
}
