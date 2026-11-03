import { describe, expect, it } from "vitest";
import {
  PlayActionIntentSchema,
  PlayMutationSchema,
} from "../models/play.js";

describe("Play model contracts", () => {
  it("accepts one explicit action and one fully identified world mutation", () => {
    const action = PlayActionIntentSchema.parse({
      actionKind: "look",
      intent: "检查门锁",
    });
    const mutation = PlayMutationSchema.parse({
      eventId: "evt-1",
      turn: 1,
      actionKind: action.actionKind,
      summary: "发现锁孔有新鲜铜屑。",
      timeAdvance: { elapsed: "约十秒", anchor: "午夜后", synchronized: ["走廊脚步靠近"] },
      entities: {
        upsert: [{
          id: "clue-brass-filings",
          type: "clue",
          label: "铜屑",
          summary: "门锁刚被工具触碰。",
          status: "seen",
          updatedEventId: "evt-1",
        }],
      },
      edges: { upsert: [], expire: [] },
      stateSlots: { upsert: [] },
      evidence: {
        transitions: [{ entityId: "clue-brass-filings", to: "seen", reason: "玩家检查门锁" }],
      },
      blocked: false,
      blockedReason: "",
      notes: [],
    });
    expect({
      action: action.actionKind,
      entity: mutation.entities.upsert[0]?.id,
      elapsed: mutation.timeAdvance?.elapsed,
    }).toEqual({ action: "look", entity: "clue-brass-filings", elapsed: "约十秒" });
  });

  it("accepts descriptive action labels while rejecting missing ids, coercions and extra fields", () => {
    expect(PlayActionIntentSchema.parse({ actionKind: "investigate", intent: "检查" }).actionKind).toBe("investigate");
    expect(() => PlayActionIntentSchema.parse({ actionKind: " ", intent: "检查" })).toThrow();
    expect(() => PlayMutationSchema.parse({
      eventId: "evt-2",
      turn: "2",
      actionKind: "look",
      entities: [{ type: "clue", label: "纸片" }],
    })).toThrow();
    expect(() => PlayMutationSchema.parse({
      eventId: "evt-2",
      turn: 2,
      actionKind: "look",
      confidence: 0.9,
    })).toThrow();
  });

  it("keeps genre-neutral state slots and evidence lifecycle typed", () => {
    const mutation = PlayMutationSchema.parse({
      eventId: "evt-3",
      turn: 3,
      actionKind: "say",
      summary: "林鹿确认笔迹。",
      entities: { upsert: [] },
      edges: { upsert: [], expire: [] },
      stateSlots: {
        upsert: [{
          id: "relationship-lin",
          ownerEntityId: "actor-player",
          kind: "relation",
          label: "林鹿对玩家的信任变化",
          value: "愿意透露半句真话",
          updatedEventId: "evt-3",
        }],
      },
      evidence: {
        transitions: [{ entityId: "letter", from: "seen", to: "verified", reason: "林鹿确认笔迹" }],
      },
      blocked: false,
      blockedReason: "",
      notes: [],
    });
    expect({
      slotKind: mutation.stateSlots.upsert[0]?.kind,
      evidence: mutation.evidence.transitions[0]?.to,
    }).toEqual({ slotKind: "relation", evidence: "verified" });
  });
});
