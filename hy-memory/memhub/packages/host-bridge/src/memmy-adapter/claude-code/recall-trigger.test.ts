import type { RecallReceipt } from "@one-memory/contracts";
import { describe, expect, it, vi } from "vitest";
import {
  createClaudeEventAdapter,
  type SourceChangeNotification,
} from "./event-adapter.js";
import { memorySessionStore } from "./session-state.js";

const config = {
  schemaVersion: 1 as const,
  mode: "recall-and-sync" as const,
  installationId: "00000000-0000-4000-8000-000000000001",
  discoveryPath: "/fixture/discovery.json",
  credentialFile: "/fixture/private/credential",
  stateDirectory: "/fixture/state",
};

function fixture() {
  const recall = vi.fn(
    async (request: { query: string }): Promise<RecallReceipt> => ({
      state: "grounded",
      query: request.query,
      scope: "all-apps",
      hits: [
        {
          memory_id: "memory-1",
          content: "上次定的部署窗口是周四晚上。",
          kind: "chat",
          scopes: ["all-apps"],
          evidence_ids: ["e-1"],
          updated_at: "2026-09-14T00:00:00Z",
          score: 1,
        },
      ],
      used_characters: 14,
      truncated: false,
    }),
  );
  const notifySourceChanged = vi.fn(
    async (_notification: SourceChangeNotification) => ({
      accepted: true as const,
    }),
  );
  const notices: string[] = [];
  return {
    recall,
    notices,
    adapter: createClaudeEventAdapter(
      config,
      { recall, notifySourceChanged },
      memorySessionStore(),
      (text) => notices.push(text),
    ),
  };
}

const prompt = (session: string, text: string) => ({
  hook_event_name: "UserPromptSubmit",
  session_id: session,
  prompt: text,
});

// HOST-01/02. The handoff is explicit that fetching on every turn is the thing
// not to copy: a greeting should cost nothing, and the user should not be told
// their memory was consulted when it had no bearing on the answer.
describe("when an authorized turn is worth a recall", () => {
  it("asks for a turn that cannot be answered without history", async () => {
    const f = fixture();

    await f.adapter.handle(prompt("s1", "我们之前定的部署窗口是哪天？"));

    expect(f.recall).toHaveBeenCalledOnce();
    expect(f.notices).toEqual(["正在使用 MemHub 查询记忆"]);
  });

  it.each(["你好", "hi", "谢谢！", "thanks", "ok", "好的"])(
    "leaves a greeting alone: %j",
    async (text) => {
      const f = fixture();

      const result = await f.adapter.handle(prompt("s1", text));

      expect(f.recall).not.toHaveBeenCalled();
      // Silence is the point. A notice here is the user being told their memory
      // was read to answer "hi".
      expect(f.notices).toEqual([]);
      expect(result.output.hookSpecificOutput).toBeUndefined();
    },
  );

  it("does not fetch the same question twice in one session", async () => {
    const f = fixture();

    await f.adapter.handle(prompt("s1", "我们之前定的部署窗口是哪天？"));
    await f.adapter.handle(prompt("s1", "我们之前定的部署窗口是哪天？  "));

    expect(f.recall).toHaveBeenCalledOnce();
  });

  it("still fetches that question for a different session", async () => {
    const f = fixture();

    await f.adapter.handle(prompt("s1", "我们之前定的部署窗口是哪天？"));
    await f.adapter.handle(prompt("s2", "我们之前定的部署窗口是哪天？"));

    expect(f.recall).toHaveBeenCalledTimes(2);
  });

  it("keeps fetching a question that only looks like the last one", async () => {
    const f = fixture();

    await f.adapter.handle(prompt("s1", "我们之前定的部署窗口是哪天？"));
    await f.adapter.handle(prompt("s1", "我们之前定的发布窗口是哪天？"));

    expect(f.recall).toHaveBeenCalledTimes(2);
  });

  // A question is only settled once something came back for it. These are the
  // cases where suppressing the retry would lose the user an answer.
  it("lets a question be asked again after an empty answer", async () => {
    const f = fixture();
    f.recall.mockResolvedValueOnce({
      state: "empty",
      query: "我们之前定的部署窗口是哪天？",
      scope: "all-apps",
      hits: [],
      used_characters: 0,
      truncated: false,
    });

    await f.adapter.handle(prompt("s1", "我们之前定的部署窗口是哪天？"));
    await f.adapter.handle(prompt("s1", "我们之前定的部署窗口是哪天？"));

    expect(f.recall).toHaveBeenCalledTimes(2);
  });

  it("lets a question be asked again after the recall was denied", async () => {
    const f = fixture();
    f.recall.mockRejectedValueOnce(
      Object.assign(new Error("denied"), { code: "host_scope_denied" }),
    );

    const denied = await f.adapter.handle(
      prompt("s1", "我们之前定的部署窗口是哪天？"),
    );
    await f.adapter.handle(prompt("s1", "我们之前定的部署窗口是哪天？"));

    expect(denied.state).toBe("denied");
    expect(f.recall).toHaveBeenCalledTimes(2);
  });

  // A session already under way when this field arrived has state without it.
  // Rejecting that state would take the hook silent for the rest of the
  // session, which is a worse outcome than one redundant fetch.
  it("reads a session written before it tracked questions", async () => {
    const store = memorySessionStore();
    const before = {
      schemaVersion: 1 as const,
      revision: 3,
      turn: 2,
      turnIdentity: null,
      closed: false,
      pendingEventId: null,
      notifiedEventId: null,
      seenEventIds: [],
    };
    await store.update("s1", () => before);
    expect(await store.read("s1")).toEqual(before);

    const recall = vi.fn(
      async (request: { query: string }): Promise<RecallReceipt> => ({
        state: "empty",
        query: request.query,
        scope: "all-apps",
        hits: [],
        used_characters: 0,
        truncated: false,
      }),
    );
    const adapter = createClaudeEventAdapter(
      config,
      { recall, notifySourceChanged: async () => ({ accepted: true }) },
      store,
    );

    expect(
      (await adapter.handle(prompt("s1", "之前那版是怎么定的？"))).state,
    ).toBe("empty");
    expect(recall).toHaveBeenCalledOnce();
  });
});
