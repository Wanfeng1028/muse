import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

// BYO agent 入驻链接：一次性令牌 + 30 分钟有效期的邀请链接（BotsTalk 自有格式）。
// 链接本身携带令牌，只存其 sha256 摘要，原文不落盘。

export interface ByoLink {
  gatewayUrl: string;
  room: string;
  agentId: string;
  token: string;
  expiresAtMs: number;
}

export class LinkError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(`${code}: ${message}`);
    this.name = "LinkError";
    this.code = code;
  }
}

const AGENT_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$/;
const REQUIRED_PARAMS = ["gateway", "room", "agent", "token", "exp"] as const;

export function parseLink(raw: string): ByoLink {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new LinkError("invalid_url", "link is not a valid URL");
  }
  if (url.protocol !== "botstalk:" && url.protocol !== "https:") {
    throw new LinkError("invalid_url", `unsupported link protocol: ${url.protocol}`);
  }
  for (const name of REQUIRED_PARAMS) {
    if (!url.searchParams.get(name)) {
      throw new LinkError("missing_param", `missing required param: ${name}`);
    }
  }
  const gateway = url.searchParams.get("gateway") as string;
  const room = url.searchParams.get("room") as string;
  const agent = url.searchParams.get("agent") as string;
  const token = url.searchParams.get("token") as string;
  const expRaw = url.searchParams.get("exp") as string;

  let gatewayUrl: URL;
  try {
    gatewayUrl = new URL(gateway);
  } catch {
    throw new LinkError("invalid_gateway", "gateway param is not a valid URL");
  }
  if (gatewayUrl.protocol !== "ws:" && gatewayUrl.protocol !== "wss:") {
    throw new LinkError("invalid_gateway", `gateway must be ws: or wss:, got ${gatewayUrl.protocol}`);
  }
  if (!AGENT_ID_PATTERN.test(agent)) {
    throw new LinkError("invalid_agent", "agent id does not match required pattern");
  }
  if (token.length < 16) {
    throw new LinkError("invalid_token", "token length must be at least 16");
  }
  const expNum = Number(expRaw);
  if (!Number.isInteger(expNum)) {
    throw new LinkError("invalid_exp", "exp must be an integer epoch-ms value");
  }
  return {
    gatewayUrl: gateway,
    room,
    agentId: agent,
    token,
    expiresAtMs: expNum,
  };
}

export function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export interface RedemptionRecord {
  tokenHash: string;
  agentId: string;
  redeemedAtMs: number;
}

export function redemptionPath(stateDir: string): string {
  return join(stateDir, "byo-link.json");
}

export function readRedemption(stateDir: string): RedemptionRecord | null {
  let content: string;
  try {
    content = readFileSync(redemptionPath(stateDir), "utf8");
  } catch {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const record = parsed as Record<string, unknown>;
  const tokenHash = record.tokenHash;
  const agentId = record.agentId;
  const redeemedAtMs = record.redeemedAtMs;
  if (typeof tokenHash !== "string" || !/^[0-9a-f]{64}$/.test(tokenHash)) return null;
  if (typeof agentId !== "string" || agentId.length === 0) return null;
  if (typeof redeemedAtMs !== "number" || !Number.isFinite(redeemedAtMs)) return null;
  return { tokenHash, agentId, redeemedAtMs };
}

export function redeemLink(stateDir: string, link: ByoLink, nowMs: number): "redeemed" | "already" {
  if (nowMs > link.expiresAtMs) {
    throw new LinkError("link_expired", "link has expired");
  }
  const existing = readRedemption(stateDir);
  if (existing !== null) {
    if (existing.tokenHash === hashToken(link.token) && existing.agentId === link.agentId) {
      // 同一安装中断后重跑同一条链接：幂等成功。
      return "already";
    }
    throw new LinkError("link_already_used", "a different link was already redeemed on this installation");
  }
  mkdirSync(stateDir, { recursive: true });
  const record: RedemptionRecord = {
    tokenHash: hashToken(link.token),
    agentId: link.agentId,
    redeemedAtMs: nowMs,
  };
  writeFileSync(redemptionPath(stateDir), `${JSON.stringify(record, null, 2)}\n`, { mode: 0o600 });
  return "redeemed";
}
