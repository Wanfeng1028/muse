import { describe, expect, it } from "vitest";
import { applyRuntimeStateDelta, type RuntimeStateSnapshot } from "../state/state-reducer.js";

describe("runtime state reducer contract", () => {
  it("keeps advancement history when a hook is deferred and advances it on resolution", () => {
    const operations={chapter:1,factOps:{upsert:[],expire:[]},hookOps:{upsert:[],mention:[],resolve:[],defer:["ledger"]},newHookCandidates:[]};
    const deferred=applyRuntimeStateDelta({snapshot:snapshot(),delta:operations});
    expect(deferred.hooks.hooks[0]).toMatchObject({status:"deferred",lastAdvancedChapter:0});
    const repeated=applyRuntimeStateDelta({snapshot:deferred,delta:{...operations,chapter:2}});
    expect(repeated.hooks).toEqual(deferred.hooks);
    const resolved=applyRuntimeStateDelta({snapshot:repeated,delta:{...operations,chapter:3,hookOps:{upsert:[],mention:[],resolve:["ledger"],defer:[]}}});
    expect(resolved.hooks.hooks[0]).toMatchObject({status:"resolved",lastAdvancedChapter:3});
  });

  it("applies facts, exact hook operations, and one chapter summary", () => {
    const next = applyRuntimeStateDelta({
      snapshot: snapshot(),
      delta: {
        chapter: 1,
        factOps: { upsert: [{ subject: "Lin", predicate: "location", object: "archive" }], expire: [] },
        hookOps: { upsert: [], mention: ["ledger"], resolve: [], defer: [] },
        newHookCandidates: [],
        chapterSummary: {
          chapter: 1,
          title: "Archive",
          characters: "Lin",
          events: "Lin enters the archive.",
          stateChanges: "location changed",
          hookActivity: "ledger mentioned",
          mood: "tense",
          chapterType: "investigation",
        },
      },
    });

    expect({
      chapter: next.manifest.lastAppliedChapter,
      fact: next.currentState.facts[0]?.object,
      hookStatus: next.hooks.hooks[0]?.status,
      summaries: next.chapterSummaries.rows.map((row) => row.chapter),
    }).toEqual({ chapter: 1, fact: "archive", hookStatus: "open", summaries: [1] });
  });

  it("rejects replay unless the caller explicitly re-applies the chapter", () => {
    const current = { ...snapshot(), manifest: { ...snapshot().manifest, lastAppliedChapter: 1 } };
    const delta = {
      chapter: 1,
      factOps: { upsert: [], expire: [] },
      hookOps: { upsert: [], mention: [], resolve: [], defer: [] },
      newHookCandidates: [],
    };
    expect(() => applyRuntimeStateDelta({ snapshot: current, delta })).toThrow(/goes backwards/);
    expect(applyRuntimeStateDelta({ snapshot: current, delta, allowReapply: true }).manifest.lastAppliedChapter).toBe(1);
  });

  it("rejects hook operations that do not name an existing canonical id", () => {
    expect(() => applyRuntimeStateDelta({
      snapshot: snapshot(),
      delta: {
        chapter: 1,
        factOps: { upsert: [], expire: [] },
        hookOps: { upsert: [], mention: [], resolve: ["unknown"], defer: [] },
        newHookCandidates: [],
      },
    })).toThrow(/unknown hook/);
  });
});

function snapshot(): RuntimeStateSnapshot {
  return {
    manifest: { schemaVersion: 2, language: "en", lastAppliedChapter: 0, projectionVersion: 1 },
    currentState: { chapter: 0, facts: [] },
    hooks: { hooks: [{
      hookId: "ledger",
      startChapter: 0,
      type: "mystery",
      status: "open",
      lastAdvancedChapter: 0,
      expectedPayoff: "Reveal the ledger origin.",
      notes: "Unresolved.",
    }] },
    chapterSummaries: { rows: [] },
  };
}
