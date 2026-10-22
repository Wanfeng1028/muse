import { useState } from 'react';
import type { ScheduledTask } from '../api';

export interface ScheduleFormValue {
  name: string;
  interval_sec: number;
  agent_id: string;
  task_title: string;
  prompt: string;
}

type Unit = 'minute' | 'hour' | 'day';

export default function ScheduleForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: ScheduledTask;
  onSubmit: (v: ScheduleFormValue) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? '');
  const [amount, setAmount] = useState(
    initial ? String(Math.round(initial.interval_sec / 60)) : '60'
  );
  const [unit, setUnit] = useState<Unit>('minute');
  const [agentId, setAgentId] = useState(initial?.agent_id ?? '');
  const [taskTitle, setTaskTitle] = useState(initial?.task_title ?? '');
  const [prompt, setPrompt] = useState(initial?.prompt ?? '');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit() {
    const trimmedName = name.trim();
    const n = Number(amount);
    const mult = unit === 'minute' ? 60 : unit === 'hour' ? 3600 : 86400;
    const secs = Math.round(n * mult);

    if (trimmedName === '') {
      setErr('名称不能为空');
      return;
    }
    if (!Number.isFinite(n) || n <= 0) {
      setErr('间隔须为正数');
      return;
    }
    if (secs < 60) {
      setErr('间隔不能小于 1 分钟');
      return;
    }
    if (prompt.trim() === '') {
      setErr('任务内容不能为空');
      return;
    }

    setBusy(true);
    try {
      await onSubmit({
        name: trimmedName,
        interval_sec: secs,
        agent_id: agentId.trim(),
        task_title: taskTitle.trim(),
        prompt: prompt.trim(),
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wf-form">
      <div className="wf-field">
        <label className="wf-label">名称</label>
        <input
          className="wf-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="如：每日早报"
        />
      </div>

      <div className="wf-row">
        <div className="wf-field">
          <label className="wf-label">间隔</label>
          <input
            className="wf-input"
            type="number"
            min={1}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <div className="wf-field">
          <label className="wf-label">单位</label>
          <select
            className="wf-select"
            value={unit}
            onChange={(e) => setUnit(e.target.value as Unit)}
          >
            <option value="minute">分钟</option>
            <option value="hour">小时</option>
            <option value="day">天</option>
          </select>
        </div>
      </div>

      <div className="wf-field">
        <label className="wf-label">执行者（可空，不填自动挑选）</label>
        <input
          className="wf-input"
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          placeholder="adapter id"
        />
      </div>

      <div className="wf-field">
        <label className="wf-label">任务标题（可空）</label>
        <input
          className="wf-input"
          value={taskTitle}
          onChange={(e) => setTaskTitle(e.target.value)}
        />
      </div>

      <div className="wf-field">
        <label className="wf-label">任务内容</label>
        <textarea
          className="wf-textarea"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="到点后发给执行者的任务正文"
        />
      </div>

      {err ? <div className="wf-err">{err}</div> : null}

      <div className="wf-actions">
        <button type="button" className="wf-cancel" onClick={onCancel}>
          取消
        </button>
        <button
          type="button"
          className="wf-submit"
          disabled={busy}
          onClick={() => void submit()}
        >
          {busy ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  );
}