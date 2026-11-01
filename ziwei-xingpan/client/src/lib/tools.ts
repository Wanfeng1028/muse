// 门户趣味工具的本地存储层（许愿 / 祈福 / 解梦 / 报告记录）。
// 纯数据与纯逻辑（MBTI、塔罗、六爻、骰子、占星师人格）见 tools-data.ts，
// 本文件只留 Taro 存储调用，便于自检脚本不依赖 Taro 运行时。
import Taro from '@tarojs/taro';
export * from './tools-data';

// ---- 许愿 / 祈福 / 解梦 / 报告记录：全部本地存储，不编造他人数据。
export const WISHES_KEY = 'zw_wishes_v1';
export const PRAYER_KEY = 'zw_prayer_v1';
export const DREAMS_KEY = 'zw_dreams_v1';
export const REPORTS_KEY = 'zw_reports_v1';

export interface WishItem {
  text: string;
  date: string;
}

function readList<T>(key: string): T[] {
  try { return (Taro.getStorageSync(key) as T[]) || []; } catch { return []; }
}

function writeList(key: string, value: unknown): void {
  try { Taro.setStorageSync(key, value); } catch { /* 存储失败时静默，页面仍可继续用 */ }
}

// 本地日期（YYYY-MM-DD）：小程序面向中国用户，日期边界必须按本地
// 时区算；UTC 日期在本地 0–8 点会差一天，导致祈福连续天数与当日
// 判定在午夜附近错位，故不用 toISOString。
function todayStr(d = new Date()): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function yesterdayStr(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return todayStr(d);
}

export function loadWishes(): WishItem[] { return readList<WishItem>(WISHES_KEY); }

export function addWish(text: string): WishItem[] {
  const list = loadWishes();
  list.unshift({ text, date: todayStr() });
  writeList(WISHES_KEY, list.slice(0, 50));
  return list.slice(0, 50);
}

export interface PrayerState {
  lastDate: string;
  streak: number;
}

const PRAYER_LINES = [
  '愿今日心安事顺，所求皆有回音。',
  '愿脚步稳、心境宽，好运藏在日常里。',
  '愿所遇皆良善，所行皆坦途。',
  '愿家人安康，自己也有力气向前。',
  '愿今日的小事都顺遂，大事有转机。',
  '愿心中有光，走到哪里都不慌。',
  '愿努力被看见，付出有回响。',
  '愿今日平安喜乐，来日皆可期。',
];

export function prayerToday(): { line: string; streak: number; doneToday: boolean } {
  const today = todayStr();
  let state: PrayerState = { lastDate: '', streak: 0 };
  try { state = (Taro.getStorageSync(PRAYER_KEY) as PrayerState) || state; } catch { /* ignore */ }
  const dayOfYear = Math.floor((new Date().getTime() - new Date(new Date().getFullYear(), 0, 0).getTime()) / 86400000);
  return {
    line: PRAYER_LINES[dayOfYear % PRAYER_LINES.length],
    streak: state.streak,
    doneToday: state.lastDate === today,
  };
}

export function doPrayer(): { streak: number } {
  const today = todayStr();
  let state: PrayerState = { lastDate: '', streak: 0 };
  try { state = (Taro.getStorageSync(PRAYER_KEY) as PrayerState) || state; } catch { /* ignore */ }
  if (state.lastDate === today) return { streak: state.streak };
  const yesterday = yesterdayStr();
  const streak = state.lastDate === yesterday ? state.streak + 1 : 1;
  writeList(PRAYER_KEY, { lastDate: today, streak });
  return { streak };
}

export function loadDreams(): WishItem[] { return readList<WishItem>(DREAMS_KEY); }

export function addDream(text: string): WishItem[] {
  const list = loadDreams();
  list.unshift({ text, date: todayStr() });
  writeList(DREAMS_KEY, list.slice(0, 50));
  return list.slice(0, 50);
}

export interface ReportItem {
  date: string;
  title: string;
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

