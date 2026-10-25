import { useCallback, useEffect, useMemo, useState } from 'react';
import type {
  ExamRecord,
  ExamTrendPoint,
  ExamSummary,
  ExamsBySubjectResponse,
  SubjectKey,
  CreateExamInput,
  Mistake,
} from '@kaoyan/shared';

import { SUBJECTS } from '@kaoyan/shared';
import { api } from '../api';

// 科目 key -> 名称 映射
const SUBJECT_NAME: Record<SubjectKey, string> = SUBJECTS.reduce(
  (acc, s) => {
    acc[s.key] = s.name;
    return acc;
  },
  {} as Record<SubjectKey, string>
);

// 科目筛选类型：'all' 或具体科目
type SubjectFilter = 'all' | SubjectKey;

export default function Exams() {
  // 记录表科目筛选
  const [subjectFilter, setSubjectFilter] = useState<SubjectFilter>('all');
  // 趋势图科目
  const [trendSubject, setTrendSubject] = useState<SubjectKey>('math');

  // 记录列表状态
  const [records, setRecords] = useState<ExamRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  // 相关错题：按考试记录 id 缓存
  const [relatedOpenId, setRelatedOpenId] = useState<number | null>(null);
  const [related, setRelated] = useState<Record<number, Mistake[]>>({});
  const [relatedLoadingId, setRelatedLoadingId] = useState<number | null>(null);

  const toggleRelated = useCallback(
    async (r: ExamRecord) => {
      if (relatedOpenId === r.id) {
        setRelatedOpenId(null);
        return;
      }
      if (related[r.id]) {
        setRelatedOpenId(r.id);
        return;
      }
      setRelatedLoadingId(r.id);
      try {
        const data = await api.examRelatedMistakes(r.id);
        setRelated((prev) => ({ ...prev, [r.id]: data }));
        setRelatedOpenId(r.id);
      } catch {
        setRelated((prev) => ({ ...prev, [r.id]: [] }));
        setRelatedOpenId(r.id);
      } finally {
        setRelatedLoadingId(null);
      }
    },
    [relatedOpenId, related],
  );


  // 趋势数据状态
  const [trend, setTrend] = useState<ExamTrendPoint[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);

  // 新增表单状态
  const [form, setForm] = useState<CreateExamInput>({
    subject: 'math',
    paper: '',
    score: 0,
    totalScore: 0,
    durationMinutes: 0,
    takenAt: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // 加载记录表
  const loadRecords = useCallback(async () => {
    setRecordsLoading(true);
    setRecordsError(null);
    try {
      const data = await api.listExams(subjectFilter === 'all' ? undefined : subjectFilter);
      setRecords(data);
    } catch (e) {
      setRecordsError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setRecordsLoading(false);
    }
  }, [subjectFilter]);

  // 加载趋势数据
  const loadTrend = useCallback(async () => {
    setTrendLoading(true);
    setTrendError(null);
    try {
      const data = await api.examTrend(trendSubject);
      setTrend(data);
    } catch (e) {
      setTrendError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setTrendLoading(false);
    }
  }, [trendSubject]);

  // 汇总数据状态
  const [summary, setSummary] = useState<ExamSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [bySubject, setBySubject] = useState<ExamsBySubjectResponse | null>(null);
  const [bySubjectLoading, setBySubjectLoading] = useState(false);
  const [bySubjectError, setBySubjectError] = useState<string | null>(null);

  // 加载汇总数据
  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const data = await api.examSummary(trendSubject);
      setSummary(data);
    } catch (e) {
      setSummaryError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setSummaryLoading(false);
    }
  }, [trendSubject]);

  // 加载分科汇总数据
  const loadBySubject = useCallback(async () => {
    setBySubjectLoading(true);
    setBySubjectError(null);
    try {
      const data = await api.examSummaryBySubject();
      setBySubject(data);
    } catch (e) {
      setBySubjectError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setBySubjectLoading(false);
    }
  }, []);


  // 依赖变化时重新加载
  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  useEffect(() => {
    loadTrend();
  }, [loadTrend]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    loadBySubject();
  }, [loadBySubject]);


  // 提交新增表单
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!form.paper.trim()) {
      setFormError('请填写试卷名称');
      return;
    }
    if (form.totalScore <= 0) {
      setFormError('满分需大于 0');
      return;
    }
    if (form.score < 0 || form.score > form.totalScore) {
      setFormError('得分需在 0 与满分之间');
      return;
    }
    setSubmitting(true);
    try {
      const payload: CreateExamInput = {
        subject: form.subject,
        paper: form.paper.trim(),
        score: form.score,
        totalScore: form.totalScore,
        durationMinutes: form.durationMinutes,
      };
      if (form.takenAt) payload.takenAt = form.takenAt;
      await api.createExam(payload);
      // 重置表单（保留科目）
      setForm((prev) => ({
        subject: prev.subject,
        paper: '',
        score: 0,
        totalScore: 0,
        durationMinutes: 0,
        takenAt: '',
      }));
      await loadRecords();
      await loadTrend();
      await loadSummary();
      await loadBySubject();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : '提交失败');

    } finally {
      setSubmitting(false);
    }
  };

  // 删除记录
  const handleDelete = async (id: number) => {
    try {
      await api.deleteExam(id);
      await loadRecords();
      await loadTrend();
      await loadSummary();
      await loadBySubject();
    } catch (e) {
      setRecordsError(e instanceof Error ? e.message : '删除失败');
    }
  };

  // 导出 CSV：按当前筛选科目导出，点击后直接下载文件
  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await api.exportExamsCsv(
        subjectFilter === 'all' ? undefined : subjectFilter
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'kaoyan-exams.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setRecordsError(e instanceof Error ? e.message : '导出失败');
    } finally {
      setExporting(false);
    }
  };


  // 计算得分率显示
  const rateOf = (r: ExamRecord) =>
    r.totalScore > 0 ? `${((r.score / r.totalScore) * 100).toFixed(1)}%` : '-';

  // 生成 SVG polyline 点坐标
  const trendChart = useMemo(() => {
    const W = 600;
    const H = 180;
    const padX = 40;
    const padY = 24;
    if (trend.length === 0) return null;
    const innerW = W - padX * 2;
    const innerH = H - padY * 2;
    const n = trend.length;
    const stepX = n > 1 ? innerW / (n - 1) : 0;
    const points = trend.map((p, i) => {
      const x = padX + (n > 1 ? i * stepX : innerW / 2);
      const rate = Math.max(0, Math.min(1, p.rate));
      const y = padY + innerH * (1 - rate);
      return { x, y, rate, point: p };
    });
    const polyline = points.map((p) => `${p.x},${p.y}`).join(' ');
    return { W, H, points, polyline };
  }, [trend]);

  return (
    <div className="page exams-page">
      <div className="page-header">
        <h1>真题统计</h1>
      </div>

      {/* 新增真题记录表单 */}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>新增真题记录</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              科目
              <select
                className="select"
                value={form.subject}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    subject: e.target.value as SubjectKey,
                  }))
                }
              >
                {SUBJECTS.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              试卷
              <input
                className="input"
                type="text"
                placeholder="如 2025 年数学一真题"
                value={form.paper}
                onChange={(e) =>
                  setForm((p) => ({ ...p, paper: e.target.value }))
                }
              />
            </label>

            <label>
              得分
              <input
                className="input"
                type="number"
                min={0}
                value={form.score}
                onChange={(e) =>
                  setForm((p) => ({ ...p, score: Number(e.target.value) }))
                }
              />
            </label>

            <label>
              满分
              <input
                className="input"
                type="number"
                min={0}
                value={form.totalScore}
                onChange={(e) =>
                  setForm((p) => ({ ...p, totalScore: Number(e.target.value) }))
                }
              />
            </label>

            <label>
              时长(分钟)
              <input
                className="input"
                type="number"
                min={0}
                value={form.durationMinutes}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    durationMinutes: Number(e.target.value),
                  }))
                }
              />
            </label>

            <label>
              考试日期
              <input
                className="input"
                type="date"
                value={form.takenAt ?? ''}
                onChange={(e) =>
                  setForm((p) => ({ ...p, takenAt: e.target.value }))
                }
              />
            </label>
          </div>

          {formError && <div className="error-box">{formError}</div>}

          <div className="form-row" style={{ marginTop: 12 }}>
            <button
              className="btn btn-primary"
              type="submit"
              disabled={submitting}
            >
              {submitting ? '提交中…' : '添加记录'}
            </button>
          </div>
        </form>
      </div>

      {/* 本阶段汇总 */}
      <div className="card exams-summary">
        <div className="form-row exams-summary-head" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>本阶段汇总</h2>
          <span className="exams-muted" style={{ fontSize: 13 }}>{SUBJECT_NAME[trendSubject]}</span>
        </div>
        {summaryLoading ? (
          <div className="loading">加载中…</div>
        ) : summaryError ? (
          <div className="error-box">{summaryError}</div>
        ) : !summary || summary.count === 0 ? (
          <div className="empty">还没有模考记录，先在上面记一场吧</div>
        ) : (
          <div className="form-row exams-summary-grid" style={{ marginTop: 12, gap: 24 }}>
            <div className="exams-summary-item">
              <div className="exams-summary-label" style={{ fontSize: 13 }}>模考场次</div>
              <div className="exams-summary-value" style={{ fontSize: 24, fontWeight: 600 }}>{summary.count}</div>
            </div>
            <div className="exams-summary-item">
              <div className="exams-summary-label" style={{ fontSize: 13 }}>平均分</div>
              <div className="exams-summary-value" style={{ fontSize: 24, fontWeight: 600 }}>{summary.avgScore}</div>
            </div>
            <div className="exams-summary-item">
              <div className="exams-summary-label" style={{ fontSize: 13 }}>平均得分率</div>
              <div className="exams-summary-value" style={{ fontSize: 24, fontWeight: 600 }}>{(summary.avgRate * 100).toFixed(1)}%</div>
            </div>
            <div className="exams-summary-item">
              <div className="exams-summary-label" style={{ fontSize: 13 }}>最高分</div>
              <div className="exams-summary-value" style={{ fontSize: 24, fontWeight: 600 }}>{summary.bestScore}</div>
              <div className="exams-summary-sub" style={{ fontSize: 12 }}>{summary.bestTakenAt}</div>
            </div>
            <div className="exams-summary-item">
              <div className="exams-summary-label" style={{ fontSize: 13 }}>进步幅度</div>
              <div
                className={
                  'exams-summary-value exams-improve ' +
                  (summary.count < 2
                    ? 'is-flat'
                    : summary.improvement > 0
                    ? 'is-up'
                    : summary.improvement < 0
                    ? 'is-down'
                    : 'is-flat')
                }
                style={{ fontSize: 24, fontWeight: 600 }}
              >
                {summary.count < 2 ? '—' : summary.improvement > 0 ? `+${summary.improvement} 分` : summary.improvement < 0 ? `${summary.improvement} 分` : '持平'}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 各科汇总 */}
      <div className="card">
        <h2>各科汇总</h2>
        {bySubjectLoading ? (
          <div className="loading">加载中…</div>
        ) : bySubjectError ? (
          <div className="error-box">{bySubjectError}</div>
        ) : !bySubject || bySubject.subjects.length === 0 ? (
          <div className="empty">还没有分科模考记录</div>
        ) : (
          <ul className="list">
            {bySubject.subjects.map((item) => (
              <li className="list-item" key={item.subject}>
                {SUBJECT_NAME[item.subject]}：共 {item.count} 场，平均分 {item.avgScore}，平均得分率 {(item.avgRate * 100).toFixed(1)}%，最高分 {item.bestScore}，进步 {item.count < 2 ? '—' : item.improvement > 0 ? `+${item.improvement} 分` : item.improvement < 0 ? `${item.improvement} 分` : '持平'}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 趋势图 */}
      <div className="card">
        <div className="form-row exams-trend-head" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>得分率趋势</h2>
          <label className="exams-trend-subject">
            科目{' '}
            <select
              className="select"
              value={trendSubject}
              onChange={(e) => setTrendSubject(e.target.value as SubjectKey)}
            >
              {SUBJECTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {trendLoading ? (
          <div className="loading">加载中…</div>
        ) : trendError ? (
          <div className="error-box">{trendError}</div>
        ) : trendChart ? (
          <svg
            width="100%"
            viewBox={`0 0 ${trendChart.W} ${trendChart.H}`}
            style={{ display: 'block', marginTop: 12 }}
          >
            {/* 坐标轴底线 */}
            <line
              className="exams-trend-axis"
              x1={40}
              y1={156}
              x2={560}
              y2={156}
              strokeWidth={1}
            />
            {/* 折线 */}
            <polyline
              points={trendChart.polyline}
              fill="none"
              stroke="var(--c-math, #4f7cff)"
              strokeWidth={2}
            />
            {/* 圆点与百分比标注 */}
            {trendChart.points.map((p, i) => (
              <g key={i}>
                <circle className="exams-trend-dot" cx={p.x} cy={p.y} r={4} />
                <text
                  className="exams-trend-text"
                  x={p.x}
                  y={p.y - 8}
                  fontSize={12}
                  textAnchor="middle"
                >
                  {(p.rate * 100).toFixed(0)}%
                </text>
              </g>
            ))}
          </svg>
        ) : (
          <div className="empty">暂无数据</div>
        )}
      </div>

      {/* 记录表 */}
      <div className="card exams-records">
        <div className="form-row exams-records-head" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>考试记录</h2>
          <div className="form-row exams-records-actions" style={{ gap: 8 }}>
            <button
              className="btn btn-sm exams-export-btn"
              onClick={handleExport}
              disabled={exporting}
            >
              {exporting ? '导出中…' : '导出 CSV'}
            </button>
            <label className="exams-filter">
              筛选{' '}
              <select
                className="select"
                value={subjectFilter}
                onChange={(e) =>
                  setSubjectFilter(e.target.value as SubjectFilter)
                }
              >
                <option value="all">全部</option>
                {SUBJECTS.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>


        {recordsLoading ? (
          <div className="loading">加载中…</div>
        ) : recordsError ? (
          <div className="error-box">{recordsError}</div>
        ) : records.length === 0 ? (
          <div className="empty">暂无记录</div>
        ) : (
          <table className="table exams-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>科目</th>
                <th>试卷</th>
                <th>得分</th>
                <th>得分率</th>
                <th>时长</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
              <>
                <tr key={r.id}>
                  <td data-label="日期">{r.takenAt}</td>
                  <td data-label="科目">
                    <span className={`badge badge-${r.subject}`}>
                      {SUBJECT_NAME[r.subject]}
                    </span>
                  </td>
                  <td data-label="试卷">{r.paper}</td>
                  <td data-label="得分">
                    {r.score}/{r.totalScore}
                  </td>
                  <td data-label="得分率">{rateOf(r)}</td>
                  <td data-label="时长">{r.durationMinutes} 分钟</td>
                  <td data-label="操作" className="exams-table-action">
                    <button
                      className="btn btn-sm"
                      style={{ marginRight: 8 }}
                      onClick={() => void toggleRelated(r)}
                      disabled={relatedLoadingId === r.id}
                    >
                      {relatedLoadingId === r.id ? '加载中…' : relatedOpenId === r.id ? '收起' : '相关错题'}
                    </button>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => handleDelete(r.id)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
                {relatedOpenId === r.id && (
                  <tr className="exams-related-row">
                    <td colSpan={7}>
                      {related[r.id] === undefined || related[r.id].length === 0 ? (
                        <span className="stat-label">附近没有错题记录</span>
                      ) : (
                        <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
                          {related[r.id].map((m) => (
                            <li key={m.id}>
                              <span className={`badge badge-${m.subject}`}>{SUBJECT_NAME[m.subject]}</span>{' '}
                              {m.title}（{m.mastered ? '已掌握' : '未掌握'}）
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                )}
              </>
            ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
