// 描述符数据源自 openagents-org/openagents（Apache-2.0）
// 包代码本身沿用仓库 MIT 许可

export type {
  AgentDescriptor,
  Logo,
  Support,
  InstallInfo,
  UninstallInfo,
  Adapter,
  Launch,
  CheckReady,
  Probe,
  EnvConfigItem,
  ResolveEnvRule,
  ResolveEnv,
} from "./schema.js";

import { Registry, DEFAULT_SUPPORT } from "./registry.js";
export { Registry, DEFAULT_SUPPORT };

/** 全局单例 */
export const registry = new Registry();
