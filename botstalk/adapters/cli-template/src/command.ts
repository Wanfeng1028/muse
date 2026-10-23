import type { AgentDescriptor } from "@botstalk/registry";

/** 把 launch.args 中的 {agent_name} 模板替换为实际 agent 名 */
export function renderArgs(args: Array<string | null | undefined>, agentName: string): string[] {
  return args
    .filter((a): a is string => typeof a === "string")
    .map((a) => a.replaceAll("{agent_name}", agentName));
}

/** 由描述符构造启动命令。launch 为 null 或 binary 为空时抛 Error("descriptor '<name>' has no launch info") */
export function buildCommand(descriptor: AgentDescriptor, agentName: string): { binary: string; args: string[] } {
  const binary = descriptor.install.binary;
  const args = descriptor.launch?.args ?? null;

  if (!args || !binary) {
    throw new Error(`descriptor '${descriptor.name}' has no launch info`);
  }

  return { binary, args: renderArgs(args, agentName) };
}

/** 展开路径开头的 ~ 为 HOME */
export function expandHome(p: string): string {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? "";

  if (p === "~") {
    return home;
  }

  if (p.startsWith("~/")) {
    return home + p.slice(1);
  }

  return p;
}