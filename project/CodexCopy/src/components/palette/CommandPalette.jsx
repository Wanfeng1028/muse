import { useState, useEffect, useRef } from 'react';
import { SearchIcon, CommandIcon, PlusIcon, SettingsIcon, ClockIcon } from '../icons';

// 复刻 Codex 的 Cmd+K 命令面板（逆向自 cmdk 相关 chunks）
const COMMANDS = [
  { group: 'Threads', items: [
    { id: 'new', label: 'New thread', icon: <PlusIcon />, hint: '⌘N' },
    { id: 'search', label: 'Search threads…', icon: <SearchIcon />, hint: '⌘F' },
  ]},
  { group: 'Go to', items: [
    { id: 'settings', label: 'Open settings', icon: <SettingsIcon /> },
    { id: 'schedules', label: 'View automations', icon: <ClockIcon /> },
  ]},
  { group: 'Thread actions', items: [
    { id: 'compact', label: 'Compact thread context', icon: <CommandIcon /> },
    { id: 'rename', label: 'Rename thread', icon: <CommandIcon /> },
  ]},
];

export default function CommandPalette({ open, onClose, onAction }) {
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const inputRef = useRef(null);
  const flat = COMMANDS.flatMap((g) =>
    g.items.filter((i) => i.label.toLowerCase().includes(q.toLowerCase())).map((i) => ({ ...i, group: g.group }))
  );

  useEffect(() => {
    if (open) { setQ(''); setSel(0); setTimeout(() => inputRef.current?.focus(), 30); }
  }, [open ]);
  useEffect(() => setSel(0), [q]);

  if (!open) return null;
  const run = (id) => { onClose(); onAction(id); };

  return (
    <div className="palette-mask" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input">
          <SearchIcon />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Type a command or search…"
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setSel(Math.min(sel + 1, flat.length - 1)); }
              if (e.key === 'ArrowUp') { e.preventDefault(); setSel(Math.max(sel - 1, 0)); }
              if (e.key === 'Enter' && flat[sel]) run(flat[sel].id);
              if (e.key === 'Escape') onClose();
            }}
          />
          <kbd>esc</kbd>
        </div>
        <div className="palette-list">
          {flat.map((c, i) => (
            <div key={c.id} className={'palette-item' + (i === sel ? ' sel' : '')}
              onMouseEnter={() => setSel(i)} onClick={() => run(c.id)}>
              <span className="palette-icon">{c.icon}</span>
              <span>{c.label}</span>
              {c.hint && <kbd>{c.hint}</kbd>}
            </div>
          ))}
          {flat.length === 0 && <div className="palette-empty">No commands found</div>}
        </div>
      </div>
    </div>
  );
}
