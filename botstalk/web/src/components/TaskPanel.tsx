import { useCallback, useEffect, useMemo, useState } from 'react';
import { X, ClipboardList, RotateCcw } from 'lucide-react';
import { fetchTasks, fetchTaskStats, cancelTask, fetchTaskDetail, TaskItem, TaskStatus, TaskProgressReport } from '../api';

interface Props {
  room: string;
  nick: string;
  refreshKey: number;
  onClose: () => void;
  onJumpToTask: (taskId: string) => void;
}

type Filter = 'all' | 'active' | 'done' | 'failed' | 'cancelled' | 'unsupported' | 'timed_out';

const STATUS_TEXT: Record<TaskStatus, string> = {
  dispatched: '已派发',
  running: '执行中',
  done: '已完成',
  failed: '失败',
  unsupported: '无可用',
  cancelled: '已取消',
  timed_out: '已超时',
};

function statusClass(status: TaskStatus): string {
  return `task-pill pill-${status}`;
}

function formatRelative(ms: number, now: number): string {
  const diff = now - ms;
  if (diff < 60_000) return '刚刚';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  const d = new Date(ms);
  const n = new Date(now);
  if (
    d.getFullYear() === n.getFullYear() &&
    d.getMonth() === n.getMonth() &&
    d.getDate() === n.getDate()
  ) {
    return `${Math.floor(diff / 3_600_000)} 小时前`;
  }
  const pad = (v: number) => (v < 10 ? `0${v}` : String(v));
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatFull(ms: number): string {
  const d = new Date(ms);
  const pad = (v: number) => (v < 10 ? `0${v}` : String(v));
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export default function TaskPanel({ room, nick, refreshKey, onClose, onJumpToTask }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TaskItem | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [progress, setProgress] = useState<TaskProgressReport[]>([]);

  useEffect(() => {
    if (selected) {
      const fresh = tasks.find((t) => t.task_id === selected.task_id);
      if (fresh) setSelected(fresh);
    }
  }, [tasks, selected]);
  useEffect(() => {
    if (!selected) { setProgress([]); return; }
    let alive = true;
    fetchTaskDetail(selected.task_id)
      .then((d) => { if (alive) setProgress(d.progress); })
      .catch(() => { if (alive) setProgress([]); });
    return () => { alive = false; };
  }, [selected]);  const [cancelling, setCancelling] = useState<boolean>(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let list: TaskItem[];
      if (filter === 'all') {
        list = await fetchTasks(room);
      } else if (filter === 'active') {
        const [a, b] = await Promise.all([
          fetchTasks(room, 'dispatched'),
          fetchTasks(room, 'running'),
        ]);
        list = [...a, ...b].sort((x, y) => y.updated_at_ms - x.updated_at_ms);
      } else {
        list = await fetchTasks(room, filter);
      }
      const stats = await fetchTaskStats(room);
      setTasks(list);
      setCounts(stats.counts);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [room, filter]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  useEffect(() => {
    if (selected) {
      const fresh = tasks.find((t) => t.task_id === selected.task_id);
      if (fresh) setSelected(fresh);
    }
  }, [tasks, selected]);

  const activeCount = useMemo(
    () => (counts.dispatched ?? 0) + (counts.running ?? 0),
    [counts],
  );

  const now = Date.now();

  const handleCancel = useCallback(async () => {
    if (!selected) return;
    if (!window.confirm('确定取消这个任务吗？')) return;
    setCancelling(true);
    setCancelError(null);
    try {
      const updated = await cancelTask(selected.task_id, nick);
      setSelected(updated);
      await load();
    } catch (e) {
      setCancelError(e instanceof Error ? e.message : '取消失败');
    } finally {
      setCancelling(false);
    }
  }, [selected, nick, load]);

  const canCancel =
    selected !== null &&
    nick === selected.owner &&
    (selected.status === 'dispatched' || selected.status === 'running');

  const filters: { key: Filter; label: string }[] = [
    { key: 'all', label: '全部' },
    { key: 'active', label: '进行中' },
    { key: 'done', label: '已完成' },
    { key: 'failed', label: '失败' },
    { key: 'timed_out', label: '已超时' },
    { key: 'cancelled', label: '已取消' },
    { key: 'unsupported', label: '无可用' },
  ];

  return (
    <div className="task-panel">
      <div className="task-panel-head">
        <div>
          <div>任务追踪</div>
          <div className="task-panel-stats">
            进行中 {activeCount} · 已完成 {counts.done ?? 0} · 失败 {counts.failed ?? 0} · 已超时 {counts.timed_out ?? 0}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭">
          <X size={16} />
        </button>
      </div>

      <div className="task-filter">
        {filters.map((f) => (
          <button
            type="button"
            key={f.key}
            className={`task-filter-chip${filter === f.key ? ' is-active' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading && <div className="task-empty">加载中…</div>}

      {error && (
        <div className="task-error">
          <span>{error}</span>
          <button type="button" onClick={() => void load()}>
            <RotateCcw size={14} />
            重试
          </button>
        </div>
      )}

      {!loading && !error && tasks.length === 0 && (
        <div className="task-empty">
          <ClipboardList size={28} />
          <div>还没有任务</div>
          <div>去聊天里 @ 一位成员派个活吧</div>
        </div>
      )}

      {!loading && !error && tasks.length > 0 && (
        <div className="task-list">
          {tasks.map((t) => (
            <button
              type="button"
              key={t.task_id}
              className="task-row"
              onClick={() => {
                setSelected(t);
                setCancelError(null);
              }}
            >
              <span className={statusClass(t.status)}>{STATUS_TEXT[t.status]}</span>
              <span className="task-row-title">{t.title}</span>
              <span className="task-row-meta">
                派给 {t.assignee ?? '—'} · {t.owner} 派发 · {formatRelative(t.created_at_ms, now)}
              </span>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="task-detail">
          <div className="task-detail-row">
            <span>任务 ID</span>
            <code>{selected.task_id}</code>
          </div>
          <div className="task-detail-row">
            <span>状态</span>
            <span className={statusClass(selected.status)}>{STATUS_TEXT[selected.status]}</span>
          </div>
          <div className="task-detail-row">
            <span>标题</span>
            <span>{selected.title}</span>
          </div>
          <div className="task-detail-row">
            <span>派发人</span>
            <span>{selected.owner}</span>
          </div>
          <div className="task-detail-row">
            <span>执行者</span>
            <span>{selected.assignee ?? '—'}</span>
          </div>
          <div className="task-detail-row">
            <span>创建时间</span>
            <span>{formatFull(selected.created_at_ms)}</span>
          </div>
          <div className="task-detail-row">
            <span>更新时间</span>
            <span>{formatFull(selected.updated_at_ms)}</span>
          </div>
          <div className="task-detail-row">
            <span>超时期限</span>
            <span>{selected.deadline_ms === null ? '无超时限制' : formatFull(selected.deadline_ms)}</span>
          </div>
          {selected.error !== null && (
            <div className="task-detail-row">
              <span>失败原因</span>
              <span>{selected.error}</span>
            </div>
          )}
          <div className="task-detail-row">
            <span>进度上报</span>
            <span>{selected.progress_count} 次</span>
          </div>
          {progress.length > 0 && (
            <div className="task-progress-list">
              {progress.map((pr) => (
                <div key={pr.seq} className="task-progress-item">
                  <span className="task-progress-seq">#{pr.seq}</span>
                  <span className="task-progress-msg">{pr.message}</span>
                  <span className="task-progress-time">{formatFull(pr.created_at_ms)}</span>
                </div>
              ))}
            </div>
          )}

          {cancelError && <div className="task-error">{cancelError}</div>}

          <div className="task-detail-row">
            <button type="button" onClick={() => onJumpToTask(selected.task_id)}>
              在聊天中定位
            </button>
            {canCancel && (
              <button type="button" onClick={() => void handleCancel()} disabled={cancelling}>
                {cancelling ? '取消中…' : '取消任务'}
              </button>
            )}
            <button type="button" onClick={() => setSelected(null)}>
              收起
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
