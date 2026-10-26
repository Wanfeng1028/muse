import type { Db } from "./db.js";

// Closed set of reaction strings the gateway supports, in canonical order.
export const SUPPORTED_REACTIONS: readonly string[] = [
  "+1",
  "like",
  "smile",
  "ok",
  "done",
  "heart",
  "thumbs_up",
  "thumbs_down",
];

// True only when v is a string exactly equal to one of SUPPORTED_REACTIONS.
export function isSupportedReaction(v: unknown): v is string {
  return typeof v === "string" && SUPPORTED_REACTIONS.includes(v);
}

// Creates the message_reactions table and its message index if missing.
export function ensureMessageReactionsTable(db: Db): void {
  db.prepare(
    `CREATE TABLE IF NOT EXISTS message_reactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      message_id INTEGER NOT NULL,
      room TEXT NOT NULL,
      reactor TEXT NOT NULL,
      reaction TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL,
      UNIQUE(message_id, reactor, reaction)
    )`
  ).run();
  db.prepare(
    "CREATE INDEX IF NOT EXISTS idx_message_reactions_message ON message_reactions(message_id)"
  ).run();
}

// Adds a reaction row unless the identical reaction already exists; true when inserted.
export function addMessageReaction(
  db: Db,
  messageId: number,
  room: string,
  reactor: string,
  reaction: string
): boolean {
  ensureMessageReactionsTable(db);
  const result = db
    .prepare(
      "INSERT OR IGNORE INTO message_reactions (message_id, room, reactor, reaction, created_at_ms) VALUES (?, ?, ?, ?, ?)"
    )
    .run(messageId, room, reactor, reaction, Date.now());
  return result.changes > 0;
}

// Deletes the matching reaction row; true when a row was deleted, false otherwise.
export function removeMessageReaction(
  db: Db,
  messageId: number,
  reactor: string,
  reaction: string
): boolean {
  ensureMessageReactionsTable(db);
  const result = db
    .prepare(
      "DELETE FROM message_reactions WHERE message_id = ? AND reactor = ? AND reaction = ?"
    )
    .run(messageId, reactor, reaction);
  return result.changes > 0;
}

// Summarizes a message's reactions grouped by type, in SUPPORTED_REACTIONS order.
export function listMessageReactions(
  db: Db,
  messageId: number
): Array<{ reaction: string; count: number; reactors: string[] }> {
  ensureMessageReactionsTable(db);
  const rows = db
    .prepare(
      "SELECT reactor, reaction FROM message_reactions WHERE message_id = ? ORDER BY created_at_ms ASC, id ASC"
    )
    .all(messageId) as Array<{ reactor: string; reaction: string }>;
  const reactorsByReaction = new Map<string, string[]>();
  for (const row of rows) {
    const reactors = reactorsByReaction.get(row.reaction);
    if (reactors) {
      reactors.push(row.reactor);
    } else {
      reactorsByReaction.set(row.reaction, [row.reactor]);
    }
  }
  const summary: Array<{ reaction: string; count: number; reactors: string[] }> = [];
  for (const reaction of SUPPORTED_REACTIONS) {
    const reactors = reactorsByReaction.get(reaction);
    if (reactors && reactors.length > 0) {
      summary.push({ reaction, count: reactors.length, reactors });
    }
  }
  return summary;
}

// Returns the room of a message, or undefined when no such message exists.
export function getMessageRoom(db: Db, messageId: number): string | undefined {
  const row = db
    .prepare("SELECT room FROM messages WHERE id = ?")
    .get(messageId) as { room: string } | undefined;
  return row?.room;
}
