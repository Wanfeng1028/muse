import { pathToFileURL } from "node:url";
import { CliAdapter } from "../cli-adapter.js";
import type { CliAdapterOptions } from "../cli-adapter.js";
import { registry } from "@botstalk/registry";

export interface CodexCliAdapterOptions extends Omit<CliAdapterOptions, "descriptor" | "agentName" | "adapterId"> {
  adapterId?: string;
  agentName?: string;
}

/** Codex CLI 本体 adapter：registry 的 codex 描述符 + CliAdapter 模板 */
export class CodexCliAdapter extends CliAdapter {
  constructor(opts: CodexCliAdapterOptions = {}) {
    const descriptor = registry.getByName("codex");
    if (!descriptor) throw new Error("descriptor 'codex' not found");
    super({
      intents: ["chat", "task"],
      ...opts,
      adapterId: opts.adapterId ?? "cli-codex",
      agentName: opts.agentName ?? "codex",
      descriptor,
    });
  }
}

// 直接运行：node dist/adapters/codex.js --gateway ws://127.0.0.1:8765 --room lobby
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2);
  const get = (k: string) => {
    const i = args.indexOf(k);
    return i >= 0 ? args[i + 1] : undefined;
  };
  const adapter = new CodexCliAdapter({
    gatewayUrl: get("--gateway"),
    room: get("--room"),
    agentName: get("--name"),
    workingDir: get("--working-dir"),
  });
  adapter.connect();
}
