import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";
import { PlayDB } from "../play/play-db.js";
import {applyPlayMutation} from '../play/play-reducer.js';
import type {PlayMutationInput} from '../models/play.js';

const require = createRequire(import.meta.url);
let hasNodeSqlite = true;
try {
  require("node:sqlite");
} catch {
  hasNodeSqlite = false;
}

const sqliteIt = hasNodeSqlite ? it : it.skip;

describe("PlayDB", () => {
  sqliteIt("persists claim transitions and entity origins while rejecting an unrelated transition", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-play-db-"));

    try {
      const db = new PlayDB(root);
      const actor={
        id: "actor_songci",
        type: "actor",
        label: "宋词",
        summary: "冷静的妻子。",
        status: "active",
        createdEventId: "event-0001",
        updatedEventId: "event-0001",
      } as const;
      const mutation:PlayMutationInput={eventId:'event-0001',turn:1,actionKind:'investigate',summary:'Read a report.',
        entities:{upsert:[actor,{id:'arrival-report',type:'claim',label:'Arrival report',summary:'An unverified report.'},{id:'arrival-chain',type:'proof_chain',label:'Arrival record chain',summary:'Records supporting the report.'}]},
        edges:{upsert:[],expire:[]},stateSlots:{upsert:[]},evidence:{transitions:[{entityId:'arrival-report',to:'hinted'},{entityId:'arrival-chain',to:'seen'}]},blocked:false,blockedReason:'',notes:[],
      };
      applyPlayMutation({db,mutation,rawInput:'Read the report.'});
      applyPlayMutation({db,mutation:{...mutation,eventId:'event-0002',turn:2,entities:{upsert:[{...actor,createdEventId:'event-0002',updatedEventId:'event-0002',status:'waiting'}]},evidence:{transitions:[]}},rawInput:'Wait.'});
      expect(()=>applyPlayMutation({db,mutation:{...mutation,eventId:'invalid',turn:2,entities:{upsert:[]},evidence:{transitions:[{entityId:actor.id,to:'verified'}]}},rawInput:'Invalid transition'})).toThrow(expect.objectContaining({code:'PLAY_EVIDENCE_ENTITY_TYPE'}));
      expect(db.snapshot().events).toHaveLength(2);
      db.close();

      const reopened = new PlayDB(root);
      expect(reopened.getEvent('event-0001')?.actionKind).toBe('investigate');
      expect(reopened.getEntity("actor_songci")).toMatchObject({
        label: "宋词",
        type: "actor",
        createdEventId:'event-0001',updatedEventId:'event-0002',
      });
      expect(reopened.getStateSlotsForEntity('arrival-report')).toEqual(expect.arrayContaining([expect.objectContaining({value:expect.objectContaining({status:'hinted'})})]));
      expect(reopened.getStateSlotsForEntity('arrival-chain')).toEqual(expect.arrayContaining([expect.objectContaining({value:expect.objectContaining({status:'seen'})})]));
      reopened.close();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  sqliteIt("stores temporal edges and excludes expired edges from current queries", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-play-db-"));
    const db = new PlayDB(root);

    try {
      db.upsertEntity({ id: "evidence_stats", type: "evidence", label: "地址统计", summary: "地址证据" });
      db.upsertEntity({ id: "claim_cohabit", type: "claim", label: "婚外同居", summary: "待证主张" });
      db.upsertEdge({
        id: "edge-supports",
        fromId: "evidence_stats",
        type: "supports",
        toId: "claim_cohabit",
        validFromEventId: "event-0001",
        sourceEventId: "event-0001",
        visibility: { player: "seen" },
        strength: 0.7,
      });

      expect(db.getCurrentEdgesForEntity("evidence_stats")).toHaveLength(1);

      db.expireEdge("edge-supports", "event-0002");
      expect(db.getCurrentEdgesForEntity("evidence_stats")).toHaveLength(0);
    } finally {
      db.close();
      await rm(root, { recursive: true, force: true });
    }
  });

  sqliteIt("finds evidence supporting a claim", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-play-db-"));
    const db = new PlayDB(root);

    try {
      db.upsertEntity({ id: "evidence_stats", type: "evidence", label: "地址统计", summary: "地址证据" });
      db.upsertEntity({ id: "claim_cohabit", type: "claim", label: "婚外同居", summary: "待证主张" });
      db.upsertEntity({ id: "evidence_recording", type: "evidence", label: "录音", summary: "录音证据" });
      db.upsertEdge({
        id: "edge-supports-1",
        fromId: "evidence_stats",
        type: "supports",
        toId: "claim_cohabit",
        validFromEventId: "event-0001",
        sourceEventId: "event-0001",
        strength: 0.6,
      });
      db.upsertEdge({
        id: "edge-supports-2",
        fromId: "evidence_recording",
        type: "supports",
        toId: "claim_cohabit",
        validFromEventId: "event-0002",
        sourceEventId: "event-0002",
        strength: 0.8,
      });

      expect(db.getEvidenceForClaim("claim_cohabit").map((entity) => entity.id))
        .toEqual(["evidence_recording", "evidence_stats"]);
    } finally {
      db.close();
      await rm(root, { recursive: true, force: true });
    }
  });

  sqliteIt("persists state slots and events", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-play-db-"));
    const db = new PlayDB(root);

    try {
      db.upsertEntity({ id: "actor_husband", type: "actor", label: "徐晋安", summary: "丈夫" });
      db.upsertStateSlot({
        id: "slot_husband_suspicion",
        ownerEntityId: "actor_husband",
        kind: "pressure",
        label: "丈夫警觉",
        value: { current: 45, min: 0, max: 100 },
        updatedEventId: "event-0002",
      });
      db.recordEvent({
        id: "event-0002",
        turn: 2,
        actionKind: "say",
        rawInput: "问他删了什么",
        outcomeSummary: "丈夫警觉提高。",
        createdAt: "2026-05-28T00:00:00.000Z",
      });

      expect(db.getStateSlotsForEntity("actor_husband")[0]?.label).toBe("丈夫警觉");
      expect(db.getEvent("event-0002")?.actionKind).toBe("say");
      expect(db.snapshot()).toMatchObject({
        entities: [expect.objectContaining({ id: "actor_husband" })],
        stateSlots: [expect.objectContaining({ id: "slot_husband_suspicion" })],
        events: [expect.objectContaining({ id: "event-0002" })],
      });
    } finally {
      db.close();
      await rm(root, { recursive: true, force: true });
    }
  });
});
