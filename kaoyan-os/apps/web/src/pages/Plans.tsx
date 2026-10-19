import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import {
  SUBJECTS,
  type SubjectKey,
  type Plan,
  type PlanSummary,
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
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  // 新增表单
  const [title, setTitle] = useState<string>('');
  const [subject, setSubject] = useState<SubjectKey>('math');
  const [plannedMinutes, setPlannedMinutes] = useState<number>(60);
  const [newDate, setNewDate] = useState<string>(date);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params: { date: string; subject?: SubjectKey } = { date };
      if (subjectFilter) params.subject = subjectFilter;
      const [list, sum] = await Promise.all([
        api.listPlans(params),
        api.planSummary(date),
      ]);
      setPlans(list);
      setSummary(sum);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [date, subjectFilter]);

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

      {error && <div className="error-box">{error}</div>}

      {loading ? (
        <div className="loading">加载中…</div>
      ) : plans.length === 0 ? (
        <div className="empty">暂无计划</div>
      ) : (
        <div className="list plans-list">
          {plans.map((plan) => {
            const s = subjectMap[plan.subject];
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
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---- api 占位引用：实际项目由 @kaoyan/shared 或全局注入 ----
// 为避免编译期缺失，这里声明所用到的接口签名（与后端契约一致）。
declare const api: {
  listPlans(params: { date: string; subject?: SubjectKey }): Promise<Plan[]>;
  createPlan(input: {
    date: string;
    subject: SubjectKey;
    title: string;
    plannedMinutes: number;
  }): Promise<Plan>;
  updatePlan(id: number, input: { done?: boolean; date?: string; subject?: SubjectKey; title?: string; plannedMinutes?: number }): Promise<Plan>;
  deletePlan(id: number): Promise<void>;
  planSummary(date: string): Promise<PlanSummary>;
};
