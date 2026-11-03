import { describe, it, expect } from "vitest";
import { visibleRecipients, validateVisibility, makeEnvelope, parseEnvelope, validateEnvelope } from "../src/index.js";
import type { MessagePayload } from "../src/index.js";

describe("visibleRecipients", () => {
  it("undefined visibility => null (room routing)", () => {
    expect(visibleRecipients("a", undefined, undefined)).toBeNull();
  });
  it("direct => sender + single target", () => {
    expect(visibleRecipients("a", "direct", ["b"])).toEqual(new Set(["a", "b"]));
  });
  it("restricted => sender + all listed", () => {
    expect(visibleRecipients("a", "restricted", ["b", "c"])).toEqual(new Set(["a", "b", "c"]));
  });
});

describe("validateVisibility", () => {
  it("accepts direct with exactly 1 and restricted with 2", () => {
    expect(validateVisibility("direct", ["b"])).toEqual([]);
    expect(validateVisibility("restricted", ["b", "c"])).toEqual([]);
  });
  it("rejects visible_to without visibility", () => {
    expect(validateVisibility(undefined, ["b"])).toContain(
      "visible_to: only allowed when visibility is 'direct' or 'restricted'",
    );
  });
  it("rejects bad visibility value", () => {
    expect(validateVisibility("public", ["b"])).toContain("visibility: must be 'direct' or 'restricted'");
  });
  it("rejects direct with 0 or 2 recipients", () => {
    expect(validateVisibility("direct", [])).toContain(
      "visible_to: must contain exactly 1 recipient when visibility is 'direct'",
    );
    expect(validateVisibility("direct", ["b", "c"])).toContain(
      "visible_to: must contain exactly 1 recipient when visibility is 'direct'",
    );
  });
  it("rejects restricted with empty list, empty item, overlong item, duplicates", () => {
    expect(validateVisibility("restricted", [])).toContain(
      "visible_to: must contain at least 1 recipient when visibility is 'restricted'",
    );
    expect(validateVisibility("restricted", [""])).toContain(
      "visible_to[0]: must be a non-empty string of at most 64 chars",
    );
    expect(validateVisibility("restricted", ["x".repeat(65)])).toContain(
      "visible_to[0]: must be a non-empty string of at most 64 chars",
    );
    expect(validateVisibility("restricted", ["b", "b"])).toContain("visible_to: duplicate recipient 'b'");
  });
});

describe("envelope visibility codec", () => {
  it("makeEnvelope carries visibility/visible_to and validates clean", () => {
    const env = makeEnvelope<MessagePayload>(
      "message", "a", "r", 1, 0, { msg_id: "m1", text: "hi", mentions: [] },
      1, { visibility: "direct", visible_to: ["b"] },
    );
    expect(env.visibility).toBe("direct");
    expect(validateEnvelope(parseEnvelope(JSON.stringify(env)))).toEqual([]);
  });
  it("invalid direct combo fails validateEnvelope", () => {
    const env = makeEnvelope<MessagePayload>(
      "message", "a", "r", 1, 0, { msg_id: "m1", text: "hi", mentions: [] },
      1, { visibility: "direct", visible_to: ["b", "c"] },
    );
    expect(validateEnvelope(parseEnvelope(JSON.stringify(env)))).toContain(
      "visible_to: must contain exactly 1 recipient when visibility is 'direct'",
    );
  });
});
