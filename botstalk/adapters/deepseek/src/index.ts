import { AdapterClient } from "@botstalk/adapter-base";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

// 配置（环境变量）：
//   ADAPTER_ID（默认 "deepseek"）、GATEWAY_URL、ROOM（默认 "lobby"）
//   DEEPSEEK_API_KEY（必需，无则 task/chat 回 failed+upstream_error 说明）
//   DEEPSEEK_BASE_URL（默认 "https://api.deepseek.com"）
//   DEEPSEEK_MODEL（默认 "deepseek-chat"）
//   DEEPSEEK_BODY（默认 "false"；"true" 时 task 走 DSH 本体）
//   DSH_COMMAND（默认 "npx -y @deepseek-ai/dsh"；按空格 split，第一段为命令）

export const MODE_LABEL = process.env.DEEPSEEK_BODY === "true" ? "body" : "brain";

const DEFAULT_BASE_URL = "https://api.deepseek.com";
const DEFAULT_MODEL = "deepseek-chat";
const DEFAULT_DSH_COMMAND = "npx -y @deepseek-ai/dsh";

const TASK_SUMMARY_MAX = 500;
const STDERR_SUMMARY_MAX = 200;

export interface ChatUsage {
  input_tokens: number;
  output_tokens: number;
}

export interface DshResult {
  text: string;
}

interface SseUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
}

interface ChatCompletionOptions {
  apiKey: string;
  baseUrl: string;
  model: string;
}

function readEnv(key: string, fallback: string): string {
  const v = process.env[key];
  if (v === undefined || v === "") return fallback;
  return v;
}

export function splitDshCommand(cmd: string): string[] {
  return cmd.split(/\s+/).filter((p) => p.length > 0);
}

export function summarize(text: string, max: number): string {
  const t = text.trim();
  if (t.length <= max) return t;
  return t.slice(0, max);
}

export async function chatCompletionStream(
  prompt: string,
  onDelta: (text: string) => void,
  opts: ChatCompletionOptions,
): Promise<ChatUsage | undefined> {
  const { apiKey, baseUrl, model } = opts;
  const url = `${baseUrl.replace(/\/+$/, "")}/chat/completions`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      messages: [{ role: "user", content: prompt }],
      stream: true,
    }),
  });

  if (!res.ok) {
    throw new Error(`upstream_error: http ${res.status}`);
  }
  if (res.body === null) {
    throw new Error("upstream_error: empty body");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let usage: ChatUsage | undefined;

  const handleLine = (line: string): boolean => {
    const trimmed = line.trim();
    if (trimmed === "") return false;
    if (!trimmed.startsWith("data:")) return false;
    const data = trimmed.slice("data:".length).trim();
    if (data === "[DONE]") return true;
    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      return false;
    }
    const obj = parsed as {
      choices?: Array<{ delta?: { content?: string } }>;
      usage?: SseUsage | null;
    };
    if (obj.usage) {
      usage = {
        input_tokens: obj.usage.prompt_tokens ?? 0,
        output_tokens: obj.usage.completion_tokens ?? 0,
      };
    }
    const delta = obj.choices?.[0]?.delta?.content;
    if (typeof delta === "string" && delta.length > 0) {
      onDelta(delta);
    }
    return false;
  };

  let done = false;
  while (!done) {
    const { value, done: streamDone } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      let idx = buffer.indexOf("\n");
      while (idx >= 0) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        if (handleLine(line)) {
          done = true;
          break;
        }
        idx = buffer.indexOf("\n");
      }
    }
    if (streamDone) {
      if (buffer.length > 0) {
        handleLine(buffer);
        buffer = "";
      }
      break;
    }
  }

  return usage;
}

export async function runDshTask(
  dshCmd: string[],
  sessionId: string,
  task: string,
): Promise<DshResult> {
  if (dshCmd.length === 0) {
    throw new Error("upstream_error: empty DSH command");
  }
  const [cmd, ...rest] = dshCmd as [string, ...string[]];
  return new Promise<DshResult>((resolve, reject) => {
    const child = spawn(
      cmd,
      [...rest, "headless", "--json", "--session-id", sessionId, task],
      { env: { ...process.env } },
    );

    let stdoutBuf = "";
    let stderrBuf = "";
    let finalText: string | null = null;
    let settled = false;

    const handleLine = (line: string): void => {
      const trimmed = line.trim();
      if (trimmed === "") return;
      let obj: unknown;
      try {
        obj = JSON.parse(trimmed);
      } catch {
        return;
      }
      const rec = obj as { type?: string; text?: string; phase?: string };
      if (rec.type === "status") {
        console.debug("[deepseek:body] status", rec.phase ?? "");
        return;
      }
      if (rec.type === "final" && typeof rec.text === "string") {
        finalText = rec.text;
      }
    };

    child.stdout.on("data", (chunk: Buffer) => {
      stdoutBuf += chunk.toString("utf8");
      let idx = stdoutBuf.indexOf("\n");
      while (idx >= 0) {
        const line = stdoutBuf.slice(0, idx);
        stdoutBuf = stdoutBuf.slice(idx + 1);
        handleLine(line);
        idx = stdoutBuf.indexOf("\n");
      }
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderrBuf += chunk.toString("utf8");
    });

    child.on("error", (err: Error) => {
      if (settled) return;
      settled = true;
      reject(new Error(`upstream_error: ${err.message}`));
    });

    child.on("close", (code: number | null) => {
      if (settled) return;
      if (stdoutBuf.trim() !== "") {
        handleLine(stdoutBuf);
        stdoutBuf = "";
      }
      settled = true;
      if (code !== 0 || stderrBuf.includes("MISSING_CREDENTIAL")) {
        reject(
          new Error(`upstream_error: ${summarize(stderrBuf, STDERR_SUMMARY_MAX) || `exit ${code}`}`),
        );
        return;
      }
      if (finalText === null) {
        reject(new Error("upstream_error: no final text"));
        return;
      }
      resolve({ text: finalText });
    });
  });
}

interface StreamSink {
  start: () => Promise<string> | string;
  chunk: (streamId: string, index: number, content: string) => Promise<void> | void;
  final: (streamId: string, index: number, usage?: ChatUsage) => Promise<void> | void;
  error: (streamId: string, index: number, reason: string) => Promise<void> | void;
}

async function emitStream(sink: StreamSink, text: string, usage?: ChatUsage): Promise<void> {
  const streamId = await sink.start();
  let idx = 0;
  if (text.length === 0) {
    await sink.final(streamId, 0, usage);
    return;
  }
  const CHUNK = 256;
  for (let i = 0; i < text.length; i += CHUNK) {
    const piece = text.slice(i, i + CHUNK);
    await sink.chunk(streamId, idx, piece);
    idx += 1;
  }
  await sink.final(streamId, idx, usage);
}

export interface DeepSeekRuntimeConfig {
  adapterId: string;
  apiKey: string;
  baseUrl: string;
  model: string;
  bodyMode: boolean;
  dshCmd: string[];
}

export function readRuntimeConfig(): DeepSeekRuntimeConfig {
  const adapterId = readEnv("ADAPTER_ID", "deepseek");
  const apiKey = process.env.DEEPSEEK_API_KEY ?? "";
  const baseUrl = readEnv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL);
  const model = readEnv("DEEPSEEK_MODEL", DEFAULT_MODEL);
  const bodyMode = process.env.DEEPSEEK_BODY === "true";
  const dshCmd = splitDshCommand(readEnv("DSH_COMMAND", DEFAULT_DSH_COMMAND));
  return { adapterId, apiKey, baseUrl, model, bodyMode, dshCmd };
}

function makeSink(client: AdapterClient): StreamSink {
  return {
    start: () => client.sendStreamStart(),
    chunk: (id, i, c) => { client.sendStreamChunk(id, i, c); },
    final: (id, i, u) => { client.sendStreamFinal(id, i, u); },
    error: (id, i, r) => { client.sendStreamError(id, i, r); },
  };
}

export function createHandlers(cfg: DeepSeekRuntimeConfig, client: AdapterClient) {
  const sink = makeSink(client);

  async function onMessage(env: Envelope<MessagePayload>): Promise<void> {
    if (env.sender === cfg.adapterId) return;
    const chat = env.payload;
    if (cfg.apiKey === "") {
      const streamId = await sink.start();
      await sink.error(streamId, 0, "upstream_error: missing DEEPSEEK_API_KEY");
      return;
    }
    const streamId = await sink.start();
    let idx = 0;
    let buffer = "";
    try {
      const usage = await chatCompletionStream(
        chat.text,
        (delta) => {
          buffer += delta;
        },
        { apiKey: cfg.apiKey, baseUrl: cfg.baseUrl, model: cfg.model },
      );
      const CHUNK = 256;
      if (buffer.length === 0) {
        await sink.final(streamId, 0, usage);
        return;
      }
      for (let i = 0; i < buffer.length; i += CHUNK) {
        await sink.chunk(streamId, idx, buffer.slice(i, i + CHUNK));
        idx += 1;
      }
      await sink.final(streamId, idx, usage);
    } catch (err) {
      const reason = err instanceof Error ? err.message : "upstream_error";
      await sink.error(streamId, idx, reason);
    }
  }

  async function onTask(env: Envelope<MessagePayload>): Promise<void> {
    if (env.sender === cfg.adapterId) return;
    if (env.payload.task_status !== undefined) return;
    const task = env.payload;
    const taskId = task.task_id ?? randomUUID();
    const label = cfg.bodyMode ? "body" : "brain";
    client.sendMessage(`[deepseek:${label}] task accepted`, {
      intent: "task",
      task_id: taskId,
      task_status: "running",
    });

    if (cfg.apiKey === "" && !cfg.bodyMode) {
      client.sendMessage(`[deepseek:${label}] failed: upstream_error: missing DEEPSEEK_API_KEY`, {
        intent: "task",
        task_id: taskId,
        task_status: "failed",
      });
      return;
    }

    const streamId = await sink.start();
    let idx = 0;

    if (cfg.bodyMode) {
      try {
        const sessionId = `botstalk-${cfg.adapterId}`;
        const result = await runDshTask(cfg.dshCmd, sessionId, task.text);
        const CHUNK = 256;
        if (result.text.length === 0) {
          await sink.final(streamId, 0);
        } else {
          for (let i = 0; i < result.text.length; i += CHUNK) {
            await sink.chunk(streamId, idx, result.text.slice(i, i + CHUNK));
            idx += 1;
          }
          await sink.final(streamId, idx);
        }
        client.sendMessage(`[deepseek:body] ${summarize(result.text, TASK_SUMMARY_MAX)}`, {
          intent: "task",
          task_id: taskId,
          task_status: "done",
        });
      } catch (err) {
        const reason = err instanceof Error ? err.message : "upstream_error";
        await sink.error(streamId, idx, reason);
        client.sendMessage(`[deepseek:body] failed: ${summarize(reason, STDERR_SUMMARY_MAX)}`, {
          intent: "task",
          task_id: taskId,
          task_status: "failed",
        });
      }
      return;
    }

    let buffer = "";
    try {
      const usage = await chatCompletionStream(
        task.text,
        (delta) => {
          buffer += delta;
        },
        { apiKey: cfg.apiKey, baseUrl: cfg.baseUrl, model: cfg.model },
      );
      const CHUNK = 256;
      if (buffer.length === 0) {
        await sink.final(streamId, 0, usage);
      } else {
        for (let i = 0; i < buffer.length; i += CHUNK) {
          await sink.chunk(streamId, idx, buffer.slice(i, i + CHUNK));
          idx += 1;
        }
        await sink.final(streamId, idx, usage);
      }
      client.sendMessage(`[deepseek:brain] ${summarize(buffer, TASK_SUMMARY_MAX)}`, {
        intent: "task",
        task_id: taskId,
        task_status: "done",
      });
    } catch (err) {
      const reason = err instanceof Error ? err.message : "upstream_error";
      await sink.error(streamId, idx, reason);
      client.sendMessage(`[deepseek:brain] failed: ${summarize(reason, STDERR_SUMMARY_MAX)}`, {
        intent: "task",
        task_id: taskId,
        task_status: "failed",
      });
    }
  }

  return { onMessage, onTask };
}

async function main(): Promise<void> {
  const cfg = readRuntimeConfig();
  const adapterId = cfg.adapterId;
  const gatewayUrl = process.env.GATEWAY_URL ?? "";
  const room = readEnv("ROOM", "lobby");
  const mode = cfg.bodyMode ? "body" : "brain";

  const handlersRef: { current?: { onMessage: (env: Envelope<MessagePayload>) => Promise<void>; onTask: (env: Envelope<MessagePayload>) => Promise<void> } } = {};

  const client = new AdapterClient({
    adapterId,
    gatewayUrl,
    room,
    intents: ["chat", "task"],
    onMessage: (env) => handlersRef.current!.onMessage(env),
    onTask: (env) => handlersRef.current!.onTask(env),
  });

  const handlers = createHandlers(cfg, client);
  handlersRef.current = handlers;

  client.connect();
  console.log(`deepseek adapter ${adapterId} mode=${mode} connected to ${gatewayUrl}`);
}

const isMain = (() => {
  try {
    const entry = process.argv[1] ?? "";
    return entry.endsWith("index.ts") || entry.endsWith("index.js");
  } catch {
    return false;
  }
})();

if (isMain) {
  main().catch((err: unknown) => {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[deepseek] fatal: ${msg}`);
    process.exitCode = 1;
  });
}
// 自查：红线 1-5 逐条通过
