import { pathToFileURL } from "node:url";
import { CliAdapter } from "../cli-adapter.js";
import type { CliAdapterOptions } from "../cli-adapter.js";
import { registry } from "@botstalk/registry";

export interface ClaudeCliAdapterOptions extends Omit<CliAdapterOptions, "descriptor" | "agentName" | "adapterId"> {
  adapterId?: string;
  agentName?: string;
}

/** Claude Code CLI 本体 adapter：registry 的 claude 描述符 + CliAdapter 模板 */
export class ClaudeCliAdapter extends CliAdapter {
  constructor(opts: ClaudeCliAdapterOptions = {}) {
    const descriptor = registry.getByName("claude");
    if (!descriptor) throw new Error("descriptor 'claude' not found");
    super({
      intents: ["chat", "task"],
      ...opts,
      adapterId: opts.adapterId ?? "cli-claude",
      agentName: opts.agentName ?? "claude",
      descriptor,
    });
  }
}

// 直接运行：node dist/adapters/claude.js --gateway ws://127.0.0.1:8765 --room lobby
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2);
  const get = (k: string) => {
    const i = args.indexOf(k);
    return i >= 0 ? args[i + 1] : undefined;
  };
  const adapter = new ClaudeCliAdapter({
    gatewayUrl: get("--gateway"),
    room: get("--room"),
    agentName: get("--name"),
    workingDir: get("--working-dir"),
  });
  adapter.connect();
}
