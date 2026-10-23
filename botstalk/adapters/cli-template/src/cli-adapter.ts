import { spawn, type ChildProcess } from "node:child_process";
import { AdapterClient } from "@botstalk/adapter-base";
import type { AdapterOptions } from "@botstalk/adapter-base";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import type { AgentDescriptor } from "@botstalk/registry";
import { buildCommand } from "./command.js";
import { checkReady, probe } from "./ready.js";

export interface CliAdapterOptions extends AdapterOptions {
  descriptor: AgentDescriptor;
  agentName?: string;
  workingDir?: string;
  taskTimeoutMs?: number;
  killGraceMs?: number;
  extraEnv?: NodeJS.ProcessEnv;
}

export interface RunTaskResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  truncated: boolean;
}

/**
 * CLI 本体 adapter 模板：把符合 registry 描述符的 coding CLI 接成 botstalk adapter。
 * 任务执行 = spawn(binary, launch.args) + prompt 写 stdin + 收集 stdout。
 */
export abstract class CliAdapter extends AdapterClient {
  protected readonly descriptor: AgentDescriptor;
  protected readonly agentName: string;
  protected readonly workingDir: string;
  protected readonly taskTimeoutMs: number;
  protected readonly killGraceMs: number;
  protected readonly extraEnv: NodeJS.ProcessEnv;
  protected current: ChildProcess | null = null;

  constructor(opts: CliAdapterOptions) {
    const agentName = opts.agentName ?? opts.adapterId ?? opts.descriptor.name;
    super({
      intents: ["chat", "task"],
      ...opts,
      adapterId: opts.adapterId ?? `cli-${opts.descriptor.name}`,
      onTask: opts.onTask ?? ((env) => this.handleTaskEnvelope(env)),
    });
    this.descriptor = opts.descriptor;
    this.agentName = agentName;
    this.workingDir = opts.workingDir ?? process.cwd();
    this.taskTimeoutMs = opts.taskTimeoutMs ?? 300_000;
    this.killGraceMs = opts.killGraceMs ?? 5_000;
    this.extraEnv = opts.extraEnv ?? {};
  }

  /** 委托 ./command.js 的 buildCommand（descriptor + agentName） */
  buildCommand(): { binary: string; args: string[] } {
    return buildCommand(this.descriptor, this.agentName);
  }

  /** 委托 ./ready.js 的 checkReady */
  checkReady(): Promise<{ ready: boolean; message?: string }> {
    return checkReady(this.descriptor);
  }

  /** 委托 ./ready.js 的 probe */
  probe(): Promise<boolean> {
    return probe(this.descriptor);
  }

  /**
   * 执行一次任务：spawn 子进程，prompt 写 stdin，收集 stdout/stderr（各上限 1MB，超了截断并 truncated=true）。
   * 超时（opts.timeoutMs ?? taskTimeoutMs）→ timedOut=true 并杀进程。
   * 同一实例同时只跑一个任务，否则抛 Error("task already running")。
   * binary 不存在（ENOENT）时抛错，message 必须包含 binary 名。
   */
  runTask(prompt: string, opts?: { timeoutMs?: number }): Promise<RunTaskResult> {
    if (this.current) {
      return Promise.reject(new Error("task already running"));
    }

    const { binary, args } = this.buildCommand();
    const timeoutMs = opts?.timeoutMs ?? this.taskTimeoutMs;
    const MAX_OUTPUT = 1024 * 1024;

    return new Promise<RunTaskResult>((resolve, reject) => {
      let stdout = "";
      let stderr = "";
      let truncated = false;
      let timedOut = false;
      let settled = false;

      const child: ChildProcess = spawn(binary, args, {
        cwd: this.workingDir,
        env: { ...process.env, ...this.extraEnv },
        // 独立进程组：kill 时可杀整组，收掉 CLI 派生的孙进程
        detached: true,
      });
      this.current = child;

      const cleanup = () => {
        clearTimeout(timer);
        if (exitTimer) clearTimeout(exitTimer);
        this.current = null;
      };

      const settle = (result?: RunTaskResult, err?: Error) => {
        if (settled) return;
        settled = true;
        cleanup();
        if (err) {
          reject(err);
        } else if (result) {
          resolve(result);
        }
      };

      // 杀整个进程组：CLI 派生的孙进程（如 shell 脚本的子命令）也会被收掉，
      // 否则孤儿孙进程占住 stdio 管道会导致 'close' 事件迟迟不到
      const killGroup = (sig: NodeJS.Signals) => {
        try {
          if (child.pid !== undefined) process.kill(-child.pid, sig);
          else child.kill(sig);
        } catch {
          try {
            child.kill(sig);
          } catch {
            // 已退出
          }
        }
      };
      const killChild = () => {
        killGroup("SIGINT");
        setTimeout(() => {
          if (child.exitCode === null && child.signalCode === null) {
            killGroup("SIGKILL");
          }
        }, this.killGraceMs);
      };

      const timer = setTimeout(() => {
        if (settled) return;
        timedOut = true;
        killChild();
      }, timeoutMs);

      child.stdout?.on("data", (chunk: Buffer) => {
        if (truncated) return;
        stdout += chunk.toString("utf8");
        if (stdout.length > MAX_OUTPUT) {
          stdout = stdout.slice(0, MAX_OUTPUT);
          truncated = true;
        }
      });

      child.stderr?.on("data", (chunk: Buffer) => {
        if (truncated) return;
        stderr += chunk.toString("utf8");
        if (stderr.length > MAX_OUTPUT) {
          stderr = stderr.slice(0, MAX_OUTPUT);
          truncated = true;
        }
      });

      child.on("error", (err: Error) => {
        settle(undefined, new Error(`failed to spawn ${binary}: ${err.message}`));
      });

      // 'close' 要求 stdio 管道全部关闭；'exit' 触发后给 2 秒宽限收尾数据，
      // 再没 'close' 就按已有数据 settle，避免无限挂起
      let exitTimer: NodeJS.Timeout | null = null;
      child.on("exit", (code: number | null) => {
        if (exitTimer) clearTimeout(exitTimer);
        exitTimer = setTimeout(() => {
          settle({ exitCode: code, stdout, stderr, timedOut, truncated });
        }, 2000);
      });

      child.on("close", (exitCode: number | null) => {
        if (exitTimer) clearTimeout(exitTimer);
        settle({
          exitCode,
          stdout,
          stderr,
          timedOut,
          truncated,
        });
      });

      if (child.stdin) {
        child.stdin.on("error", () => {
          // 进程可能提前退出导致 EPIPE，忽略
        });
        child.stdin.write(prompt);
        child.stdin.end();
      }
    });
  }

  /** 停止当前任务：SIGINT，killGraceMs 内未退出则 SIGKILL；无运行任务时直接 resolve */
  stopCurrent(): Promise<void> {
    const child = this.current;
    if (!child) {
      return Promise.resolve();
    }

    return new Promise<void>((resolve) => {
      let graceTimer: NodeJS.Timeout | null = null;
      const onClose = () => {
        if (graceTimer) {
          clearTimeout(graceTimer);
        }
        if (this.current === child) {
          this.current = null;
        }
        resolve();
      };

      child.once("close", onClose);
      child.kill("SIGINT");
      graceTimer = setTimeout(() => {
        if (child.exitCode === null && child.signalCode === null) {
          child.kill("SIGKILL");
        }
      }, this.killGraceMs);
    });
  }

  /**
   * onTask 默认实现：runTask 成功返回 stdout；timedOut 抛 Error("task timed out")；
   * 非零退出码抛 Error，message 含 stderr 前 500 字符。
   */
  protected async handleTaskMessage(prompt: string): Promise<string> {
    const result = await this.runTask(prompt);
    if (result.timedOut) {
      throw new Error("task timed out");
    }
    if (result.exitCode !== 0) {
      const stderrHead = result.stderr.slice(0, 500);
      throw new Error(`task failed with exit code ${result.exitCode}: ${stderrHead}`);
    }
    return result.stdout;
  }

  protected async handleTaskEnvelope(env: Envelope<MessagePayload>): Promise<void> {
    const taskId = env.payload.task_id;
    const text = env.payload.text;
    if (!taskId) {
      return;
    }
    try {
      const stdout = await this.handleTaskMessage(text);
      this.sendMessage(stdout, {
        intent: "task",
        task_id: taskId,
        task_status: "done",
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      this.sendMessage(`任务执行失败：${msg}`, {
        intent: "task",
        task_id: taskId,
        task_status: "failed",
      });
    }
  }
}