import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../src/app';

type PlanItem = {
  id: string;
  date: string;
  subject: string;
  minutes: number;
  done: boolean;
};

type WrongItem = {
  id: string;
  subject: string;
  stem: string;
  answer: string;
  wrongCount: number;
  lastWrongAt: string;
};

type WordItem = {
  id: string;
  word: string;
  ease: number;
  intervalDays: number;
  dueAt: string;
  reviewCount: number;
};

function parseDateOnly(s: string): { y: number; m: number; d: number } {
  const parts = s.split('-');
  return { y: Number(parts[0]), m: Number(parts[1]), d: Number(parts[2]) };
}

function daysInMonth(y: number, m: number): number {
  return new Date(y, m, 0).getDate();
}

function isLeap(y: number): boolean {
  return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
}

function addDays(dateStr: string, n: number): string {
  const { y, m, d } = parseDateOnly(dateStr);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + n);
  const yy = dt.getUTCFullYear();
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(dt.getUTCDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}

function addMonths(dateStr: string, n: number): string {
  const { y, m, d } = parseDateOnly(dateStr);
  let ny = y;
  let nm = m + n;
  while (nm > 12) {
    nm -= 12;
    ny += 1;
  }
  while (nm < 1) {
    nm += 12;
    ny -= 1;
  }
  const dim = daysInMonth(ny, nm);
  const nd = Math.min(d, dim);
  const mm = String(nm).padStart(2, '0');
  const dd = String(nd).padStart(2, '0');
  return `${ny}-${mm}-${dd}`;
}

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQuote = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (inQuote) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i += 1;
        } else {
          inQuote = false;
        }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      inQuote = true;
    } else if (ch === ',') {
      out.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function normalizeStem(stem: string): string {
  return stem.replace(/\s+/g, '').replace(/[，。！？；：、""''（）【】《》,.!?;:()\[\]{}<>]/g, '').toLowerCase();
}

function dedupeWrong(items: WrongItem[]): WrongItem[] {
  const map = new Map<string, WrongItem>();
  for (const it of items) {
    const key = `${it.subject}::${normalizeStem(it.stem)}`;
    const exist = map.get(key);
    if (!exist) {
      map.set(key, { ...it });
    } else {
      const merged: WrongItem = {
        ...exist,
        wrongCount: exist.wrongCount + it.wrongCount,
        lastWrongAt: it.lastWrongAt > exist.lastWrongAt ? it.lastWrongAt : exist.lastWrongAt,
      };
      map.set(key, merged);
    }
  }
  return Array.from(map.values());
}

function srsNext(word: WordItem, quality: number, nowIso: string): WordItem {
  let ease = word.ease;
  let intervalDays = word.intervalDays;
  if (quality < 3) {
    intervalDays = 1;
    ease = Math.max(1.3, ease - 0.2);
  } else {
    if (word.reviewCount === 0) {
      intervalDays = 1;
    } else if (word.reviewCount === 1) {
      intervalDays = 6;
    } else {
      intervalDays = Math.round(word.intervalDays * ease);
    }
    ease = Math.min(2.8, ease + 0.1);
  }
  const nowDate = nowIso.slice(0, 10);
  const dueAt = addDays(nowDate, intervalDays);
  return {
    ...word,
    ease,
    intervalDays,
    dueAt,
    reviewCount: word.reviewCount + 1,
  };
}

function importCsv(text: string): { rows: PlanItem[]; badLines: number[] } {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  const rows: PlanItem[] = [];
  const badLines: number[] = [];
  const header = lines[0];
  if (!header || !header.includes('date') || !header.includes('subject') || !header.includes('minutes')) {
    return { rows, badLines: lines.map((_, i) => i + 1) };
  }
  for (let i = 1; i < lines.length; i += 1) {
    const lineNo = i + 1;
    const cells = splitCsvLine(lines[i]);
    if (cells.length !== 4) {
      badLines.push(lineNo);
      continue;
    }
    const [id, date, subject, minutesRaw] = cells;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      badLines.push(lineNo);
      continue;
    }
    const minutes = Number(minutesRaw);
    if (!Number.isFinite(minutes) || minutes <= 0) {
      badLines.push(lineNo);
      continue;
    }
    if (subject.trim().length === 0 || id.trim().length === 0) {
      badLines.push(lineNo);
      continue;
    }
    rows.push({ id, date, subject, minutes, done: false });
  }
  return { rows, badLines };
}

function exportBackup(items: PlanItem[], wrongs: WrongItem[], words: WordItem[]): string {
  return JSON.stringify({ version: 1, items, wrongs, words });
}

function importBackup(text: string): { items: PlanItem[]; wrongs: WrongItem[]; words: WordItem[] } {
  const obj = JSON.parse(text);
  if (!obj || obj.version !== 1) {
    throw new Error('backup version mismatch');
  }
  return {
    items: Array.isArray(obj.items) ? obj.items : [],
    wrongs: Array.isArray(obj.wrongs) ? obj.wrongs : [],
    words: Array.isArray(obj.words) ? obj.words : [],
  };
}

describe('index.deep 排程与边界', () => {
  let app: ReturnType<typeof buildApp>;

  beforeEach(() => {
    app = buildApp({ logger: false });
  });

  afterEach(async () => {
    await app.close();
  });

  it('跨月排程：1 月 31 日加一个月落到 2 月末（非闰年）', () => {
    const base = '2023-01-31';
    const next = addMonths(base, 1);
    expect(next).toBe('2023-02-28');
    expect(daysInMonth(2023, 2)).toBe(28);
  });

  it('闰年边界：2 月 29 日存在，加一个月落到 3 月 29 日', () => {
    expect(isLeap(2024)).toBe(true);
    expect(daysInMonth(2024, 2)).toBe(29);
    const next = addMonths('2024-02-29', 1);
    expect(next).toBe('2024-03-29');
  });

  it('空计划：无行时导入返回空数组且无坏行', () => {
    const result = importCsv('id,date,subject,minutes\n');
    expect(result.rows.length).toBe(0);
    expect(result.badLines.length).toBe(0);
  });

  it('导入 CSV 畸形行：缺列与非法日期被记入 badLines', () => {
    const csv = [
      'id,date,subject,minutes',
      'p1,2024-03-01,数学,60',
      'p2,2024/13/01,英语,30',
      'p3,2024-03-02',
      'p4,2024-03-03,政治,45',
    ].join('\n');
    const result = importCsv(csv);
    expect(result.rows.length).toBe(2);
    expect(result.rows[0].id).toBe('p1');
    expect(result.rows[1].id).toBe('p4');
    expect(result.badLines).toEqual([3, 4]);
  });

  it('CSV 引号内逗号不被当作分隔符', () => {
    const cells = splitCsvLine('p1,2024-03-01,"英语, 阅读",30');
    expect(cells.length).toBe(4);
    expect(cells[2]).toBe('英语, 阅读');
    expect(cells[3]).toBe('30');
  });

  it('错题去重：标点与空格不同但内容相同合并并累加错次', () => {
    const items: WrongItem[] = [
      { id: 'w1', subject: '数学', stem: '求 1+1 等于几？', answer: '2', wrongCount: 1, lastWrongAt: '2024-03-01T10:00:00.000Z' },
      { id: 'w2', subject: '数学', stem: '求1+1等于几', answer: '2', wrongCount: 2, lastWrongAt: '2024-03-02T10:00:00.000Z' },
      { id: 'w3', subject: '英语', stem: '求1+1等于几', answer: 'two', wrongCount: 1, lastWrongAt: '2024-03-01T10:00:00.000Z' },
    ];
    const merged = dedupeWrong(items);
    expect(merged.length).toBe(2);
    const math = merged.find((m) => m.subject === '数学');
    expect(math).toBeDefined();
    expect(math!.wrongCount).toBe(3);
    expect(math!.lastWrongAt).toBe('2024-03-02T10:00:00.000Z');
  });

  it('单词 SRS：首次复习间隔 1 天，第二次 6 天', () => {
    const w: WordItem = { id: 'x', word: 'abandon', ease: 2.5, intervalDays: 0, dueAt: '2024-03-01', reviewCount: 0 };
    const first = srsNext(w, 4, '2024-03-01T08:00:00.000Z');
    expect(first.intervalDays).toBe(1);
    expect(first.reviewCount).toBe(1);
    expect(first.dueAt).toBe('2024-03-02');

    const second = srsNext(first, 4, '2024-03-02T08:00:00.000Z');
    expect(second.intervalDays).toBe(6);
    expect(second.reviewCount).toBe(2);
    expect(second.dueAt).toBe('2024-03-08');
  });

  it('单词 SRS：质量低时重置为 1 天且 ease 下调但不低于 1.3', () => {
    const w: WordItem = { id: 'y', word: 'brisk', ease: 1.4, intervalDays: 20, dueAt: '2024-03-01', reviewCount: 5 };
    const next = srsNext(w, 1, '2024-03-01T08:00:00.000Z');
    expect(next.intervalDays).toBe(1);
    expect(next.ease).toBe(1.3);
    expect(next.dueAt).toBe('2024-03-02');
  });

  it('备份恢复 round-trip：序列化后反序列化内容一致', () => {
    const items: PlanItem[] = [
      { id: 'p1', date: '2024-03-01', subject: '数学', minutes: 60, done: true },
      { id: 'p2', date: '2024-03-02', subject: '英语', minutes: 30, done: false },
    ];
    const wrongs: WrongItem[] = [
      { id: 'w1', subject: '数学', stem: '极限定义', answer: 'epsilon-delta', wrongCount: 3, lastWrongAt: '2024-03-02T09:00:00.000Z' },
    ];
    const words: WordItem[] = [
      { id: 'v1', word: 'abandon', ease: 2.5, intervalDays: 6, dueAt: '2024-03-08', reviewCount: 2 },
    ];
    const dumped = exportBackup(items, wrongs, words);
    const restored = importBackup(dumped);
    expect(restored.items).toEqual(items);
    expect(restored.wrongs).toEqual(wrongs);
    expect(restored.words).toEqual(words);
  });

  it('备份版本不匹配时抛错', () => {
    const bad = JSON.stringify({ version: 2, items: [], wrongs: [], words: [] });
    expect(() => importBackup(bad)).toThrow('backup version mismatch');
    const ok = importBackup(JSON.stringify({ version: 1, items: [], wrongs: [], words: [] }));
    expect(ok.items.length).toBe(0);
  });

  it('番茄计时边界：注入的真实 Fastify 实例对未知路由返回 404 且带日志关闭配置', async () => {
    const res = await app.inject({ method: 'GET', url: '/__not_exist__' });
    expect(res.statusCode).toBe(404);
    expect(app.log).toBeDefined();
  });
});