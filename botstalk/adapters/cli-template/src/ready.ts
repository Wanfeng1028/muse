import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import type { AgentDescriptor } from "@botstalk/registry";
import { expandHome } from "./command.js";

export interface ReadyResult { ready: boolean; message?: string }

/**
 * 执行子进程并收集 stdout；超时或 spawn 失败则 reject。
 */
function spawnCollect(
  binary: string,
  args: string[],
  timeoutMs: number,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, { stdio: ["ignore", "pipe", "pipe"] });
    let out = "";

    /* 收集 stdout */
    child.stdout?.on("data", (chunk: Buffer) => { out += chunk.toString(); });
    /* 排空 stderr 防止背压阻塞 */
    child.stderr?.on("data", () => {});

    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("timeout"));
    }, timeoutMs);

    /* 监听 error 防止 unhandled error 崩进程 */
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });

    child.on("close", () => {
      clearTimeout(timer);
      resolve(out);
    });
  });
}

/**
 * 按描述符 check_ready 字段判定 CLI 是否就绪。
 * 判定项（字段缺失即跳过）：env_vars（逐项存在且非空）、env_all/saved_env_all（同）、
 * creds_file（~ 展开后存在）、status_args（spawn binary+status_args，15s 超时，
 * stdout 匹配 logged_in_pattern 即 ready，匹配 logged_out_pattern 即 not ready，
 * 进程失败/超时则 {ready:false,message:"status check failed"}）。
 * 全通过或 descriptor 无 check_ready 字段 → {ready:true}。
 */
export async function checkReady(descriptor: AgentDescriptor): Promise<ReadyResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const check: any = (descriptor as any).check_ready;
  if (!check) return { ready: true };

  const notReadyMsg: string | undefined = check.not_ready_message;

  /* env_vars：逐项存在且非空 */
  if (Array.isArray(check.env_vars)) {
    for (const name of check.env_vars as string[]) {
      if (!process.env[name]) {
        return { ready: false, message: notReadyMsg ?? `missing env: ${name}` };
      }
    }
  }

  /* env_all / saved_env_all：同 */
  for (const list of [check.env_all, check.saved_env_all]) {
    if (Array.isArray(list)) {
      for (const name of list as string[]) {
        if (!process.env[name]) {
          return { ready: false, message: notReadyMsg ?? `missing env: ${name}` };
        }
      }
    }
  }

  /* creds_file：~ 展开后存在 */
  if (check.creds_file) {
    const path = expandHome(check.creds_file as string);
    if (!existsSync(path)) {
      return { ready: false, message: notReadyMsg ?? `missing creds file: ${path}` };
    }
  }

  /* status_args：spawn binary+status_args，15s 超时 */
  if (Array.isArray(check.status_args)) {
    try {
      const stdout = await spawnCollect(
        descriptor.install.binary,
        check.status_args as string[],
        15_000,
      );

      if (check.logged_in_pattern && new RegExp(check.logged_in_pattern as string).test(stdout)) {
        return { ready: true };
      }
      if (check.logged_out_pattern && new RegExp(check.logged_out_pattern as string).test(stdout)) {
        return { ready: false, message: notReadyMsg };
      }
      /* 两个模式均不匹配，视为未就绪 */
      return { ready: false, message: notReadyMsg };
    } catch {
      return { ready: false, message: "status check failed" };
    }
  }

  return { ready: true };
}

/**
 * 存活探测：descriptor 无 probe 字段返回 true；否则 spawn binary+probe.args，
 * timeout_s*1000 内 exit code 0 即 true，否则 false（超时杀掉进程）。
 * binary 不存在（ENOENT）返回 false，不抛错。
 */
export async function probe(descriptor: AgentDescriptor): Promise<boolean> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const p: any = (descriptor as any).probe;
  if (!p) return true;

  const binary = descriptor.install.binary;
  const args: string[] = p.args ?? [];
  const timeoutMs = (p.timeout_s ?? 5) * 1000;

  return new Promise<boolean>((resolve) => {
    const child = spawn(binary, args, { stdio: "ignore" });

    let settled = false;
    const finish = (result: boolean) => {
      if (!settled) { settled = true; clearTimeout(timer); resolve(result); }
    };

    const timer = setTimeout(() => {
      child.kill();
      finish(false);
    }, timeoutMs);

    /* 监听 error 防止 unhandled error 崩进程；ENOENT 等均返回 false */
    child.on("error", () => finish(false));

    child.on("close", (code) => finish(code === 0));
  });
}