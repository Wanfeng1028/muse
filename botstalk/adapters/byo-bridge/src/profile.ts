import { chmodSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// 每个 BYO agent 一份本地 profile：非秘密的身份与 provider 启动配置。
// 目录布局：<byoHome>/<agentId>/profile.json（默认 ~/.botstalk/byo/，可用
// BOTSTALK_BYO_DIR 或 XDG_CONFIG_HOME 覆盖）。

export interface ByoProviderConfig {
  command: string;
  args: string[];
  cwd: string;
}

export interface ByoProfile {
  agentId: string;
  gatewayUrl: string;
  room: string;
  provider: ByoProviderConfig;
  createdAtMs: number;
  updatedAtMs: number;
}

export function byoHomeDir(env: NodeJS.ProcessEnv = process.env): string {
  if (env.BOTSTALK_BYO_DIR) return env.BOTSTALK_BYO_DIR;
  if (env.XDG_CONFIG_HOME) return join(env.XDG_CONFIG_HOME, "botstalk", "byo");
  return join(homedir(), ".botstalk", "byo");
}

export function profilePath(homeDir: string, agentId: string): string {
  return join(homeDir, agentId, "profile.json");
}

export function validateProfile(p: unknown): p is ByoProfile {
  if (typeof p !== "object" || p === null) return false;
  const o = p as Record<string, unknown>;
  if (typeof o.agentId !== "string" || o.agentId.length === 0) return false;
  if (typeof o.gatewayUrl !== "string" || o.gatewayUrl.length === 0) return false;
  if (typeof o.room !== "string" || o.room.length === 0) return false;
  if (typeof o.provider !== "object" || o.provider === null) return false;
  const provider = o.provider as Record<string, unknown>;
  if (typeof provider.command !== "string" || provider.command.length === 0) return false;
  if (!Array.isArray(provider.args) || !provider.args.every((a) => typeof a === "string")) return false;
  if (typeof provider.cwd !== "string" || provider.cwd.length === 0) return false;
  if (typeof o.createdAtMs !== "number" || !Number.isFinite(o.createdAtMs)) return false;
  if (typeof o.updatedAtMs !== "number" || !Number.isFinite(o.updatedAtMs)) return false;
  return true;
}

export function saveProfile(homeDir: string, profile: ByoProfile): void {
  const dir = join(homeDir, profile.agentId);
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const file = profilePath(homeDir, profile.agentId);
  writeFileSync(file, `${JSON.stringify(profile, null, 2)}\n`, { mode: 0o600 });
  try {
    chmodSync(file, 0o600);
  } catch {
    // 权限收紧失败不阻断保存（例如个别文件系统不支持 chmod）。
  }
}

export function loadProfile(homeDir: string, agentId: string): ByoProfile | null {
  let content: string;
  try {
    content = readFileSync(profilePath(homeDir, agentId), "utf8");
  } catch {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    return null;
  }
  return validateProfile(parsed) ? parsed : null;
}

export function listProfiles(homeDir: string): ByoProfile[] {
  let entries: string[];
  try {
    entries = readdirSync(homeDir, { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => e.name);
  } catch {
    return [];
  }
  const profiles: ByoProfile[] = [];
  for (const name of entries) {
    const profile = loadProfile(homeDir, name);
    if (profile !== null) profiles.push(profile);
  }
  return profiles;
}
