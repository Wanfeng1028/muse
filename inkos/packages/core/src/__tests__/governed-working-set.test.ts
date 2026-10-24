import { describe, expect, it } from "vitest";
import { buildGovernedHookWorkingSet } from "../utils/governed-working-set.js";

describe("governed-working-set", () => {
  it("projects only the hook ids selected by the semantic context package", () => {
    const hooks = [
      hook("opening-call", 1, "mystery", "匿名来电开篇出现"),
      hook("nearby-ledger", 4, "evidence", "近期开启的账本线"),
      hook("future-pr-machine", 22, "conspiracy", "远期舆情操盘线"),
      hook("future-template", 45, "system", "远期系统性话术线"),
    ];

    const filtered = buildGovernedHookWorkingSet({
      hooks,
      contextPackage: {
        chapter: 1,
        selectedContext: [
          {
            source: "story/pending_hooks.md#opening-call",
            reason: "Current chapter opening hook.",
            excerpt: "mystery | open | 8 | 匿名来电开篇出现",
            protection: "protected",
          },
        ],
      },
      language: "zh",
    });

    expect(filtered).toContain("opening-call");
    expect(filtered).not.toContain("nearby-ledger");
    expect(filtered).not.toContain("future-pr-machine");
    expect(filtered).not.toContain("future-template");
  });


  it("keeps the complete source when no semantic hook selection exists", () => {
    const hooks = [
      { ...hook("river-oath", 8, "relationship", "Long debt should stay visible through the middle game"), status: "progressing" as const, lastAdvancedChapter: 16 },
      hook("future-pr-machine", 45, "system", "Future hook should stay hidden"),
    ];

    const filtered = buildGovernedHookWorkingSet({
      hooks,
      contextPackage: {
        chapter: 20,
        selectedContext: [],
      },
      language: "en",
    });

    expect(filtered).toContain("river-oath");
    expect(filtered).toContain("future-pr-machine");
  });

});

function hook(hookId: string, startChapter: number, type: string, notes: string) {
  return {
    hookId,
    startChapter,
    type,
    status: "open" as const,
    lastAdvancedChapter: startChapter,
    expectedPayoff: notes,
    notes,
  };
}
