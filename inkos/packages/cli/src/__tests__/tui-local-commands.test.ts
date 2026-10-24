import { describe, expect, it } from "vitest";
import { classifyLocalTuiCommand, parseDepthCommand, parseModelCommand } from "../tui/local-commands.js";

describe("TUI slash-command protocol", () => {
  it("keeps host commands explicit and leaves free text to Pi", () => {
    expect([
      classifyLocalTuiCommand("/help"),
      classifyLocalTuiCommand("/status"),
      classifyLocalTuiCommand("/clear"),
      classifyLocalTuiCommand("/config"),
      classifyLocalTuiCommand("/quit"),
    ]).toEqual(["help", "status", "clear", "config", "quit"]);
    expect(["help", "状态", "bye", "配置", "continue current book"]
      .map(classifyLocalTuiCommand)).toEqual([undefined, undefined, undefined, undefined, undefined]);
  });

  it("parses only explicit depth and model commands", () => {
    expect([
      parseDepthCommand("/depth deep"),
      parseDepthCommand("/深度 轻量"),
      parseDepthCommand("depth light"),
    ]).toEqual(["deep", "light", undefined]);
    expect(parseModelCommand("/model gemini-3.1-pro-preview"))
      .toEqual({ kind: "set", model: "gemini-3.1-pro-preview" });
    expect(parseModelCommand("我们讨论一下模型选择")).toBeUndefined();
  });
});
