import { createAssistantMessageEventStream } from "@mariozechner/pi-ai";
import type { Model } from "@mariozechner/pi-ai";
import { afterEach, describe, expect, it } from "vitest";
import { guardAssistantMessageStream } from "../llm/provider.js";

const MODEL = {
  id: "slow-model",
  name: "slow-model",
  api: "openai-completions",
  provider: "openai",
  baseUrl: "https://example.invalid/v1",
  reasoning: false,
  input: ["text"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 128_000,
  maxTokens: 4096,
} satisfies Model<"openai-completions">;

describe("guardAssistantMessageStream", () => {
  it("does not let empty transport deltas keep a stalled stream alive", async () => {
    let attempts = 0;
    const guarded = guardAssistantMessageStream(MODEL, signal => {
      attempts++;
      const stream = createAssistantMessageEventStream();
      const partial = {role:'assistant' as const,api:MODEL.api,provider:MODEL.provider,model:MODEL.id,content:[],
        usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop' as const,timestamp:Date.now()};
      stream.push({type:'start',partial});
      const heartbeat = setInterval(()=>stream.push({type:'text_delta',contentIndex:0,delta:'',partial}),2);
      signal.addEventListener('abort',()=>{clearInterval(heartbeat);stream.end();},{once:true});
      return stream;
    },undefined,{firstEventTimeoutMs:20,idleTimeoutMs:20});
    expect((await guarded.result()).stopReason).toBe('error');
    expect(attempts).toBe(1);
  });
  it("removes executable tool calls when a streamed response reaches the output limit", async () => {
    const guarded = guardAssistantMessageStream(MODEL, () => {
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "done", reason: "length", message: {
        role: "assistant", api: MODEL.api, provider: MODEL.provider, model: MODEL.id,
        content: [{ type: "toolCall", id: "partial", name: "submit_short_outline", arguments: { planMarkdown: "Partial" } }],
        usage: { input: 0, output: 8, cacheRead: 0, cacheWrite: 0, totalTokens: 8, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        stopReason: "length", timestamp: Date.now(),
      } });
      return stream;
    });
    const result = await guarded.result();
    expect(result.stopReason).toBe("length");
    expect(result.content.some(part => part.type === "toolCall")).toBe(false);
  });
  it("retries HTTP 503 before visible output but preserves a failure after partial output", async () => {
    async function run(partial: boolean) {
      let attempts = 0;
      const guarded = guardAssistantMessageStream(MODEL, () => {
        attempts++;
        const stream = createAssistantMessageEventStream();
        const message = {
          role:"assistant" as const,content:[],api:MODEL.api,provider:MODEL.provider,model:MODEL.id,
          usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},
          stopReason:"error" as const,errorMessage:"HTTP 503",timestamp:Date.now(),
        };
        if (attempts === 1) {
          if(partial) stream.push({type:"text_delta",contentIndex:0,delta:"x",partial:message});
          stream.push({type:"error",reason:"error",error:message});
        } else stream.push({type:"done",reason:"stop",message:{...message,stopReason:"stop"}});
        return stream;
      });
      const events=[];for await(const event of guarded)events.push(event);
      return {attempts,events:events.map((event)=>event.type)};
    }
    expect(await run(false)).toEqual({attempts:2,events:["done"]});
    expect(await run(true)).toEqual({attempts:1,events:["text_delta","error"]});
  });
  afterEach(() => {
    delete process.env.INKOS_LLM_FIRST_EVENT_TIMEOUT_MS;
    delete process.env.INKOS_LLM_STREAM_IDLE_TIMEOUT_MS;
  });

  it("ends a stream that never produces its first event", async () => {
    let attempts = 0;
    const guarded = guardAssistantMessageStream(
      MODEL,
      () => {
        attempts += 1;
        return createAssistantMessageEventStream();
      },
      undefined,
      { firstEventTimeoutMs: 10 },
    );

    const events = [];
    for await (const event of guarded) events.push(event);

    expect(events).toHaveLength(1);
    expect(attempts).toBe(1);
    expect(events[0]).toMatchObject({
      type: "error",
      reason: "error",
      error: {
        stopReason: "error",
        errorMessage: "LLM stream produced no event within 10ms",
      },
    });
  });

  it("keeps environment overrides authoritative", async () => {
    process.env.INKOS_LLM_FIRST_EVENT_TIMEOUT_MS = "10";
    const guarded = guardAssistantMessageStream(
      MODEL,
      () => createAssistantMessageEventStream(),
      undefined,
      { firstEventTimeoutMs: 60_000 },
    );

    const events = [];
    for await (const event of guarded) events.push(event);

    expect(events[0]).toMatchObject({
      type: "error",
      error: { errorMessage: "LLM stream produced no event within 10ms" },
    });
  });
});
