import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import { createInterface } from "node:readline";
import type { Writable } from "node:stream";

import {
  type InstalledRecallCommand,
  type RecallHostLayout,
  readInstalledRecallCommand,
} from "./recall-installer.js";

/** The query that asks the app to prove the link rather than search it.
 *
 * A probe has to tell "this link is broken" from "this link works and the
 * library is empty", and a new library really is empty. So core answers this
 * one query with a fixed receipt of its own making.
 *
 * Matched by exact equality on the core side, and sent from here with no
 * caller input in it, so it cannot become a way to ask core for something
 * else.
 */
export const PROBE_QUERY = "__om_probe__";

/** What a probe found, in terms of what the user would have to do about it.
 *
 * Three verdicts rather than a boolean, because a boolean cannot separate the
 * two failures that matter: the app is simply not running, which needs
 * nothing done and will fix itself, against the host pointing somewhere the
 * app will never write, which will never fix itself and needs repointing.
 * Reported as one "not working" they would be acted on identically, and one
 * of the two actions is always wrong.
 */
export type RecallLinkState = "wired" | "unreachable" | "reachable_but_blind";

export interface RecallProbe {
  hostId: string;
  state: RecallLinkState;
  /** Read from the host's own entry, so a wrong one shows as it is. */
  discoveryPath: string | null;
  discoveryPresent: boolean;
  /** Why, in the host's own words where there are any.
   *
   * The verdict decides what the desktop offers; this is what it can show
   * when the user asks why, and it is the only part of the probe that carries
   * the host's or the broker's actual complaint.
   */
  detail: string;
  probedAt: string;
}

/** How long to wait for a host's server to speak.
 *
 * Generous on purpose: starting Node and loading the bundle competes with
 * whatever else the machine is doing, and a probe that timed out on a busy
 * machine would report a working install as broken.
 */
const REPLY_TIMEOUT_MS = 20_000;

/** Prove the link end to end, by making the call the host would make.
 *
 * Complements `verifyRecallInstall` rather than replacing it: that one asks
 * whether our files are still as we wrote them, this one asks whether the
 * chain they describe actually reaches the app. Both are needed, because
 * either can pass while the other fails. The recorded failure was exactly
 * that: hashes intact, handshake fine, three hosts recalling nothing.
 *
 * Runs without the host: we start the server ourselves, from the entry the
 * host has on disk. Otherwise a batch self-check before a release would mean
 * opening eleven applications.
 */
export async function probeRecallInstall(
  layout: RecallHostLayout,
): Promise<RecallProbe> {
  const probedAt = new Date().toISOString();
  const installed = await readInstalledRecallCommand(layout);
  if (installed === null) {
    return {
      hostId: layout.hostId,
      state: "unreachable",
      discoveryPath: null,
      discoveryPresent: false,
      detail: "MemHub is not installed in this host",
      probedAt,
    };
  }
  const discoveryPresent =
    installed.discoveryPath !== null && (await exists(installed.discoveryPath));
  const outcome =
    installed.channel === "cli"
      ? await callThroughCli(installed)
      : await callThroughMcp(installed);

  return {
    hostId: layout.hostId,
    state: verdict(outcome, discoveryPresent),
    discoveryPath: installed.discoveryPath,
    discoveryPresent,
    detail: outcome.detail,
    probedAt,
  };
}

/** What one call came back as, before it is judged. */
interface CallOutcome {
  /** True only for a structurally valid receipt, empty or not. */
  answered: boolean;
  /** True once the server itself has been reached, whatever it then said. */
  handshook: boolean;
  detail: string;
}

function verdict(
  outcome: CallOutcome,
  discoveryPresent: boolean,
): RecallLinkState {
  if (outcome.answered) return "wired";
  // Never got as far as the server, or the entry names a file the app will
  // never write to. Both are a link that was never made, and both are fixed
  // by changing what is on disk rather than by waiting.
  if (!outcome.handshook || !discoveryPresent) return "unreachable";
  // The server is there and the entry points at a real discovery file, and
  // still no receipt: the app is down, or answering something other than
  // this. Nothing on disk to fix, so it must not be offered as one.
  return "reachable_but_blind";
}

async function callThroughMcp(
  installed: InstalledRecallCommand,
): Promise<CallOutcome> {
  const child = spawn(installed.command, installed.args, {
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, ...installed.env },
  });
  const failedToStart = new Promise<CallOutcome>((resolve) => {
    child.on("error", (error) => {
      resolve({
        answered: false,
        handshook: false,
        detail: `the host's recall server could not be started: ${error.message}`,
      });
    });
  });
  try {
    return await Promise.race([failedToStart, exchange(child)]);
  } finally {
    child.kill();
  }
}

async function exchange(child: ReturnType<typeof spawn>): Promise<CallOutcome> {
  if (child.stdin === null || child.stdout === null) {
    return {
      answered: false,
      handshook: false,
      detail: "the host's recall server has no stdio to speak over",
    };
  }
  // Keep an error observer for the stream's whole lifetime. A write callback
  // may report success when bytes enter Node's buffer and the OS can still
  // deliver EPIPE later, after a short-lived host command has exited. Without
  // this persistent listener that delayed error becomes a process-wide
  // uncaught exception even though the probe already classified the host.
  child.stdin.on("error", () => undefined);
  const replies = collect(child, 3);
  try {
    await writeJsonRpc(child.stdin, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2025-03-26" },
    });
    await writeJsonRpc(child.stdin, {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/list",
    });
    // The step that makes this a probe rather than a second verify. The two
    // above both succeed on a host that recalls nothing: the server starts and
    // lists its tool without ever needing the app.
    await writeJsonRpc(child.stdin, {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: "om_recall", arguments: { query: PROBE_QUERY } },
    });
  } catch (error) {
    return {
      answered: false,
      handshook: false,
      detail: `the host's recall server closed before the handshake: ${describe(error)}`,
    };
  }

  const lines = await replies;
  const answers = new Map<unknown, Record<string, unknown>>();
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line) as Record<string, unknown>;
      answers.set(parsed.id, parsed);
    } catch {
      // Not ours to interpret. A server that writes anything other than
      // JSON-RPC to stdout has not answered, which is what the absence of an
      // entry here will say.
    }
  }
  const handshake = answers.get(1);
  if (handshake === undefined || handshake.error !== undefined) {
    return {
      answered: false,
      handshook: false,
      detail: "the host's recall server did not complete the handshake",
    };
  }
  if (answers.get(2)?.error !== undefined) {
    return {
      answered: false,
      handshook: false,
      detail: "the host's recall server would not list its tool",
    };
  }
  const call = answers.get(3);
  if (call === undefined) {
    return {
      answered: false,
      handshook: true,
      detail: "the host's recall server never answered the recall call",
    };
  }
  return fromToolResult(call);
}

/** Write one request while owning the stream's error event.
 *
 * A host entry can legitimately point at a command that exits immediately.
 * Writing the next request after that used to emit an unhandled EPIPE after
 * the probe had already returned, turning an unreachable host into a global
 * test/process error. The callback and temporary error listener settle one
 * promise instead, so early exit remains an ordinary probe result.
 */
function writeJsonRpc(
  stream: Writable,
  request: Record<string, unknown>,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error?: Error | null) => {
      if (settled) return;
      settled = true;
      stream.off("error", onError);
      if (error) reject(error);
      else resolve();
    };
    const onError = (error: Error) => finish(error);
    stream.once("error", onError);
    try {
      stream.write(`${JSON.stringify(request)}\n`, finish);
    } catch (error) {
      finish(error instanceof Error ? error : new Error(String(error)));
    }
  });
}

function fromToolResult(call: Record<string, unknown>): CallOutcome {
  if (call.error !== undefined) {
    return {
      answered: false,
      handshook: true,
      detail: describe(call.error),
    };
  }
  const result = call.result as
    | { isError?: boolean; structuredContent?: unknown; content?: unknown }
    | undefined;
  if (result === undefined) {
    return {
      answered: false,
      handshook: true,
      detail: "the recall call came back with nothing in it",
    };
  }
  if (result.isError === true) {
    return {
      answered: false,
      handshook: true,
      detail: firstText(result.content) ?? "the recall call reported an error",
    };
  }
  if (!isReceipt(result.structuredContent)) {
    return {
      answered: false,
      handshook: true,
      detail: "the recall call answered with something that is not a receipt",
    };
  }
  const receipt = result.structuredContent;
  return {
    answered: true,
    handshook: true,
    detail: `recalled ${receipt.hits.length} memories for the self-check`,
  };
}

async function callThroughCli(
  installed: InstalledRecallCommand,
): Promise<CallOutcome> {
  // A CLI host has no tool to call: the skill tells the model to run a
  // command. So the probe runs that command, for the same reason it starts
  // the server for the others.
  const child = spawn(
    installed.command,
    [...installed.args, PROBE_QUERY, "--json"],
    {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ...installed.env },
    },
  );
  const printed: string[] = [];
  child.stdout?.on("data", (chunk: Buffer) => {
    printed.push(chunk.toString("utf8"));
  });
  const finished = await new Promise<{ code: number | null; failed?: string }>(
    (resolve) => {
      const timer = setTimeout(() => {
        child.kill();
        resolve({ code: null });
      }, REPLY_TIMEOUT_MS);
      child.on("error", (error) => {
        clearTimeout(timer);
        resolve({ code: null, failed: error.message });
      });
      child.on("close", (code) => {
        clearTimeout(timer);
        resolve({ code });
      });
    },
  );
  if (finished.failed !== undefined) {
    return {
      answered: false,
      handshook: false,
      detail: `the host's recall command could not be run: ${finished.failed}`,
    };
  }
  let printedValue: unknown;
  try {
    printedValue = JSON.parse(printed.join(""));
  } catch {
    return {
      answered: false,
      handshook: finished.code !== null,
      detail: "the host's recall command printed something that is not JSON",
    };
  }
  if (!isReceipt(printedValue)) {
    return {
      answered: false,
      handshook: true,
      detail: describeCliRefusal(printedValue),
    };
  }
  return {
    answered: true,
    handshook: true,
    detail: `recalled ${printedValue.hits.length} memories for the self-check`,
  };
}

function describeCliRefusal(printed: unknown): string {
  const reason =
    printed && typeof printed === "object" && "reason" in printed
      ? String((printed as { reason: unknown }).reason)
      : null;
  return reason === null
    ? "the host's recall command answered with something that is not a receipt"
    : `the host's recall command reported: ${reason}`;
}

interface Receipt {
  state: string;
  hits: unknown[];
}

/** A receipt, empty or not.
 *
 * The check is the whole point of the empty case: a probe that accepted any
 * JSON would call a broker answering nonsense wired, and a probe that
 * required a hit would call an empty library broken. Both are wrong, and a
 * new library is genuinely empty.
 */
function isReceipt(value: unknown): value is Receipt {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Receipt> & { scope?: unknown };
  return (
    (candidate.state === "grounded" || candidate.state === "empty") &&
    Array.isArray(candidate.hits) &&
    typeof candidate.scope === "string"
  );
}

function firstText(content: unknown): string | null {
  if (!Array.isArray(content)) return null;
  for (const item of content) {
    if (
      item &&
      typeof item === "object" &&
      typeof (item as { text?: unknown }).text === "string"
    ) {
      return (item as { text: string }).text;
    }
  }
  return null;
}

function describe(error: unknown): string {
  if (
    error &&
    typeof error === "object" &&
    typeof (error as { message?: unknown }).message === "string"
  ) {
    return (error as { message: string }).message;
  }
  return "the recall call was refused";
}

function collect(
  child: ReturnType<typeof spawn>,
  count: number,
): Promise<string[]> {
  return new Promise((resolve) => {
    if (child.stdout === null) {
      resolve([]);
      return;
    }
    const lines: string[] = [];
    const reader = createInterface({
      input: child.stdout,
      crlfDelay: Number.POSITIVE_INFINITY,
    });
    const done = () => {
      clearTimeout(timer);
      reader.close();
      resolve(lines);
    };
    // Whatever arrived by the deadline is what it answered. Waiting for all
    // three when one is never coming would turn a diagnosable failure into a
    // hang, and the probe is meant to be runnable across eleven hosts at once.
    const timer = setTimeout(done, REPLY_TIMEOUT_MS);
    reader.on("line", (line) => {
      lines.push(line);
      if (lines.length >= count) done();
    });
    // A server that dies mid-exchange has answered as much as it is going to.
    child.on("close", done);
  });
}

async function exists(target: string): Promise<boolean> {
  try {
    await access(target);
    return true;
  } catch {
    return false;
  }
}
