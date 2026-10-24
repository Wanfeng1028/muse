import { describe, expect, it } from "vitest";
import { turnHasObservableOutcome } from "../agent/agent-session.js";

describe("agent turn completion evidence", () => {
  it("requires text or a structured tool outcome", () => {
    expect({
      empty: turnHasObservableOutcome([
        { role: "assistant", content: [], stopReason: "stop" } as never,
      ]),
      text: turnHasObservableOutcome([
        { role: "assistant", content: [{ type: "text", text: "ready" }], stopReason: "stop" } as never,
      ]),
      tool: turnHasObservableOutcome([
        { role: "toolResult", toolCallId: "call-1", toolName: "write", content: [] } as never,
      ]),
    }).toEqual({ empty: false, text: true, tool: true });
  });
});
