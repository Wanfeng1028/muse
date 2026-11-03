import { useState } from 'react';
import type { TriggerRule } from '../api';

export interface TriggerFormValue {
  name: string;
  match_type: 'keyword' | 'sender' | 'event';
  pattern: string;
  agent_id: string;
  task_title: string;
  prompt: string;
  cooldown_sec: number;
}

export default function TriggerForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: TriggerRule;
  onSubmit: (v: TriggerFormValue) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? '');
  const [matchType, setMatchType] = useState<TriggerFormValue['match_type']>(
    initial?.match_type ?? 'keyword'
  );
  const [pattern, setPattern] = useState(initial?.pattern ?? '');
  const [agentId, setAgentId] = useState(initial?.agent_id ?? '');
  const [taskTitle, setTaskTitle] = useState(initial?.task_title ?? '');
  const [prompt, setPrompt] = useState(initial?.prompt ?? '');
  const [cooldown, setCooldown] = useState(initial ? String(initial.cooldown_sec) : '300');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const patternPlaceholder =
    matchType === 'keyword'
      ? '多个词用逗号分隔，如：早报,日报'
      : matchType === 'sender'
        ? '发送者 id，完全相等才触发'
        : 'done / failed 等任务状态';

  const handleSubmit = async () => {
    if (busy) return;

    if (!name.trim()) {
      setErr('名称不能为空');
      return;
    }
    if (!pattern.trim()) {
      setErr('匹配模式不能为空');
      return;
    }
    if (!prompt.trim()) {
      setErr('任务内容不能为空');
      return;
    }

    const cool = Number(cooldown);
    if (!Number.isInteger(cool) || cool < 0) {
      setErr('冷却秒数须为非负整数');
      return;
    }

    setErr(null);
    setBusy(true);
    try {
      await onSubmit({
        name: name.trim(),
        match_type: matchType,
        pattern: pattern.trim(),
        agent_id: agentId.trim(),
        task_title: taskTitle.trim(),
        prompt: prompt.trim(),
        cooldown_sec: cool,
      });
    } catch (error) {
      setErr(error instanceof Error ? error.message : '保存失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wf-form">
      <div className="wf-field">
        <label className="wf-label">名称</label>
        <input
          className="wf-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="触发器名称"
          disabled={busy}
        />
      </div>

      <div className="wf-field">
        <label className="wf-label">匹配类型</label>
        <select
          className="wf-select"
          value={matchType}
          onChange={(e) => setMatchType(e.target.value as TriggerFormValue['match_type'])}
          disabled={busy}
        >
          <option value="keyword">关键词</option>
          <option value="sender">发送者</option>
          <option value="event">任务事件</option>
        </select>
      </div>

      <div className="wf-field">
        <label className="wf-label">匹配模式</label>
        <input
          className="wf-input"
          value={pattern}
          onChange={(e) => setPattern(e.target.value)}
          placeholder={patternPlaceholder}
          disabled={busy}
        />
      </div>

      <div className="wf-field">
        <label className="wf-label">执行者（可空，不填自动挑选）</label>
        <input
          className="wf-input"
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          placeholder="执行者 id"
          disabled={busy}
        />
      </div>

      <div className="wf-field">
        <label className="wf-label">任务标题（可空）</label>
        <input
          className="wf-input"
          value={taskTitle}
          onChange={(e) => setTaskTitle(e.target.value)}
          placeholder="任务标题"
          disabled={busy}
        />
      </div>

      <div className="wf-field">
        <label className="wf-label">任务内容</label>
        <textarea
          className="wf-textarea"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="支持 {text} {sender} {room} 占位符"
          disabled={busy}
        />
      </div>

      <div className="wf-field">
        <label className="wf-label">冷却秒数</label>
        <input
          className="wf-input"
          type="number"
          min={0}
          value={cooldown}
          onChange={(e) => setCooldown(e.target.value)}
          disabled={busy}
        />
      </div>

      {err ? <div className="wf-err">{err}</div> : null}

      <div className="wf-actions">
        <button
          type="button"
          className="wf-btn"
          onClick={onCancel}
          disabled={busy}
        >
          取消
        </button>
        <button
          type="button"
          className="wf-btn wf-btn-primary"
          onClick={() => {
            void handleSubmit();
          }}
          disabled={busy}
        >
          保存
        </button>
      </div>
    </div>
  );
}