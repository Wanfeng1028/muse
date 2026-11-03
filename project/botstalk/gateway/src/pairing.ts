import { createHash } from "node:crypto";

const CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

// 生成形如 ABCD-EFGH 的 8 字符配对码
export function generatePairingCode(random: () => number = Math.random): string {
  let code = "";
  for (let i = 0; i < 8; i++) {
    code += CHARSET[Math.floor(random() * CHARSET.length)];
  }
  return `${code.slice(0, 4)}-${code.slice(4)}`;
}

// 归一化配对码：去连字符与空白、转大写，校验后返回 8 字符或 null
export function normalizePairingCode(input: unknown): string | null {
  if (typeof input !== "string") return null;
  const cleaned = input.replace(/[-\s]/g, "").toUpperCase();
  if (/^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{8}$/.test(cleaned)) {
    return cleaned;
  }
  return null;
}

// 将归一化的 8 字符配对码格式化为 4+4 连字符形式
export function formatPairingCode(normalized: string): string {
  return `${normalized.slice(0, 4)}-${normalized.slice(4)}`;
}

// 对归一化的配对码进行 SHA-256 哈希
export function hashPairingCode(normalized: string): string {
  return createHash("sha256").update(normalized).digest("hex");
}

// 钳制配对码有效时长（分钟）至 [1, 60] 区间
export function clampPairingTtlMinutes(input: unknown, fallback = 10): number {
  const clampedFallback = Math.max(1, Math.min(60, fallback));
  if (typeof input !== "number" || !Number.isInteger(input) || !Number.isFinite(input) || input <= 0) {
    return clampedFallback;
  }
  return Math.max(1, Math.min(60, input));
}

export interface PairingCodeRecord {
  codeHash: string;
  room: string;
  createdAtMs: number;
  expiresAtMs: number;
  redeemedAtMs: number | null;
  redeemedAdapterId: string | null;
}

// 判断配对码是否已过期
export function isPairingExpired(record: PairingCodeRecord, nowMs: number): boolean {
  return nowMs > record.expiresAtMs;
}

// 判断配对码是否已兑换
export function isPairingRedeemed(record: PairingCodeRecord): boolean {
  return record.redeemedAtMs !== null;
}
