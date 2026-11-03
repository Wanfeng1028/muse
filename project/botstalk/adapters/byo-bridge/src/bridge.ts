import { AdapterClient } from "@botstalk/adapter-base";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import { AcpClient, AcpError, type AcpSessionUpdateParams } from "./acp.js";
import type { ByoProfile } from "./profile.js";

// BYO 桥接：把跑在用户本机的 agent 进程（经 ACP 的 stdio 会话）以成员身份
// 接入 BotsTalk 房间。桥接本身是普通 adapter——hello/capability/心跳、任务
// 台账与审批门都走网关既有机制，本类只负责 BotsTalk 帧与 ACP 会话之间的翻译。
// 会话模型（v1）：每个桥接实例懒启动一个 provider 进程、复用一个 ACP 会话；
// 进程退出或出错后清空会话，下一个任务重新拉起。

const OK_STOP_REASONS = new Set(["end_turn", "stop_sequence", "max_tokens"]);
const ERROR_SUMMARY_MAX = 200;

interface RunSink {
  onChunk: (text: string) => void;
}

export class ByoBridge extends AdapterClient {
  private readonly profile: ByoProfile;
  private readonly busyState: { busy: boolean };
  private acp: AcpClient | null = null;
  private sessionId: string | null = null;
  private starting: Promise<string> | null = null;
  private activeRun: RunSink | null = null;

  constructor(profile: ByoProfile) {
    const busyState = { busy: false };
    super({
      adapterId: profile.agentId,
      room: profile.room,
      gatewayUrl: profile.gatewayUrl,
      intents: ["chat", "task"],
      status: () => (busyState.busy ? "thinking" : "online"),
      onTask: (env) => {
        void this.handleTask(env);
      },
      onMessage: (env) => {
        void this.handleChat(env);
      },
    });
    this.profile = profile;
    this.busyState = busyState;
  }

  async handleTask(env: Envelope<MessagePayload>): Promise<void> {
    if (env.sender === this.profile.agentId) return;
    if (env.payload.task_status !== undefined) return;
    const taskId = env.payload.task_id ?? env.payload.msg_id;
    this.busyState.busy = true;
    this.sendMessage("[byo] task accepted", {
      intent: "task",
      task_id: taskId,
      task_status: "running",
    });
    const streamId = this.sendStreamStart();
    let chunkIndex = 0;
    try {
      const { full, stopReason } = await this.runPrompt(env.payload.text, (delta) => {
        this.sendStreamChunk(streamId, chunkIndex, delta);
        chunkIndex += 1;
      });
      if (OK_STOP_REASONS.has(stopReason)) {
        this.sendStreamFinal(streamId, chunkIndex);
        this.sendMessage(full.length > 0 ? full : "[byo] (no output)", {
          intent: "task",
          task_id: taskId,
          task_status: "done",
        });
      } else {
        this.sendStreamError(streamId, chunkIndex, `acp stop: ${stopReason}`);
        this.sendMessage(`[byo] task failed: acp stop ${stopReason}`, {
          intent: "task",
          task_id: taskId,
          task_status: "failed",
        });
      }
    } catch (err) {
      const summary = summarizeError(err);
      this.resetSession();
      this.sendStreamError(streamId, chunkIndex, summary);
      this.sendMessage(`[byo] task failed: ${summary}`, {
        intent: "task",
        task_id: taskId,
        task_status: "failed",
      });
    } finally {
      this.busyState.busy = false;
    }
  }

  async handleChat(env: Envelope<MessagePayload>): Promise<void> {
    if (env.sender === this.profile.agentId) return;
    if ((env.payload.intent ?? "chat") !== "chat") return;
    // 聊天只响应被 @ 的消息，避免桥接 agent 对房间每句话都发言。
    if (!env.payload.mentions.includes(this.profile.agentId)) return;
    this.busyState.busy = true;
    try {
      const { full, stopReason } = await this.runPrompt(env.payload.text, null);
      if (OK_STOP_REASONS.has(stopReason)) {
        this.sendMessage(full.length > 0 ? full : "[byo] (no output)", { mentions: [] });
      } else {
        this.sendMessage(`[byo] error: acp stop ${stopReason}`, { mentions: [] });
      }
    } catch (err) {
      this.resetSession();
      this.sendMessage(`[byo] error: ${summarizeError(err)}`, { mentions: [] });
    } finally {
      this.busyState.busy = false;
    }
  }

  async shutdown(): Promise<void> {
    this.resetSession();
    this.disconnect();
  }

  private async runPrompt(
    text: string,
    onChunk: ((delta: string) => void) | null,
  ): Promise<{ full: string; stopReason: string }> {
    const sessionId = await this.ensureSession();
    const client = this.acp;
    if (client === null) throw new AcpError(-32000, "acp session is not ready");
    let full = "";
    this.activeRun = {
      onChunk: (delta) => {
        full += delta;
        onChunk?.(delta);
      },
    };
    try {
      const { stopReason } = await client.prompt(sessionId, text);
      return { full, stopReason };
    } finally {
      this.activeRun = null;
    }
  }

  private async ensureSession(): Promise<string> {
    if (this.sessionId !== null) return this.sessionId;
    if (this.starting !== null) return this.starting;
    const { command, args, cwd } = this.profile.provider;
    const starting = (async () => {
      const client = new AcpClient(command, args, { cwd });
      client.onUpdate = (params) => this.routeUpdate(params);
      await client.start();
      await client.initialize();
      const sessionId = await client.newSession(cwd);
      this.acp = client;
      this.sessionId = sessionId;
      return sessionId;
    })();
    this.starting = starting;
    try {
      return await starting;
    } finally {
      if (this.starting === starting) this.starting = null;
    }
  }

  private routeUpdate(params: AcpSessionUpdateParams): void {
    if (this.sessionId !== null && params.sessionId !== this.sessionId) return;
    const update = params.update;
    if (update.sessionUpdate !== "agent_message_chunk") return;
    const text = update.content?.text;
    if (typeof text === "string" && text.length > 0) {
      this.activeRun?.onChunk(text);
    }
  }

  private resetSession(): void {
    const client = this.acp;
    this.acp = null;
    this.sessionId = null;
    this.starting = null;
    this.activeRun = null;
    if (client !== null) {
      void client.close();
    }
  }
}

function summarizeError(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  const trimmed = message.trim();
  return trimmed.length <= ERROR_SUMMARY_MAX ? trimmed : trimmed.slice(0, ERROR_SUMMARY_MAX);
}
