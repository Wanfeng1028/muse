/**
 * 农历 ⇄ 公历换算 —— **只做历法，不做命理**。
 *
 * ★ 2026-08-05 抽出来的原因：
 *   1) 原生 App 的农历起盘一直得绕回网页层，因为 Swift 侧没有 lunar-javascript 的
 *      换算能力。`POST /api/lunar-to-solar` 让原生一次 HTTP 拿到公历日期，
 *      这是拆 WebView 的一个真障碍。
 *   2) 换算口径此前只长在 `lib/ziwei/share.ts` 里（表单专用）。接口再抄一份
 *      就会有两套闰月规则，所以统一收到这里，share.ts 改成调用本模块。
 *
 * 口径（沿用 lunar-javascript 与 share.ts 原有写法，未做任何改动）：
 *   · 闰月用**负月份**表示：闰五月 = -5。
 *   · 月天数与闰月是否存在，一律查 `LunarMonth` 表，不用公历的月长去猜。
 *
 * ⚠️ 这里**不许**出现排盘 / 时辰 / 真太阳时 / 四化 任何一行。
 *    那些属于 lib/ziwei/algorithm.ts 与 /api/generate，别顺手塞进来。
 */
import { Lunar, LunarMonth } from 'lunar-javascript';

export interface SolarDate {
  year: number;
  month: number;
  day: number;
}

/** 与 /api/generate 对齐的受理年份区间，超出直接判非法（lunar 表在极端年份不可靠） */
export const LUNAR_YEAR_MIN = 1900;
export const LUNAR_YEAR_MAX = 2050;

function isIntInRange(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;
}

/**
 * 该农历年该月的天数（29 或 30）。
 * 月份不存在（例如那年根本没有闰四月）返回 0。
 */
export function lunarMonthDayCount(year: number, month: number, isLeapMonth = false): number {
  if (!isIntInRange(year, LUNAR_YEAR_MIN, LUNAR_YEAR_MAX) || !isIntInRange(month, 1, 12)) return 0;
  try {
    const lunarMonth = LunarMonth.fromYm(year, isLeapMonth ? -month : month);
    const dayCount = lunarMonth?.getDayCount();
    return typeof dayCount === 'number' && Number.isInteger(dayCount) && dayCount > 0 ? dayCount : 0;
  } catch {
    return 0;
  }
}

/** 该农历年的闰月月份（1-12）；无闰月返回 0 */
export function leapMonthOfLunarYear(year: number): number {
  if (!isIntInRange(year, LUNAR_YEAR_MIN, LUNAR_YEAR_MAX)) return 0;
  for (let month = 1; month <= 12; month++) {
    if (lunarMonthDayCount(year, month, true) > 0) return month;
  }
  return 0;
}

/** 农历日期是否真实存在（含闰月是否存在、当月是否有这一天） */
export function isValidLunarDate(year: number, month: number, day: number, isLeapMonth = false): boolean {
  if (!isIntInRange(day, 1, 30)) return false;
  const dayCount = lunarMonthDayCount(year, month, isLeapMonth);
  return dayCount > 0 && day <= dayCount;
}

/**
 * 农历 → 公历。输入非法（年份越界 / 闰月不存在 / 当月没这天）一律返回 null，
 * **绝不静默滚动到相邻日期**——那会让用户排到一张错盘还不知道。
 */
export function lunarToSolar(year: number, month: number, day: number, isLeapMonth = false): SolarDate | null {
  if (!isValidLunarDate(year, month, day, isLeapMonth)) return null;
  try {
    const solar = Lunar.fromYmd(year, isLeapMonth ? -month : month, day).getSolar();
    const result = { year: solar.getYear(), month: solar.getMonth(), day: solar.getDay() };
    if (!Number.isInteger(result.year) || !Number.isInteger(result.month) || !Number.isInteger(result.day)) return null;
    return result;
  } catch {
    return null;
  }
}
