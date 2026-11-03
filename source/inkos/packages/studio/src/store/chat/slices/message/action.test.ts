import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { createStore } from "zustand/vanilla";
import type { ChatStore, SessionMessage } from "../../types";
import { initialChatState } from "../../initialState";
import { createCreateSlice } from "../create/action";
import { createMessageSlice } from "./action";
import { closeStudioEventConnections, subscribeStudioEvents } from "../../../../lib/studio-events";

const { fetchJson } = vi.hoisted(() => ({
  fetchJson: vi.fn(),
}));

vi.mock("../../../../hooks/use-api", () => ({ fetchJson }));

class FakeEventSource {
  readonly url: string;
  readonly listeners = new Map<string, Array<(event: MessageEvent) => void>>();
  closed = false;
  constructor(url: string) {
    this.url = url;
    fakeEventSources.push(this);
  }
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    const current = this.listeners.get(type) ?? [];
    current.push(listener);
    this.listeners.set(type, current);
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data: JSON.stringify(data) } as MessageEvent);
    }
  }
}

const fakeEventSources: FakeEventSource[] = [];

function createTestStore() {
  return createStore<ChatStore>()((...args) => ({
    ...initialChatState,
    ...createMessageSlice(...args),
    ...createCreateSlice(...args),
  }));
}

describe("chat message actions", () => {
  const originalEventSource = globalThis.EventSource;

  beforeEach(() => {
    fetchJson.mockReset();
    fetchJson.mockResolvedValue({});
    fakeEventSources.length = 0;
    (globalThis as any).EventSource = FakeEventSource;
  });

  afterEach(() => {
    closeStudioEventConnections();
    (globalThis as any).EventSource = originalEventSource;
  });

  it("shares dashboard and session events without closing another consumer's connection", () => {
    const dashboard = subscribeStudioEvents();
    const conversation = subscribeStudioEvents("/api/v1/events?sessionId=probe");
    const globalListener = vi.fn(), sessionListener = vi.fn();
    dashboard.addEventListener("log", globalListener);
    conversation.addEventListener("log", sessionListener);
    expect(fakeEventSources).toHaveLength(1);
    fakeEventSources[0]!.emit("log", { sessionId: "probe" });
    expect(globalListener).toHaveBeenCalledTimes(1);
    expect(sessionListener).toHaveBeenCalledTimes(1);
    conversation.close();
    expect(fakeEventSources[0]!.closed).toBe(false);
    fakeEventSources[0]!.emit("log", { sessionId: "probe" });
    expect(globalListener).toHaveBeenCalledTimes(2);
    expect(sessionListener).toHaveBeenCalledTimes(1);
    dashboard.close();
    expect(fakeEventSources[0]!.closed).toBe(true);
  });

  it("creates a Work session while retaining the selected service and model identity", async () => {
    const store = createTestStore();
    store.setState({selectedModel:"shared-model",selectedService:"custom:responses"});
    fetchJson.mockResolvedValueOnce({
      session: {
        sessionId: "work-session",
        bookId: null,
        sessionKind: "work",
        profileId: "script",
        workId: "script-work",
        title: null,
      },
    });

    const sessionId = await store.getState().createSession(null, "work", undefined, {
      profileId: "script",
      workId: "script-work",
    });

    expect(sessionId).toBe("work-session");
    expect(fetchJson.mock.calls[0][0]).toBe("/sessions");
    expect(JSON.parse(fetchJson.mock.calls[0][1].body)).toMatchObject({bookId:null,sessionKind:"work",profileId:"script",workId:"script-work",modelOverride:"shared-model",serviceOverride:"custom:responses"});
    expect(store.getState().sessions[sessionId]).toMatchObject({
      profileId: "script",
      workId: "script-work",
      modelOverride:"shared-model",
      serviceOverride:"custom:responses",
    });
  });

  it("keeps the previous request alive across navigation until an explicit stop", async () => {
    const store = createTestStore();
    const previousId = store.getState().createDraftSession(null, "chat");
    const nextId = store.getState().createDraftSession(null, "chat");
    const stream = new FakeEventSource(`/api/v1/events?sessionId=${previousId}`);
    store.setState((state) => ({
      activeSessionId: previousId,
      sessions: {
        ...state.sessions,
        [previousId]: {
          ...state.sessions[previousId]!,
          isStreaming: true,
          isChatStreaming: true,
          stream: stream as unknown as EventSource,
        },
      },
    }));
    fetchJson.mockClear();

    store.getState().activateSession(nextId);

    expect(store.getState().activeSessionId).toBe(nextId);
    expect(store.getState().sessions[previousId]).toMatchObject({isStreaming:true,isChatStreaming:true,stream});
    expect(stream.closed).toBe(false);
    expect(fetchJson).not.toHaveBeenCalled();
    await store.getState().abortSession(previousId,"chat");
    await vi.waitFor(() => expect(store.getState().sessions[previousId]).toMatchObject({
      isStreaming: false,
      isChatStreaming: false,
      stream: null,
    }));
    expect(stream.closed).toBe(true);
    await vi.waitFor(() => {
      expect(fetchJson).toHaveBeenCalledWith(`/sessions/${previousId}/abort?scope=chat`, { method: "POST" });
    });
  });

  it("keeps production alive and a new draft selected when an earlier session creation arrives late", async () => {
    const store = createTestStore();
    const previousId = store.getState().createDraftSession(null, "short");
    const nextId = store.getState().createDraftSession(null, "chat");
    const stream = new FakeEventSource(`/api/v1/events?sessionId=${previousId}`);
    store.setState((state) => ({
      activeSessionId: previousId,
      sessions: {
        ...state.sessions,
        [previousId]: {
          ...state.sessions[previousId]!,
          isStreaming: true,
          isChatStreaming: true,
          stream: stream as unknown as EventSource,
          messages: [{
            role: "assistant",
            content: "",
            timestamp: 10,
            toolExecutions: [{
              id: "short-task-1",
              tool: "short_fiction_run",
              label: "短篇生产",
              status: "running",
              startedAt: 10,
              background: true,
            }],
          }],
        },
      },
    }));
    fetchJson.mockClear();

    let finishCreation!:(value:unknown)=>void;
    fetchJson.mockImplementationOnce(()=>new Promise(resolve=>{finishCreation=resolve;}));
    const creating=store.getState().createSession(null,"chat");
    const draftId=store.getState().createDraftSession(null,"chat");
    finishCreation({session:{sessionId:'late-session',bookId:null,sessionKind:'chat'}});
    await creating;
    expect(store.getState().activeSessionId).toBe(draftId);
    expect(draftId).not.toBe(nextId);

    await vi.waitFor(() => expect(store.getState().sessions[previousId]).toMatchObject({
      isStreaming: true,
      isChatStreaming: true,
      stream,
    }));
    expect(store.getState().sessions[previousId]?.messages[0]?.toolExecutions?.[0]).toMatchObject({
      status: "running",
      background: true,
    });
    expect(stream.closed).toBe(false);
    expect(fetchJson.mock.calls.map(call=>call[0])).toEqual(['/sessions']);
  });

  it("keeps play mode local for draft sessions until the first message persists them", () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "play", "open");

    store.getState().setSessionPlayMode(sessionId, "guided");

    expect(store.getState().sessions[sessionId]?.playMode).toBe("guided");
    expect(fetchJson).not.toHaveBeenCalled();
  });

  it("syncs the created book id returned by /agent back into the current runtime session", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "book-create");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "book-create" } })
      .mockResolvedValueOnce({
        response: "已创建书籍。",
        session: { sessionId, activeBookId: "new-book", sessionKind: "book" },
      });

    await store.getState().sendMessage(sessionId, "创建一本债务悬疑长篇", { sessionKind: "book-create" });

    expect(store.getState().sessions[sessionId]).toMatchObject({
      bookId: "new-book",
      sessionKind: "book",
      isDraft: false,
    });
    expect(store.getState().sessionIdsByBook["new-book"]).toContain(sessionId);
  });

  it("sends the session-bound book id when no explicit activeBookId option is provided", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession("harbor-book", "book");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    store.getState().setSelectedModel("MiniMax-M2.7", "minimax");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: "harbor-book", sessionKind: "book" } })
      .mockResolvedValueOnce({
        response: "ok",
        session: { sessionId, activeBookId: "harbor-book", sessionKind: "book" },
      });

    await store.getState().sendMessage(sessionId, "审第 1 章");

    const agentCall = fetchJson.mock.calls.find(([path]) => path === "/agent");
    expect(agentCall).toBeDefined();
    const body = JSON.parse((agentCall?.[1] as { body: string }).body);
    expect(body.activeBookId).toBe("harbor-book");
    expect(body.sessionKind).toBe("book");
    expect(body.service).toBe("kkaiapi");
    expect(body.model).toBe("deepseek-v4-flash");
  });

  it("does not send a selected Work's instruction through a stale bound session", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession("old-book", "book");
    store.getState().setSelectedModel("gpt-5.6-sol", "kkaiapi");
    await store.getState().sendMessage(sessionId, "Revise the selected book", {
      activeBookId: "new-book", workId: "old-book",
    });
    expect(fetchJson).not.toHaveBeenCalled();
    expect(store.getState().sessions[sessionId].bookId).toBe("old-book");
    expect(store.getState().sessions[sessionId].isDraft).toBe(true);
  });

  it("parses @skill directives into requestedSkills and strips them from the agent instruction", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "play", "open");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "play" } })
      .mockResolvedValueOnce({
        response: "ok",
        session: { sessionId, bookId: null, sessionKind: "play" },
      });

    await store.getState().sendMessage(sessionId, "@open-world-play 做一个魔兽风开放世界", {
      sessionKind: "play",
    });

    const agentCall = fetchJson.mock.calls.find(([path]) => path === "/agent");
    expect(agentCall).toBeDefined();
    const body = JSON.parse((agentCall?.[1] as { body: string }).body);
    expect(body.instruction).toBe("做一个魔兽风开放世界");
    expect(body.requestedSkills).toEqual(["open-world-play"]);
  });

  it("keeps a tool-only stream when /agent returns an empty response after a proposal", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "book-create");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let resolveAgent!: (value: unknown) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "book-create" } })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveAgent = resolve;
      }));

    const sent = store.getState().sendMessage(sessionId, "创建一本债务悬疑长篇", { sessionKind: "book-create" });
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));

    fakeEventSources[0].emit("tool:start", {
      sessionId,
      id: "proposal-1",
      tool: "propose_action",
    });
    fakeEventSources[0].emit("tool:end", {
      sessionId,
      id: "proposal-1",
      tool: "propose_action",
      details: {
        kind: "proposed_action",
        action: "create_book",
        targetSessionKind: "book-create",
        sameSession: true,
        title: "确认建书",
        instruction: "创建一本债务悬疑长篇",
      },
    });

    resolveAgent({ response: "", session: { sessionId, sessionKind: "book-create" } });
    await sent;

    const messages = store.getState().sessions[sessionId]?.messages ?? [];
    const assistant = messages.find((message) => message.role === "assistant");
    expect(assistant?.content).not.toContain("模型未返回文本内容");
    expect(assistant?.parts).toEqual([
      expect.objectContaining({
        type: "tool",
        execution: expect.objectContaining({
          tool: "propose_action",
          status: "completed",
        }),
      }),
    ]);
  });

  it("restores confirmed proposal cards when loading persisted session messages", () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "play", "open");

    store.getState().loadSessionMessages(sessionId, [
      {
        role: "assistant",
        content: "",
        timestamp: 1,
        toolExecutions: [
          {
            id: "proposal-1",
            tool: "propose_action",
            label: "确认动作",
            status: "completed",
            startedAt: 1,
            details: {
              kind: "proposed_action",
              action: "play_start",
              targetSessionKind: "play",
              instruction: "启动旧影院",
            },
          },
        ],
      },
      {
        role: "assistant",
        content: "",
        timestamp: 2,
        toolExecutions: [
          {
            id: "play-1",
            tool: "play_start",
            label: "启动互动世界",
            status: "completed",
            startedAt: 2,
            details: {
              kind: "play_world_started",
              requestedIntent: "play_start",
              presentation: "immersive-scene",
            },
          },
        ],
      },
    ]);

    expect(store.getState().resolvedProposals).toEqual({ "proposal-1": "confirmed" });
  });

  it("does not replace an active local stream while session detail is loading", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "short");
    const stream = new FakeEventSource(`/api/v1/events?sessionId=${sessionId}`);
    store.setState((state) => ({
      sessions: {
        ...state.sessions,
        [sessionId]: {
          ...state.sessions[sessionId]!,
          isDraft: false,
          isStreaming: true,
          stream: stream as unknown as EventSource,
        },
      },
    }));
    fetchJson.mockClear();

    await store.getState().loadSessionDetail(sessionId);

    expect(fetchJson).not.toHaveBeenCalled();
    expect(store.getState().sessions[sessionId]).toMatchObject({
      isStreaming: true,
      stream,
    });
  });

  it("restores and reconnects a running production task when session detail reloads", async () => {
    const store = createTestStore();
    fetchJson.mockResolvedValueOnce({
      session: { sessionId: "short-session-1", bookId: null, sessionKind: "short", title: "雨夜账本" },
    });
    const sessionId = await store.getState().createSession(null, "short");
    fetchJson.mockResolvedValueOnce({
      session: {
        sessionId,
        bookId: null,
        sessionKind: "short",
        title: "雨夜账本",
        messages: [],
      },
      task: {
        version: 1,
        sessionId,
        requestedIntent: "short_run",
        updatedAt: 20,
        execution: {
          id: "short-task-1",
          tool: "short_fiction_run",
          label: "生成短篇",
          status: "running",
          startedAt: 10,
          logs: ["正在生成大纲"],
        },
      },
    });

    await store.getState().loadSessionDetail(sessionId);

    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true });
    expect(store.getState().sessions[sessionId]?.messages[0]?.toolExecutions?.[0]).toMatchObject({
      id: "short-task-1",
      status: "running",
      logs: ["正在生成大纲"],
    });
    expect(fakeEventSources).toHaveLength(1);
    expect(fakeEventSources[0]?.url).toBe("/api/v1/events");

    fakeEventSources[0]?.emit("task:snapshot", {
      version: 1,
      sessionId,
      requestedIntent: "short_run",
      updatedAt: 30,
      execution: {
        id: "short-task-1",
        tool: "short_fiction_run",
        label: "生成短篇",
        status: "completed",
        startedAt: 10,
        completedAt: 30,
        result: "短篇已完成",
      },
    });

    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: false, stream: null });
    expect(store.getState().sessions[sessionId]?.messages).toHaveLength(1);
    expect(store.getState().sessions[sessionId]?.messages[0]?.toolExecutions?.[0]).toMatchObject({
      id: "short-task-1",
      status: "completed",
      result: "短篇已完成",
    });
  });

  it("restores the transcript user bubble alongside the running task card without duplication", async () => {
    const store = createTestStore();
    fetchJson.mockResolvedValueOnce({
      session: { sessionId: "short-session-2", bookId: null, sessionKind: "short", title: null },
    });
    const sessionId = await store.getState().createSession(null, "short");
    fetchJson.mockResolvedValueOnce({
      session: {
        sessionId,
        bookId: null,
        sessionKind: "short",
        title: null,
        // 任务开始时预写进 transcript 的用户指令
        messages: [{ role: "user", content: "写一篇雨夜档案馆悬疑短篇。", timestamp: 5 }],
      },
      task: {
        version: 1,
        sessionId,
        requestedIntent: "short_run",
        updatedAt: 20,
        execution: {
          id: "short-task-2",
          tool: "short_fiction_run",
          label: "生成短篇",
          status: "running",
          startedAt: 10,
        },
      },
    });

    await store.getState().loadSessionDetail(sessionId);

    const messages = store.getState().sessions[sessionId]?.messages ?? [];
    // 用户气泡（来自 transcript）+ 运行中任务卡（来自快照 merge）共存且不重复
    expect(messages).toHaveLength(2);
    expect(messages[0]).toMatchObject({ role: "user", content: "写一篇雨夜档案馆悬疑短篇。" });
    expect(messages[1]?.toolExecutions?.[0]).toMatchObject({ id: "short-task-2", status: "running" });
    expect(
      messages.filter((message) => message.role === "user" && message.content === "写一篇雨夜档案馆悬疑短篇。"),
    ).toHaveLength(1);
  });

  it("ignores a stale terminal task snapshot replayed onto a new agent stream", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "short");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let resolveAgent!: (value: unknown) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "short" } })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveAgent = resolve;
      }));

    const sent = store.getState().sendMessage(sessionId, "再生成一篇短篇", { sessionKind: "short" });
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));

    // 服务端在 SSE 连接建立时会重放该会话磁盘上的任务快照；
    // 上一轮已完成的任务快照不能把本轮新建立的流关掉。
    fakeEventSources[0]?.emit("task:snapshot", {
      sessionId,
      execution: {
        id: "finished-task-9",
        tool: "short_fiction_run",
        label: "短篇生产",
        status: "completed",
        startedAt: 100,
        completedAt: 200,
        result: "上一轮短篇已完成",
      },
    });

    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true });
    expect(store.getState().sessions[sessionId]?.stream).not.toBeNull();
    const staleExecutions = (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => message.toolExecutions ?? [])
      .filter((execution) => execution.id === "finished-task-9");
    expect(staleExecutions).toHaveLength(0);

    resolveAgent({ response: "ok", session: { sessionId, sessionKind: "short" } });
    await sent;
  });

  it("marks the active tool card as stopped without requiring a refresh", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "short");
    store.getState().loadSessionMessages(sessionId, [{
      role: "assistant",
      content: "",
      timestamp: 10,
      toolExecutions: [{
        id: "short-task-1",
        tool: "short_fiction_run",
        label: "短篇生产",
        status: "running",
        startedAt: 10,
      }],
    }]);

    await store.getState().abortSession(sessionId);

    expect(store.getState().sessions[sessionId]?.messages[0]?.toolExecutions?.[0]).toMatchObject({
      status: "error",
      error: "已由用户停止",
      completedAt: expect.any(Number),
    });
    expect(fetchJson).toHaveBeenCalledWith(`/sessions/${sessionId}/abort`, { method: "POST" });
  });

  it("keeps one stopped task card when the aborted agent request later rejects", async () => {
    const now = vi.spyOn(Date, "now").mockReturnValue(1_000);
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "short");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let rejectAgent!: (error: Error) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "short" } })
      .mockImplementationOnce(() => new Promise((_resolve, reject) => {
        rejectAgent = reject;
      }))
      .mockResolvedValueOnce({});

    const sent = store.getState().sendMessage(sessionId, "确认生成短篇", { sessionKind: "short" });
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));
    fakeEventSources[0]?.emit("task:snapshot", {
      sessionId,
      execution: {
        id: "short-task-1",
        tool: "short_fiction_run",
        label: "短篇生产",
        status: "running",
        startedAt: 1_100,
      },
    });

    now.mockReturnValue(2_000);
    await store.getState().abortSession(sessionId);
    rejectAgent(new Error("This operation was aborted"));
    await sent;

    const taskExecutions = (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => message.toolExecutions ?? [])
      .filter((execution) => execution.id === "short-task-1");
    expect(taskExecutions).toEqual([
      expect.objectContaining({
        status: "error",
        error: "已由用户停止",
      }),
    ]);
    expect(store.getState().sessions[sessionId]?.messages).not.toContainEqual(
      expect.objectContaining({ content: expect.stringContaining("This operation was aborted") }),
    );
    now.mockRestore();
  });

  // 恢复出一个"任务运行中"的会话：磁盘上有 running 任务快照，前端加载详情后
  // 会 merge 任务卡、建立 SSE 连接并把 isStreaming 置为 true。
  async function setupRunningTaskSession(store: ReturnType<typeof createTestStore>): Promise<string> {
    fetchJson.mockResolvedValueOnce({
      session: { sessionId: "task-session-1", bookId: null, sessionKind: "short", title: "雨夜账本" },
    });
    const sessionId = await store.getState().createSession(null, "short");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson.mockResolvedValueOnce({
      session: { sessionId, bookId: null, sessionKind: "short", title: "雨夜账本", messages: [] },
      task: {
        version: 1,
        sessionId,
        requestedIntent: "short_run",
        updatedAt: 20,
        execution: {
          id: "direct-short_run-1",
          tool: "short_fiction_run",
          label: "短篇生产",
          status: "running",
          startedAt: 10,
        },
      },
    });
    await store.getState().loadSessionDetail(sessionId);
    expect(fakeEventSources).toHaveLength(1);
    return sessionId;
  }

  function findTaskExecution(store: ReturnType<typeof createTestStore>, sessionId: string) {
    return (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => message.toolExecutions ?? [])
      .find((execution) => execution.id === "direct-short_run-1");
  }

  it("keeps the task stream open when the chat round completes while the task is still running", async () => {
    const store = createTestStore();
    const sessionId = await setupRunningTaskSession(store);

    let resolveAgent!: (value: unknown) => void;
    fetchJson.mockClear();
    fetchJson.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAgent = resolve;
    }));

    const sent = store.getState().sendMessage(sessionId, "顺便聊两句");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(2));

    // 聊天轮的 agent:complete 到达时任务仍在跑：不能把连接关掉
    fakeEventSources[1]?.emit("agent:complete", { sessionId });
    expect(fakeEventSources[1]?.closed).toBe(false);
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true });

    resolveAgent({ response: "聊完了。", session: { sessionId, sessionKind: "short" } });
    await sent;

    expect(fakeEventSources[1]?.closed).toBe(false);
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true, isChatStreaming: false });

    // 任务完成：tool:end 按 execution id 找到早前消息里的任务卡收尾，随后的 agent:complete 关闭连接
    fakeEventSources[1]?.emit("tool:end", {
      sessionId,
      id: "direct-short_run-1",
      tool: "short_fiction_run",
      result: { content: [{ type: "text", text: "短篇已完成" }] },
    });
    fakeEventSources[1]?.emit("agent:complete", { sessionId });

    expect(findTaskExecution(store, sessionId)).toMatchObject({ status: "completed" });
    expect(fakeEventSources[1]?.closed).toBe(true);
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: false, stream: null });
  });

  it("keeps the streaming chat open when a terminal task snapshot lands mid-chat", async () => {
    const store = createTestStore();
    const sessionId = await setupRunningTaskSession(store);

    let resolveAgent!: (value: unknown) => void;
    fetchJson.mockClear();
    fetchJson.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAgent = resolve;
    }));

    const sent = store.getState().sendMessage(sessionId, "顺便聊两句");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(2));

    // 竞态：任务刚结束、消息里还有 in-flight 任务卡，此刻聊天轮建立的新连接
    // 收到服务端重放的终态快照。任务卡要收尾，但正在流式的聊天连接不能被关掉。
    fakeEventSources[1]?.emit("task:snapshot", {
      sessionId,
      execution: {
        id: "direct-short_run-1",
        tool: "short_fiction_run",
        label: "短篇生产",
        status: "completed",
        startedAt: 10,
        completedAt: 40,
        result: "短篇已完成",
      },
    });

    // 任务卡转为 completed
    expect(findTaskExecution(store, sessionId)).toMatchObject({
      status: "completed",
      result: "短篇已完成",
    });
    // 聊天轮仍在流式：连接未关、流式状态保持
    expect(fakeEventSources[1]?.closed).toBe(false);
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true, isChatStreaming: true });
    expect(store.getState().sessions[sessionId]?.stream).not.toBeNull();

    resolveAgent({ response: "聊完了。", session: { sessionId, sessionKind: "short" } });
    await sent;

    // 聊天轮自己收尾：任务已完成，连接关闭
    expect(store.getState().sessions[sessionId]).toMatchObject({
      isStreaming: false,
      isChatStreaming: false,
      stream: null,
    });
    expect(fakeEventSources[1]?.closed).toBe(true);
  });

  it("closes the stream after a plain chat round when no production task is running", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "chat");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let resolveAgent!: (value: unknown) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "chat" } })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveAgent = resolve;
      }));

    const sent = store.getState().sendMessage(sessionId, "你好");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true, isChatStreaming: true });

    resolveAgent({ response: "你好！", session: { sessionId, sessionKind: "chat" } });
    await sent;

    expect(store.getState().sessions[sessionId]).toMatchObject({
      isStreaming: false,
      isChatStreaming: false,
      stream: null,
    });
    expect(fakeEventSources[0]?.closed).toBe(true);
  });

  it("aborts the chat round and its running production workflow together", async () => {
    const store = createTestStore();
    const sessionId = await setupRunningTaskSession(store);

    let rejectAgent!: (error: Error) => void;
    fetchJson.mockClear();
    fetchJson
      .mockImplementationOnce(() => new Promise((_resolve, reject) => {
        rejectAgent = reject;
      }))
      .mockResolvedValueOnce({ ok: true, aborted: true });

    const sent = store.getState().sendMessage(sessionId, "顺便问一下");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(2));

    await store.getState().abortSession(sessionId);

    const abortCall = fetchJson.mock.calls.find(([path]) => path === `/sessions/${sessionId}/abort`);
    expect(abortCall?.[1]).toEqual({ method: "POST" });
    expect(findTaskExecution(store, sessionId)).toMatchObject({ status: "error" });
    expect(fakeEventSources[1]?.closed).toBe(true);
    expect(store.getState().sessions[sessionId]).toMatchObject({
      isStreaming: false,
      isChatStreaming: false,
      stream: null,
    });

    rejectAgent(new Error("This operation was aborted"));
    await sent;

    expect(findTaskExecution(store, sessionId)).toMatchObject({ status: "error" });
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: false });
  });

  function findChatToolExecution(store: ReturnType<typeof createTestStore>, sessionId: string) {
    return (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => message.toolExecutions ?? [])
      .find((execution) => execution.id === "chat-tool-1");
  }

  it("routes executionId-tagged logs to the task card while untagged logs follow the latest running card", async () => {
    const store = createTestStore();
    const sessionId = await setupRunningTaskSession(store);

    let resolveAgent!: (value: unknown) => void;
    fetchJson.mockClear();
    fetchJson.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAgent = resolve;
    }));
    const sent = store.getState().sendMessage(sessionId, "顺便审一下最新章节");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(2));

    // 聊天轮启动了自己的工具卡：它成为"最近一张运行中的卡"
    fakeEventSources[1]?.emit("tool:start", {
      sessionId,
      id: "chat-tool-1",
      tool: "write_chapters",
      args: { agent: "auditor" },
    });

    // 带 executionId 的任务日志：附加到更早消息里的任务卡，而不是最新运行中的卡
    fakeEventSources[1]?.emit("log", {
      sessionId,
      executionId: "direct-short_run-1",
      level: "info",
      tag: "studio",
      message: "第 2 章草稿完成",
    });
    // 不带 executionId 的日志：维持现有回退，附加到最新运行中的聊天工具卡
    fakeEventSources[1]?.emit("log", {
      sessionId,
      level: "info",
      tag: "studio",
      message: "审稿进行中",
    });

    expect(findTaskExecution(store, sessionId)?.logs).toEqual(["第 2 章草稿完成"]);
    expect(findChatToolExecution(store, sessionId)?.logs).toEqual(["审稿进行中"]);

    resolveAgent({ response: "审完了。", session: { sessionId, sessionKind: "short" } });
    await sent;
  });

  it("reclassifies a free-text turn as a production task when the server starts a background task", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession("demo-book", "book");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let resolveAgent!: (value: unknown) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: "demo-book", sessionKind: "book" } })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveAgent = resolve;
      }));

    // free-text 发送：前端无法预知服务端会命中写章启发式，先按聊天轮对待
    const sent = store.getState().sendMessage(sessionId, "写下一章");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true, isChatStreaming: true });
    const agentRequest = fetchJson.mock.calls.find(([path]) => path === "/agent");
    const sourceRequestId = JSON.parse(String(agentRequest?.[1]?.body)).clientRequestId as string;

    // 普通聊天轮工具启动（不带 background 标记）不改变轮次分类
    fakeEventSources[0]?.emit("tool:start", { sessionId, id: "chat-tool-0", tool: "read" });
    expect(store.getState().sessions[sessionId]).toMatchObject({ isChatStreaming: true });
    fakeEventSources[0]?.emit("tool:end", { sessionId, id: "chat-tool-0", tool: "read", result: "ok" });

    // 服务端广播带 background 标记的 tool:start：这轮实际按后台生产任务执行
    fakeEventSources[0]?.emit("tool:start", {
      sessionId,
      id: "direct-write_next-1",
      tool: "write_chapters",
      args: { bookId: "demo-book" },
      background: true,
      sourceRequestId,
    });

    // 重分类：isChatStreaming 归 false（停止按钮据此走 scope=all，能拿到任务控制器），
    // isStreaming 维持 true（任务还在跑），工具卡带上 background 标记
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true, isChatStreaming: false });
    const taskExecution = (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => message.toolExecutions ?? [])
      .find((execution) => execution.id === "direct-write_next-1");
    expect(taskExecution).toMatchObject({ status: "running", background: true });

    // 任务结束：tool:end 收尾任务卡，挂起的 fetch 返回后 finally 正常收尾（不重复、不残留）
    fakeEventSources[0]?.emit("tool:end", {
      sessionId,
      id: "direct-write_next-1",
      tool: "write_chapters",
      result: { content: [{ type: "text", text: "第 3 章已完成" }] },
    });
    resolveAgent({ response: "", session: { sessionId, sessionKind: "book" } });
    await sent;

    expect(store.getState().sessions[sessionId]).toMatchObject({
      isStreaming: false,
      isChatStreaming: false,
      stream: null,
    });
    expect(fakeEventSources[0]?.closed).toBe(true);
  });

  it("keeps one task card when a replayed snapshot arrives before tool:start", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "play", "guided");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let resolveAgent!: (value: unknown) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "play", playMode: "guided" } })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveAgent = resolve;
      }));

    const sent = store.getState().sendMessage(sessionId, "启动世界", {
      sessionKind: "play",
      playMode: "guided",
      actionSource: "button",
      requestedIntent: "play_start",
    });
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));
    const agentRequest = fetchJson.mock.calls.find(([path]) => path === "/agent");
    const sourceRequestId = JSON.parse(String(agentRequest?.[1]?.body)).clientRequestId as string;
    const execution = {
      id: "direct-play_start-1",
      tool: "play_start",
      label: "启动互动世界",
      status: "running" as const,
      startedAt: 10,
      background: true,
    };

    fakeEventSources[0]?.emit("task:snapshot", {
      sessionId,
      sourceRequestId,
      execution,
    });
    fakeEventSources[0]?.emit("tool:start", {
      sessionId,
      sourceRequestId,
      id: execution.id,
      tool: execution.tool,
      background: true,
    });

    const matching = (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => message.toolExecutions ?? [])
      .filter((item) => item.id === execution.id);
    expect(matching).toHaveLength(1);

    fakeEventSources[0]?.emit("tool:end", {
      sessionId,
      id: execution.id,
      tool: execution.tool,
      result: "世界已启动",
    });
    resolveAgent({ response: "", session: { sessionId, sessionKind: "play", playMode: "guided" } });
    await sent;
  });

  it("merges the final HTTP tool result into the existing SSE card by execution id", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "play", "open");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let resolveAgent!: (value: unknown) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "play", playMode: "open" } })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveAgent = resolve;
      }));

    const sent = store.getState().sendMessage(sessionId, "启动开放世界", {
      sessionKind: "play",
      playMode: "open",
      requestedIntent: "play_start",
    });
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));

    const executionId = "direct-play_start-1";
    fakeEventSources[0]?.emit("tool:start", {
      sessionId,
      id: executionId,
      tool: "play_start",
      background: true,
    });
    fakeEventSources[0]?.emit("tool:end", {
      sessionId,
      id: executionId,
      tool: "play_start",
      details: { kind: "play_world_started", sceneText: "镇口日落。" },
    });

    resolveAgent({
      response: "",
      details: {
        toolExecutions: [{
          id: executionId,
          tool: "play_start",
          label: "启动互动世界",
          status: "completed",
          startedAt: 10,
          completedAt: 20,
          details: { kind: "play_world_started", sceneText: "镇口日落。" },
        }],
      },
      session: { sessionId, sessionKind: "play", playMode: "open" },
    });
    await sent;

    const matching = (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => message.toolExecutions ?? [])
      .filter((execution) => execution.id === executionId);
    expect(matching).toHaveLength(1);
    expect(matching[0]).toMatchObject({
      status: "completed",
      completedAt: 20,
      details: { kind: "play_world_started", sceneText: "镇口日落。" },
    });
  });

  it("does not duplicate a production card when task snapshot wins the startup race", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "script");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let resolveAgent!: (value: unknown) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "script" } })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveAgent = resolve;
      }));

    const sent = store.getState().sendMessage(sessionId, "确认创建剧本", {
      sessionKind: "script",
      actionSource: "button",
      requestedIntent: "script_create",
    });
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));
    const agentRequest = fetchJson.mock.calls.find(([path]) => path === "/agent");
    const sourceRequestId = JSON.parse(String(agentRequest?.[1]?.body)).clientRequestId as string;
    const executionId = "direct-script_create-1";

    // The task snapshot can be replayed while GET /events races the POST /agent
    // startup. Its timestamp differs from the client stream timestamp.
    fakeEventSources[0]?.emit("task:snapshot", {
      sessionId,
      sourceRequestId,
      execution: {
        id: executionId,
        tool: "script_create",
        label: "剧本创作",
        status: "running",
        startedAt: 10,
      },
    });
    fakeEventSources[0]?.emit("tool:start", {
      sessionId,
      sourceRequestId,
      id: executionId,
      tool: "script_create",
      background: true,
    });

    resolveAgent({
      response: "",
      details: {
        toolExecutions: [{
          id: executionId,
          tool: "script_create",
          label: "剧本创作",
          status: "completed",
          startedAt: 10,
          completedAt: 20,
          details: { kind: "script_created", scriptPath: "dramas/demo/script.md" },
        }],
      },
      session: { sessionId, sessionKind: "script" },
    });
    await sent;

    const matching = (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => message.toolExecutions ?? [])
      .filter((execution) => execution.id === executionId);
    expect(matching).toHaveLength(1);
    expect(matching[0]).toMatchObject({
      status: "completed",
      completedAt: 20,
      details: { kind: "script_created", scriptPath: "dramas/demo/script.md" },
    });
  });

  it("reclassifies a free-text turn from a replayed task snapshot and stops the production task", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession("demo-book", "book");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let resolveAgent!: (value: unknown) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: "demo-book", sessionKind: "book" } })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveAgent = resolve;
      }))
      .mockResolvedValueOnce({ ok: true, aborted: true });

    const sent = store.getState().sendMessage(sessionId, "连续写五章");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));
    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true, isChatStreaming: true });
    const agentRequest = fetchJson.mock.calls.find(([path]) => path === "/agent");
    const sourceRequestId = JSON.parse(String(agentRequest?.[1]?.body)).clientRequestId as string;

    // EventSource 可能晚于生产任务启动才连上：实时 tool:start 已经错过，服务端
    // 会回放带同一请求 ID 的 running 快照。它必须完成与 tool:start 相同的重分类。
    fakeEventSources[0]?.emit("task:snapshot", {
      sessionId,
      sourceRequestId,
      execution: {
        id: "direct-write_next-replayed",
        tool: "write_chapters",

        status: "running",
        startedAt: Date.now(),
      },
    });

    expect(store.getState().sessions[sessionId]).toMatchObject({ isStreaming: true, isChatStreaming: false });
    await store.getState().abortSession(sessionId);
    const abortCall = fetchJson.mock.calls.find(([path]) => path === `/sessions/${sessionId}/abort`);
    expect(abortCall?.[1]).toMatchObject({ method: "POST" });
    expect(abortCall?.[1]).not.toHaveProperty("body");

    resolveAgent({ error: { code: "REQUEST_ABORTED", message: "This operation was aborted" } });
    await sent;
  });

  it("keeps a parallel chat turn classified as chat when replaying an older background task", async () => {
    const store = createTestStore();
    const sessionId = await setupRunningTaskSession(store);

    let resolveAgent!: (value: unknown) => void;
    fetchJson.mockClear();
    fetchJson.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAgent = resolve;
    }));

    const sent = store.getState().sendMessage(sessionId, "顺便解释一下当前进度");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(2));
    expect(store.getState().sessions[sessionId]?.isChatStreaming).toBe(true);

    fakeEventSources[1]?.emit("task:snapshot", {
      sessionId,
      sourceRequestId: "older-request",
      execution: {
        id: "direct-short_run-1",
        tool: "short_fiction_run",
        status: "running",
        startedAt: 1,
      },
    });

    expect(store.getState().sessions[sessionId]?.isChatStreaming).toBe(true);
    resolveAgent({ response: "任务仍在运行。", session: { sessionId, sessionKind: "short" } });
    await sent;
  });

  it("routes executionId-tagged llm progress to the task card's active stage", async () => {
    const store = createTestStore();
    const sessionId = await setupRunningTaskSession(store);

    // 服务端快照重放会带 stages：给任务卡一个 active 阶段
    fakeEventSources[0]?.emit("task:snapshot", {
      sessionId,
      execution: {
        id: "direct-short_run-1",
        tool: "short_fiction_run",
        label: "短篇生产",
        status: "running",
        startedAt: 10,
        stages: [{ label: "撰写正文", status: "active" }],
      },
    });

    let resolveAgent!: (value: unknown) => void;
    fetchJson.mockClear();
    fetchJson.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAgent = resolve;
    }));
    const sent = store.getState().sendMessage(sessionId, "顺便聊两句");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(2));
    fakeEventSources[1]?.emit("tool:start", {
      sessionId,
      id: "chat-tool-1",
      tool: "write_chapters",
      args: { agent: "auditor" },
      stages: ["审稿"],
    });

    fakeEventSources[1]?.emit("llm:progress", {
      sessionId,
      executionId: "direct-short_run-1",
      status: "写作中",
      elapsedMs: 1200,
      totalChars: 800,
      chineseChars: 640,
    });

    // 带 executionId 的进度精确写进任务卡的 active 阶段
    expect(findTaskExecution(store, sessionId)?.stages?.[0]?.progress).toMatchObject({
      elapsedMs: 1200,
      totalChars: 800,
      chineseChars: 640,
    });
    // 最新运行中的聊天工具卡没有被任务进度污染
    expect(findChatToolExecution(store, sessionId)?.stages?.[0]?.progress).toBeUndefined();

    resolveAgent({ response: "聊完了。", session: { sessionId, sessionKind: "short" } });
    await sent;
  });

  it("drops id-less logs and progress instead of attaching them to a background task card", async () => {
    const store = createTestStore();
    const sessionId = await setupRunningTaskSession(store);
    // 快照重放给任务卡一个 active 阶段，验证无 id 进度也不会写进去
    fakeEventSources[0]?.emit("task:snapshot", {
      sessionId,
      execution: {
        id: "direct-short_run-1",
        tool: "short_fiction_run",
        label: "短篇生产",
        status: "running",
        startedAt: 10,
        stages: [{ label: "撰写正文", status: "active" }],
      },
    });

    let resolveAgent!: (value: unknown) => void;
    fetchJson.mockClear();
    fetchJson.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAgent = resolve;
    }));
    const sent = store.getState().sendMessage(sessionId, "顺便聊两句");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(2));

    // 聊天轮还没有自己的工具卡：无 id 的 log / llm:progress 不能回退到
    // 后台任务卡（会反向串排），只能丢弃（任务快照重放会带回累积日志）。
    fakeEventSources[1]?.emit("log", {
      sessionId,
      level: "info",
      tag: "studio",
      message: "游离的聊天轮日志",
    });
    fakeEventSources[1]?.emit("llm:progress", {
      sessionId,
      status: "思考中",
      elapsedMs: 900,
      totalChars: 120,
      chineseChars: 100,
    });
    expect(findTaskExecution(store, sessionId)?.logs).toBeUndefined();
    expect(findTaskExecution(store, sessionId)?.stages?.[0]?.progress).toBeUndefined();

    // 聊天轮工具卡出现后：无 id 日志照旧落在聊天卡上，任务卡不受影响
    fakeEventSources[1]?.emit("tool:start", {
      sessionId,
      id: "chat-tool-1",
      tool: "write_chapters",
      args: { agent: "auditor" },
    });
    fakeEventSources[1]?.emit("log", {
      sessionId,
      level: "info",
      tag: "studio",
      message: "审稿进行中",
    });
    expect(findChatToolExecution(store, sessionId)?.logs).toEqual(["审稿进行中"]);
    expect(findTaskExecution(store, sessionId)?.logs).toBeUndefined();

    resolveAgent({ response: "聊完了。", session: { sessionId, sessionKind: "short" } });
    await sent;
  });

  it("records the failed send with its original text and options when /agent rejects", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession("demo-book", "book");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: "demo-book", sessionKind: "book" } })
      .mockRejectedValueOnce(new Error("Request timed out"));

    await store.getState().sendMessage(sessionId, "写下一章", {
      sessionKind: "book",
      requestedSkills: ["style-guard"],
    });

    expect(store.getState().sessions[sessionId]?.lastError).toBe("Request timed out");
    expect(store.getState().sessions[sessionId]?.lastFailedSend).toMatchObject({
      text: "写下一章",
      options: { sessionKind: "book", requestedSkills: ["style-guard"] },
    });
  });

  it("restores a failed submission after a fresh page load and retries against its current saved Work", async () => {
    const store = createTestStore();
    const sessionId = "restored-failure";
    const options = { sessionKind: "chat" as const, requestedSkills: ["style-guard"],
      disabledSkills: ["inkos-story-review"], attachments: [{ id: "note", filename: "note.txt",
        mediaType: "text/plain", size: 5, dataUrl: "data:text/plain;base64,aGVsbG8=" }] };
    const snapshot = { session: { sessionId, bookId: null, workId: "saved-work", profileId: "script", sessionKind: "work" as const,
      messages: [{ role: "user" as const, content: "Revise the attached passage", timestamp: 10 }] },
      chatRequest: { sessionId, requestId: "failed-round", startedAt: 10, completedAt: 20, status: "failed" as const,
        error: { code: "CHAT_REQUEST_FAILED", message: "Provider disconnected" }, retry: { text: "Revise the attached passage", options } } };
    await store.getState().loadSessionDetail(sessionId, true, snapshot);
    await store.getState().loadSessionDetail(sessionId, true, snapshot);
    expect(store.getState().sessions[sessionId]).toMatchObject({ isChatStreaming: false, isStreaming: false,
      lastFailedSend: snapshot.chatRequest.retry });
    expect(store.getState().sessions[sessionId]!.messages.filter(x => x.kind === "error")).toHaveLength(1);
    store.getState().setSelectedModel("fixture-model", "custom:fixture");
    fetchJson.mockResolvedValueOnce({ response: "Saved", session: snapshot.session });
    await store.getState().retryLastSend(sessionId);
    const request = fetchJson.mock.calls.find(([path]) => path === "/agent")!;
    expect(JSON.parse(request[1].body)).toMatchObject({ instruction: snapshot.chatRequest.retry.text,
      workId: "saved-work", profileId: "script", sessionKind: "work", attachments: options.attachments,
      requestedSkills: options.requestedSkills, disabledSkills: options.disabledSkills });
    expect(store.getState().sessions[sessionId]?.lastFailedSend).toBeUndefined();
    await store.getState().loadSessionDetail(sessionId, true, { ...snapshot, chatRequest: { ...snapshot.chatRequest, status: "cancelled", retry: undefined } });
    expect(store.getState().sessions[sessionId]?.lastFailedSend).toBeUndefined();
    expect(store.getState().sessions[sessionId]?.lastError).toBeNull();
    let restore!: (value: unknown) => void, complete!: (value: unknown) => void;
    fetchJson.mockImplementation(path => new Promise(resolve => {
      if (path === "/agent") complete = resolve; else restore = resolve;
    }));
    const staleLoad = store.getState().loadSessionDetail(sessionId, true);
    const newSend = store.getState().sendMessage(sessionId, "Read the saved result");
    restore(snapshot);
    expect(await staleLoad).toBe(false);
    expect(store.getState().sessions[sessionId]).toMatchObject({ isChatStreaming: true, lastFailedSend: undefined });
    complete({ response: "Saved", session: snapshot.session });
    await newSend;
  });

  it("recovers a detached chat from server state, prevents duplicate sends, and restores stop after refresh", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "chat");
    store.getState().setSelectedModel("fixture-model", "custom:fixture");
    let online = false, sends = 0;
    const session = { sessionId, bookId: null, sessionKind: "chat" as const,
      messages: [{ role: "user", content: "Continue", timestamp: 10 }] as SessionMessage[] };
    let chatRequest = { sessionId, requestId: "pending", startedAt: 10, status: "running" as "running" | "completed" };
    fetchJson.mockImplementation(async (path, init) => {
      if (path === "/sessions") return { session };
      if (path === "/agent") {
        sends++;
        chatRequest.requestId = JSON.parse(init.body).clientRequestId;
        throw new TypeError("Failed to fetch");
      }
      if (path.endsWith("/abort")) return { ok: true, aborted: true };
      if (!online) throw new TypeError("Failed to fetch");
      return { session, chatRequest };
    });
    await store.getState().sendMessage(sessionId, "Continue");
    expect(store.getState().sessions[sessionId]).toMatchObject({
      isChatStreaming: true, isStreaming: true, detachedChatRequestId: chatRequest.requestId, lastError: null,
    });
    await store.getState().sendMessage(sessionId, "Continue");
    await store.getState().retryLastSend(sessionId);
    expect(sends).toBe(1);

    online = true;
    (fakeEventSources.at(-1) as unknown as { onopen: () => void }).onopen();
    await vi.waitFor(() => expect(store.getState().sessions[sessionId]?.messages).toHaveLength(1));
    chatRequest = { ...chatRequest, status: "completed" };
    session.messages.push({ role: "assistant", content: "Saved result", timestamp: 20 });
    fakeEventSources.at(-1)!.emit("request:snapshot", chatRequest);
    await vi.waitFor(() => expect(store.getState().sessions[sessionId]).toMatchObject({
      isChatStreaming: false, isStreaming: false, detachedChatRequestId: undefined,
      lastFailedSend: undefined, stream: null,
    }));
    expect(store.getState().sessions[sessionId]?.messages.map(message => message.timestamp)).toEqual([10, 20]);

    chatRequest = { ...chatRequest, requestId: "next-request", status: "running" };
    const refreshed = createTestStore();
    await refreshed.getState().loadSessionDetail(sessionId);
    expect(refreshed.getState().sessions[sessionId]).toMatchObject({
      isChatStreaming: true, isStreaming: true, detachedChatRequestId: "next-request",
    });
    fetchJson.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await refreshed.getState().abortSession(sessionId, "chat");
    expect(refreshed.getState().sessions[sessionId]).toMatchObject({ isChatStreaming: true, isStreaming: true });
    await refreshed.getState().abortSession(sessionId, "chat");
    expect(fetchJson).toHaveBeenLastCalledWith(`/sessions/${sessionId}/abort?scope=chat`, { method: "POST" });
    expect(refreshed.getState().sessions[sessionId]).toMatchObject({
      isChatStreaming: false, isStreaming: false, detachedChatRequestId: undefined,
    });
  });

  it("records the failed send when /agent responds with an error payload", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "chat");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "chat" } })
      .mockResolvedValueOnce({
        error: { code: "upstream_error", message: "模型接口 500" },
        session: { sessionId, sessionKind: "chat" },
      });

    await store.getState().sendMessage(sessionId, "你好");

    expect(store.getState().sessions[sessionId]?.lastFailedSend).toMatchObject({ text: "你好" });
  });

  it.each([false, true])("settles a failed request after an earlier tool error, with background work=%s", async (background) => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "chat");
    store.getState().setSelectedModel("fixture-model", "custom:fixture");
    let rejectAgent!: (error: Error) => void;
    fetchJson.mockResolvedValueOnce({ session: { sessionId, sessionKind: "chat" } })
      .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectAgent = reject; }));
    const sent = store.getState().sendMessage(sessionId, "Continue the work");
    await vi.waitFor(() => expect(rejectAgent).toBeTypeOf("function"));
    const events = fakeEventSources.at(-1)!;
    if (background) events.emit("tool:start", {
      sessionId, id: "background-task", tool: "short_fiction_run", background: true, sourceRequestId: "other-request",
    });
    events.emit("tool:start", { sessionId, id: "earlier-worker", tool: "review_work_artifact" });
    events.emit("tool:end", { sessionId, id: "earlier-worker", tool: "review_work_artifact", isError: true, result: { code: "WORKER_RESULT_INVALID" } });
    events.emit("context:compression", { sessionId, category: "session_context", phase: "start" });
    rejectAgent(Object.assign(new Error("Request timed out"), { payload: { error: { code: "upstream_error" }, session: { sessionId, sessionKind: "chat" } } }));
    await sent;
    const runtime = store.getState().sessions[sessionId]!;
    expect(runtime.lastFailedSend).toMatchObject({ text: "Continue the work" });
    expect(runtime.isChatStreaming).toBe(false);
    expect(runtime.isStreaming).toBe(background);
    const executions = runtime.messages.flatMap(message => message.toolExecutions ?? []);
    expect(executions.find(item => item.id === "earlier-worker")?.status).toBe("error");
    expect(executions.find(item => item.id === "context-session_context")?.status).toBe("error");
    expect(executions.filter(item => item.status === "running").map(item => item.id)).toEqual(background ? ["background-task"] : []);
    expect(fakeEventSources.at(-1)!.closed).toBe(!background);
  });

  it("retains the host target after an HTTP failure and retries against the created Work", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession("parent", "book");
    store.getState().setSelectedModel("fixture-model", "custom:fixture");
    fetchJson.mockResolvedValueOnce({ session: { sessionId, bookId: "parent", sessionKind: "book" } })
      .mockRejectedValueOnce(Object.assign(new Error("Continuation failed"), { payload: {
        session: { sessionId, bookId: null, workId: "child", profileId: "script", sessionKind: "work" },
      } }));
    await store.getState().sendMessage(sessionId, "Create a derived script and export", { activeBookId: "parent", sessionKind: "book" });
    expect(store.getState().sessions[sessionId]).toMatchObject({ bookId: null, workId: "child", profileId: "script", sessionKind: "work" });
    expect(store.getState().sessions[sessionId]?.pendingWorkTarget).toEqual({ workId: "child", profileId: "script", fromWorkId: "parent" });
    fetchJson.mockResolvedValueOnce({ response: "Exported", session: { sessionId, bookId: null, workId: "child", profileId: "script", sessionKind: "work" } });
    await store.getState().retryLastSend(sessionId);
    const sent = fetchJson.mock.calls.filter(([path]) => path === "/agent").map(([, init]) => JSON.parse(init.body));
    expect(sent).toHaveLength(2);
    expect(sent[1]).toMatchObject({ workId: "child", profileId: "script", sessionKind: "work" });
    expect(sent[1].activeBookId).toBeUndefined();
  });

  it("retries the last failed send with identical business parameters and a fresh request id", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession("demo-book", "book");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: "demo-book", sessionKind: "book" } })
      .mockRejectedValueOnce(new Error("Request timed out"))
      .mockResolvedValueOnce({ response: "ok", session: { sessionId, sessionKind: "book" } });

    await store.getState().sendMessage(sessionId, "写下一章", {
      sessionKind: "book",
      requestedSkills: ["style-guard"],
    });

    await store.getState().retryLastSend(sessionId);

    const agentCalls = fetchJson.mock.calls.filter(([path]) => path === "/agent");
    expect(agentCalls).toHaveLength(2);
    const firstBody = JSON.parse((agentCalls[0]?.[1] as { body: string }).body);
    const retryBody = JSON.parse((agentCalls[1]?.[1] as { body: string }).body);
    expect(retryBody.clientRequestId).toEqual(expect.any(String));
    expect(retryBody.clientRequestId).not.toBe(firstBody.clientRequestId);
    const { clientRequestId: firstRequestId, ...firstBusinessParams } = firstBody;
    const { clientRequestId: retryRequestId, retryOfRequestId, ...retryBusinessParams } = retryBody;
    expect(retryOfRequestId).toBe(firstBody.clientRequestId);
    expect(firstRequestId).toEqual(expect.any(String));
    expect(retryRequestId).toEqual(expect.any(String));
    expect(retryBusinessParams).toEqual(firstBusinessParams);
    expect(store.getState().sessions[sessionId]?.lastFailedSend).toBeUndefined();
  });

  it("keeps no failed-send record after a successful round", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "chat");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "chat" } })
      .mockResolvedValueOnce({ response: "你好！", session: { sessionId, sessionKind: "chat" } });

    await store.getState().sendMessage(sessionId, "你好");

    expect(store.getState().sessions[sessionId]?.lastFailedSend).toBeUndefined();
  });

  it("does not record a failed send when the user stops the round themselves", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "chat");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");

    let rejectAgent!: (error: Error) => void;
    fetchJson
      .mockResolvedValueOnce({ session: { sessionId, bookId: null, sessionKind: "chat" } })
      .mockImplementationOnce(() => new Promise((_resolve, reject) => {
        rejectAgent = reject;
      }))
      .mockResolvedValueOnce({});

    const sent = store.getState().sendMessage(sessionId, "你好");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(1));

    await store.getState().abortSession(sessionId);
    rejectAgent(new Error("This operation was aborted"));
    await sent;

    expect(store.getState().sessions[sessionId]?.lastFailedSend).toBeUndefined();
  });

  it("does nothing when retryLastSend is called without a failed-send record", async () => {
    const store = createTestStore();
    const sessionId = store.getState().createDraftSession(null, "chat");
    store.getState().setSelectedModel("deepseek-v4-flash", "kkaiapi");
    fetchJson.mockClear();

    await store.getState().retryLastSend(sessionId);

    expect(fetchJson).not.toHaveBeenCalled();
  });

  it("routes task-tagged context compression to the task card and never into the chat stream", async () => {
    const store = createTestStore();
    const sessionId = await setupRunningTaskSession(store);

    let resolveAgent!: (value: unknown) => void;
    fetchJson.mockClear();
    fetchJson.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAgent = resolve;
    }));
    const sent = store.getState().sendMessage(sessionId, "顺便聊两句");
    await vi.waitFor(() => expect(fakeEventSources).toHaveLength(2));

    const allExecutions = () => (store.getState().sessions[sessionId]?.messages ?? [])
      .flatMap((message) => [
        ...(message.toolExecutions ?? []),
        ...(message.parts ?? []).flatMap((part) => (part.type === "tool" ? [part.execution] : [])),
      ]);

    // 任务 pipeline 的压缩事件带任务 execution id：作为阶段挂到任务卡上
    fakeEventSources[1]?.emit("context:compression", {
      sessionId,
      executionId: "direct-short_run-1",
      category: "story_context",
      phase: "start",
      protectedTokens: 1200,
    });
    expect(findTaskExecution(store, sessionId)?.stages).toEqual([
      expect.objectContaining({ label: "压缩故事上下文", status: "active" }),
    ]);
    // 不产生聊天流内容：没有 context-* 伪工具卡被写进消息
    expect(allExecutions().some((execution) => execution.id.startsWith("context-"))).toBe(false);

    fakeEventSources[1]?.emit("context:compression", {
      sessionId,
      executionId: "direct-short_run-1",
      category: "story_context",
      phase: "end",
    });
    expect(findTaskExecution(store, sessionId)?.stages).toEqual([
      expect.objectContaining({ label: "压缩故事上下文", status: "completed" }),
    ]);

    // id 指向的卡不存在：事件丢弃，同样不写进聊天流
    fakeEventSources[1]?.emit("context:compression", {
      sessionId,
      executionId: "direct-unknown-9",
      category: "session_context",
      phase: "start",
    });
    expect(allExecutions().some((execution) => execution.id.startsWith("context-"))).toBe(false);

    resolveAgent({ response: "聊完了。", session: { sessionId, sessionKind: "short" } });
    await sent;
  });
});
