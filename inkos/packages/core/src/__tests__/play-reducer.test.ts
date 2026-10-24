import { describe, expect, it } from "vitest";
import type {
  PlayEdge,
  PlayEdgeInput,
  PlayEntity,
  PlayEntityInput,
  PlayEventInput,
  PlayStateSlot,
  PlayStateSlotInput,
} from "../models/play.js";
import { applyPlayMutation } from "../play/play-reducer.js";

class FakePlayDB {
  readonly entities = new Map<string, PlayEntity>();
  readonly edges = new Map<string, PlayEdge>();
  readonly stateSlots = new Map<string, PlayStateSlot>();
  readonly events: PlayEventInput[] = [];
  transactionCalls = 0;

  transaction<T>(fn: () => T): T {
    this.transactionCalls += 1;
    return fn();
  }

  upsertEntity(entity: PlayEntityInput): void {
    this.entities.set(entity.id, { status: "", ...entity });
  }

  getEntity(id: string): PlayEntity | null {
    return this.entities.get(id) ?? null;
  }

  upsertEdge(edge: PlayEdgeInput): void {
    this.edges.set(edge.id, {
      value: {},
      validUntilEventId: null,
      visibility: {},
      ...edge,
    });
  }

  expireEdge(edgeId: string, validUntilEventId: string): void {
    const edge = this.edges.get(edgeId);
    if (edge) this.edges.set(edgeId, { ...edge, validUntilEventId });
  }

  upsertStateSlot(slot: PlayStateSlotInput): void {
    this.stateSlots.set(slot.id, { ownerEntityId: null, ...slot, value: slot.value });
  }

  getStateSlotsForEntity(entityId: string): PlayStateSlot[] {
    return [...this.stateSlots.values()].filter((slot) => slot.ownerEntityId === entityId);
  }

  recordEvent(event: PlayEventInput): void {
    this.events.push(event);
  }
}

describe("play reducer invariants", () => {
  it("commits one valid typed world transition as a single transaction", () => {
    const db = new FakePlayDB();

    const result = applyPlayMutation({
      db,
      mutation: {
        eventId: "evt-1",
        turn: 1,
        actionKind: "look",
        summary: "玩家看见了账本。",
        entities: { upsert: [
          { id: "actor_player", type: "actor", label: "宋词", summary: "玩家", createdEventId: "evt-1", updatedEventId: "evt-1" },
          { id: "ledger", type: "evidence", label: "常用地址统计", summary: "地址证据", createdEventId: "evt-1", updatedEventId: "evt-1" },
          { id: "claim-affair", type: "claim", label: "徐晋安另有家庭", summary: "待证主张", createdEventId: "evt-1", updatedEventId: "evt-1" },
        ] },
        edges: { upsert: [{
          id: "edge-ledger-claim",
          fromId: "ledger",
          type: "supports",
          toId: "claim-affair",
          validFromEventId: "evt-1",
          sourceEventId: "evt-1",
          strength: 0.7,
        }], expire: [] },
        stateSlots: { upsert: [{
          id: "pressure:actor_player:danger",
          ownerEntityId: "actor_player",
          kind: "pressure",
          label: "被发现风险",
          value: { current: 120 },
          updatedEventId: "evt-1",
        }] },
        evidence: { transitions: [{ entityId: "ledger", to: "seen", reason: "屏幕弹出统计。" }] },
        blocked: false,
        blockedReason: "",
        notes: [],
      },
      rawInput: "看一下导航记录",
      createdAt: "2026-05-28T00:00:00.000Z",
    });

    expect(result.event.id).toBe("evt-1");
    expect(db.transactionCalls).toBe(1);
    expect(db.events).toHaveLength(1);
    expect(db.edges.get("edge-ledger-claim")?.toId).toBe("claim-affair");
    expect(db.stateSlots.get("pressure:actor_player:danger")?.value).toEqual({ current: 120 });
    expect(db.stateSlots.get("evidence:ledger:status")?.value).toMatchObject({ status: "seen" });
  });

  it("rejects an invalid graph transition before committing any partial state", () => {
    const db = new FakePlayDB();

    expect(() => applyPlayMutation({
      db,
      mutation: {
        eventId: "evt-2",
        turn: 2,
        actionKind: "do",
        summary: "调查未完成。",
        entities: { upsert: [{ id: "actor_player", type: "actor", label: "林远", summary: "玩家" }] },
        edges: { upsert: [{
          id: "dangling-edge",
          fromId: "actor_player",
          type: "knows",
          toId: "missing-actor",
          validFromEventId: "evt-2",
          sourceEventId: "evt-2",
        }], expire: [] },
        stateSlots: { upsert: [] },
        evidence: { transitions: [] },
        blocked: false,
        blockedReason: "",
        notes: [],
      },
      rawInput: "调查",
    })).toThrow(/missing endpoint/);

    expect({ transactions: db.transactionCalls, events: db.events.length, entities: db.entities.size }).toEqual({
      transactions: 0,
      events: 0,
      entities: 0,
    });
  });

  it("rejects evidence regression and preserves the accepted state", () => {
    const db = new FakePlayDB();
    db.upsertEntity({ id: "receipt", type: "evidence", label: "住院收据", summary: "收据证据" });
    db.upsertStateSlot({
      id: "evidence:receipt:status",
      ownerEntityId: "receipt",
      kind: "evidence",
      label: "证据状态",
      value: { status: "verified" },
      updatedEventId: "evt-old",
    });

    expect(() => applyPlayMutation({
      db,
      mutation: {
        eventId: "evt-3",
        turn: 3,
        actionKind: "look",
        summary: "重新检查收据。",
        entities: { upsert: [] },
        edges: { upsert: [], expire: [] },
        stateSlots: { upsert: [] },
        evidence: { transitions: [{ entityId: "receipt", from: "verified", to: "seen" }] },
        blocked: false,
        blockedReason: "",
        notes: [],
      },
      rawInput: "重新看收据",
    })).toThrow(/goes backwards/);

    expect(db.stateSlots.get("evidence:receipt:status")?.value).toEqual({ status: "verified" });
    expect(db.events).toHaveLength(0);
  });
});
