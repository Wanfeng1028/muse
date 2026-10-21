#!/usr/bin/env node
import { LinkError, parseLink, redeemLink } from "./link.js";
import {
  byoHomeDir,
  listProfiles,
  loadProfile,
  saveProfile,
  type ByoProfile,
} from "./profile.js";
import { ByoBridge } from "./bridge.js";

// BYO agent 入驻 CLI（在用户本机运行）：
//   link --url <link> [--cwd <dir>] -- <launch command> [args...]
//     兑换一次性链接（单次有效、同一安装可幂等重跑），把 provider 启动命令
//     存为该 agent 的 profile。
//   run [--agent <id>]
//     按 profile 启动桥接；无 profile 时可用环境变量临时组装
//     （BYO_COMMAND 必需，BYO_ARGS/BYO_CWD 可选；ADAPTER_ID/GATEWAY_URL/ROOM
//     与其他 adapter 一致）。
//   status
//     列出本机已保存的 profile。

function flagValue(argv: string[], name: string): string | undefined {
  const idx = argv.indexOf(name);
  if (idx < 0) return undefined;
  return argv[idx + 1];
}

function usageError(message: string): never {
  console.error(`error: ${message}`);
  console.error("usage: byo-bridge <link|run|status> [flags] [-- <launch command...>]");
  process.exit(2);
}

function cmdLink(rest: string[]): void {
  const sep = rest.indexOf("--");
  const head = sep >= 0 ? rest.slice(0, sep) : rest;
  const tail = sep >= 0 ? rest.slice(sep + 1) : [];
  const url = flagValue(head, "--url");
  if (url === undefined) usageError("link requires --url <link>");
  if (tail.length === 0) usageError("link requires a launch command after --");
  const cwd = flagValue(head, "--cwd") ?? process.cwd();
  const home = byoHomeDir();
  const link = parseLink(url);
  const outcome = redeemLink(home, link, Date.now());
  const now = Date.now();
  const existing = loadProfile(home, link.agentId);
  const command = tail[0] as string;
  const profile: ByoProfile = {
    agentId: link.agentId,
    gatewayUrl: link.gatewayUrl,
    room: link.room,
    provider: { command, args: tail.slice(1), cwd },
    createdAtMs: existing?.createdAtMs ?? now,
    updatedAtMs: now,
  };
  saveProfile(home, profile);
  console.log(
    `linked agent ${link.agentId} -> room ${link.room} @ ${link.gatewayUrl} (${outcome}); provider: ${tail.join(" ")}`,
  );
}

function profileFromEnv(): ByoProfile | null {
  const command = process.env.BYO_COMMAND;
  if (command === undefined || command === "") return null;
  const now = Date.now();
  return {
    agentId: process.env.ADAPTER_ID ?? "byo",
    gatewayUrl: process.env.GATEWAY_URL ?? "ws://127.0.0.1:8765",
    room: process.env.ROOM ?? "lobby",
    provider: {
      command,
      args: (process.env.BYO_ARGS ?? "").split(/\s+/).filter((p) => p.length > 0),
      cwd: process.env.BYO_CWD ?? process.cwd(),
    },
    createdAtMs: now,
    updatedAtMs: now,
  };
}

function cmdRun(rest: string[]): void {
  const home = byoHomeDir();
  const agentId = flagValue(rest, "--agent") ?? process.env.BOTSTALK_AGENT_ID;
  let profile = agentId !== undefined ? loadProfile(home, agentId) : null;
  if (profile === null) {
    const profiles = listProfiles(home);
    if (agentId === undefined && profiles.length === 1) {
      profile = profiles[0] as ByoProfile;
    }
  }
  if (profile === null) profile = profileFromEnv();
  if (profile === null) {
    console.error("error: no byo profile found; run `byo-bridge link` first or set BYO_COMMAND");
    process.exit(1);
  }
  const bridge = new ByoBridge(profile);
  bridge.connect();
  console.log(
    `byo-bridge agent ${profile.agentId} connected to ${profile.gatewayUrl} room ${profile.room}; provider: ${profile.provider.command}`,
  );
  const stop = (): void => {
    void bridge.shutdown().then(() => process.exit(0));
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
}

function cmdStatus(): void {
  const profiles = listProfiles(byoHomeDir());
  if (profiles.length === 0) {
    console.log("no byo profiles");
    return;
  }
  for (const p of profiles) {
    console.log(
      `${p.agentId}\troom=${p.room}\tgateway=${p.gatewayUrl}\tprovider=${p.provider.command} ${p.provider.args.join(" ")}`,
    );
  }
}

function main(): void {
  const [cmd, ...rest] = process.argv.slice(2);
  switch (cmd) {
    case "link":
      cmdLink(rest);
      return;
    case "run":
      cmdRun(rest);
      return;
    case "status":
      cmdStatus();
      return;
    default:
      usageError(cmd === undefined ? "missing subcommand" : `unknown subcommand: ${cmd}`);
  }
}

try {
  main();
} catch (err) {
  if (err instanceof LinkError) {
    console.error(`error: ${err.message}`);
    process.exit(1);
  }
  throw err;
}
