import { useCallback, useEffect, useState } from 'react';
import { SUBJECTS, type WeeklyStats } from '@kaoyan/shared';
import { api } from '../api';

// 计算某偏移周的周一（本地时区），offset=0 本周，-1 上一周
function mondayOfOffset(offset: number): string {
  const d = new Date();
  const dow = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - dow + offset * 7);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// 日期字符串加减天数（本地时区）
function addDaysLocal(dateStr: string, n: number): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + n);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, '0');
  const dd = String(dt.getDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}

export default function Weekly() {
  const [offset, setOffset] = useState(0);
  const [stats, setStats] = useState<WeeklyStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prevStats, setPrevStats] = useState<WeeklyStats | null>(null);

  const start = mondayOfOffset(offset);

  const load = useCallback(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    const prevStart = mondayOfOffset(offset - 1);
    Promise.all([
      api.weeklyStats(start),
      api.weeklyStats(prevStart).catch((err) => {
        console.warn('[weekly] 上周数据加载失败', err);
        return null;
      }),
    ])
    .then(([cur, prev]) => {
      if (!alive) return;
      setStats(cur);
      setPrevStats(prev);
      setLoading(false);
    })
    .catch((err) => {
      if (!alive) return;
      console.warn('[weekly] 加载失败', err);
      setError('加载周报失败');
      setStats(null);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [start, offset]);

  useEffect(() => {
    const cleanup = load();
    return cleanup;
  }, [load]);

  const totalFocus = stats?.focusMinutes ?? 0;
  const focusHours = Math.floor(totalFocus / 60);
  const focusMins = totalFocus % 60;

  const plansTotal = stats?.plansTotal ?? 0;
  const plansDone = stats?.plansDone ?? 0;
  const plansRate = plansTotal > 0 ? Math.round((plansDone / plansTotal) * 100) : 0;

  const wordsTotal = stats?.wordsTotal ?? 0;
  const wordsLearned = stats?.wordsLearned ?? 0;
  const wordsDue = stats?.wordsDue ?? 0;
  const wordsRate = wordsTotal > 0 ? Math.round((wordsLearned / wordsTotal) * 100) : 0;

  const mistakesNew = stats?.mistakesNew?? 0;
  const mistakesUnmastered = stats?.mistakesUnmastered?? 0;
  const examsTaken = stats?.examsTaken?? 0;

  const rawFocusByDay = stats?.focusMinutesByDay?? [];
  const focusByDay: number[] = Array.from({ length: 7 }, (_, i) => rawFocusByDay[i] ?? 0);
  const maxDayMinutes = Math.max(1, ...focusByDay);
  const streakDays = stats?.currentStreak?? 0;

  const prevPlansTotal = prevStats?.plansTotal?? 0;
  const prevPlansDone = prevStats?.plansDone?? 0;
  const prevPlansRate =
    prevPlansTotal > 0? Math.round((prevPlansDone / prevPlansTotal) * 100): 0;

  function cmp(cur: number, prev: number, unit: string): string {
    const d = cur - prev;
    if (d === 0) return '和上周一样';
    if (d > 0) return `比上周多 ${d} ${unit}`;
    return `比上周少 ${-d} ${unit}`;
  }

  function cmpPoints(cur: number, prev: number): string {
    const d = cur - prev;
    if (d === 0) return '和上周一样';
    if (d > 0) return `比上周高 ${d} 个百分点`;
    return `比上周低 ${-d} 个百分点`;
  }

  const RING_R = 54;
  const RING_C = 2 * Math.PI * RING_R;

  const rangeLabel = stats
  ? `${stats.weekStart} ~ ${addDaysLocal(stats.weekEnd, -1)}（周一至周日）`
  : '加载中';

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>周报</h1>
          <p className="stat-label" style={{ marginTop: 4}}>
            这一周学了多少，一页看完
          </p>
        </div>
        <div className="form-row" style={{ gap: 8, alignItems: 'center'}}>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setOffset((o) => o - 1)}
            >
            上一周
          </button>
          {offset!== 0 && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setOffset(0)}
              >
              回本周
            </button>
          )}
        </div>
      </div>

      {loading && <div className="loading">加载中…</div>}

      {!loading && error && <div className="error-box">{error}</div>}

      {!loading &&!error && stats && (
        <>
          <div className="card">
            <h2 style={{ margin: 0}}>{rangeLabel}</h2>
          </div>

          <div className="grid grid-3" style={{ marginTop: 16}}>
            <div className="stat-card">
              <div className="stat-value">
                {focusHours} 小时 {focusMins} 分
              </div>
              <div className="stat-label">本周专注</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{plansRate}%</div>
              <div className="stat-label">
                完成 {plansDone}/{plansTotal}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{streakDays} 天</div>
              <div className="stat-label">连续打卡</div>
            </div>
          </div>

          <div className="grid grid-2" style={{ marginTop: 12}}>
            <div className="stat-card">
              <div className="stat-value">{mistakesNew} 道</div>
              <div className="stat-label">本周新增错题</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{examsTaken} 场</div>
              <div className="stat-label">本周模考</div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 16}}>
            <h3>每天专注</h3>
            {totalFocus === 0? (
              <div className="empty">这周还没记过专注，先去番茄页记一个吧</div>
            ) : (
              <div className="wk-bars">
                {focusByDay.map((mins: number, i: number) => (
                  <div className="wk-bar-col" key={WEEKDAYS[i]}>
                    <span className="wk-bar-val">{mins}′</span>
                    <div
                      className={'wk-bar ' + barLevel(mins)}
                      style={{
                        height: Math.max(
                          4,
                          Math.round((mins / maxDayMinutes) * 120)
                        ),
                      }}
                    />
                    <span className="wk-bar-label">{WEEKDAYS[i]}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card" style={{ marginTop: 16}}>
            <h3>计划与科目</h3>
            <div className="form-row" style={{ gap: 24, alignItems: 'center', marginTop: 12}}>
              <div style={{ flex: '0 0 auto'}}>
                <svg width={140} height={140} viewBox="0 0 140 140">
                  <circle
                    className="wk-ring-track"
                    cx={70}
                    cy={70}
                    r={RING_R}
                    strokeWidth={12}
                  />
                  <circle
                    className="wk-ring-bar"
                    cx={70}
                    cy={70}
                    r={RING_R}
                    strokeWidth={12}
                    strokeDasharray={RING_C}
                    strokeDashoffset={RING_C * (1 - plansRate / 100)}
                    strokeLinecap="round"
                    transform="rotate(-90 70 70)"
                  />
                  <text
                    className="wk-ring-text"
                    x={70}
                    y={70}
                    textAnchor="middle"
                    dominantBaseline="central"
                    >
                    {plansRate}%
                  </text>
                </svg>
                <div className="stat-label" style={{ textAlign: 'center', marginTop: 6}}>
                  完成 {plansDone} / {plansTotal}
                </div>
              </div>
              <div style={{ flex: 1, minWidth: 0}}>
                {SUBJECTS.map((s) => {
                  const mins = stats.focusBySubject[s.key]?? 0;
                  const pct =
                    totalFocus > 0? Math.round((mins / totalFocus) * 100): 0;
                  return (
                    <div
                      key={s.key}
                      className="form-row"
                      style={{ gap: 12, marginTop: 8, alignItems: 'center'}}
                      >
                      <span style={{ width: 90}}>{s.name}</span>
                      <div className="progress" style={{ flex: 1}}>
                        <div
                          className="progress-bar"
                          style={{ width: pct + '%', backgroundColor: s.color}}
                        />
                      </div>
                      <span className="stat-label">{mins} 分钟</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {prevStats && (
            <div className="card" style={{ marginTop: 16}}>
              <h3>和上周比一比</h3>
              <div style={{ marginTop: 8}}>
                <div className="wk-delta-row">
                  <span className="stat-label">专注分钟</span>
                  <span>
                    本周 {totalFocus} 分钟，
                    {cmp(totalFocus, prevStats.focusMinutes, '分钟')}
                  </span>
                </div>
                <div className="wk-delta-row">
                  <span className="stat-label">计划完成率</span>
                  <span>
                    本周 {plansRate}%，{cmpPoints(plansRate, prevPlansRate)}
                  </span>
                </div>
                <div className="wk-delta-row">
                  <span className="stat-label">新增错题</span>
                  <span>
                    本周 {mistakesNew} 道，
                    {cmp(mistakesNew, prevStats.mistakesNew, '道')}
                  </span>
                </div>
                <div className="wk-delta-row">
                  <span className="stat-label">模考场次</span>
                  <span>
                    本周 {examsTaken} 场，
                    {cmp(examsTaken, prevStats.examsTaken, '场')}
                  </span>
                </div>
              </div>
            </div>
          )}

          <div className="card" style={{ marginTop: 16}}>
            <h3>单词</h3>
            <div className="stat-label">词库总数 {wordsTotal}</div>
            <div className="stat-label">已学习 {wordsLearned}</div>
            <div className="stat-label">待复习 {wordsDue}</div>
            <div className="progress" style={{ marginTop: 8}}>
              <div
                className="progress-bar"
                style={{ width: wordsRate + '%', backgroundColor: '#206bc4'}}
              />
            </div>
            <div className="stat-label" style={{ marginTop: 16}}>
              还有 {mistakesUnmastered} 道错题没掌握，抽空重做一遍
            </div>
          </div>
        </>
      )}
    </div>
  );
}

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

function barLevel(mins: number): string {
  if (mins <= 0) return 'wk-lv0';
  if (mins <= 30) return 'wk-lv1';
  if (mins <= 60) return 'wk-lv2';
  if (mins <= 120) return 'wk-lv3';
  return 'wk-lv4';
}
