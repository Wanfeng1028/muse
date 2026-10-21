import { describe, expect, it, vi } from "vitest";
import { createClaudeEventAdapter } from "./event-adapter.js";
import { runtimeConfig } from "./runtime-config.js";
import { memorySessionStore } from "./session-state.js";

const config = {
  schemaVersion: 1 as const,
  mode: "sync-only" as const,
  installationId: "00000000-0000-4000-8000-000000000001",
  discoveryPath: "/fixture/discovery.json",
  credentialFile: "/fixture/private/credential",
  stateDirectory: "/fixture/state",
};

describe("D37 sync-only hook", () => {
  it("validates and freezes an explicit mode and rejects missing or unknown modes", () => {
    expect(runtimeConfig(config)).toEqual(config);
    expect(Object.isFrozen(runtimeConfig(config))).toBe(true);
    const { mode: _mode, ...missing } = config;
    expect(() => runtimeConfig(missing)).toThrow("invalid_runtime_config");
    expect(() => runtimeConfig({ ...config, mode: "fallback" })).toThrow(
      "invalid_runtime_config",
    );
    expect(runtimeConfig({ ...config, mode: "recall-and-sync" }).mode).toBe(
      "recall-and-sync",
    );
  });

  it.each(["normal private prompt", "q".repeat(20_000)])(
    "records only bounded metadata for prompts and leaves recall to MCP",
    async (prompt) => {
      const recall = vi.fn();
      const notice = vi.fn();
      const notifySourceChanged = vi.fn(async () => ({
        accepted: true as const,
      }));
      const store = memorySessionStore();
      const adapter = createClaudeEventAdapter(
        config,
        { recall, notifySourceChanged },
        store,
        notice,
      );
      const payload = {
        hook_event_name: "UserPromptSubmit",
        session_id: "s1",
        event_id: "e1",
        turn_id: "t1",
        prompt,
      };
      const result = await adapter.handle(payload);
      expect(result).toEqual({
        state: "local",
        output: { continue: true, suppressOutput: true },
      });
      expect(recall).not.toHaveBeenCalled();
      expect(notice).not.toHaveBeenCalled();
      expect((await adapter.handle(payload)).state).toBe("ignored");
      const state = await store.read("s1");
      expect(state?.pendingEventId).toMatch(/^[0-9a-f]{64}$/);
      expect(JSON.stringify(state)).not.toContain(prompt);
      expect(JSON.stringify(state).length).toBeLessThan(600);
      expect(
        (
          await adapter.handle({
            hook_event_name: "Stop",
            session_id: "s1",
            turn_id: "old",
          })
        ).state,
      ).toBe("ignored");
      expect(
        (
          await adapter.handle({
            hook_event_name: "Stop",
            session_id: "s1",
            turn_id: "t1",
            transcript_path: "/never/read",
            last_assistant_message: "private answer",
          })
        ).state,
      ).toBe("notified");
      expect(notifySourceChanged).toHaveBeenCalledExactlyOnceWith({
        version: 1,
        event_id: state?.pendingEventId,
        session_id: "s1",
        event_kind: "source-changed",
      });
      expect(
        (await adapter.handle({ hook_event_name: "Stop", session_id: "s1" }))
          .state,
      ).toBe("ignored");
    },
  );

  it("keeps Stop notification available when recall mode rejects an oversized query", async () => {
    const recall = vi.fn();
    const notifySourceChanged = vi.fn(async () => ({
      accepted: true as const,
    }));
    const store = memorySessionStore();
    const adapter = createClaudeEventAdapter(
      { ...config, mode: "recall-and-sync" },
      { recall, notifySourceChanged },
      store,
    );
    expect(
      (
        await adapter.handle({
          hook_event_name: "UserPromptSubmit",
          session_id: "s1",
          prompt: "q".repeat(2001),
        })
      ).state,
    ).toBe("invalid");
    expect(recall).not.toHaveBeenCalled();
    expect(
      (await adapter.handle({ hook_event_name: "Stop", session_id: "s1" }))
        .state,
    ).toBe("notified");
  });

  it("does not require a recall transport and suppresses sync-only error context", async () => {
    const store = memorySessionStore();
    const notifySourceChanged = vi.fn(async () => {
      throw Object.assign(new Error("private"), {
        code: "source_not_authorized",
      });
    });
    const adapter = createClaudeEventAdapter(
      config,
      { notifySourceChanged },
      store,
    );
    await adapter.handle({
      hook_event_name: "UserPromptSubmit",
      session_id: "s1",
      prompt: "q",
    });
    expect(
      await adapter.handle({ hook_event_name: "Stop", session_id: "s1" }),
    ).toEqual({
      state: "denied",
      output: { continue: true, suppressOutput: true },
    });
    expect((await store.read("s1"))?.notifiedEventId).toBeNull();
    await adapter.handle({ hook_event_name: "SessionEnd", session_id: "s1" });
    expect(
      (await adapter.handle({ hook_event_name: "Stop", session_id: "s1" }))
        .state,
    ).toBe("ignored");
  });
});
