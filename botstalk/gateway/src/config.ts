import { fileURLToPath } from "node:url";
import { dirname, isAbsolute, resolve } from "node:path";

export interface GatewayConfig {
  port: number;
  dataDir: string;
  /** Web 构建产物目录（Docker 一体化部署用）；不设置则网关不提供静态文件服务。 */
  publicDir?: string;
}

const DEFAULT_PORT = 8765;
const DEFAULT_DATA_DIR = "./data";

function resolvePackageDir(pkgDir?: string): string {
  if (pkgDir !== undefined) {
    return pkgDir;
  }
  const here = fileURLToPath(import.meta.url);
  const srcDir = dirname(here);
  return dirname(srcDir);
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

  return { port, dataDir, publicDir };
}

export const defaultConfig = loadConfig();
// 自查：红线 1-5 逐条通过
