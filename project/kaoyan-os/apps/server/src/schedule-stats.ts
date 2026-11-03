import type { SubjectKey } from '@kaoyan/shared';

export interface PlanLite {
  id: number;
  date: string;
  subject: SubjectKey;
  title: string;
  plannedMinutes: number;
  kind: 'new' | 'review' | 'manual';
  done: boolean;
}

export interface DayLoad {
  date: string;
  items: PlanLite[];
  totalMinutes: number;
  overloaded: boolean;
}

export function kindOf(title: string): 'new' | 'review' | 'manual' {
  if (title.startsWith('智能排期·')) {
    if (title.includes(' 新学')) return 'new';
    if (title.includes(' 复习')) return 'review';
  }
  return 'manual';
}

export function computeDayLoads(
  plans: Array<{
    id: number;
    date: string;
    subject: SubjectKey;
    title: string;
    plannedMinutes: number;
    done: boolean;
  }>,
  dailyMinutes: number,
  fromDate: string,
  days: number,
): DayLoad[] {
  // 计算日期区间上界（含）
  const endDate = (() => {
    const [y, m, d] = fromDate.split('-').map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    dt.setUTCDate(dt.getUTCDate() + days - 1);
    const yy = dt.getUTCFullYear();
    const mm = String(dt.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(dt.getUTCDate()).padStart(2, '0');
    return `${yy}-${mm}-${dd}`;
  })();

  // 按日期过滤到 [fromDate, endDate] 区间
  const inRange = plans.filter((p) => p.date >= fromDate && p.date <= endDate);

  // 按日期分组
  const byDate = new Map<string, typeof inRange>();
  for (const p of inRange) {
    const list = byDate.get(p.date);
    if (list) list.push(p);
    else byDate.set(p.date, [p]);
  }

  // 生成每一天
  const result: DayLoad[] = [];
  for (let i = 0; i < days; i++) {
    const [y, m, d] = fromDate.split('-').map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    dt.setUTCDate(dt.getUTCDate() + i);
    const yy = dt.getUTCFullYear();
    const mm = String(dt.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(dt.getUTCDate()).padStart(2, '0');
    const date = `${yy}-${mm}-${dd}`;

    const raw = byDate.get(date) ?? [];
    const sorted = raw.slice().sort((a, b) => {
      if (b.plannedMinutes !== a.plannedMinutes) {
        return b.plannedMinutes - a.plannedMinutes;
      }
      return a.id - b.id;
    });

    const items: PlanLite[] = sorted.map((p) => ({
      id: p.id,
      date: p.date,
      subject: p.subject,
      title: p.title,
      plannedMinutes: p.plannedMinutes,
      kind: kindOf(p.title),
      done: p.done,
    }));

    const totalMinutes = items.reduce((sum, it) => sum + it.plannedMinutes, 0);

    result.push({
      date,
      items,
      totalMinutes,
      overloaded: totalMinutes > dailyMinutes,
    });
  }

  return result;
}
