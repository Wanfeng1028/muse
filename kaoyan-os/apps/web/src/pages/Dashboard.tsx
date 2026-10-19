import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import {
  SUBJECTS,
  type PlanSummary,
  type FocusStats,
  type WordWithState,
  type Mistake,
  type ExamRecord,
  type Settings,
  DEFAULT_SETTINGS,
} from '@kaoyan/shared';

// 科目 key -> 名称 / badge 类名 映射
const subjectName = (key: string) => SUBJECTS.find((s) => s.key === key)?.name ?? key;
const subjectBadge = (key: string) => `badge badge-${key}`;

// 日期显示：取后 5 位（MM-DD）
const shortDate = (d: string) => d.slice(-5);

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [summary, setSummary] = useState<PlanSummary | null>(null);
  const [focus, setFocus] = useState<FocusStats | null>(null);
  const [dueWords, setDueWords] = useState<WordWithState[]>([]);
  const [mistakes, setMistakes] = useState<Mistake[]>([]);
  const [exams, setExams] = useState<ExamRecord[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);

  // mount 时并行加载所有数据
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        setLoading(true);
        const [s, f, w, m, e, cfg] = await Promise.all([
          api.planSummary(),
          api.focusStats(7),
          api.dueWords(),
          api.listMistakes({ mastered: false }),
          api.listExams(),
          api.getSettings().catch(() => DEFAULT_SETTINGS),
        ]);
        if (!alive) return;
        setSummary(s);
        setFocus(f);
        setDueWords(w);
        setMistakes(m);
        setExams(e);
        setSettings(cfg ?? DEFAULT_SETTINGS);
        setError(null);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // 今日日期
  const today = useMemo(() => {
    const d = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }, []);

  // 近 7 天专注柱状图的最大值（用于比例）
  const maxMinutes = useMemo(() => {
    if (!focus || focus.days.length === 0) return 0;
    return Math.max(...focus.days.map((d) => d.minutes), 1);
  }, [focus]);

  // 最近 5 条真题
  const recentExams = useMemo(() => exams.slice(0, 5), [exams]);

  if (loading) {
    return (
      <div className="page">
        <div className="loading">加载中…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <div className="error-box">{error}</div>
      </div>
    );
  }

  const dailyGoal = settings.dailyGoalMinutes || 300;
  const todayMinutes = focus?.todayMinutes ?? 0;

  return (
    <div className="page">
      <div className="page-header">
        <h1>今日概览</h1>
        <span>{today}</span>
      </div>

      {/* 三张统计卡片 */}
      <div className="grid grid-3 dash-stat-grid">
        <div className="stat-card card">
          <div className="stat-label">今日计划完成</div>
          <div className="stat-value dash-stat-value">
            {summary ? `${summary.done}/${summary.total}` : '0/0'}
          </div>
          <div className="progress">
            <div
              className="progress-bar"
              style={{ width: `${summary ? Math.round(summary.completionRate * 100) : 0}%` }}
            />
          </div>
        </div>

        <div className="stat-card card">
          <div className="stat-label">今日专注分钟</div>
          <div className="stat-value dash-stat-value">
            {todayMinutes} / {dailyGoal}
          </div>
          <div className="progress">
            <div
              className="progress-bar"
              style={{ width: `${Math.min(100, (todayMinutes / dailyGoal) * 100)}%` }}
            />
          </div>
        </div>

        <div className="stat-card card">
          <div className="stat-label">待复习单词数</div>
          <div className="stat-value dash-stat-value">{dueWords.length}</div>
        </div>
      </div>

      {/* 第二行：专注图表 + 真题得分率 */}
      <div className="grid grid-2 dash-row2">
        <div className="card">
          <h2>近 7 天专注</h2>
          {focus && focus.days.length > 0 ? (
            <div className="chart-bars dash-chart">
              {focus.days.map((d) => (
                <div className="bar-col" key={d.date}>
                  <div
                    className="bar"
                    style={{ height: `${(d.minutes / maxMinutes) * 100}%` }}
                    title={`${d.date} ${d.minutes} 分钟`}
                  />
                  <div className="bar-label">
                    {shortDate(d.date)}
                    <br />
                    {d.minutes}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty">暂无专注记录</div>
          )}
        </div>

        <div className="card">
          <h2>各科真题得分率</h2>
          {recentExams.length > 0 ? (
            <ul className="list dash-exam-list">
              {recentExams.map((e) => {
                const rate = e.totalScore > 0 ? (e.score / e.totalScore) * 100 : 0;
                return (
                  <li className="list-item dash-exam-item" key={e.id}>
                    <span className="dash-exam-paper" data-label="试卷">
                      {e.paper}
                    </span>
                    <span
                      className={`${subjectBadge(e.subject)} dash-exam-subject`}
                      data-label="科目"
                    >
                      {subjectName(e.subject)}
                    </span>
                    <span className="dash-exam-rate" data-label="得分率">
                      {rate.toFixed(1)}%
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="empty">暂无真题记录</div>
          )}
        </div>
      </div>

      {/* 未掌握错题 */}
      <div className="card dash-mistake-card">
        <h2>未掌握错题（{mistakes.length}）</h2>
        {mistakes.length > 0 ? (
          <ul className="list dash-mistake-list">
            {mistakes.slice(0, 5).map((m) => (
              <li className="list-item dash-mistake-item" key={m.id}>
                <span
                  className={`${subjectBadge(m.subject)} dash-mistake-subject`}
                  data-label="科目"
                >
                  {subjectName(m.subject)}
                </span>
                <span className="dash-mistake-title" data-label="题目">
                  {m.title}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty">暂无未掌握错题</div>
        )}
      </div>
    </div>
  );
}
