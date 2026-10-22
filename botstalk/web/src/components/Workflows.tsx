import { useEffect, useState } from 'react';
import { X, Clock, Zap, Plus, Pencil, Trash2, Power } from 'lucide-react';
import {
  fetchSchedules, createSchedule, updateSchedule, deleteSchedule,
  fetchTriggers, createTrigger, updateTrigger, deleteTrigger,
} from '../api';
import type { ScheduledTask, TriggerRule, NewScheduledTask } from '../api';
import ScheduleForm, { type ScheduleFormValue } from './ScheduleForm';
import TriggerForm, { type TriggerFormValue } from './TriggerForm';

type TabKey = 'schedule' | 'trigger';

function fmtInterval(sec: number): string {
  if (sec >= 86400) return `${Math.floor(sec / 86400)} 天`;
  if (sec >= 3600) return `${Math.floor(sec / 3600)} 小时`;
  return `${Math.floor(sec / 60)} 分钟`;
}

function fmtNext(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}-${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function matchLabel(t: string): string {
  return t === 'keyword' ? '关键词' : t === 'sender' ? '发送者' : '任务事件';
}

function fmtCooldown(sec: number): string {
  return sec >= 60 ? `${Math.floor(sec / 60)} 分钟` : `${sec} 秒`;
}

export default function Workflows({ room, onClose }: { room: string; onClose: () => void }) {
  const [tab, setTab] = useState<TabKey>('schedule');
  const [schedules, setSchedules] = useState<ScheduledTask[]>([]);
  const [triggers, setTriggers] = useState<TriggerRule[]>([]);
  const [err, setErr] = useState('');
  const [showSchedForm, setShowSchedForm] = useState(false);
  const [editingSched, setEditingSched] = useState<ScheduledTask | null>(null);
  const [showTrigForm, setShowTrigForm] = useState(false);
  const [editingTrig, setEditingTrig] = useState<TriggerRule | null>(null);

  const reload = async () => {
    setErr('');
    try {
      if (tab === 'schedule') {
        setSchedules(await fetchSchedules(room));
      } else {
        setTriggers(await fetchTriggers(room));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      if (tab === 'schedule') {
        setSchedules([]);
      } else {
        setTriggers([]);
      }
    }
  };

  useEffect(() => {
    void reload();
  }, [tab, room]);

  const toggleSched = async (item: ScheduledTask) => {
    try {
      await updateSchedule(room, item.id, { enabled: !item.enabled });
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const delSched = async (item: ScheduledTask) => {
    if (!window.confirm(`删除定时任务「${item.name}」？`)) return;
    try {
      await deleteSchedule(room, item.id);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const submitSched = async (v: ScheduleFormValue) => {
    try {
      if (editingSched) {
        await updateSchedule(room, editingSched.id, {
          name: v.name,
          interval_sec: v.interval_sec,
          agent_id: v.agent_id || null,
          task_title: v.task_title || undefined,
          prompt: v.prompt,
        });
      } else {
        const input: NewScheduledTask = {
          name: v.name,
          interval_sec: v.interval_sec,
          agent_id: v.agent_id || undefined,
          task_title: v.task_title || undefined,
          prompt: v.prompt,
        };
        await createSchedule(room, input);
      }
      setShowSchedForm(false);
      setEditingSched(null);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const toggleTrig = async (item: TriggerRule) => {
    try {
      await updateTrigger(room, item.id, { enabled: !item.enabled });
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const delTrig = async (item: TriggerRule) => {
    if (!window.confirm(`删除触发规则「${item.name}」？`)) return;
    try {
      await deleteTrigger(room, item.id);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const submitTrig = async (v: TriggerFormValue) => {
    try {
      if (editingTrig) {
        await updateTrigger(room, editingTrig.id, {
          name: v.name,
          match_type: v.match_type,
          pattern: v.pattern,
          agent_id: v.agent_id || null,
          task_title: v.task_title || undefined,
          prompt: v.prompt,
          cooldown_sec: v.cooldown_sec,
        });
      } else {
        await createTrigger(room, {
          name: v.name,
          match_type: v.match_type,
          pattern: v.pattern,
          agent_id: v.agent_id || undefined,
          task_title: v.task_title || undefined,
          prompt: v.prompt,
          cooldown_sec: v.cooldown_sec,
        });
      }
      setShowTrigForm(false);
      setEditingTrig(null);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section className="appr-panel" aria-label="工作流">
      <header className="appr-head">
        <div>
          <h2 className="appr-title">工作流</h2>
          <div className="appr-stats">
            {tab === 'schedule'
              ? `${schedules.length} 个定时任务`
              : `${triggers.length} 条触发规则`}
          </div>
        </div>
        <button
          type="button"
          className="appr-close"
          onClick={onClose}
          aria-label="关闭"
        >
          <X size={16} />
        </button>
      </header>

      <div className="wf-tabs">
        <button
          type="button"
          className={`wf-tab ${tab === 'schedule' ? 'active' : ''}`}
          onClick={() => setTab('schedule')}
        >
          <Clock size={14} /> 定时任务
        </button>
        <button
          type="button"
          className={`wf-tab ${tab === 'trigger' ? 'active' : ''}`}
          onClick={() => setTab('trigger')}
        >
          <Zap size={14} /> 触发规则
        </button>
      </div>

      {tab === 'schedule' ? (
        <>
          <div className="appr-hint">
            到点自动派发任务给执行者，间隔至少 1 分钟。
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setEditingSched(null);
                setShowSchedForm(true);
              }}
            >
              <Plus size={14} /> 新建
            </button>
          </div>

          {showSchedForm ? (
            <ScheduleForm
              initial={editingSched ?? undefined}
              onSubmit={submitSched}
              onCancel={() => setShowSchedForm(false)}
            />
          ) : null}

          <div className="appr-list">
            {err ? <div className="wf-err">{err}</div> : null}
            {schedules.length === 0 && !showSchedForm ? (
              <div className="appr-empty">
                还没有定时任务
                <div className="appr-empty-sub">点新建添加第一条</div>
              </div>
            ) : (
              schedules.map((item) => (
                <article
                  key={item.id}
                  className={`appr-card${!item.enabled ? ' wf-card-off' : ''}`}
                >
                  <div className="appr-card-top">
                    <h3 className="appr-title-text">{item.name}</h3>
                    <button
                      type="button"
                      className={`wf-toggle${item.enabled ? ' on' : ''}`}
                      title={item.enabled ? '停用' : '启用'}
                      onClick={() => toggleSched(item)}
                    >
                      <Power size={14} />
                    </button>
                  </div>
                  <div className="appr-meta">
                    {`每 ${fmtInterval(item.interval_sec)} 运行 · 下次 ${fmtNext(item.next_run_ms)}`}
                  </div>
                  <div className="appr-meta">
                    {item.task_title || item.prompt.slice(0, 30)}
                    {item.agent_id ? ` → ${item.agent_id}` : ''}
                  </div>
                  <div className="appr-actions">
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => {
                        setEditingSched(item);
                        setShowSchedForm(true);
                      }}
                    >
                      <Pencil size={14} /> 编辑
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => delSched(item)}
                    >
                      <Trash2 size={14} /> 删除
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        </>
      ) : (
        <>
          <div className="appr-hint">
            消息命中规则时自动派发任务，prompt 支持占位符 {'{text}'} {'{sender}'} {'{room}'}。
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setEditingTrig(null);
                setShowTrigForm(true);
              }}
            >
              <Plus size={14} /> 新建
            </button>
          </div>

          {showTrigForm ? (
            <TriggerForm
              initial={editingTrig ?? undefined}
              onSubmit={submitTrig}
              onCancel={() => setShowTrigForm(false)}
            />
          ) : null}

          <div className="appr-list">
            {err ? <div className="wf-err">{err}</div> : null}
            {triggers.length === 0 && !showTrigForm ? (
              <div className="appr-empty">
                还没有触发规则
                <div className="appr-empty-sub">点新建添加第一条</div>
              </div>
            ) : (
              triggers.map((item) => (
                <article
                  key={item.id}
                  className={`appr-card${!item.enabled ? ' wf-card-off' : ''}`}
                >
                  <div className="appr-card-top">
                    <h3 className="appr-title-text">{item.name}</h3>
                    <button
                      type="button"
                      className={`wf-toggle${item.enabled ? ' on' : ''}`}
                      title={item.enabled ? '停用' : '启用'}
                      onClick={() => toggleTrig(item)}
                    >
                      <Power size={14} />
                    </button>
                  </div>
                  <div className="appr-meta">
                    {matchLabel(item.match_type)} · {item.pattern}
                  </div>
                  <div className="appr-meta">
                    {item.prompt.slice(0, 30)} · 冷却 {fmtCooldown(item.cooldown_sec)}
                    {item.agent_id ? ` → ${item.agent_id}` : ''}
                  </div>
                  <div className="appr-actions">
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => {
                        setEditingTrig(item);
                        setShowTrigForm(true);
                      }}
                    >
                      <Pencil size={14} /> 编辑
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => delTrig(item)}
                    >
                      <Trash2 size={14} /> 删除
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        </>
      )}
    </section>
  );
}