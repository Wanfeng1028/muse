import { useState } from 'react';
import { ClockIcon, PlayIcon, PauseIcon, TrashIcon, PlusIcon } from '../icons';

// 复刻 Codex 的自动化/定时任务视图（逆向自 automation chunk）
const SEED = [
  { id: 1, name: 'Morning brief', cron: '0 9 * * *', last: '今天 09:00', on: true, desc: '汇总昨夜 CI 状态发到 thread' },
  { id: 2, name: 'Dependency check', cron: '0 2 * * 1', last: '周一 02:00', on: true, desc: '每周检查过期依赖并提 PR' },
  { id: 3, name: 'DB backup verify', cron: '30 3 * * *', last: '今天 03:30', on: false, desc: '验证备份可恢复性' },
];

export default function SchedulesView() {
  const [items, setItems] = useState(SEED);
  const toggle = (id) => setItems(items.map((i) => (i.id === id ? { ...i, on: !i.on } : i)));
  const remove = (id) => setItems(items.filter((i) => i.id !== id));
  return (
    <div className="page-scroll">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <h1>Automations</h1>
            <p className="page-desc">Scheduled tasks Codex runs on its own.</p>
          </div>
          <button className="btn-primary"><PlusIcon size={13} /> New automation</button>
        </div>
        {items.map((a) => (
          <div className="auto-card" key={a.id}>
            <span className="tool-icon"><ClockIcon /></span>
            <div className="auto-info">
              <div className="auto-name">{a.name} {!a.on && <span className="pill">paused</span>}</div>
              <div className="auto-desc">{a.desc}</div>
              <div className="auto-meta mono">{a.cron} · last run {a.last}</div>
            </div>
            <button className="icon-btn sm" title={a.on ? 'Pause' : 'Resume'} onClick={() => toggle(a.id)}>
              {a.on ? <PauseIcon /> : <PlayIcon />}
            </button>
            <button className="icon-btn sm danger" title="Delete" onClick={() => remove(a.id)}>
              <TrashIcon />
            </button>
          </div>
        ))}
        {items.length === 0 && <div className="empty-note">No automations yet.</div>}
      </div>
    </div>
  );
}
