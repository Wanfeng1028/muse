import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import { routeMessage } from "../src/router.js";
import { openDb, getTask } from "../src/db.js";
import type { DatabaseSync } from "node:sqlite";
import type { Hub } from "../src/hub.js";
type Intents = ("chat" | "task")[];
interface ConnSpec { id: string; intents: Intents; skills?: string[]; tags?: string[]; }
class FakeHub {
  conns: ConnSpec[];
  sent: Array<{ to: string; env: Envelope<MessagePayload> }> = [];
  broadcasted: Array<{ room: string; env: Envelope<MessagePayload> }> = [];
  taskEvents: Array<{ room: string; payload: Record<string, unknown> }> = [];
  private seq = 0;
  constructor(conns: ConnSpec[]) { this.conns = conns; }
  getOnlineAdapters(): string[] { return this.conns.map((c) => c.id); }
  getConn(id: string): { capabilities: { intents: Intents }; capabilitySkills: string[]; capabilityTags: string[] } | undefined {
    const found = this.conns.find((c) => c.id === id);
    if (!found) return undefined;
    return { capabilities: { intents: found.intents }, capabilitySkills: found.skills ?? [], capabilityTags: found.tags ?? [] };
  }
  sendTo(adapterId: string, env: Envelope<MessagePayload>): boolean { this.sent.push({ to: adapterId, env }); return true; }
  broadcast(room: string, env: Envelope<MessagePayload>, _exclude?: string): void { this.broadcasted.push({ room, env }); }
  broadcastTaskEvent(room: string, payload: Record<string, unknown>): void { this.taskEvents.push({ room, payload }); }
  nextSeq(): number { this.seq += 1; return this.seq; }
}
const TEST_TMP_ROOT = join(import.meta.dirname ?? __dirname, "test-tmp");
mkdirSync(TEST_TMP_ROOT, { recursive: true });
let dir: string;
let db: DatabaseSync;
beforeEach(() => { dir = mkdtempSync(join(TEST_TMP_ROOT, "router-capability-")); db = openDb(dir); });
afterEach(() => { db.close(); rmSync(dir, { recursive: true, force: true }); });
function asHub(h: FakeHub): Hub { return h as unknown as Hub; }
function mkUserEnv(payload: Partial<MessagePayload> & Record<string, unknown>): Envelope<MessagePayload> {
  return makeEnvelope("message", "user", "room1", 1, 0, payload as MessagePayload);
}

describe("router capability matching", () => {
  it("prefers adapter with required skill even when id is lexically larger", () => {
    const hub = new FakeHub([
      { id: "alpha", intents: ["chat", "task"], skills: [] },
      { id: "zebra", intents: ["chat", "task"], skills: ["code-review"] },
    ]);
    const env = mkUserEnv({
      msg_id: "m-cap-1",
      text: "review this",
      mentions: [],
      intent: "task",
      task_id: "t-cap-1",
      required_capabilities: { skills: ["code-review"] },
    });

    routeMessage(asHub(hub), env, db);

    expect(
      hub.taskEvents.some((e) => e.payload.status === "dispatched" && e.payload.assignee === "zebra"),
    ).toBe(true);
    expect(getTask(db, "t-cap-1")?.assignee).toBe("zebra");
  });

  it("breaks score ties by lexically smallest adapter id", () => {
    const hub = new FakeHub([
      { id: "banana", intents: ["chat", "task"], skills: ["code-review"] },
      { id: "apple", intents: ["chat", "task"], skills: ["code-review"] },
    ]);
    const env = mkUserEnv({
      msg_id: "m-cap-2",
      text: "review this",
      mentions: [],
      intent: "task",
      task_id: "t-cap-2",
      required_capabilities: { skills: ["code-review"] },
    });

    routeMessage(asHub(hub), env, db);

    expect(
      hub.taskEvents.some((e) => e.payload.status === "dispatched" && e.payload.assignee === "apple"),
    ).toBe(true);
    expect(getTask(db, "t-cap-2")?.assignee).toBe("apple");
  });

  it("marks task unsupported when no adapter has any required dimension", () => {
    const hub = new FakeHub([
      { id: "a1", intents: ["chat", "task"], skills: ["other"] },
      { id: "a2", intents: ["chat", "task"], skills: [] },
    ]);
    const env = mkUserEnv({
      msg_id: "m-cap-3",
      text: "review this",
      mentions: [],
      intent: "task",
      task_id: "t-cap-3",
      required_capabilities: { skills: ["code-review"] },
    });

    routeMessage(asHub(hub), env, db);

    expect(hub.taskEvents.some((e) => e.payload.status === "unsupported")).toBe(true);
    expect(hub.sent).toEqual([]);
  });

  it("ignores capability scoring when mention is present", () => {
    const hub = new FakeHub([
      { id: "low", intents: ["chat", "task"], skills: [] },
      { id: "high", intents: ["chat", "task"], skills: ["code-review"] },
    ]);
    const env = mkUserEnv({
      msg_id: "m-cap-4",
      text: "review this",
      mentions: ["low"],
      intent: "task",
      task_id: "t-cap-4",
      required_capabilities: { skills: ["code-review"] },
    });

    routeMessage(asHub(hub), env, db);

    expect(
      hub.taskEvents.some((e) => e.payload.status === "dispatched" && e.payload.assignee === "low"),
    ).toBe(true);
    expect(getTask(db, "t-cap-4")?.assignee).toBe("low");
  });

  it("keeps legacy behavior when required_capabilities is absent", () => {
    const hub = new FakeHub([
      { id: "zebra", intents: ["chat", "task"] },
      { id: "alpha", intents: ["chat", "task"] },
    ]);
    const env = mkUserEnv({
      msg_id: "m-cap-5",
      text: "do this",
      mentions: [],
      intent: "task",
      task_id: "t-cap-5",
    });

    routeMessage(asHub(hub), env, db);

    expect(
      hub.taskEvents.some((e) => e.payload.status === "dispatched" && e.payload.assignee === "alpha"),
    ).toBe(true);
    expect(getTask(db, "t-cap-5")?.assignee).toBe("alpha");
  });
});
