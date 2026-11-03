import { describe, it, expect } from "vitest";
import { makeEnvelope, parseEnvelope, validateEnvelope } from "../src/codec.js";
import type { MessagePayload } from "../src/types.js";

function msg(payload: Partial<MessagePayload>) {
  const env = makeEnvelope<MessagePayload>("message", "a", "r", 1, 0, { msg_id: "m1", text: "hi", mentions: [], ...payload });
  return JSON.stringify(env);
}

describe("thread codec", () => {
  it("accepts reply_to + thread_id", () => {
    expect(validateEnvelope(parseEnvelope(msg({ reply_to: "m0", thread_id: "m0" })))).toEqual([]);
  });
  it("rejects empty reply_to", () => {
    expect(validateEnvelope(parseEnvelope(msg({ reply_to: "" })))).toContain(
      "payload.reply_to: must be a non-empty string of at most 128 chars",
    );
  });
  it("rejects reply_to over 128 chars", () => {
    expect(validateEnvelope(parseEnvelope(msg({ reply_to: "x".repeat(129) })))).toContain(
      "payload.reply_to: must be a non-empty string of at most 128 chars",
    );
  });
  it("rejects self-reply", () => {
    expect(validateEnvelope(parseEnvelope(msg({ reply_to: "m1" })))).toContain(
      "payload.reply_to: must not equal msg_id",
    );
  });
  it("rejects thread_id over 128 chars", () => {
    expect(validateEnvelope(parseEnvelope(msg({ thread_id: "x".repeat(129) })))).toContain(
      "payload.thread_id: must be a non-empty string of at most 128 chars",
    );
  });
});
