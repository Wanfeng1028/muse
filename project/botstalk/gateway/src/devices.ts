import { createHash, randomBytes } from "node:crypto";

// 生成并返回 64 个字符的小写十六进制格式的设备密钥
export function generateDeviceKey(): string {
  return randomBytes(32).toString("hex");
}

// 对设备密钥进行 SHA-256 哈希并返回十六进制字符串
export function hashDeviceKey(key: string): string {
  return createHash("sha256").update(key).digest("hex");
}

// 去除首尾空格且长度在 1 到 128 之间的字符串返回原值，否则返回 null
export function normalizeDeviceId(input: unknown): string | null {
  if (typeof input !== "string") return null;
  const trimmed = input.trim();
  return trimmed.length >= 1 && trimmed.length <= 128 ? trimmed : null;
}

// 定义设备记录接口
export interface DeviceRecord {
  device_id: string;
  room: string;
  device_key_hash: string;
  adapter_id: string;
  created_at_ms: number;
  last_seen_ms: number;
  revoked_at_ms: number | null;
}

// 检查设备记录中的撤销时间戳是否不为空
export function isDeviceRevoked(record: DeviceRecord): boolean {
  return record.revoked_at_ms !== null;
}
