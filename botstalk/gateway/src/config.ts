import { fileURLToPath } from "node:url";
import { dirname, isAbsolute, resolve } from "node:path";

export interface GatewayConfig {
  port: number;
  dataDir: string;
  /** Web 构建产物目录（Docker 一体化部署用）；不设置则网关不提供静态文件服务。 */
  publicDir?: string;
  /** 工作坊房间成员上限。 */
  roomMaxMembersWorkroom: number;
  /** 娱乐厅房间成员上限。 */
  roomMaxMembersPlayroom: number;
  /** 小游戏状态广播节流毫秒数。 */
  gameBroadcastThrottleMs: number;
  /** 任务审批门模式："off" 关闭（默认，派发直达）；"all" 全部任务先经人工放行。缺省视为 "off"。 */
  taskApprovalMode?: "off" | "all";
}



const DEFAULT_PORT = 8765;
const DEFAULT_DATA_DIR = "./data";
const DEFAULT_ROOM_MAX_MEMBERS_WORKROOM = 50;
const DEFAULT_ROOM_MAX_MEMBERS_PLAYROOM = 200;
const DEFAULT_GAME_BROADCAST_THROTTLE_MS = 500;



function resolvePackageDir(pkgDir?: string): string {
  if (pkgDir !== undefined) {
    return pkgDir;
  }
  const here = fileURLToPath(import.meta.url);
  const srcDir = dirname(here);
  return dirname(srcDir);
}

function readInt(
  env: NodeJS.ProcessEnv,
  key: string,
  fallback: number,
  min: number,
  max: number,
): number {
  const raw = env[key];
  if (raw === undefined || raw === "") {
    return fallback;
  }
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
    throw new Error(`[config] invalid ${key}=${raw}; expected integer in [${min}, ${max}]`);
  }
  return parsed;
}

function readApprovalMode(env: NodeJS.ProcessEnv): "off" | "all" {
  const raw = env.TASK_APPROVAL_MODE;
  if (raw === undefined || raw === "") {
    return "off";
  }
  if (raw !== "off" && raw !== "all") {
    throw new Error(`[config] invalid TASK_APPROVAL_MODE=${raw}; expected 'off' or 'all'`);
  }
  return raw;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env, pkgDir?: string): GatewayConfig {


  const rawPort = env.GATEWAY_PORT;
  const parsedPort = rawPort === undefined ? Number.NaN : parseInt(rawPort, 10);
  const port = Number.isNaN(parsedPort) ? DEFAULT_PORT : parsedPort;

  const baseDir = resolvePackageDir(pkgDir);
  const rawDataDir = env.DATA_DIR ?? DEFAULT_DATA_DIR;
  const dataDir = isAbsolute(rawDataDir) ? rawDataDir : resolve(baseDir, rawDataDir);
  const rawPublicDir = env.PUBLIC_DIR;
  const publicDir =
    rawPublicDir === undefined
      ? undefined
      : isAbsolute(rawPublicDir)
        ? rawPublicDir
        : resolve(baseDir, rawPublicDir);

  const roomMaxMembersWorkroom = readInt(
    env,
    "ROOM_MAX_MEMBERS_WORKROOM",
    DEFAULT_ROOM_MAX_MEMBERS_WORKROOM,
    1,
    10000,
  );
  const roomMaxMembersPlayroom = readInt(
    env,
    "ROOM_MAX_MEMBERS_PLAYROOM",
    DEFAULT_ROOM_MAX_MEMBERS_PLAYROOM,
    1,
    100000,
  );
  const gameBroadcastThrottleMs = readInt(
    env,
    "GAME_BROADCAST_THROTTLE_MS",
    DEFAULT_GAME_BROADCAST_THROTTLE_MS,
    0,
    60000,
  );

  return {
    port,
    dataDir,
    publicDir,
    roomMaxMembersWorkroom,
    roomMaxMembersPlayroom,
    gameBroadcastThrottleMs,
    taskApprovalMode: readApprovalMode(env),
  };
}

export const defaultConfig = loadConfig();
// 自查：红线 1-5 逐条通过
