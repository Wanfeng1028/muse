import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  SUPPORTED_REACTIONS,
  isSupportedReaction,
  addMessageReaction,
  removeMessageReaction,
  listMessageReactions,
  getMessageRoom,
} from "../src/reactions.js";
import { openDb, saveMessage } from "../src/db.js";
import { startServer } from "../src/server.js";

describe("reactions (pure functions)", () => {
  let dataDir: string;
  let db: Awaited<ReturnType<typeof openDb>>;
  let messageId: number;

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "reactions-fn-"));
    db = await openDb(join(dataDir, "db"));
    messageId = saveMessage(db, {
      room: "room1",
      sender: "alice",
      seq: 1,
      type: "message",
      payload: JSON.stringify({ text: "hello" }),
      ts: Date.now(),
    });
  });

  afterEach(() => {
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("isSupportedReaction returns true for all supported reactions", () => {
    for (const reaction of ["+1", "like", "smile", "ok", "done", "heart", "thumbs_up", "thumbs_down"]) {
      expect(isSupportedReaction(reaction)).toBe(true);
    }
  });

  it("isSupportedReaction returns false for unsupported values", () => {
    const invalid: unknown[] = ["", "Love", "LIKE", "heart ", 123, null, undefined];
    for (const value of invalid) {
      expect(isSupportedReaction(value as string)).toBe(false);
    }
  });

  it("add then list shows the reaction with reactor", () => {
    expect(addMessageReaction(db, messageId, "room1", "bob", "heart")).toBe(true);
    expect(listMessageReactions(db, messageId)).toEqual([
      { reaction: "heart", count: 1, reactors: ["bob"] },
    ]);
  });

  it("duplicate add returns false and keeps count at 1", () => {
    expect(addMessageReaction(db, messageId, "room1", "bob", "heart")).toBe(true);
    expect(addMessageReaction(db, messageId, "room1", "bob", "heart")).toBe(false);
    expect(listMessageReactions(db, messageId)).toEqual([
      { reaction: "heart", count: 1, reactors: ["bob"] },
    ]);
  });

  it("remove returns true once and false on repeat", () => {
    expect(addMessageReaction(db, messageId, "room1", "bob", "heart")).toBe(true);
    expect(removeMessageReaction(db, messageId, "bob", "heart")).toBe(true);
    expect(removeMessageReaction(db, messageId, "bob", "heart")).toBe(false);
  });

  it("list is ordered by SUPPORTED_REACTIONS with reactors in insertion order", () => {
    expect(addMessageReaction(db, messageId, "room1", "carol", "heart")).toBe(true);
    expect(addMessageReaction(db, messageId, "room1", "bob", "like")).toBe(true);
    expect(addMessageReaction(db, messageId, "room1", "bob", "heart")).toBe(true);
    expect(listMessageReactions(db, messageId)).toEqual([
      { reaction: "like", count: 1, reactors: ["bob"] },
      { reaction: "heart", count: 2, reactors: ["carol", "bob"] },
    ]);
    expect(SUPPORTED_REACTIONS.indexOf("like")).toBeLessThan(SUPPORTED_REACTIONS.indexOf("heart"));
  });

  it("list on unknown message id returns []", () => {
    expect(listMessageReactions(db, 999999)).toEqual([]);
  });

  it("getMessageRoom returns the room or undefined", () => {
    expect(getMessageRoom(db, messageId)).toBe("room1");
    expect(getMessageRoom(db, 999999)).toBeUndefined();
  });
});

describe("REST reactions", () => {
  let dataDir: string;
  let db: Awaited<ReturnType<typeof openDb>>;
  let server: Awaited<ReturnType<typeof startServer>>;
  let baseUrl: string;
  let messageId: number;
  const api = async (path: string, method: string, body?: unknown) => {
    const res = await fetch(baseUrl + path, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return { status: res.status, body: await res.json() };
  };
  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "reactions-rest-test-"));
    db = await openDb(join(dataDir, "dbdir"));
    messageId = saveMessage(db, { room: "room1", sender: "alice", seq: 1, type: "message", payload: JSON.stringify({ text: "hello" }), ts: Date.now() });
    server = await startServer({ port: 0, dataDir: join(dataDir, "dbdir"), roomMaxMembersWorkroom: 50, roomMaxMembersPlayroom: 200, gameBroadcastThrottleMs: 500 }, db);
    const address = server.httpServer.address();
    const port = typeof address === "object" && address !== null ? address.port : 0;
    baseUrl = `http://127.0.0.1:${port}`;
  });
  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("GET reactions on a fresh message returns 200 with empty reactions", async () => {
    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "GET");
    expect(res.status).toBe(200);
    expect(res.body.message_id).toBe(messageId);
    expect(res.body.room).toBe("room1");
    expect(res.body.reactions).toEqual([]);
  });

  it("POST add returns 200, added true, and the reaction list", async () => {
    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", { reaction: "heart", requester: "bob" });
    expect(res.status).toBe(200);
    expect(res.body.added).toBe(true);
    expect(res.body.reactions).toEqual([{ reaction: "heart", count: 1, reactors: ["bob"] }]);
  });

  it("POST duplicate returns 200, added false, count still 1", async () => {
    await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", { reaction: "heart", requester: "bob" });
    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", { reaction: "heart", requester: "bob" });
    expect(res.status).toBe(200);
    expect(res.body.added).toBe(false);
    expect(res.body.reactions[0].count).toBe(1);
  });

  it("POST second user returns added true and reactors in order", async () => {
    await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", { reaction: "heart", requester: "bob" });
    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", { reaction: "heart", requester: "carol" });
    expect(res.status).toBe(200);
    expect(res.body.added).toBe(true);
    expect(res.body.reactions[0].reactors).toEqual(["bob", "carol"]);
  });

  it("POST invalid reaction returns 400 INVALID_REACTION", async () => {
    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", { reaction: "Love", requester: "bob" });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("INVALID_REACTION");
  });

  it("POST missing requester returns 400", async () => {
    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", { reaction: "heart" });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("requester required");
  });

  it("POST unknown message returns 404 MESSAGE_NOT_FOUND", async () => {
    const res = await api("/api/rooms/room1/messages/999999/reactions", "POST", { reaction: "heart", requester: "bob" });
    expect(res.status).toBe(404);
    expect(res.body.error).toBe("MESSAGE_NOT_FOUND");
  });

  it("POST room mismatch returns 404 MESSAGE_NOT_FOUND", async () => {
    const res = await api(`/api/rooms/other/messages/${messageId}/reactions`, "POST", { reaction: "heart", requester: "bob" });
    expect(res.status).toBe(404);
    expect(res.body.error).toBe("MESSAGE_NOT_FOUND");
  });

  it("DELETE remove returns true once and false on repeat", async () => {
    await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", { reaction: "heart", requester: "bob" });
    const delRes = await api(`/api/rooms/room1/messages/${messageId}/reactions?reaction=heart&requester=bob`, "DELETE");
    expect(delRes.status).toBe(200);
    expect(delRes.body.removed).toBe(true);
    const delRes2 = await api(`/api/rooms/room1/messages/${messageId}/reactions?reaction=heart&requester=bob`, "DELETE");
    expect(delRes2.status).toBe(200);
    expect(delRes2.body.removed).toBe(false);
  });

  it("DELETE invalid reaction returns 400 INVALID_REACTION", async () => {
    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions?reaction=Love&requester=bob`, "DELETE");
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("INVALID_REACTION");
  });

  it("GET non-numeric message id returns 400 INVALID_MESSAGE_ID", async () => {
    const res = await api("/api/rooms/room1/messages/abc/reactions", "GET");
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("INVALID_MESSAGE_ID");
  });
});
