import { describe, expect, it } from "vitest";
import {
  ActionPayloadSchema,
  ActionSourceSchema,
  ExecutionStatusSchema,
  InteractionSessionSchema,
  PlayModeSchema,
  RequestedIntentSchema,
  InteractiveFilmCreateActionPayloadSchema,
  FanficCreateActionPayloadSchema,
  ContinuationImportActionPayloadSchema,
  SpinoffCreateActionPayloadSchema,
  ImitationCreateActionPayloadSchema,
  ScriptCreateActionPayloadSchema,
  ScriptTargetFormatSchema,
  SessionKindSchema,
  StoryboardCreateActionPayloadSchema,
  bindActiveBook,
  isTerminalExecutionStatus,
  normalizeActionSource,
  normalizePlayMode,
  normalizeRequestedIntent,
  appendInteractionMessage,
} from "../index.js";

describe("interaction models", () => {
  it("parses Studio/agent action envelope fields from one shared schema", () => {
    expect(ActionSourceSchema.parse("free-text")).toBe("free-text");
    expect(ActionSourceSchema.parse("button")).toBe("button");
    expect(RequestedIntentSchema.parse("create_book")).toBe("create_book");
    expect(RequestedIntentSchema.parse("play_start")).toBe("play_start");
    expect(RequestedIntentSchema.parse("script_create")).toBe("script_create");
    expect(RequestedIntentSchema.parse("storyboard_create")).toBe("storyboard_create");
    expect(RequestedIntentSchema.parse("interactive_film_create")).toBe("interactive_film_create");
    expect(RequestedIntentSchema.parse("fanfic_init")).toBe("fanfic_init");
    expect(RequestedIntentSchema.parse("style_imitation")).toBe("style_imitation");
    expect(SessionKindSchema.parse("script")).toBe("script");
    expect(SessionKindSchema.parse("storyboard")).toBe("storyboard");
    expect(SessionKindSchema.parse("interactive-film")).toBe("interactive-film");
    expect(SessionKindSchema.parse("work")).toBe("work");
    expect(ScriptTargetFormatSchema.parse("vertical_short_drama")).toBe("vertical_short_drama");
    expect(ScriptTargetFormatSchema.parse("舞台剧分场本")).toBe("舞台剧分场本");
    expect(PlayModeSchema.parse("guided")).toBe("guided");

    expect(normalizeActionSource(undefined)).toBe("free-text");
    expect(normalizeActionSource("slash")).toBe("slash");
    expect(normalizeRequestedIntent("short_run")).toBe("short_run");
    expect(normalizeRequestedIntent("")).toBeUndefined();
    expect(normalizePlayMode("open")).toBe("open");
    expect(normalizePlayMode(null)).toBeUndefined();

    expect(ActionPayloadSchema.parse({
      writeNext: { chapterCount: 21 },
    })).toEqual({
      writeNext: { chapterCount: 21 },
    });
  });

  it("validates structured script and storyboard creation payloads", () => {
    expect(ScriptCreateActionPayloadSchema.parse({
      title: "冷库账页",
      targetFormat: "vertical_short_drama",
      episodeCount: 12,
      episodeDuration: "2分钟",
      requirements: "保留调查线七成、家怨三成。",
    })).toMatchObject({
      title: "冷库账页",
      targetFormat: "vertical_short_drama",
      episodeCount: 12,
    });

    expect(StoryboardCreateActionPayloadSchema.parse({
      title: "冷库账页分镜",
      visualStyle: "写实冷色",
      aspectRatio: "9:16",
      granularity: "按关键镜头拆分",
      maxShots: 18,
    })).toMatchObject({
      title: "冷库账页分镜",
      visualStyle: "写实冷色",
      maxShots: 18,
    });

    expect(InteractiveFilmCreateActionPayloadSchema.parse({
      title: "盛世账页",
      requirements: "多分支，多结局，变量记录关键抉择。",
      targetAudience: "欧美互动影游用户",
      budget: "5000元",
      referenceMode: "盛世天下式多走向",
    })).toMatchObject({
      title: "盛世账页",
      budget: "5000元",
    });
  });

  it("validates derivative-work payloads without magic routes", () => {
    expect(FanficCreateActionPayloadSchema.parse({
      title: "霜港来信",
      sourcePath: ".inkos/uploads/canon.pdf",
      mode: "canon",
    })).toMatchObject({ title: "霜港来信", mode: "canon" });
    expect(FanficCreateActionPayloadSchema.safeParse({ title: "缺少正典" }).success).toBe(false);

    expect(ContinuationImportActionPayloadSchema.parse({
      title: "雾港续章",
      sourcePath: ".inkos/uploads/novel.txt",
      instruction: "Keep the cabinet locked",
    })).toMatchObject({ title: "雾港续章", instruction: "Keep the cabinet locked" });
    expect(ContinuationImportActionPayloadSchema.safeParse({
      sourcePath: "novel.txt",
      targetRoute: "import:continuation",
    }).success).toBe(false);

    expect(SpinoffCreateActionPayloadSchema.parse({
      title: "雨夜番外",
      parentBookId: "harbor",
      direction: "老船工视角",
    })).toMatchObject({ parentBookId: "harbor" });

    expect(ImitationCreateActionPayloadSchema.parse({
      title: "纸灯新案",
      referenceText: "参考文风片段",
      storyIdea: "原创县城悬疑",
    })).toMatchObject({ storyIdea: "原创县城悬疑" });
    expect(ImitationCreateActionPayloadSchema.safeParse({
      title: "缺少参考",
      storyIdea: "原创故事",
    }).success).toBe(false);
  });

  it("recognizes terminal execution statuses", () => {
    expect(isTerminalExecutionStatus(ExecutionStatusSchema.parse("completed"))).toBe(true);
    expect(isTerminalExecutionStatus(ExecutionStatusSchema.parse("failed"))).toBe(true);
    expect(isTerminalExecutionStatus(ExecutionStatusSchema.parse("idle"))).toBe(false);
    expect(isTerminalExecutionStatus(ExecutionStatusSchema.parse("writing"))).toBe(false);
  });

  it("binds the active book without disturbing unrelated session fields", () => {
    const session = InteractionSessionSchema.parse({
      sessionId: "session-1",
      projectRoot: "/tmp/project",
      messages: [],
      currentExecution: {
        status: "waiting_human",
        bookId: "book-a",
        chapterNumber: 3,
        stageLabel: "waiting for approval",
      },
    });

    expect(bindActiveBook(session, "book-b")).toEqual({
      ...session,
      activeBookId: "book-b",
    });
  });

  it("persists TUI surface, model, and structured confirmation state", () => {
    const session = InteractionSessionSchema.parse({
      sessionId: "tui-session",
      projectRoot: "/tmp/project",
      sessionKind: "interactive-film",
      modelOverride: "deepseek-v4-pro",
      messages: [],
      pendingProposedAction: {
        action: "interactive_film_create",
        targetSessionKind: "interactive-film",
        instruction: "生成三幕互动影游",
        requestedSkills: ["interactive-film-authoring"],
        actionPayload: {
          interactiveFilmCreate: { title: "回声航线", episodeCount: 3 },
        },
      },
    });

    expect(session).toMatchObject({
      sessionKind: "interactive-film",
      modelOverride: "deepseek-v4-pro",
      pendingProposedAction: {
        action: "interactive_film_create",
        requestedSkills: ["interactive-film-authoring"],
      },
    });
  });

  it("appends interaction messages in timestamp order", () => {
    const session = InteractionSessionSchema.parse({
      sessionId: "session-3",
      projectRoot: "/tmp/project",
      messages: [],
    });

    const next = appendInteractionMessage(session, {
      role: "user",
      content: "continue",
      timestamp: 1,
    });

    expect(next.messages).toEqual([{
      role: "user",
      content: "continue",
      timestamp: 1,
    }]);
  });

  it("round-trips task execution metadata through the shared chat schema", () => {
    const session = InteractionSessionSchema.parse({
      sessionId: "session-task",
      projectRoot: "/tmp/project",
      messages: [{
        role: "assistant",
        content: "",
        timestamp: 2,
        toolExecutions: [{
          id: "task-1",
          tool: "longform__create_book",
          label: "Create long-form Work",
          status: "completed",
          logs: ["Creating foundation"],
          background: true,
          stages: [{
            label: "Foundation",
            status: "completed",
            progress: {
              status: "streaming",
              elapsedMs: 1200,
              totalChars: 1800,
              chineseChars: 1200,
            },
          }],
          startedAt: 1,
          completedAt: 2,
        }],
      }],
    });

    expect(session.messages[0]?.toolExecutions?.[0]).toMatchObject({
      logs: ["Creating foundation"],
      background: true,
      stages: [{ progress: { totalChars: 1800 } }],
    });
  });


});
