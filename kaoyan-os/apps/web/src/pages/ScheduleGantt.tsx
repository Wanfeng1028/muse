import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type { DayLoad, DayLoadItem, OverloadResponse, SubjectKey } from '@kaoyan/shared';
import { SUBJECTS } from '@kaoyan/shared';

// 本地时区日期字符串 YYYY-MM-DD
function localDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// 在给定日期上加天数，返回新的 Date
function addDays(d: Date, n: number): Date {
  const r = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  r.setDate(r.getDate() + n);
  return r;
}

// 取某日期所在周的周一（本地时区）
function mondayOf(d: Date): Date {
  const day = d.getDay(); // 0=Sun..6=Sat
  const diff = day === 0 ? -6 : 1 - day;
  return addDays(d, diff);
}

// MM-DD 显示
function mdLabel(dateStr: string): string {
  const parts = dateStr.split('-');
  if (parts.length < 3) return dateStr;
  return `${parts[1]}-${parts[2]}`;
}

const WEEK_DAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

const DEFAULT_MINUTES = 240;
const MIN_MINUTES = 30;
const MAX_MINUTES = 1440;

interface DragState {
  id: number;
  fromDate: string;
}

function subjectMeta(key: string): { name: string; color: string } {
  const found = SUBJECTS.find((s) => s.key === key);
  if (found) return { name: found.name, color: found.color };
  return { name: key, color: '#6b7280' };
}

function subjectColor(key: string): string {
  return subjectMeta(key).color;
}

function subjectLabel(key: string): string {
  return subjectMeta(key).name;
}

export default function ScheduleGantt() {
  const today = useMemo(() => new Date(), []);
  const [weekStart, setWeekStart] = useState<string>(() => localDateStr(mondayOf(today)));
  const [dailyMinutes, setDailyMinutes] = useState<number>(DEFAULT_MINUTES);
  const [minutesInput, setMinutesInput] = useState<string>(String(DEFAULT_MINUTES));
  const [data, setData] = useState<OverloadResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const load = useCallback(async (ws: string, dm: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.plansOverload(ws, dm);
      setData(res);
    } catch (e) {
      const msg = e instanceof Error ? e.message : '加载失败';
      setError(msg);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(weekStart, dailyMinutes);
  }, [weekStart, dailyMinutes, load]);

  // 提交每日分钟数（blur / Enter）
  const commitMinutes = useCallback(() => {
    const n = parseInt(minutesInput, 10);
    if (!Number.isFinite(n)) {
      setMinutesInput(String(dailyMinutes));
      return;
    }
    const clamped = Math.max(MIN_MINUTES, Math.min(MAX_MINUTES, n));
    setMinutesInput(String(clamped));
    if (clamped !== dailyMinutes) setDailyMinutes(clamped);
  }, [minutesInput, dailyMinutes]);

  const goPrevWeek = useCallback(() => {
    const d = new Date(weekStart + 'T00:00:00');
    setWeekStart(localDateStr(addDays(d, -7)));
  }, [weekStart]);

  const goNextWeek = useCallback(() => {
    const d = new Date(weekStart + 'T00:00:00');
    setWeekStart(localDateStr(addDays(d, 7)));
  }, [weekStart]);

  const goThisWeek = useCallback(() => {
    setWeekStart(localDateStr(mondayOf(new Date())));
  }, []);

  // 周区间显示 MM-DD～MM-DD
  const weekEnd = useMemo(() => {
    const d = new Date(weekStart + 'T00:00:00');
    return localDateStr(addDays(d, 6));
  }, [weekStart]);

  // 组装 7 列：以 weekStart 为周一
  const columns = useMemo(() => {
    const startDate = new Date(weekStart + 'T00:00:00');
    const days: DayLoad[] = [];
    const byDate = new Map<string, DayLoad>();
    if (data) {
      for (const d of data.days) byDate.set(d.date, d);
    }
    for (let i = 0; i < 7; i++) {
      const dateStr = localDateStr(addDays(startDate, i));
      const existing = byDate.get(dateStr);
      if (existing) {
        days.push(existing);
      } else {
        days.push({
          date: dateStr,
          items: [],
          totalMinutes: 0,
          overloaded: false,
        });
      }
    }
    return days;
  }, [data, weekStart]);

  const overloadedDays = useMemo(() => {
    return columns.filter((d) => d.overloaded || d.totalMinutes > dailyMinutes);
  }, [columns, dailyMinutes]);

  const handleDragStart = useCallback((e: React.DragEvent, item: DayLoadItem, fromDate: string) => {
    setDrag({ id: item.id, fromDate });
    try {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', String(item.id));
    } catch {
      // 忽略
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, date: string) => {
    if (!drag) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dropTarget !== date) setDropTarget(date);
  }, [drag, dropTarget]);

  const handleDragLeave = useCallback((date: string) => {
    if (dropTarget === date) setDropTarget(null);
  }, [dropTarget]);

  const handleDrop = useCallback(async (e: React.DragEvent, date: string) => {
    e.preventDefault();
    const cur = drag;
    setDropTarget(null);
    setDrag(null);
    if (!cur) return;
    if (cur.fromDate === date) return;
    try {
      await api.updatePlan(cur.id, { date });
      await load(weekStart, dailyMinutes);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '调整日期失败';
      setError(msg);
    }
  }, [drag, weekStart, dailyMinutes, load]);

  const handleDragEnd = useCallback(() => {
    setDrag(null);
    setDropTarget(null);
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <h1>排期周视图</h1>
        <p className="gantt-hint">拖动色块可调整日期</p>
      </div>

      <div className="card gantt-toolbar">
        <div className="gantt-toolbar-left">
          <button type="button" className="gantt-btn" onClick={goPrevWeek}>上一周</button>
          <button type="button" className="gantt-btn" onClick={goThisWeek}>本周</button>
          <button type="button" className="gantt-btn" onClick={goNextWeek}>下一周</button>
          <span className="gantt-range">
            {mdLabel(weekStart)}～{mdLabel(weekEnd)}
          </span>
        </div>
        <div className="gantt-toolbar-right">
          <label className="gantt-minutes-label" htmlFor="gantt-minutes">每日分钟数</label>
          <input
            id="gantt-minutes"
            type="number"
            className="gantt-minutes-input"
            min={MIN_MINUTES}
            max={MAX_MINUTES}
            step={30}
            value={minutesInput}
            onChange={(e) => setMinutesInput(e.target.value)}
            onBlur={commitMinutes}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                (e.target as HTMLInputElement).blur();
              }
            }}
          />
        </div>
      </div>

      {error && (
        <div className="error-box">
          {error}
        </div>
      )}

      {overloadedDays.length > 0 && (
        <div className="gantt-warn">
          <div className="gantt-warn-title">
            有 {overloadedDays.length} 天超负荷了，可以调整一下：
          </div>
          <ul className="gantt-warn-list">
            {overloadedDays.map((d) => {
              const over = d.totalMinutes - dailyMinutes;
              return (
                <li key={d.date}>
                  {mdLabel(d.date)} 安排了 {d.totalMinutes} 分钟，超出 {over} 分钟，建议把复习块挪到后面几天
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {loading ? (
        <div className="loading">加载中…</div>
      ) : (
        <div className="gantt-grid">
          {columns.map((day, idx) => {
            const over = day.totalMinutes > dailyMinutes;
            const isDrop = dropTarget === day.date;
            return (
              <div
                key={day.date}
                className={
                  'gantt-col' +
                  (over ? ' gantt-col-over' : '') +
                  (isDrop ? ' gantt-col-drop' : '')
                }
                onDragOver={(e) => handleDragOver(e, day.date)}
                onDragLeave={() => handleDragLeave(day.date)}
                onDrop={(e) => { void handleDrop(e, day.date); }}
              >
                <div className={'gantt-col-head' + (over ? ' gantt-col-head-over' : '')}>
                  <div className="gantt-col-date">
                    {mdLabel(day.date)} <span className="gantt-col-weekday">{WEEK_DAYS[idx]}</span>
                  </div>
                  <div className="gantt-col-total">
                    {day.totalMinutes} 分钟
                    {over && <span className="gantt-over-tag">超负荷</span>}
                  </div>
                </div>
                <div className="gantt-col-body">
                  {day.items.length === 0 ? (
                    <div className="gantt-empty">当天无计划</div>
                  ) : (
                    day.items.map((item) => {
                      const color = subjectColor(item.subject);
                      const kindCls =
                        item.kind === 'review'
                          ? ' gantt-block-review'
                          : item.kind === 'manual'
                            ? ' gantt-block-manual'
                            : ' gantt-block-new';
                      const cls = 'gantt-block' + kindCls + (item.done ? ' gantt-block-done' : '');
                      return (
                        <div
                          key={item.id}
                          className={cls}
                          style={{ '--gantt-c': color } as React.CSSProperties}
                          draggable
                          onDragStart={(e) => handleDragStart(e, item, day.date)}
                          onDragEnd={handleDragEnd}
                          title={`${subjectLabel(item.subject)} · ${item.title} · ${item.plannedMinutes} 分钟`}
                        >
                          <div className="gantt-block-title">{item.title}</div>
                          <div className="gantt-block-meta">
                            {item.plannedMinutes} 分钟
                            {item.done ? ' · 已完成' : ''}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="card gantt-legend">
        <div className="gantt-legend-title">图例</div>
        <div className="gantt-legend-items">
          <span className="gantt-legend-item">
            <span className="gantt-legend-swatch gantt-legend-new" />
            新学
          </span>
          <span className="gantt-legend-item">
            <span className="gantt-legend-swatch gantt-legend-review" />
            复习
          </span>
          <span className="gantt-legend-item">
            <span className="gantt-legend-swatch gantt-legend-manual" />
            手动添加
          </span>
          <span className="gantt-legend-item">
            <span className="gantt-legend-swatch gantt-legend-over" />
            超负荷
          </span>
          <span className="gantt-legend-item">
            <span className="gantt-legend-swatch gantt-legend-done" />
            已完成（变淡+删除线）
          </span>
        </div>
      </div>
    </div>
  );
}

// 类型守卫：确保 SubjectKey 引用（保留导入以满足严格模式需求）
export type { SubjectKey };
