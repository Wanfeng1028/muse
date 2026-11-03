import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { makeEnvelope, APPROVAL_TTL_MS } from "@botstalk/protocol";
import type { ApprovalDecisionPayload, ApprovalRequestPayload, Envelope, MessagePayload } from "@botstalk/protocol";
import { routeMessage, routeApprovalDecision, setTaskApprovalMode, sweepApprovals, getPendingApprovals } from "../src/router.js";
import { loadConfig } from "../src/config.js";
import { openDb, getTask } from "../src/db.js";
import type { DatabaseSync } from "node:sqlite";
import type { Hub } from "../src/hub.js";

type Intents = ("chat" | "task")[];

interface ConnSpec {
  id: string;
  intents: Intents;
}

class FakeHub {
  conns: ConnSpec[];
  sent: Array<{ to: string; env: Envelope }> = [];
  broadcasted: Array<{ room: string; env: Envelope }> = [];
  taskEvents: Array<{ room: string; payload: Record<string, unknown> }> = [];
  private seq = 0;

  constructor(conns: ConnSpec[]) {
    this.conns = conns;
  }

  getOnlineAdapters(): string[] {
    return this.conns.map((c) => c.id);
  }

  getConn(id: string): { capabilities: { intents: Intents } } | undefined {
    const found = this.conns.find((c) => c.id === id);
    if (!found) return undefined;
    return { capabilities: { intents: found.intents } };
  }

  sendTo(adapterId: string, env: Envelope): boolean {
    this.sent.push({ to: adapterId, env });
    return true;
  }

  broadcast(room: string, env: Envelope, _exclude?: string): void {
    this.broadcasted.push({ room, env });
  }

  broadcastTaskEvent(room: string, payload: Record<string, unknown>): void {
    this.taskEvents.push({ room, payload });
  }

  nextSeq(): number {
    this.seq += 1;
    return this.seq;
  }
}

const TEST_TMP_ROOT = join(import.meta.dirname ?? __dirname, "test-tmp");
mkdirSync(TEST_TMP_ROOT, { recursive: true });
let dir: string;
let db: DatabaseSync;

beforeEach(() => {
  dir = mkdtempSync(join(TEST_TMP_ROOT, "approvals-"));
  db = openDb(dir);
  setTaskApprovalMode("all");
});

afterEach(() => {
  setTaskApprovalMode("off");
  db.close();
  rmSync(dir, { recursive: true, force: true });
});

function asHub(h: FakeHub): Hub {
  return h as unknown as Hub;
}

function mkHub(): FakeHub {
  return new FakeHub([
    { id: "user", intents: ["chat"] },
    { id: "echo", intents: ["chat", "task"] },
  ]);
}

function mkTaskEnv(): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", "user", "room1", 1, 0, {
    msg_id: "m1",
    text: "@echo 帮我写个日报",
    mentions: ["echo"],
    intent: "task",
    task_id: "t1",
  });
}

function gateOne(hub: FakeHub): string {
  routeMessage(asHub(hub), mkTaskEnv(), db);
  const req = hub.broadcasted.find((b) => b.env.type === "approval_request");
  expect(req).toBeDefined();
  return (req!.env.payload as ApprovalRequestPayload).approval_id;
}

function mkDecision(sender: string, approvalId: string, decision: "approve" | "reject"): Envelope<ApprovalDecisionPayload> {
  return makeEnvelope<ApprovalDecisionPayload>("approval_decision", sender, "room1", 2, 0, {
    approval_id: approvalId,
    decision,
  });
}

describe("approval gate", () => {
  it("holds the task instead of dispatching, and records pending_approval", () => {
    const hub = mkHub();
    const approvalId = gateOne(hub);
    expect(approvalId.length).toBeGreaterThan(0);
    expect(hub.sent.find((s) => s.to === "echo")).toBeUndefined();
    expect(hub.taskEvents.find((e) => e.payload.status === "pending_approval" && e.payload.task_id === "t1")).toBeDefined();
    expect(getTask(db, "t1")!.status).toBe("pending_approval");
    expect(getPendingApprovals().get(approvalId)).toBeDefined();
  });

  it("approve dispatches the original task frame to the assignee", () => {
    const hub = mkHub();
    const approvalId = gateOne(hub);
    routeApprovalDecision(asHub(hub), mkDecision("user", approvalId, "approve"), db);
    const sent = hub.sent.find((s) => s.to === "echo");
    expect(sent).toBeDefined();
    expect((sent!.env.payload as MessagePayload).task_id).toBe("t1");
    expect(hub.taskEvents.find((e) => e.payload.status === "dispatched")).toBeDefined();
    expect(getTask(db, "t1")!.status).toBe("dispatched");
    expect(getPendingApprovals().get(approvalId)).toBeUndefined();
  });

  it("reject fails the task and notifies the requester", () => {
    const hub = mkHub();
    const approvalId = gateOne(hub);
    routeApprovalDecision(asHub(hub), mkDecision("user", approvalId, "reject"), db);
    expect(hub.sent.find((s) => s.to === "echo")).toBeUndefined();
    expect(getTask(db, "t1")!.status).toBe("failed");
    const note = hub.sent.find((s) => s.to === "user" && (s.env.payload as MessagePayload).task_status === "failed");
    expect(note).toBeDefined();
    expect((note!.env.payload as MessagePayload).text).toContain("TASK_APPROVAL_REJECTED");
  });

  it("the assignee cannot approve its own task", () => {
    const hub = mkHub();
    const approvalId = gateOne(hub);
    routeApprovalDecision(asHub(hub), mkDecision("echo", approvalId, "approve"), db);
    expect(hub.sent.find((s) => s.to === "echo")).toBeUndefined();
    expect(getPendingApprovals().get(approvalId)).toBeDefined();
    expect(getTask(db, "t1")!.status).toBe("pending_approval");
  });

  it("unknown approval_id is a no-op", () => {
    const hub = mkHub();
    routeApprovalDecision(asHub(hub), mkDecision("user", "nope", "approve"), db);
    expect(hub.sent.length).toBe(0);
    expect(hub.taskEvents.length).toBe(0);
  });

  it("expired approvals are cancelled by the sweep", () => {
    const hub = mkHub();
    const approvalId = gateOne(hub);
    sweepApprovals(asHub(hub), db, Date.now() + APPROVAL_TTL_MS + 1000);
    expect(getTask(db, "t1")!.status).toBe("cancelled");
    expect(hub.taskEvents.find((e) => e.payload.status === "cancelled")).toBeDefined();
    expect(getPendingApprovals().get(approvalId)).toBeUndefined();
  });

  it("mode off keeps direct dispatch (no gate)", () => {
    setTaskApprovalMode("off");
    const hub = mkHub();
    routeMessage(asHub(hub), mkTaskEnv(), db);
    expect(hub.sent.find((s) => s.to === "echo")).toBeDefined();
    expect(getTask(db, "t1")!.status).toBe("dispatched");
  });
});

describe("config TASK_APPROVAL_MODE", () => {
  it("parses off/all and rejects invalid values", () => {
    expect(loadConfig({} as NodeJS.ProcessEnv).taskApprovalMode).toBe("off");
    expect(loadConfig({ TASK_APPROVAL_MODE: "all" } as NodeJS.ProcessEnv).taskApprovalMode).toBe("all");
    expect(() => loadConfig({ TASK_APPROVAL_MODE: "sometimes" } as NodeJS.ProcessEnv)).toThrow(/TASK_APPROVAL_MODE/);
  });
});
