// 用户自己的解读访问记录（本地存储，按日去重）。
// 2026-11-01 纠正轮自 lib/tools.ts 原样移出：tools.ts 随门户趣味工具
// 一并删除；interpret 页的 recordReport 调用逻辑零动，仅 import 改指
// 这里。我的页“报告记录”入口已删（门户轮附加模块），目前暂无读取方，
// 写入继续（本地数据，用户自有），不编造任何他人数据。
import Taro from '@tarojs/taro';

export const REPORTS_KEY = 'zw_reports_v1';

export interface ReportItem {
  date: string;
  title: string;
}

function readList<T>(key: string): T[] {
  try { return (Taro.getStorageSync(key) as T[]) || []; } catch { return []; }
}

function writeList(key: string, value: unknown): void {
  try { Taro.setStorageSync(key, value); } catch { /* 存储失败时静默，页面仍可继续用 */ }
}

// 本地日期（YYYY-MM-DD）：小程序面向中国用户，日期边界必须按本地
// 时区算；UTC 日期在本地 0–8 点会差一天，故不用 toISOString。
function todayStr(d = new Date()): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

export function loadReports(): ReportItem[] { return readList<ReportItem>(REPORTS_KEY); }

// 解读页每次打开且已有命盘时记一条（同一天只记一次）：这是用户自己
// 的浏览记录，不是伪造的报告数据。
export function recordReport(): void {
  const today = todayStr();
  const list = loadReports();
  if (list.some((r) => r.date === today)) return;
  list.unshift({ date: today, title: '命盘解读' });
  writeList(REPORTS_KEY, list.slice(0, 100));
}
