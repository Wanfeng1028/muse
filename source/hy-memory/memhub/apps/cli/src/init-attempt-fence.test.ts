import path from "node:path";
import { describe, expect, it } from "vitest";

import { initPlanAttemptPath } from "./cli.js";
import { interactiveInitAttemptPath } from "./init-attempt.js";

// Regression: `init --source <id> --import` used to pass the literal string
// `"init"` to `claimPlanAttempt`, which resolved to `<cwd>/init.one-memory-attempt`.
// Two consequences: the fence was shared across unrelated runs in the same
// directory, and any unrelated file named `init` could make a valid import
// report a misleading usage error (exit 2) instead of reading its receipt.
describe("init import attempt fence", () => {
  it("lives under the data dir, not the current working directory", () => {
    const fence = initPlanAttemptPath(
      "/tmp/example data",
      "11111111-2222-4333-8444-555555555555",
    );
    expect(fence).toBe(
      path.join(
        "/tmp/example data",
        ".cli-init-attempt-11111111-2222-4333-8444-555555555555",
      ),
    );
    expect(path.isAbsolute(fence)).toBe(true);
    expect(fence).not.toBe("init");
    // Directly under the data dir: no nested directory that could fail to be
    // created and turn a valid import into a usage error.
    expect(path.dirname(fence)).toBe("/tmp/example data");
  });

  it("is per data dir and per operation, so installs/runs cannot collide", () => {
    const a = initPlanAttemptPath("/tmp/data-a", "op-1");
    const b = initPlanAttemptPath("/tmp/data-b", "op-1");
    const c = initPlanAttemptPath("/tmp/data-a", "op-2");
    expect(new Set([a, b, c]).size).toBe(3);
  });
});

// QA-CLI R3 F1: the interactive wizard passed a CWD-relative singleton
// (`init` or `<journalDir>/init`) to `claimPlanAttempt`. A stale
// `init.one-memory-attempt` in the working directory then made every later
// `memhub init` fail with "交互计划无效 / exit 2".
describe("interactive init attempt fence", () => {
  it("lives under the data dir and is unique per operation", () => {
    const fence = interactiveInitAttemptPath(
      "/tmp/data",
      "11111111-2222-4333-8444-555555555555",
    );
    expect(fence).toBe(
      path.join(
        "/tmp/data",
        ".cli-init-attempt-11111111-2222-4333-8444-555555555555",
      ),
    );
    expect(path.isAbsolute(fence)).toBe(true);
    expect(fence).not.toBe("init");
  });

  it("does not reuse one fence for two distinct plans", () => {
    const first = interactiveInitAttemptPath("/tmp/data", "op-1");
    const second = interactiveInitAttemptPath("/tmp/data", "op-2");
    expect(first).not.toBe(second);
  });
});
