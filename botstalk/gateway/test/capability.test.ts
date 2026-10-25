import { describe, it, expect } from "vitest";
import {
  normalizeLocalAdapter,
  matchStructured,
  scoreCapability,
  pickBestCandidate,
} from "../src/capability.js";
import {
  buildLlmMatchingPrompt,
  parseLlmMatchingResponse,
} from "../src/capability-llm.js";

describe("normalizeLocalAdapter", () => {
  it("defaults empty input_modes/output_modes to ['text']", () => {
    const result = normalizeLocalAdapter("agent1", { skills: ["a"], tags: ["b"] });
    expect(result.input_modes).toEqual(["text"]);
    expect(result.output_modes).toEqual(["text"]);
  });

  it("deduplicates skills/tags preserving order and removes empty strings", () => {
    const result = normalizeLocalAdapter("agent1", {
      skills: ["a", "b", "a", "", "c"],
      tags: ["x", "y", "x", "", "z"],
      input_modes: ["text"],
      output_modes: ["text"],
    });
    expect(result.skills).toEqual(["a", "b", "c"]);
    expect(result.tags).toEqual(["x", "y", "z"]);
  });

  it("passes through description and raw as raw_capabilities", () => {
    const result = normalizeLocalAdapter("agent1", {
      skills: ["a"],
      tags: [],
      description: "test desc",
      raw: { foo: "bar" },
    });
    expect(result.description).toBe("test desc");
    expect(result.raw_capabilities).toEqual({ foo: "bar" });
  });

  it("sets agent_id and agent_type to local", () => {
    const result = normalizeLocalAdapter("agent1", { skills: ["a"] });
    expect(result.agent_id).toBe("agent1");
    expect(result.agent_type).toBe("local");
  });
});

describe("matchStructured", () => {
  it("returns true when all required skills are present", () => {
    const required = { skills: ["a", "b"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a", "b", "c"] });
    expect(matchStructured(required, normalized)).toBe(true);
  });

  it("returns false when a required skill is missing", () => {
    const required = { skills: ["a", "b"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a"] });
    expect(matchStructured(required, normalized)).toBe(false);
  });

  it("returns true when all required tags are present", () => {
    const required = { tags: ["x", "y"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a"], tags: ["x", "y", "z"] });
    expect(matchStructured(required, normalized)).toBe(true);
  });

  it("returns false when a required input_mode is missing", () => {
    const required = { input_modes: ["voice"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a"], input_modes: ["text"] });
    expect(matchStructured(required, normalized)).toBe(false);
  });

  it("returns true when required is all empty", () => {
    const required = {};
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a"] });
    expect(matchStructured(required, normalized)).toBe(true);
  });

  it("is case sensitive: 'Code' !== 'code'", () => {
    const required = { skills: ["Code"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["code"] });
    expect(matchStructured(required, normalized)).toBe(false);
  });
});

describe("scoreCapability", () => {
  it("single skills dimension all match → score 1", () => {
    const required = { skills: ["a", "b"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a", "b", "c"] });
    const result = scoreCapability(required, normalized);
    expect(result.score).toBe(1);
    expect(result.breakdown.skills).toBe(1);
  });

  it("skills 2 match 1 → skills breakdown 0.5", () => {
    const required = { skills: ["a", "b"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a", "c"] });
    const result = scoreCapability(required, normalized);
    expect(result.breakdown.skills).toBeCloseTo(0.5, 3);
  });

  it("skills 2 match 1 + tags all match → score ≈ 0.6667", () => {
    const required = { skills: ["a", "b"], tags: ["x"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a", "c"], tags: ["x"] });
    const result = scoreCapability(required, normalized);
    expect(result.score).toBeCloseTo(0.6667, 3);
  });

  it("required all empty → score 0 and breakdown all 0", () => {
    const required = {};
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a"] });
    const result = scoreCapability(required, normalized);
    expect(result.score).toBe(0);
    expect(result.breakdown.skills).toBe(0);
    expect(result.breakdown.tags).toBe(0);
    expect(result.breakdown.input_modes).toBe(0);
    expect(result.breakdown.output_modes).toBe(0);
  });

  it("matched/missing only contain skills+tags preserving order with dedup", () => {
    const required = { skills: ["a", "b", "c"], tags: ["x", "y"] };
    const normalized = normalizeLocalAdapter("agent1", { skills: ["a", "c"], tags: ["x"] });
    const result = scoreCapability(required, normalized);
    expect(result.matched).toEqual(["a", "c", "x"]);
    expect(result.missing).toEqual(["b", "y"]);
  });
});

describe("pickBestCandidate", () => {
  it("highest score wins", () => {
    const required = { skills: ["a"] };
    const n1 = normalizeLocalAdapter("agent1", { skills: ["a", "b"] });
    const n2 = normalizeLocalAdapter("agent2", { skills: ["c"] });
    const result = pickBestCandidate(
      [
        { id: "agent1", capability: n1 },
        { id: "agent2", capability: n2 },
      ],
      required
    );
    expect(result.pick).toBe("agent1");
    expect(result.bestScore).toBeGreaterThan(0);
  });

  it("tie → lexicographically smallest id wins", () => {
    const required = { skills: ["a"] };
    const n1 = normalizeLocalAdapter("b_agent", { skills: ["a"] });
    const n2 = normalizeLocalAdapter("a_agent", { skills: ["a"] });
    const result = pickBestCandidate(
      [
        { id: "b_agent", capability: n1 },
        { id: "a_agent", capability: n2 },
      ],
      required
    );
    expect(result.pick).toBe("a_agent");
  });

  it("all 0 score → pick is null", () => {
    const required = { skills: ["x"] };
    const n1 = normalizeLocalAdapter("agent1", { skills: ["a"] });
    const n2 = normalizeLocalAdapter("agent2", { skills: ["b"] });
    const result = pickBestCandidate(
      [
        { id: "agent1", capability: n1 },
        { id: "agent2", capability: n2 },
      ],
      required
    );
    expect(result.pick).toBeNull();
  });

  it("empty candidates → pick null and bestScore 0", () => {
    const result = pickBestCandidate([], { skills: ["a"] });
    expect(result.pick).toBeNull();
    expect(result.bestScore).toBe(0);
  });
});

describe("buildLlmMatchingPrompt", () => {
  it("output contains task description, agent id, JSON capabilities, and confidence >= 0.5", () => {
    const caps = { skills: ["translation"], tags: ["nlp"] };
    const prompt = buildLlmMatchingPrompt("translate text", "agent-42", caps);
    expect(prompt).toContain("translate text");
    expect(prompt).toContain("agent-42");
    expect(prompt).toContain("translation");
    expect(prompt).toContain("nlp");
    expect(prompt).toContain("confidence >= 0.5");
  });
});

describe("parseLlmMatchingResponse", () => {
  it("parses normal JSON correctly", () => {
    const result = parseLlmMatchingResponse(
      JSON.stringify({ matches: true, confidence: 0.9, reason: "good match" })
    );
    expect(result.matches).toBe(true);
    expect(result.confidence).toBe(0.9);
    expect(result.reason).toBe("good match");
  });

  it("parses fenced JSON correctly", () => {
    const json = JSON.stringify({ matches: false, confidence: 0.3, reason: "weak" });
    const result = parseLlmMatchingResponse("```json\n" + json + "\n```");
    expect(result.matches).toBe(false);
    expect(result.confidence).toBe(0.3);
    expect(result.reason).toBe("weak");
  });

  it("missing fields → matches false, confidence 0.5, reason empty string", () => {
    const result = parseLlmMatchingResponse(JSON.stringify({}));
    expect(result.matches).toBe(false);
    expect(result.confidence).toBe(0.5);
    expect(result.reason).toBe("");
  });

  it("invalid JSON → matches false, confidence 0, reason 'Failed to parse LLM response'", () => {
    const result = parseLlmMatchingResponse("this is not json");
    expect(result.matches).toBe(false);
    expect(result.confidence).toBe(0);
    expect(result.reason).toBe("Failed to parse LLM response");
  });
});
