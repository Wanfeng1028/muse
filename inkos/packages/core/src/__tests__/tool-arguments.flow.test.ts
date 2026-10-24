import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Agent } from "@mariozechner/pi-agent-core";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@mariozechner/pi-ai";
import { expect, it } from "vitest";
import { preserveToolArgumentTypes } from "../agent/tool-arguments.js";
import { createAddVariableTool, createConnectChoiceTool, createSetWorldAnchorTool } from "../agent/film-authoring-tools.js";
import { createLLMClient } from "../llm/provider.js";
import { loadStoryGraph } from "../interactive-film/graph-store.js";
import { initVarState, applyEffects, visibleChoices } from "../interactive-film/evaluator.js";

it("persists original scalar types through Pi and rejects coercible invalid input before mutation", async () => {
  const root = await mkdtemp(join(tmpdir(), "inkos-tool-arguments-"));
  try {
    const values = [true, false, 1, 0, "1", "0"];
    const node = {
      id: "opening", title: "Opening", type: "start", act: "one",
      sceneDesc: "A door opens.", dialogue: [],
      choices: [{
        id: "enter", text: "Enter", targetNodeId: "opening",
        condition: { var: "v1", op: "==", value: false },
        effects: [{ var: "v1", op: "set", value: true }],
      }],
    };
    const calls: ToolCall[] = values.map((value, index) => ({
      type: "toolCall", id: "variable-" + index, name: "add_variable",
      arguments: { name: "v" + index, type: "story-value", default: value },
    }));
    calls.push({ type: "toolCall", id: "node", name: "connect_choice", arguments: { node } });
    calls.push({ type: "toolCall", id: "invalid", name: "set_world_anchor", arguments: { durationMinutes: "12" } });
    const client = createLLMClient({
      service: "custom", provider: "openai", configSource: "studio", model: "fixture",
      baseUrl: "https://example.invalid/v1", apiKey: "fixture", apiFormat: "chat",
      temperature: 0, stream: true, thinkingBudget: 0,
    });
    let turns = 0;
    const agent = new Agent({
      initialState: { model: client._piModel!, tools: [
        createAddVariableTool(root, "film"), createConnectChoiceTool(root, "film"),
        createSetWorldAnchorTool(root, "film"),
      ] },
      beforeToolCall: preserveToolArgumentTypes,
      toolExecution: "sequential",
      streamFn: (model) => {
        const stream = createAssistantMessageEventStream();
        const first = turns++ === 0;
        const message: AssistantMessage = {
          role: "assistant", content: first ? calls : [], model: model.id,
          api: model.api, provider: model.provider, timestamp: Date.now(),
          stopReason: first ? "toolUse" : "stop",
          usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        };
        stream.push({ type: "done", reason: first ? "toolUse" : "stop", message });
        stream.end(message);
        return stream;
      },
    });
    await agent.prompt("Apply the supplied fixture changes.");
    const graph = (await loadStoryGraph(root, "film"))!;
    expect(graph.variables.map(variable => variable.default)).toEqual(values);
    expect(graph.nodes[0]?.choices).toEqual(node.choices);
    const state = initVarState(graph.variables);
    expect(visibleChoices(graph.nodes[0]!, state).map(choice => choice.id)).toEqual(["enter"]);
    expect(visibleChoices(graph.nodes[0]!, applyEffects(state, graph.nodes[0]!.choices[0]!.effects))).toEqual([]);
    const results = agent.state.messages.filter(message => message.role === "toolResult");
    expect(results.filter(result => result.isError)).toHaveLength(1);
    const failure = results.find(result => result.toolCallId === "invalid")!;
    expect(JSON.parse(failure.content.filter(part => part.type === "text").map(part => part.text).join("")))
      .toMatchObject({ code: "TOOL_SCHEMA_INVALID", issues: [{ path: "/durationMinutes" }] });
    expect(graph.worldAnchor).toBeUndefined();
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
