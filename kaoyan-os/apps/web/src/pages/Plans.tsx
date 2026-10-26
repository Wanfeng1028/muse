import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import {
  SUBJECTS,
  type SubjectKey,
  type Plan,
  type PlanSummary,
  type OverduePlansResponse,
  type PlansBySubjectResponse,
  type PlanProgress,
  type AutoScheduleInput,
  type AutoScheduleItem,
  type AutoScheduleResult,
} from '@kaoyan/shared';

// 本地日期 -> YYYY-MM-DD
function localDateStr(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

const subjectMap: Record<SubjectKey, { name: string; color: string }> = SUBJECTS.reduce(
  (acc, s) => {
    acc[s.key] = { name: s.name, color: s.color };
    return acc;
  },
  {} as Record<SubjectKey, { name: string; color: string }>
);

type Filter = '' | SubjectKey;

export default function Plans() {
  const [date, setDate] = useState<string>(localDateStr());
  const [subjectFilter, setSubjectFilter] = useState<Filter>('');

  const [plans, setPlans] = useState<Plan[]>([]);
  const [summary, setSummary] = useState<PlanSummary | null>(null);
  const [overdue, setOverdue] = useState<OverduePlansResponse | null>(null);
  const [bySubject, setBySubject] = useState<PlansBySubjectResponse | null>(null);
  const [bySubjectWindow, setBySubjectWindow] = useState<'all' | '7' | '1'>('all');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  // 新增表单
  const [title, setTitle] = useState<string>('');
  const [subject, setSubject] = useState<SubjectKey>('math');
  const [plannedMinutes, setPlannedMinutes] = useState<number>(60);
  const [newDate, setNewDate] = useState<string>(date);

  // 智能排期弹窗
  const [schedOpen, setSchedOpen] = useState(false);
  const [schedSubjects, setSchedSubjects] = useState<SubjectKey[]>(['math']);
  const [schedDailyMinutes, setSchedDailyMinutes] = useState(240);
  const [schedExamDate, setSchedExamDate] = useState('2026-12-19');
  const [schedStartDate, setSchedStartDate] = useState(localDateStr());
  const [schedPreview, setSchedPreview] = useState<AutoScheduleItem[] | null>(null);
  const [schedBusy, setSchedBusy] = useState(false);
  const [schedError, setSchedError] = useState('');

  const toggleSchedSubject = (key: SubjectKey) => {
    setSchedSubjects((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
    setSchedPreview(null);
  };

  const handleSchedPreview = async () => {
    if (schedSubjects.length === 0) {
      setSchedError('请至少选择一个科目');
      return;
    }
    setSchedBusy(true);
    setSchedError('');
    try {
      const data = await api.autoSchedulePreview({
        subjects: schedSubjects.join(','),
        dailyMinutes: Number(schedDailyMinutes) || 0,
        examDate: schedExamDate,
        startDate: schedStartDate,
      });
      setSchedPreview(data.items);
    } catch (e) {
      setSchedError(e instanceof Error ? e.message : '生成预览失败');
    } finally {
      setSchedBusy(false);
    }
  };

  const handleSchedConfirm = async () => {
    if (schedSubjects.length === 0) {
      setSchedError('请至少选择一个科目');
      return;
    }
    setSchedBusy(true);
    setSchedError('');
    try {
      const input: AutoScheduleInput = {
        subjects: schedSubjects,
        dailyMinutes: Number(schedDailyMinutes) || 0,
        examDate: schedExamDate,
        startDate: schedStartDate,
      };
      await api.autoSchedule(input);
      setSchedOpen(false);
      setSchedPreview(null);
      await loadList();
    } catch (e) {
      setSchedError(e instanceof Error ? e.message : '生成失败');
    } finally {
      setSchedBusy(false);
    }
  };

  const loadList = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params: { date: string; subject?: SubjectKey } = { date };
      if (subjectFilter) params.subject = subjectFilter;
      const [list, sum, ov, bySub] = await Promise.all([
        api.listPlans(params),
        api.planSummary(date),
        api.overduePlans(),
        api.plansBySubject(bySubjectWindow === 'all' ? undefined : Number(bySubjectWindow)),
      ]);
      setPlans(list);
      setSummary(sum);
      setOverdue(ov);
      setBySubject(bySub);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [date, subjectFilter, bySubjectWindow]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  // 日期切换时同步新增表单的默认日期
  useEffect(() => {
    setNewDate(date);
  }, [date]);

  const handleToggle = async (plan: Plan) => {
    try {
      await api.updatePlan(plan.id, { done: !plan.done });
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : '更新失败');
    }
  };

  const handleOverdueDone = async (plan: Plan) => {
    try {
      await api.updatePlan(plan.id, { done: true });
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : '更新失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.deletePlan(id);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await api.createPlan({
        date: newDate,
        subject,
        title: title.trim(),
        plannedMinutes: Number(plannedMinutes) || 0,
      });
      setTitle('');
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建失败');
    }
  };

  const summaryText = useMemo(() => {
    if (!summary) return '';
    return `共 ${summary.total} 项、完成 ${summary.done} 项`;
  }, [summary]);

  return (
    <div className="page">
      <div className="page-header">
                <h1>复习计划</h1>
                <button
                  className="btn btn-primary btn-sm"
                  type="button"
                  onClick={() => setSchedOpen(true)}
                >
                  智能排期
                </button>
        <div className="form-row plans-filter-row">
          <input
            className="input"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
          <select
            className="select"
            value={subjectFilter}
            onChange={(e) => setSubjectFilter(e.target.value as Filter)}
          >
            <option value="">全部</option>
            {SUBJECTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 新增计划 */}
      <form className="card plans-create-form" onSubmit={handleCreate}>
        <div className="form-grid plans-form-grid">
          <input
            className="input"
            type="text"
            placeholder="计划标题"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <select
            className="select"
            value={subject}
            onChange={(e) => setSubject(e.target.value as SubjectKey)}
          >
            {SUBJECTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </select>
          <input
            className="input"
            type="number"
            min={0}
            placeholder="计划分钟"
            value={plannedMinutes}
            onChange={(e) => setPlannedMinutes(Number(e.target.value))}
          />
          <input
            className="input"
            type="date"
            value={newDate}
            onChange={(e) => setNewDate(e.target.value)}
          />
          <button className="btn btn-primary" type="submit">
            添加
          </button>
        </div>
      </form>

      {/* 概要 */}
      {summary && (
        <div className="stat-card plans-summary-card">{summaryText}</div>
      )}

      {overdue && overdue.count > 0 && (
        <div className="card plans-overdue-card">
          <h2>逾期未完成（{overdue.count}）</h2>
          <ul className="list plans-overdue-list">
            {overdue.plans.map((plan) => (
              <li className="list-item plans-overdue-item" key={plan.id}>
                <span className={`badge badge-${plan.subject}`}>
                  {subjectMap[plan.subject]?.name ?? plan.subject}
                </span>
                <span>{plan.title}</span>
                <span data-label="原定日期">{plan.date}</span>
                <span>{`${plan.plannedMinutes} 分钟`}</span>
                <button
                  className="btn btn-primary btn-sm"
                  type="button"
                  onClick={() => void handleOverdueDone(plan)}
                >
                  标为完成
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {bySubject && bySubject.subjects.length > 0 && (
        <div className="card plans-bysubject-card">
          <h2>各科汇总</h2>
          <div className="form-row">
            <button
              type="button"
              className={bySubjectWindow === 'all' ? 'btn btn-primary' : 'btn btn-ghost'}
              onClick={() => setBySubjectWindow('all')}
            >
              全部
            </button>
            <button
              type="button"
              className={bySubjectWindow === '7' ? 'btn btn-primary' : 'btn btn-ghost'}
              onClick={() => setBySubjectWindow('7')}
            >
              近 7 天
            </button>
            <button
              type="button"
              className={bySubjectWindow === '1' ? 'btn btn-primary' : 'btn btn-ghost'}
              onClick={() => setBySubjectWindow('1')}
            >
              今日
            </button>
          </div>
          <ul className="list plans-bysubject-list">
            {bySubject.subjects.map((s) => (
              <li className="list-item plans-bysubject-item" key={s.subject}>
                <span className={`badge badge-${s.subject}`}>
                  {subjectMap[s.subject]?.name ?? s.subject}
                </span>
                <span>{`共 ${s.total} 条，已完成 ${s.done} 条`}</span>
                <span>{`完成率 ${Math.round(s.completionRate * 100)}%`}</span>
                <span>{`计划 ${s.plannedMinutes} 分钟，已专注 ${s.actualMinutes} 分钟`}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {schedOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.45)',
            zIndex: 80,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
          onClick={() => setSchedOpen(false)}
        >
          <div
            className="card"
            style={{ width: '100%', maxWidth: 560, maxHeight: '85vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0 }}>智能排期</h2>
            <div className="form-row" style={{ gap: 12, flexWrap: 'wrap' }}>
              {SUBJECTS.map((s) => (
                <label key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <input
                    type="checkbox"
                    checked={schedSubjects.includes(s.key)}
                    onChange={() => toggleSchedSubject(s.key)}
                  />
                  {s.name}
                </label>
              ))}
            </div>
            <div className="form-grid" style={{ marginTop: 12 }}>
              <label>
                每日分钟数
                <input
                  className="input"
                  type="number"
                  min={30}
                  value={schedDailyMinutes}
                  onChange={(e) => {
                    setSchedDailyMinutes(Number(e.target.value));
                    setSchedPreview(null);
                  }}
                />
              </label>
              <label>
                考试日期
                <input
                  className="input"
                  type="date"
                  value={schedExamDate}
                  onChange={(e) => {
                    setSchedExamDate(e.target.value);
                    setSchedPreview(null);
                  }}
                />
              </label>
              <label>
                开始日期
                <input
                  className="input"
                  type="date"
                  value={schedStartDate}
                  onChange={(e) => {
                    setSchedStartDate(e.target.value);
                    setSchedPreview(null);
                  }}
                />
              </label>
            </div>
            {schedError && <div className="error-box">{schedError}</div>}
            <div className="form-row" style={{ marginTop: 12, gap: 8 }}>
              <button
                className="btn btn-primary btn-sm"
                type="button"
                disabled={schedBusy}
                onClick={() => void handleSchedPreview()}
              >
                {schedBusy ? '生成中…' : '生成预览'}
              </button>
              <button
                className="btn btn-sm"
                type="button"
                onClick={() => setSchedOpen(false)}
              >
                关闭
              </button>
            </div>
            {schedPreview && (
              <div style={{ marginTop: 12 }}>
                <div className="stat-label">共 {schedPreview.length} 条，先看前 10 条：</div>
                <ul style={{ paddingLeft: 18, margin: '8px 0' }}>
                  {schedPreview.slice(0, 10).map((item, i) => (
                    <li key={i}>
                      {item.date} {item.title}（{item.plannedMinutes} 分钟）
                    </li>
                  ))}
                </ul>
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={schedBusy}
                  onClick={() => void handleSchedConfirm()}
                >
                  {schedBusy ? '写入中…' : `确认生成（${schedPreview.length} 条）`}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
      {error && <div className="error-box">{error}</div>}

      {loading ? (
        <div className="loading">加载中…</div>
      ) : plans.length === 0 ? (
        <div className="empty">暂无计划</div>
      ) : (
        <div className="list plans-list">
          {plans.map((plan) => {
            const s = subjectMap[plan.subject];
            const actual =
              summary?.plans?.find((p) => p.id === plan.id)?.actualMinutes ?? 0;
            const planned = plan.plannedMinutes;
            const pct =
              planned > 0 ? Math.min(100, Math.round((actual / planned) * 100)) : 0;
            return (
              <div className="list-item plans-list-item" key={plan.id}>
                <div className="plans-item-main">
                  <input
                    className="plans-checkbox"
                    type="checkbox"
                    checked={plan.done}
                    onChange={() => void handleToggle(plan)}
                  />
                  <span className={`badge badge-${plan.subject}`}>{s?.name ?? plan.subject}</span>
                  <span
                    className="plans-item-title"
                    style={{
                      flex: 1,
                      textDecoration: plan.done ? 'line-through' : 'none',
                      color: plan.done ? '#999' : 'inherit',
                    }}
                  >
                    {plan.title}
                  </span>
                </div>
                <div className="plans-item-meta">
                  <span className="plans-item-minutes" data-label="时长">
                    {plan.plannedMinutes} 分钟
                  </span>
                  <button
                    className="btn btn-danger btn-sm plans-item-del"
                    onClick={() => void handleDelete(plan.id)}
                  >
                    删除
                  </button>
                </div>
                <div className="plans-item-progress">
                  <span className="stat-label">
                    已专注 {actual} / {planned} 分钟
                  </span>
                  <div className="progress">
                    <div
                      className="progress-bar"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
