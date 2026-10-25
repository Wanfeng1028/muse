import { describe, it, expect } from "vitest";
import { makeEnvelope, validateEnvelope } from "../src/index.js";
import type { MessagePayload, CapabilityUpdatePayload } from "../src/index.js";

describe("codec-capability", () => {
  it("capability_update with skills/tags has no errors", () => {
    const payload: CapabilityUpdatePayload = {
      version: 1,
      capabilities: {
        intents: ["task"],
        skills: ["code-review", "testing"],
        tags: ["v2"],
      },
    };
    const envelope = makeEnvelope("capability_update", "alice", "room1", 1, 0, payload);
    expect(validateEnvelope(envelope)).toEqual([]);
  });

  it("capability_update with non-string skills has at least 1 error", () => {
    const payload = {
      version: 1,
      capabilities: {
        intents: ["task"],
        skills: [123, true],
      },
    } as unknown as CapabilityUpdatePayload;
    const envelope = makeEnvelope("capability_update", "alice", "room1", 2, 0, payload);
    expect(validateEnvelope(envelope).length).toBeGreaterThanOrEqual(1);
  });

  it("message with intent=task and required_capabilities has no errors", () => {
    const payload: MessagePayload = {
      msg_id: "m1",
      text: "test",
      mentions: [],
      intent: "task",
      task_id: "t1",
      required_capabilities: { skills: ["code-review"] },
    };
    const envelope = makeEnvelope("message", "alice", "room1", 3, 0, payload);
    expect(validateEnvelope(envelope)).toEqual([]);
  });

  it("required_capabilities.skills with non-string has at least 1 error", () => {
    const payload = {
      msg_id: "m1",
      text: "test",
      mentions: [],
      intent: "task",
      task_id: "t1",
      required_capabilities: { skills: [42] },
    } as unknown as MessagePayload;
    const envelope = makeEnvelope("message", "alice", "room1", 4, 0, payload);
    expect(validateEnvelope(envelope).length).toBeGreaterThanOrEqual(1);
  });

  it("required_capabilities as non-object has at least 1 error", () => {
    const payload = {
      msg_id: "m1",
      text: "test",
      mentions: [],
      intent: "task",
      task_id: "t1",
      required_capabilities: "not-an-object",
    } as unknown as MessagePayload;
    const envelope = makeEnvelope("message", "alice", "room1", 5, 0, payload);
    expect(validateEnvelope(envelope).length).toBeGreaterThanOrEqual(1);
  });

  it("legacy capability_update without skills/tags has no errors", () => {
    const payload: CapabilityUpdatePayload = {
      version: 1,
      capabilities: { intents: ["chat"] },
    };
    const envelope = makeEnvelope("capability_update", "alice", "room1", 6, 0, payload);
    expect(validateEnvelope(envelope)).toEqual([]);
  });

  it("legacy message without required_capabilities has no errors", () => {
    const payload: MessagePayload = {
      msg_id: "m2",
      text: "test",
      mentions: [],
      intent: "task",
      task_id: "t2",
    };
    const envelope = makeEnvelope("message", "alice", "room1", 7, 0, payload);
    expect(validateEnvelope(envelope)).toEqual([]);
  });
});