import { describe, expect, it } from "vitest";

import {
  parseSelection,
  parseYesNo,
  runInitWizard,
  type WizardPrompter,
} from "./init-wizard.js";

function scripted(
  lines: string[],
): WizardPrompter & { asked: string[]; wrote: string[] } {
  let index = 0;
  const asked: string[] = [];
  const wrote: string[] = [];
  return {
    asked,
    wrote,
    async ask(question: string) {
      asked.push(question);
      const line = lines[index];
      index += 1;
      if (line === undefined) throw new Error("script exhausted");
      return line;
    },
    write(line: string) {
      wrote.push(line);
    },
  };
}

const options = [
  { source_id: "codex", display_name: "Codex" },
  { source_id: "cursor", display_name: "Cursor" },
  { source_id: "claude-code", display_name: "Claude Code" },
];

describe("init wizard selection parsing", () => {
  it("treats an empty answer as select-all (the product default)", () => {
    expect(parseSelection("", 3)).toEqual([0, 1, 2]);
    expect(parseSelection("all", 3)).toEqual([0, 1, 2]);
    expect(parseSelection("  ", 3)).toEqual([0, 1, 2]);
  });

  it("accepts none / 0 as an explicit empty pick", () => {
    expect(parseSelection("none", 3)).toEqual([]);
    expect(parseSelection("0", 3)).toEqual([]);
  });

  it("parses a comma/space list and rejects out-of-range values", () => {
    expect(parseSelection("1,3", 3)).toEqual([0, 2]);
    expect(parseSelection("2 1", 3)).toEqual([0, 1]);
    expect(parseSelection("4", 3)).toBeNull();
    expect(parseSelection("x", 3)).toBeNull();
  });
});

describe("init wizard yes/no parsing", () => {
  it("uses the supplied default on an empty answer", () => {
    expect(parseYesNo("", true)).toBe(true);
    expect(parseYesNo("", false)).toBe(false);
  });

  it("accepts English and Chinese, rejects nonsense", () => {
    expect(parseYesNo("y", false)).toBe(true);
    expect(parseYesNo("否", true)).toBe(false);
    expect(parseYesNo("maybe", true)).toBeNull();
  });
});

describe("init wizard flow", () => {
  it("defaults to all sources and starts processing", async () => {
    const prompter = scripted(["", ""]);
    const outcome = await runInitWizard(options, prompter);
    expect(outcome).toEqual({
      state: "answered",
      answers: {
        sourceIds: ["codex", "cursor", "claude-code"],
        processing: true,
      },
    });
  });

  it("lets the user deselect down to a subset", async () => {
    const prompter = scripted(["1,3", ""]);
    const outcome = await runInitWizard(options, prompter);
    expect(outcome.state).toBe("answered");
    if (outcome.state !== "answered") return;
    expect(outcome.answers.sourceIds).toEqual(["codex", "claude-code"]);
  });

  it("cancels when nothing is selected", async () => {
    const prompter = scripted(["none"]);
    await expect(runInitWizard(options, prompter)).resolves.toEqual({
      state: "cancelled",
    });
  });

  it("allows the selected Harnesses to remain frozen", async () => {
    const prompter = scripted(["", "n"]);
    const outcome = await runInitWizard(options, prompter);
    expect(outcome.state).toBe("answered");
    if (outcome.state !== "answered") return;
    expect(outcome.answers.processing).toBe(false);
  });

  it("re-asks on an unrecognised selection instead of guessing", async () => {
    const prompter = scripted(["7", "1", ""]);
    const outcome = await runInitWizard(options, prompter);
    expect(outcome.state).toBe("answered");
    if (outcome.state !== "answered") return;
    expect(outcome.answers.sourceIds).toEqual(["codex"]);
    expect(prompter.wrote.some((line) => line.includes("无法识别"))).toBe(true);
  });
});
