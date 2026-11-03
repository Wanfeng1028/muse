import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

// 极简 ACP（Agent Client Protocol）客户端：经 stdio 以 NDJSON 承载 JSON-RPC 2.0，
// 只实现桥接所需的客户端子集：initialize / session/new / session/prompt /
// session/cancel，以及 session/update 通知的接收。协议为公开标准
// （agentclientprotocol.com），本实现按 BotsTalk 需要独立编写。
// v1 范围：不响应 agent 侧反向请求（如 fs/*、session/request_permission），
// 统一回 JSON-RPC -32601，避免无声挂起。

export interface AcpUpdate {
  sessionUpdate: string;
  content?: { type?: string; text?: string };
  [key: string]: unknown;
}

export interface AcpSessionUpdateParams {
  sessionId: string;
  update: AcpUpdate;
}

export interface AcpPromptResult {
  stopReason: string;
}

export class AcpError extends Error {
  readonly code: number;

  constructor(code: number, message: string) {
    super(message);
    this.name = "AcpError";
    this.code = code;
  }
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
}

export interface AcpClientOptions {
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  onStderr?: (chunk: string) => void;
}

const ACP_PROTOCOL_VERSION = 1;

export class AcpClient {
  onUpdate: ((params: AcpSessionUpdateParams) => void) | null = null;

  private readonly command: string;
  private readonly args: string[];
  private readonly opts: AcpClientOptions;
  private child: ChildProcessWithoutNullStreams | null = null;
  private buffer = "";
  private nextId = 1;
  private readonly pending = new Map<number, PendingRequest>();

  constructor(command: string, args: string[], opts: AcpClientOptions = {}) {
    this.command = command;
    this.args = args;
    this.opts = opts;
  }

  async start(): Promise<void> {
    if (this.child !== null) return;
    const child = spawn(this.command, this.args, {
      cwd: this.opts.cwd,
      env: this.opts.env ?? process.env,
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.child = child;
    child.stdout.on("data", (chunk: Buffer) => {
      this.onData(chunk.toString("utf8"));
    });
    child.stderr.on("data", (chunk: Buffer) => {
      this.opts.onStderr?.(chunk.toString("utf8"));
    });
    child.on("error", (err: Error) => {
      this.failAll(new AcpError(-32000, `acp process error: ${err.message}`));
    });
    child.on("exit", (code: number | null, signal: NodeJS.Signals | null) => {
      this.failAll(
        new AcpError(-32000, `acp process exited (code=${code ?? "null"}, signal=${signal ?? "null"})`),
      );
      if (this.child === child) this.child = null;
    });
    await new Promise<void>((resolve, reject) => {
      child.once("spawn", () => resolve());
      child.once("error", (err: Error) => reject(new AcpError(-32000, `acp spawn failed: ${err.message}`)));
    });
  }

  async initialize(): Promise<unknown> {
    return this.request("initialize", {
      protocolVersion: ACP_PROTOCOL_VERSION,
      clientInfo: { name: "botstalk-byo-bridge", version: "0.1.0" },
      clientCapabilities: {},
    });
  }

  async newSession(cwd: string): Promise<string> {
    const result = (await this.request("session/new", { cwd, mcpServers: [] })) as
      | Record<string, unknown>
      | undefined;
    const sessionId = result?.sessionId;
    if (typeof sessionId !== "string" || sessionId.length === 0) {
      throw new AcpError(-32000, "session/new response missing sessionId");
    }
    return sessionId;
  }

  async prompt(sessionId: string, text: string): Promise<AcpPromptResult> {
    const result = (await this.request("session/prompt", {
      sessionId,
      prompt: [{ type: "text", text }],
    })) as Record<string, unknown> | undefined;
    const stopReason = result?.stopReason;
    return { stopReason: typeof stopReason === "string" ? stopReason : "end_turn" };
  }

  async cancel(sessionId: string): Promise<void> {
    this.notify("session/cancel", { sessionId });
  }

  async close(): Promise<void> {
    const child = this.child;
    if (child === null) return;
    this.child = null;
    this.failAll(new AcpError(-32000, "acp client closed"));
    try {
      child.kill("SIGTERM");
    } catch {
      // 进程可能已经退出，忽略。
    }
  }

  private request(method: string, params: Record<string, unknown>): Promise<unknown> {
    const child = this.child;
    if (child === null) {
      return Promise.reject(new AcpError(-32000, "acp process is not running"));
    }
    const id = this.nextId;
    this.nextId += 1;
    return new Promise<unknown>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.writeLine({ jsonrpc: "2.0", id, method, params });
    });
  }

  private notify(method: string, params: Record<string, unknown>): void {
    if (this.child === null) return;
    this.writeLine({ jsonrpc: "2.0", method, params });
  }

  private writeLine(message: Record<string, unknown>): void {
    const child = this.child;
    if (child === null) return;
    child.stdin.write(`${JSON.stringify(message)}\n`);
  }

  private onData(chunk: string): void {
    this.buffer += chunk;
    let idx = this.buffer.indexOf("\n");
    while (idx >= 0) {
      const line = this.buffer.slice(0, idx).trim();
      this.buffer = this.buffer.slice(idx + 1);
      idx = this.buffer.indexOf("\n");
      if (line.length > 0) this.handleLine(line);
    }
  }

  private handleLine(line: string): void {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return; // 非 JSON 行（provider 的杂散输出）直接忽略。
    }
    const id = msg.id;
    if (typeof id === "number" && ("result" in msg || "error" in msg)) {
      const pending = this.pending.get(id);
      if (pending === undefined) return;
      this.pending.delete(id);
      if ("error" in msg && msg.error !== undefined) {
        const err = msg.error as Record<string, unknown>;
        const code = typeof err.code === "number" ? err.code : -32000;
        const message = typeof err.message === "string" ? err.message : "acp request failed";
        pending.reject(new AcpError(code, message));
      } else {
        pending.resolve(msg.result);
      }
      return;
    }
    if (msg.method === "session/update") {
      const params = msg.params as AcpSessionUpdateParams | undefined;
      if (params !== undefined && typeof params.sessionId === "string") {
        this.onUpdate?.(params);
      }
      return;
    }
    if (typeof msg.method === "string" && typeof id === "number") {
      // agent 侧反向请求：v1 不支持，明确回错而不是挂起对方。
      this.writeLine({
        jsonrpc: "2.0",
        id,
        error: { code: -32601, message: `method not supported by byo-bridge v1: ${msg.method}` },
      });
    }
  }

  private failAll(err: Error): void {
    const pending = [...this.pending.values()];
    this.pending.clear();
    for (const p of pending) p.reject(err);
  }
}
