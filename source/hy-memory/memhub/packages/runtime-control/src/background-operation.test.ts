import { randomUUID } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  type BackgroundOperationSnapshot,
  validateBackgroundSnapshot,
  validateBackgroundTransition,
} from "./background-operation.js";

const owner = { userId: "local", runtimeId: "stable-data-id" };
function snapshot(): BackgroundOperationSnapshot {
  return {
    schemaVersion: 1,
    ...owner,
    revision: 1,
    operations: [
      {
        operationId: randomUUID(),
        expectedRevision: 0,
        action: "enable",
        planDigest: "a".repeat(64),
        artifactDigest: "b".repeat(64),
        state: "prepared",
        code: null,
      },
    ],
  };
}
function next(
  value: BackgroundOperationSnapshot,
  state: "applying" | "committed" | "unknown" | "rejected",
): BackgroundOperationSnapshot {
  return {
    ...value,
    revision: value.revision + 1,
    operations: value.operations.map((item) => ({ ...item, state })),
  };
}
describe("background operation contract", () => {
  it("compares schema fields independently of JSON property order", () => {
    const first = snapshot(),
      applying = next(first, "applying");
    const reversed = {
      ...applying,
      operations: applying.operations.map((item) =>
        Object.fromEntries(Object.entries(item).reverse()),
      ),
    } as unknown as BackgroundOperationSnapshot;
    expect(() =>
      validateBackgroundTransition(first, reversed, owner),
    ).not.toThrow();
  });
  it("requires prepared before applying before committed", () => {
    const first = snapshot();
    validateBackgroundTransition(null, first, owner);
    expect(() =>
      validateBackgroundTransition(first, next(first, "committed"), owner),
    ).toThrow();
    const applied = next(first, "applying");
    validateBackgroundTransition(first, applied, owner);
    validateBackgroundTransition(applied, next(applied, "committed"), owner);
  });
  it("unknown cannot reset to applying and cannot be dropped for another operation", () => {
    const value = next(next(snapshot(), "applying"), "unknown");
    expect(() =>
      validateBackgroundTransition(value, next(value, "applying"), owner),
    ).toThrow();
    const changed = {
      ...value,
      revision: value.revision + 1,
      operations: [
        ...value.operations,
        { ...snapshot().operations[0], expectedRevision: value.revision },
      ],
    };
    expect(() => validateBackgroundTransition(value, changed, owner)).toThrow();
    validateBackgroundTransition(value, next(value, "committed"), owner);
    validateBackgroundTransition(value, next(value, "rejected"), owner);
  });
  it("binds action artifacts owner and expected revision", () => {
    const first = snapshot();
    const applied = next(first, "applying");
    for (const patch of [
      { action: "disable" },
      { planDigest: "c".repeat(64) },
      { artifactDigest: "c".repeat(64) },
      { expectedRevision: 9 },
    ]) {
      const changed = {
        ...applied,
        operations: [{ ...applied.operations[0], ...patch }],
      } as BackgroundOperationSnapshot;
      expect(() =>
        validateBackgroundTransition(first, changed, owner),
      ).toThrow();
    }
    expect(() =>
      validateBackgroundSnapshot({ ...first, userId: "other" }, owner),
    ).toThrow();
    expect(() =>
      validateBackgroundSnapshot({ ...first, secret: "no" }, owner),
    ).toThrow();
  });
  it("retains at most32 terminal histories and stale revision prevents old replay", () => {
    let state = snapshot();
    for (let i = 0; i < 40; i++) {
      const applying = {
        ...state,
        revision: state.revision + 1,
        operations: [
          ...state.operations.slice(0, -1),
          {
            ...state.operations[state.operations.length - 1],
            state: "applying" as const,
          },
        ],
      };
      validateBackgroundTransition(state, applying, owner);
      const done = {
        ...applying,
        revision: applying.revision + 1,
        operations: [
          ...applying.operations.slice(0, -1),
          {
            ...applying.operations[applying.operations.length - 1],
            state: "committed" as const,
          },
        ],
      };
      validateBackgroundTransition(applying, done, owner);
      const added = {
        ...done,
        revision: done.revision + 1,
        operations: [
          ...done.operations.slice(-31),
          { ...snapshot().operations[0], expectedRevision: done.revision },
        ],
      };
      validateBackgroundTransition(done, added, owner);
      state = added;
    }
    expect(state.operations).toHaveLength(32);
    expect(() =>
      validateBackgroundTransition(state, snapshot(), owner),
    ).toThrow();
  });
  it("does not accept arbitrary exception text as a persisted code", () => {
    const value = snapshot();
    expect(() =>
      validateBackgroundSnapshot(
        {
          ...value,
          operations: [{ ...value.operations[0], code: "token=secret" }],
        },
        owner,
      ),
    ).toThrow();
  });
});
