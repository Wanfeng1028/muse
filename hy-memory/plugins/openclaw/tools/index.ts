import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import type { HyMemoryConfig, HyMemoryProvider } from "../types.ts";

import { createMemorySearchTool } from "./memory-search.ts";
import { createMemoryAddTool } from "./memory-add.ts";
import { createMemoryGetTool } from "./memory-get.ts";
import { createMemoryUpdateTool } from "./memory-update.ts";
import { createMemoryDeleteTool } from "./memory-delete.ts";

export interface ToolDeps {
  api: OpenClawPluginApi;
  provider: HyMemoryProvider;
  cfg: HyMemoryConfig;
}

export function registerAllTools(deps: ToolDeps): void {
  const { api } = deps;
  const nonOptional = { optional: false };

  api.registerTool(createMemorySearchTool(deps), nonOptional);
  api.registerTool(createMemoryAddTool(deps), nonOptional);
  api.registerTool(createMemoryGetTool(deps), nonOptional);
  api.registerTool(createMemoryUpdateTool(deps), nonOptional);
  api.registerTool(createMemoryDeleteTool(deps), nonOptional);
}
