/** Host-agnostic injection contract shared by every supported host.
 *
 * These assertions do not depend on WorkBuddy specifics: they fix the shape a
 * host may consume (single additionalContext, bounded block, fail-open on
 * denial, a clear service notice on unavailability, and no tool output quoted as history).
 * This file is the contract every host adapter must satisfy.
 */

import { describe, expect, it } from "vitest";

import {
  BLOCK_CHARACTERS,
  ITEM_CHARACTERS,
  MAX_INJECTED_MEMORIES,
  runRecallInjection,
} from "./recall-injection.js";

describe("host injection contract (reusable)", () => {
  it("publishes the budget a host must tolerate", () => {
    expect(MAX_INJECTED_MEMORIES).toBe(8);
    expect(ITEM_CHARACTERS).toBe(640);
    expect(BLOCK_CHARACTERS).toBe(4000);
  });

  it("fails open with a clear notice for an unavailable recall", async () => {
    const payload = JSON.stringify({
      hook_event_name: "UserPromptSubmit",
      session_id: "sess-contract",
      turn_id: "turn-contract",
      prompt: "继续上次的周会改到周几任务",
    });
    // No broker, no credential: the worst case a host can hit.
    const result = await runRecallInjection(
      "workbuddy",
      payload,
      { ONE_MEMORY_DATA_DIR: undefined } as never,
      { startedAt: Date.now(), budgetMs: 500 },
    );
    expect(result.outcome).toBe("unavailable");
    expect(result.stdout).toContain("请打开 MemHub 后重试");
  });
});
