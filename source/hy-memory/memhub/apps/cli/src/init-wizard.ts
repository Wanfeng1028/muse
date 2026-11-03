/** A2: the human-facing onboarding loop.
 *
 * The non-interactive `init --source … --import` path stays exactly as it was:
 * a CVM/CI/agent caller must never be prompted or blocked. This module is only
 * entered when stdin is a TTY and no `--source` was given, and it asks the
 * two questions the product needs: which sources, and whether their processing
 * pipeline starts now or stays frozen.
 *
 * All I/O goes through an injectable prompter so the whole flow is testable
 * without a real terminal — a pty is only needed for the end-to-end check.
 */

export interface WizardOption {
  source_id: string;
  display_name: string;
}

export interface WizardPrompter {
  /** Ask a question and resolve with one line of input. */
  ask(question: string): Promise<string>;
  /** Ask without echoing the entered value. Present only on the real TTY and
   * on tests that opt into the extended onboarding flow. */
  askSecret?(question: string): Promise<string>;
  /** Write a line that is not a question (headings, echo of parsed answers). */
  write(line: string): void;
}

export interface WizardAnswers {
  sourceIds: string[];
  processing: boolean;
}

export type WizardOutcome =
  | { state: "answered"; answers: WizardAnswers }
  | { state: "cancelled" }
  | { state: "invalid"; code: string };

/**
 * Parse a numbered multi-select line.
 *
 * "" or "all" → every option (the product default: 扫描后默认全选导入).
 * "none"/"0"  → no options.
 * "1,3"       → those (1-based) options, de-duplicated and order-normalised.
 */
export function parseSelection(line: string, count: number): number[] | null {
  const trimmed = line.trim().toLowerCase();
  if (trimmed === "" || trimmed === "all" || trimmed === "*") {
    return Array.from({ length: count }, (_, index) => index);
  }
  if (trimmed === "none" || trimmed === "0") return [];
  const parts = trimmed.split(/[\s,]+/).filter((part) => part !== "");
  const picked = new Set<number>();
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return null;
    const value = Number(part);
    if (!Number.isSafeInteger(value) || value < 1 || value > count) return null;
    picked.add(value - 1);
  }
  if (picked.size === 0) return null;
  return [...picked].sort((left, right) => left - right);
}

export function parseYesNo(line: string, fallback: boolean): boolean | null {
  const trimmed = line.trim().toLowerCase();
  if (trimmed === "") return fallback;
  if (["y", "yes", "是", "开", "on", "1"].includes(trimmed)) return true;
  if (["n", "no", "否", "关", "off", "0"].includes(trimmed)) return false;
  return null;
}

export async function runInitWizard(
  options: readonly WizardOption[],
  prompter: WizardPrompter,
): Promise<WizardOutcome> {
  if (options.length === 0) return { state: "invalid", code: "no_sources" };

  prompter.write("检测到以下来源：");
  options.forEach((option, index) => {
    prompter.write(
      `  ${index + 1}) ${option.source_id}  ${option.display_name}`,
    );
  });

  let selected: number[] | null = null;
  while (selected === null) {
    const line = await prompter.ask(
      "选择要接入的来源（回车=全选，输入 none 取消，如 1,3）: ",
    );
    const parsed = parseSelection(line, options.length);
    if (parsed === null) {
      prompter.write("输入无法识别，请重新输入编号、all 或 none。");
      continue;
    }
    selected = parsed;
  }
  if (selected.length === 0) return { state: "cancelled" };

  const processingAnswer = await prompter.ask(
    "开启处理？开启后会处理历史未完成会话并持续接收新会话；输入 n 保持冻结。[Y/n]: ",
  );
  const processing = parseYesNo(processingAnswer, true);
  if (processing === null) return { state: "invalid", code: "invalid_answer" };

  return {
    state: "answered",
    answers: {
      sourceIds: selected.map((index) => options[index]!.source_id),
      processing,
    },
  };
}

export interface TerminalPrompter extends WizardPrompter {
  close(): void;
}

/** A prompter backed by a real terminal, built with the built-in readline.
 * No new dependency: `@clack/prompts` is what Memmy uses, and it is not worth
 * pulling in for three questions. */
export async function createTerminalPrompter(): Promise<TerminalPrompter> {
  const { Writable } = await import("node:stream");
  const { createInterface } = await import("node:readline/promises");
  let muted = false;
  const output = new Writable({
    write(chunk, _encoding, callback) {
      if (!muted) process.stdout.write(chunk);
      callback();
    },
  });
  const rl = createInterface({
    input: process.stdin,
    output,
    terminal: true,
  });
  return {
    async ask(question: string) {
      return rl.question(question);
    },
    async askSecret(question: string) {
      process.stdout.write(question);
      muted = true;
      try {
        return await rl.question("");
      } finally {
        muted = false;
        process.stdout.write("\n");
      }
    },
    write(line: string) {
      process.stdout.write(`${line}\n`);
    },
    close() {
      rl.close();
    },
  };
}
