import { describe, expect, it } from "vitest";
import { summarizeToolResult } from "./tool-result";

describe("summarizeToolResult", () => {
  it("reads Pi text content blocks", () => {
    expect(summarizeToolResult({ content: [{ type: "text", text: "This operation was aborted" }] }))
      .toBe("This operation was aborted");
  });

  it("falls back to JSON for structured results", () => {
    expect(summarizeToolResult({ status: "cancelled", resumeCursor: "2" }))
      .toBe('{"status":"cancelled","resumeCursor":"2"}');
  });
  it("renders the model observation's display content without treating nested source JSON as another envelope", () => {
    const source = JSON.stringify({ status: "success", summary: "source", artifacts: [], observations: [], facts: {} });
    const observation = { status: "success", summary: "Read", content: source, artifacts: [], observations: [], facts: { kind: "artifact_read" } };
    expect(summarizeToolResult({ content: [{ type: "text", text: JSON.stringify(observation) }] })).toBe(source);
    expect(summarizeToolResult({ content: [{ type: "text", text: JSON.stringify(observation) }], details: { displayText: source } })).toBe(source);
  });
});
