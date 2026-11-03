import { createHash } from "node:crypto";

const SHARE_TOKEN_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

// 生成 32 位只读分享令牌，字符取自字母数字字符集。
export function generateShareToken(random: () => number = Math.random): string {
  let token = "";
  for (let i = 0; i < 32; i++) {
    token += SHARE_TOKEN_CHARSET[Math.floor(random() * SHARE_TOKEN_CHARSET.length)];
  }
  return token;
}

// 校验并规范化分享令牌：仅接受 trim 后长度 32 的字母数字串，且保持原样。
export function normalizeShareToken(input: unknown): string | null {
  if (typeof input !== "string") return null;
  const trimmed = input.trim();
  if (/^[A-Za-z0-9]{32}$/.test(trimmed)) {
    return trimmed;
  }
  return null;
}

// 计算分享令牌的 sha256 十六进制摘要，用于存储与比对。
export function hashShareToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

// 将分享有效期（小时）钳制到 [1, 720]，非法输入回退到同样钳制后的 fallback。
export function clampShareTtlHours(input: unknown, fallback = 168): number {
  const clampedFallback = Math.max(1, Math.min(720, fallback));
  if (typeof input !== "number" || !Number.isInteger(input) || !Number.isFinite(input) || input <= 0) {
    return clampedFallback;
  }
  return Math.max(1, Math.min(720, input));
}

export interface ShareLinkRecord {
  id: string;
  tokenHash: string;
  room: string;
  createdAtMs: number;
  expiresAtMs: number;
  revokedAtMs: number | null;
}

// 判断分享链接在给定时间点是否已过期。
export function isShareExpired(record: ShareLinkRecord, nowMs: number): boolean {
  return nowMs > record.expiresAtMs;
}

// 判断分享链接是否已被吊销。
export function isShareRevoked(record: ShareLinkRecord): boolean {
  return record.revokedAtMs !== null;
}

// 判断分享链接当前是否可用：既未过期也未吊销。
export function isShareUsable(record: ShareLinkRecord, nowMs: number): boolean {
  return !isShareExpired(record, nowMs) && !isShareRevoked(record);
}
