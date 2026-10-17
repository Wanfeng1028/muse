import { describe, it, expect } from "vitest";
import { validateGameAction } from "../src/types";

describe("validateGameAction", () => {
  it("accepts a full valid payload", () => {
    expect(validateGameAction({ game: "who_is_undercover", seat: "1", action: { vote: "2" } })).toEqual([]);
  });

  it("accepts a minimal valid payload", () => {
    expect(validateGameAction({ game: "x" })).toEqual([]);
  });

  it("rejects an empty game string", () => {
    expect(validateGameAction({ game: "" }).length).toBeGreaterThan(0);
  });

  it("rejects a missing game field", () => {
    expect(validateGameAction({}).length).toBeGreaterThan(0);
  });

  it("rejects a non-string game field", () => {
    expect(validateGameAction({ game: 123 }).length).toBeGreaterThan(0);
  });

  it("rejects a non-string seat field", () => {
    expect(validateGameAction({ game: "x", seat: 1 }).length).toBeGreaterThan(0);
  });

  it("rejects a non-object payload", () => {
    expect(validateGameAction("nope").length).toBeGreaterThan(0);
  });

  it("rejects a null payload", () => {
    expect(validateGameAction(null).length).toBeGreaterThan(0);
  });
});
