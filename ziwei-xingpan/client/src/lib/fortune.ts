// 门户运势 / 万年历 / 八字的本地计算层。
//
// 一切分数都由排盘引擎实算，公式公开写在这里与 PORTAL.md 中，
// 绝不编造“多少人觉得准”类营销数字。无盘时调用方展示诚实空态，
// 本模块不对无盘造数。
import { Solar } from 'lunar-javascript';
import type { Palace, ZiweiChart } from '../engine/types';

export function palaceByName(chart: ZiweiChart, name: string): Palace | undefined {
  return chart.palaces.find((p) => p.name === name);
}

// 主星亮度分：庙 8、旺 6、得 4、利 2、平 0、不 -2、闲 -1、陷 -6、地 -4。
const BRIGHT_SCORE: Record<string, number> = {
  '庙': 8, '旺': 6, '得': 4, '利': 2, '平': 0, '不': -2, '闲': -1, '陷': -6, '地': -4,
};
// 四化分：禄 5、权 3、科 3、忌 -8。
const SIHUA_SCORE: Record<string, number> = { '禄': 5, '权': 3, '科': 3, '忌': -8 };

export function palaceScore(p?: Palace): number {
  if (!p) return 0;
  let score = 0;
  for (const s of p.stars) {
    if (s.type === 'major' && s.brightnessRaw) score += BRIGHT_SCORE[s.brightnessRaw] ?? 0;
    if (s.siHua) score += SIHUA_SCORE[s.siHua] ?? 0;
  }
  const lucky = p.stars.filter((s) => s.type === 'lucky').length;
  const sha = p.stars.filter((s) => s.type === 'sha').length;
  score += Math.min(lucky * 2, 6);
  score += Math.max(sha * -3, -9);
  return score;
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

// 单维分数：60 + 宫分，夹在 35 与 95 之间。
export function dimScore(p?: Palace): number {
  return clamp(60 + palaceScore(p), 35, 95);
}

export interface Fortune {
  dateLabel: string;
  weekday: string;
  lunarLabel: string;
  total: number;
  love: number;
  wealth: number;
  career: number;
  study: number;
  dayBranch: number;
  dayPalaceName: string;
  dayAdj: number;
  lovePalace: string;
  wealthPalace: string;
  careerPalace: string;
  studyPalace: string;
  band: string;
  oneLiner: string;
}

const ZODIAC = ['鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊', '猴', '鸡', '狗', '猪'];
const WEEKDAYS = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
const LUNAR_MONTHS = ['正月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '冬月', '腊月'];
const LUNAR_DAYS = [
  '初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
  '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
  '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十',
];

export function lunarMonthName(month: number): string {
  const leap = month < 0;
  const base = LUNAR_MONTHS[Math.abs(month) - 1] ?? '';
  return leap ? '闰' + base : base;
}

export function lunarDayName(day: number): string {
  return LUNAR_DAYS[day - 1] ?? '';
}

export function todayHeader(date: Date): { dateLabel: string; weekday: string; lunarLabel: string } {
  const lunar = Solar.fromYmd(date.getFullYear(), date.getMonth() + 1, date.getDate()).getLunar();
  return {
    dateLabel: `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`,
    weekday: WEEKDAYS[date.getDay()] ?? '',
    lunarLabel: `农历${lunarMonthName(lunar.getMonth())}${lunarDayName(lunar.getDay())}`,
  };
}

function bandLine(total: number): string {
  if (total >= 80) return '今日整体气色较顺，宜把重要安排放在状态好的时段。';
  if (total >= 65) return '今日平稳向好，按部就班即可，留意分数最高那一项的机缘。';
  return '今日宜放缓节奏，先稳住基本盘，再图其他。';
}

export function fortuneToday(chart: ZiweiChart, date: Date = new Date()): Fortune {
  const header = todayHeader(date);
  const loveP = palaceByName(chart, '夫妻');
  const wealthP = palaceByName(chart, '财帛');
  const careerP = palaceByName(chart, '官禄');
  const studyP = palaceByName(chart, '父母');
  const love = dimScore(loveP);
  const wealth = dimScore(wealthP);
  const career = dimScore(careerP);
  const study = dimScore(studyP);
  // 今日地支：lunar-javascript 当日生肖即当日地支（鼠=子……猪=亥）。
  const lunar = Solar.fromYmd(date.getFullYear(), date.getMonth() + 1, date.getDate()).getLunar();
  const dayBranch = ZODIAC.indexOf(lunar.getDayShengXiao());
  const dayPalace = dayBranch >= 0 ? chart.palaces.find((p) => p.branch === dayBranch) : undefined;
  const dayLucky = dayPalace ? dayPalace.stars.filter((s) => s.type === 'lucky').length : 0;
  const daySha = dayPalace ? dayPalace.stars.filter((s) => s.type === 'sha').length : 0;
  const dayAdj = dayLucky > 0 && daySha === 0 ? 4 : daySha > 0 && dayLucky === 0 ? -4 : 0;
  const total = clamp(Math.round((love + wealth + career + study) / 4 + dayAdj), 35, 95);
  return {
    ...header,
    total, love, wealth, career, study,
    dayBranch,
    dayPalaceName: dayPalace ? dayPalace.name : '',
    dayAdj,
    lovePalace: loveP ? loveP.name : '夫妻',
    wealthPalace: wealthP ? wealthP.name : '财帛',
    careerPalace: careerP ? careerP.name : '官禄',
    studyPalace: studyP ? studyP.name : '父母',
    band: total >= 80 ? '顺' : total >= 65 ? '稳' : '缓',
    oneLiner: bandLine(total),
  };
}

// ---- 八字：四柱取引擎 lunarInfo（节气四柱优先，农历口径备选），五行按天干地支映射计数。
const STEM_ELEMENT: Record<string, string> = {
  '甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
  '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水',
};
const BRANCH_ELEMENT: Record<string, string> = {
  '子': '水', '亥': '水', '寅': '木', '卯': '木', '巳': '火', '午': '火',
  '申': '金', '酉': '金', '辰': '土', '戌': '土', '丑': '土', '未': '土',
};

export interface Bazi {
  pillars: string[];
  dayMaster: string;
  dayMasterElement: string;
  counts: Record<string, number>;
}

export function baziOf(chart: ZiweiChart): Bazi {
  const pillars = chart.lunarInfo.fourPillars ?? chart.lunarInfo.fourPillarsLunar ?? [];
  const counts: Record<string, number> = { '金': 0, '木': 0, '水': 0, '火': 0, '土': 0 };
  for (const pillar of pillars) {
    for (const ch of pillar) {
      const el = STEM_ELEMENT[ch] ?? BRANCH_ELEMENT[ch];
      if (el) counts[el] += 1;
    }
  }
  const dayMaster = pillars[2]?.[0] ?? '';
  return { pillars, dayMaster, dayMasterElement: STEM_ELEMENT[dayMaster] ?? '', counts };
}

// ---- 万年历 / 老黄历 / 星宿：全部取 lunar-javascript 1.7.3 实测可用的方法。
// 实测：getDayYi/getDayJi/getXiu/getDayChong/getDaySha/getDayShengXiao/
// getDayGan/getDayZhi（干支须分开取，合并的 getDayGanZhi 不存在）、
// getJieQi/getFestivals 存在；getDayWuXing 不存在，故不展示日五行，
// 不编造。本文件不引入任何手写历法表。
export interface CalendarCell {
  y: number;
  m: number;
  d: number;
  inMonth: boolean;
  lunarLabel: string;
  jieqi: string;
  festivals: string;
  isToday: boolean;
}

function cellOf(y: number, m: number, d: number, inMonth: boolean, today: Date): CalendarCell {
  const solar = Solar.fromYmd(y, m, d);
  const lunar = solar.getLunar();
  const lMonth = lunar.getMonth();
  const lDay = lunar.getDay();
  const lunarLabel = lDay === 1 ? lunarMonthName(lMonth) : lunarDayName(lDay);
  const festivals = [...solar.getFestivals(), ...lunar.getFestivals()].join(' ');
  return {
    y, m, d, inMonth, lunarLabel,
    jieqi: lunar.getJieQi() || '',
    festivals,
    isToday: y === today.getFullYear() && m === today.getMonth() + 1 && d === today.getDate(),
  };
}

export function calendarMonth(year: number, month: number, today: Date = new Date()): CalendarCell[][] {
  const first = new Date(year, month - 1, 1);
  const startOffset = first.getDay(); // 周日为首列
  const daysInMonth = new Date(year, month, 0).getDate();
  const daysInPrev = new Date(year, month - 1, 0).getDate();
  const cells: CalendarCell[] = [];
  for (let i = startOffset - 1; i >= 0; i--) {
    const d = daysInPrev - i;
    const prev = month === 1 ? { y: year - 1, m: 12 } : { y: year, m: month - 1 };
    cells.push(cellOf(prev.y, prev.m, d, false, today));
  }
  for (let d = 1; d <= daysInMonth; d++) cells.push(cellOf(year, month, d, true, today));
  while (cells.length % 7 !== 0) {
    const d = cells.length - startOffset - daysInMonth + 1;
    const next = month === 12 ? { y: year + 1, m: 1 } : { y: year, m: month + 1 };
    cells.push(cellOf(next.y, next.m, d, false, today));
  }
  const weeks: CalendarCell[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

export interface DayInfo {
  lunarFull: string;
  ganzhiDay: string;
  yi: string[];
  ji: string[];
  xiu: string;
  chong: string;
  sha: string;
  dayShengxiao: string;
  jieqi: string;
  festivals: string;
}

export function dayInfo(y: number, m: number, d: number): DayInfo {
  const solar = Solar.fromYmd(y, m, d);
  const lunar = solar.getLunar();
  return {
    lunarFull: `${lunar.getYearShengXiao()}年${lunarMonthName(lunar.getMonth())}${lunarDayName(lunar.getDay())}`,
    ganzhiDay: `${lunar.getDayGan()}${lunar.getDayZhi()}`,
    yi: lunar.getDayYi(),
    ji: lunar.getDayJi(),
    xiu: lunar.getXiu() || '',
    chong: lunar.getDayChong() || '',
    sha: lunar.getDaySha() || '',
    dayShengxiao: lunar.getDayShengXiao(),
    jieqi: lunar.getJieQi() || '',
    festivals: [...solar.getFestivals(), ...lunar.getFestivals()].join(' '),
  };
}
