// 职责：导出协议 v1.3 的全部时间/数量常量与退避计算函数。
// 无副作用；退避抖动的叠加由调用方负责。

export const PROTOCOL_VERSION = 1 as const;
export const PROTOCOL_VERSION_STR = "1.3";

export const HEARTBEAT_MS = 20000;
export const OFFLINE_AFTER_MS = 45000;
export const ZOMBIE_SWEEP_MS = 15000;

export const BACKOFF_MIN_MS = 1000;
export const BACKOFF_MAX_MS = 30000;

export const DEDUP_WINDOW = 500;

export const RESEND_MAX_MSGS = 200;
export const RESEND_MAX_BYTES = 65536;

export const STREAM_DANGLING_MS = 60000;
export const GAP_RESEND_MS = 5000;

export const UPLOAD_URL_WINDOW_MS = 300000;

/** 审批门：任务挂起等待人工放行的最长毫秒数，超时自动取消。 */
export const APPROVAL_TTL_MS = 300000;

/**
 * 指数退避：attempt 从 0 起，delay = min(30000, 1000 * 2^attempt)。
 * 抖动由调用方在此结果上叠加，本函数不加抖动。
 */
export function backoffDelay(attempt: number): number {
  const raw = BACKOFF_MIN_MS * Math.pow(2, attempt);
  return Math.min(BACKOFF_MAX_MS, raw);
}
