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

  const start = mondayOfOffset(offset);

  const load = useCallback(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .weeklyStats(start)
      .then((s) => {
        if (!alive) return;
        setStats(s);
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
  }, [start]);

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

  const mistakesNew = stats?.mistakesNew ?? 0;
  const mistakesUnmastered = stats?.mistakesUnmastered ?? 0;
  const examsTaken = stats?.examsTaken ?? 0;

  const rangeLabel = stats
    ? `${stats.weekStart} ~ ${addDaysLocal(stats.weekEnd, -1)}（周一至周日）`
    : '加载中';

  return (
    <div className="page">
      <div className="page-header">
        <h1>周报</h1>
      </div>

      <div className="card">
        <div className="form-row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>{rangeLabel}</h2>
          <div className="form-row" style={{ gap: 8, alignItems: 'center' }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setOffset((o) => o - 1)}
            >
              上一周
            </button>
            {offset !== 0 && (
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

        {!loading && !error && stats && (
          <>
            <div style={{ marginTop: 16 }}>
              <h3>专注统计</h3>
              <div className="stat-label">
                本周专注 {focusHours} 小时 {focusMins} 分钟
              </div>
              <div style={{ marginTop: 8 }}>
                {SUBJECTS.map((s) => {
                  const mins = stats.focusBySubject[s.key] ?? 0;
                  const pct =
                    totalFocus > 0 ? Math.round((mins / totalFocus) * 100) : 0;
                  return (
                    <div
                      key={s.key}
                      className="form-row"
                      style={{ gap: 12, marginTop: 8, alignItems: 'center' }}
                    >
                      <span style={{ width: 90 }}>{s.name}</span>
                      <div className="progress" style={{ flex: 1 }}>
                        <div
                          className="progress-bar"
                          style={{ width: pct + '%', backgroundColor: s.color }}
                        />
                      </div>
                      <span className="stat-label">{mins} 分钟</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div style={{ marginTop: 24 }}>
              <h3>复习计划</h3>
              <div className="stat-label">
                完成 {plansDone} / {plansTotal}
              </div>
              <div className="progress" style={{ marginTop: 8 }}>
                <div
                  className="progress-bar"
                  style={{ width: plansRate + '%', backgroundColor: '#206bc4' }}
                />
              </div>
            </div>

            <div style={{ marginTop: 24 }}>
              <h3>单词</h3>
              <div className="stat-label">词库总数 {wordsTotal}</div>
              <div className="stat-label">已学习 {wordsLearned}</div>
              <div className="stat-label">待复习 {wordsDue}</div>
              <div className="progress" style={{ marginTop: 8 }}>
                <div
                  className="progress-bar"
                  style={{ width: wordsRate + '%', backgroundColor: '#206bc4' }}
                />
              </div>
            </div>

            <div style={{ marginTop: 24 }}>
              <h3>错题与模考</h3>
              <div className="stat-label">本周新增错题 {mistakesNew}</div>
              <div className="stat-label">未掌握错题 {mistakesUnmastered}</div>
              <div className="stat-label">本周模考 {examsTaken} 场</div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
