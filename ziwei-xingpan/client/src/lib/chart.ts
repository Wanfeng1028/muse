import Taro from '@tarojs/taro';
import { generateChart } from '../engine/algorithm';
import { calculateTrueSolarTime, branchFromSolarMinutes } from '../engine/true-solar-time';
import { isChinaDST } from '../engine/dst-cn';
import { clockToStandardDelta, shiftClock, formatClock } from '../engine/clock-adjust';
import type { ZiweiChart } from '../engine/types';
import { BRANCHES, SHICHEN, STEMS } from '../engine/constants';

export interface BirthFormInput {
  name: string;
  gender: 'male' | 'female';
  date: string; // YYYY-MM-DD, clock date as entered
  clockHour: number;
  clockMinute: number;
  province: string;
  city: string;
  longitude: number;
  // Effective branch used for the chart (may differ from clock branch after a manual correction).
  branch: number;
  // Manual, reversible corrections the user applied; empty = none applied.
  corrections: string[];
  // Original clock input, kept so every correction can be undone.
  originalClockHour: number;
  originalClockMinute: number;
  originalDate: string;
}

export const STORAGE_INPUT = 'zw_input_v1';
export const STORAGE_CHART = 'zw_chart_v1';

export function branchFromClock(hour: number): number {
  return Math.floor((((hour + 1) % 24)) / 2);
}

export function shichenLabel(branch: number): string {
  return SHICHEN[branch]?.name ?? '';
}

export function shichenRange(branch: number): string {
  return SHICHEN[branch]?.range ?? '';
}

export function parseDate(date: string): { year: number; month: number; day: number } {
  const [y, m, d] = date.split('-').map((v) => parseInt(v, 10));
  return { year: y, month: m, day: d };
}

export function formatDate(y: number, m: number, d: number): string {
  const p = (v: number) => String(v).padStart(2, '0');
  return `${y}-${p(m)}-${p(d)}`;
}

export function shiftDate(date: string, offset: number): string {
  const { year, month, day } = parseDate(date);
  const dt = new Date(Date.UTC(year, month - 1, day + offset));
  return formatDate(dt.getUTCFullYear(), dt.getUTCMonth() + 1, dt.getUTCDate());
}

export function buildChart(input: BirthFormInput): ZiweiChart {
  const { year, month, day } = parseDate(input.date);
  return generateChart({
    year,
    month,
    day,
    hour: input.branch,
    gender: input.gender,
    name: input.name || undefined,
    province: input.province,
    city: input.city,
    longitude: input.longitude,
  });
}

export function saveInput(input: BirthFormInput): void {
  Taro.setStorageSync(STORAGE_INPUT, input);
  try {
    Taro.setStorageSync(STORAGE_CHART, buildChart(input));
  } catch (e) {
    Taro.setStorageSync(STORAGE_CHART, null);
    throw e;
  }
}

export function loadInput(): BirthFormInput | null {
  try { return (Taro.getStorageSync(STORAGE_INPUT) as BirthFormInput) || null; } catch { return null; }
}

export function loadChart(): ZiweiChart | null {
  try { return (Taro.getStorageSync(STORAGE_CHART) as ZiweiChart) || null; } catch { return null; }
}

export interface CorrectionPreview {
  isDst: boolean;
  dstNote: string;
  solar: ReturnType<typeof calculateTrueSolarTime> | null;
  solarBranch: number | null;
  clockShifted: string | null;
}

/** Pure preview: never mutates the input. Corrections only apply when the user taps a button. */
export function previewCorrections(input: BirthFormInput): CorrectionPreview {
  const { year, month, day } = parseDate(input.date);
  const isDst = isChinaDST(year, month, day);
  const solar = calculateTrueSolarTime({
    year, month, day,
    clockHour: input.clockHour, clockMinute: input.clockMinute,
    longitude: input.longitude,
  });
  const solarBranch = solar ? branchFromSolarMinutes(solar.normalizedMinutes) : null;
  const shifted = isDst
    ? shiftClock(
      { clockHour: String(input.clockHour), clockMinute: String(input.clockMinute) },
      clockToStandardDelta(540, 480),
    )
    : null;
  return {
    isDst,
    dstNote: isDst ? '该日期处于中国大陆夏令时期间（通行口径表），钟表读数可能比标准时间快 1 小时。' : '',
    solar,
    solarBranch,
    clockShifted: shifted ? formatClock(shifted) : null,
  };
}

export function stemBranchLabel(stem: number, branch: number): string {
  return `${STEMS[stem] ?? ''}${BRANCHES[branch] ?? ''}`;
}

export function branchLabel(branch: number): string {
  return BRANCHES[branch] ?? '';
}

export const DISCLAIMER = '内容源自传统紫微斗数文化，仅供学习与娱乐参考，不构成人生决策建议。';
