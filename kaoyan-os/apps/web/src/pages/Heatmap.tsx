import { useEffect, useMemo, useState } from 'react';
import type { FocusSession, HeatmapDay, HeatmapResponse } from '@kaoyan/shared';
import { SUBJECTS } from '@kaoyan/shared';

import { api } from '../api';

type Months = 1 | 3 | 6;

const MONTH_OPTIONS: Months[] = [1, 3, 6];

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function toDateKey(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function parseDateKey(key: string): Date {
  const [y, m, d] = key.split('-').map((s) => Number(s));
  return new Date(y, m - 1, d);
}

function addDaysLocal(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

function mondayOf(d: Date): Date {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  return addDaysLocal(d, diff);
}

function levelClass(minutes: number): string {
  if (minutes <= 0) return 'hm-0';
  if (minutes <= 30) return 'hm-1';
  if (minutes <= 60) return 'hm-2';
  if (minutes <= 120) return 'hm-3';
  return 'hm-4';
}

function cellTitle(day: HeatmapDay): string {
  return `${day.date}\n专注 ${day.focusMinutes} 分钟\n计划 ${day.plansDone}/${day.plansTotal}\n新增错题 ${day.mistakesNew}\n模考 ${day.examsTaken}`;
}

export default function Heatmap() {
  const [months, setMonths] = useState<Months>(3);
  const [data, setData] = useState<HeatmapResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [daySessions, setDaySessions] = useState<FocusSession[]>([]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    api
      .heatmapStats(months)
      .then((res) => {
        if (!alive) return;
        setData(res);
      })
      .catch(() => {
        if (!alive) return;
        setError('加载热力图失败');
      })
      .finally(() => {
        if (!alive) return;
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [months]);

  useEffect(() => {
    if (!selectedDate) {
      setDaySessions([]);
      return;
    }
    let alive = true;
    api
      .listFocus(200)
      .then((list) => {
        if (!alive) return;
        setDaySessions(
          list.filter((s: FocusSession) => s.startedAt.slice(0, 10) === selectedDate),
        );
      })
      .catch(() => {
        if (!alive) return;
        setDaySessions([]);
      });
    return () => {
      alive = false;
    };
  }, [selectedDate]);

  const weeks = useMemo<Array<Array<HeatmapDay | null>>>(() => {
    if (!data || data.days.length === 0) return [];
    const byDate = new Map<string, HeatmapDay>();
    data.days.forEach((d: HeatmapDay) => byDate.set(d.date, d));

    const start = parseDateKey(data.startDate);
    const end = parseDateKey(data.endDate);
    const firstMonday = mondayOf(start);

    const cols: Array<Array<HeatmapDay | null>> = [];
    let cursor = firstMonday;
    while (cursor.getTime() <= end.getTime()) {
      const col: Array<HeatmapDay | null> = [];
      for (let i = 0; i < 7; i += 1) {
        const day = addDaysLocal(cursor, i);
        const key = toDateKey(day);
        if (day.getTime() < start.getTime() || day.getTime() > end.getTime()) {
          col.push(null);
        } else {
          col.push(byDate.get(key) ?? null);
        }
      }
      cols.push(col);
      cursor = addDaysLocal(cursor, 7);
    }
    return cols;
  }, [data]);

  const monthLabels = useMemo<string[]>(() => {
    const labels: string[] = [];
    let lastMonth = -1;
    weeks.forEach((col) => {
      const first = col.find((d: HeatmapDay | null) => d !== null);
      if (!first) {
        labels.push('');
        return;
      }
      const m = parseDateKey(first.date).getMonth();
      if (m !== lastMonth) {
        labels.push(`${m + 1}月`);
        lastMonth = m;
      } else {
        labels.push('');
      }
    });
    return labels;
  }, [weeks]);

  const selectedDay = useMemo<HeatmapDay | null>(() => {
    if (!data || !selectedDate) return null;
    return data.days.find((d: HeatmapDay) => d.date === selectedDate) ?? null;
  }, [data, selectedDate]);

  return (
    <div className="page">
      <div className="page-header">
        <h1>自律热力图</h1>
        <p>每天的学习刻度盘——格子越深，当天专注越久</p>
      </div>

      {error && <div className="error-box">{error}</div>}
      {loading && <div className="loading">加载中…</div>}

      <div className="card hm-toolbar">
        <div className="hm-toolbar-head">
          <h2 className="hm-range">
            {data ? `${data.startDate} ~ ${data.endDate}` : '—'}
          </h2>
          <div className="hm-month-btns">
            {MONTH_OPTIONS.map((m: Months) => (
              <button
                key={m}
                type="button"
                className={`btn btn-ghost btn-sm${months === m ? ' btn-primary' : ''}`}
                onClick={() => setMonths(m)}
              >
                近 {m} 个月
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-3 hm-stat-grid">
        <div className="stat-card">
          <div className="stat-value">{data ? data.currentStreak : 0} 天</div>
          <div className="stat-label">当前连续打卡</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data ? data.bestStreak : 0} 天</div>
          <div className="stat-label">历史最长连续</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data ? data.activeDays : 0} 天</div>
          <div className="stat-label">累计专注天数</div>
        </div>
      </div>

      <div className="card">
        {!data || data.days.length === 0 ? (
          <div className="empty">暂无数据</div>
        ) : (
          <div className="hm-scroll">
            <div className="hm-months">
              {monthLabels.map((label: string, i: number) => (
                <div className="hm-month" key={i}>
                  {label}
                </div>
              ))}
            </div>
            <div className="hm-grid">
              {weeks.map((col, ci) => (
                <div className="hm-col" key={ci}>
                  {col.map((day, ri) => {
                    if (!day) {
                      return <div className="hm-cell hm-empty" key={ri} />;
                    }
                    const cls = `hm-cell ${levelClass(day.focusMinutes)} hm-clickable${
                      selectedDate === day.date ? ' hm-selected' : ''
                    }`;
                    return (
                      <button
                        type="button"
                        className={cls}
                        key={ri}
                        title={cellTitle(day)}
                        aria-label={cellTitle(day)}
                        onClick={() => setSelectedDate(day.date)}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
            <div className="hm-legend">
              <span>少</span>
              <div className="hm-cell hm-0 hm-legend-cell" />
              <div className="hm-cell hm-1 hm-legend-cell" />
              <div className="hm-cell hm-2 hm-legend-cell" />
              <div className="hm-cell hm-3 hm-legend-cell" />
              <div className="hm-cell hm-4 hm-legend-cell" />
              <span>多</span>
            </div>
          </div>
        )}
      </div>

      {selectedDate && (
        <div className="card">
          <h3>{selectedDate}</h3>
          {selectedDay ? (
            <>
              <div className="stat-label">当日专注 {selectedDay.focusMinutes} 分钟</div>
              <div className="stat-label">
                计划完成 {selectedDay.plansDone}/{selectedDay.plansTotal}
              </div>
              <div className="stat-label">新增错题 {selectedDay.mistakesNew}</div>
              <div className="stat-label">模考 {selectedDay.examsTaken} 场</div>
            </>
          ) : (
            <div className="stat-label">当日无记录</div>
          )}

          {daySessions.length === 0 ? (
            <div className="empty">当日无专注会话记录</div>
          ) : (
            <table className="table hm-session-table">
              <thead>
                <tr>
                  <th>科目</th>
                  <th>分钟</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody>
                {daySessions.map((s: FocusSession) => (
                  <tr key={s.id}>
                    <td data-label="科目">
                      {SUBJECTS.find((x) => x.key === s.subject)?.name ?? s.subject}
                    </td>
                    <td data-label="分钟">{s.minutes}</td>
                    <td data-label="备注">{s.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
