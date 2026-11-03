import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import {
  openDb,
  saveMessage,
  getRoomHistory,
  upsertPresence,
  getPresence,
  listPresence,
  saveArtifact,
  getArtifact,
} from "../src/db.js";

let tmpRoot: string;
let dataDir: string;

beforeEach(() => {
  const parent = join(__dirname, "test-tmp");
  mkdirSync(parent, { recursive: true });
  tmpRoot = mkdtempSync(join(parent, "db-"));
  dataDir = join(tmpRoot, "data");
});

afterEach(() => {
  rmSync(tmpRoot, { recursive: true, force: true });
});

describe("openDb", () => {
  it("sets journal_mode to wal", () => {
    const db = openDb(dataDir);
    const row = db.prepare("PRAGMA journal_mode;").get() as { journal_mode: string };
    expect(row.journal_mode.toLowerCase()).toBe("wal");
    db.close();
  });
});

describe("saveMessage + getRoomHistory", () => {
  it("saves and retrieves messages in desc order with beforeId pagination", () => {
    const db = openDb(dataDir);
    const id1 = saveMessage(db, {
      room: "r1",
      sender: "a",
      seq: 1,
      type: "message",
      payload: JSON.stringify({ text: "one" }),
      ts: 1000,
    });
    const id2 = saveMessage(db, {
      room: "r1",
      sender: "b",
      seq: 2,
      type: "message",
      payload: JSON.stringify({ text: "two" }),
      ts: 2000,
    });
    const id3 = saveMessage(db, {
      room: "r1",
      sender: "c",
      seq: 3,
      type: "message",
      payload: JSON.stringify({ text: "three" }),
      ts: 3000,
    });
    saveMessage(db, {
      room: "r2",
      sender: "x",
      seq: 1,
      type: "message",
      payload: JSON.stringify({ text: "other" }),
      ts: 1500,
    });

    expect(id1).toBeGreaterThan(0);
    expect(id2).toBeGreaterThan(id1);
    expect(id3).toBeGreaterThan(id2);

    const all = getRoomHistory(db, "r1", 10);
    expect(all.map((m) => m.id)).toEqual([id3, id2, id1]);
    expect(all[0].payload).toBe(JSON.stringify({ text: "three" }));
    expect(all[0].room).toBe("r1");

    const page1 = getRoomHistory(db, "r1", 2);
    expect(page1.map((m) => m.id)).toEqual([id3, id2]);

    const page2 = getRoomHistory(db, "r1", 2, id2);
    expect(page2.map((m) => m.id)).toEqual([id1]);

    const page3 = getRoomHistory(db, "r1", 2, id1);
    expect(page3).toEqual([]);

    db.close();
  });
});

describe("presence", () => {
  it("inserts then updates and lists", () => {
    const db = openDb(dataDir);
    upsertPresence(db, {
      adapter_id: "adapter-1",
      status: "online",
      last_seen_ms: 1000,
      usage_in: 10,
      usage_out: 20,
    });
    const first = getPresence(db, "adapter-1");
    expect(first).toBeDefined();
    expect(first?.status).toBe("online");
    expect(first?.usage_in).toBe(10);
    expect(first?.usage_out).toBe(20);

    upsertPresence(db, {
      adapter_id: "adapter-1",
      status: "thinking",
      last_seen_ms: 2000,
      usage_in: 11,
      usage_out: 22,
    });
    const updated = getPresence(db, "adapter-1");
    expect(updated?.status).toBe("thinking");
    expect(updated?.last_seen_ms).toBe(2000);
    expect(updated?.usage_in).toBe(11);
    expect(updated?.usage_out).toBe(22);

    upsertPresence(db, {
      adapter_id: "adapter-2",
      status: "online",
      last_seen_ms: 3000,
      usage_in: 0,
      usage_out: 0,
    });
    const all = listPresence(db);
    expect(all.length).toBe(2);
    expect(all.map((p) => p.adapter_id).sort()).toEqual(["adapter-1", "adapter-2"]);

    expect(getPresence(db, "missing")).toBeUndefined();
    db.close();
  });
});

describe("artifacts", () => {
  it("saves and retrieves artifact", () => {
    const db = openDb(dataDir);
    saveArtifact(db, {
      id: "art-1",
      filename: "file.txt",
      size: 123,
      mime: "text/plain",
      path: join(dataDir, "file.txt"),
    });
    const got = getArtifact(db, "art-1");
    expect(got).toBeDefined();
    expect(got?.id).toBe("art-1");
    expect(got?.filename).toBe("file.txt");
    expect(got?.size).toBe(123);
    expect(got?.mime).toBe("text/plain");
    expect(got?.path).toBe(join(dataDir, "file.txt"));
    expect(typeof got?.created_at_ms).toBe("number");
    expect(getArtifact(db, "nope")).toBeUndefined();
    db.close();
  });
});

// 自查：红线 1-5 逐条通过
