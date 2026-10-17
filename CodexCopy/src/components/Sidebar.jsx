import { useState } from 'react';
import { PlusIcon, SearchIcon, SettingsIcon, CodexLogo } from './icons';

const STATUS_COLORS = { working: '#e5a54b', done: '#4caf7d', idle: '#8e8e8e' };

export default function Sidebar({ threads, activeId, onSelect, onNew }) {
  const [filter, setFilter] = useState('');
  const groups = {};
  threads.forEach((t) => {
    if (filter && !t.title.toLowerCase().includes(filter.toLowerCase())) return;
    (groups[t.group] = groups[t.group] || []).push(t);
  });

  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <button className="new-thread-btn" onClick={onNew}>
          <PlusIcon />
          <span>New thread</span>
        </button>
        <button className="icon-btn" title="Search">
          <SearchIcon />
        </button>
      </div>

      <div className="sidebar-search" onClick={() => document.getElementById('thread-filter')?.focus()}>
        <SearchIcon />
        <input
          id="thread-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter threads"
          style={{ background: 'transparent', border: 'none', outline: 'none', color: 'inherit', fontSize: 'inherit', width: '100%' }}
        />
        <kbd>⌘K</kbd>
      </div>

      <div className="thread-groups">
        {Object.entries(groups).map(([g, list]) => (
          <div key={g}>
            <div className="thread-group-label">{g}</div>
            {list.map((t) => (
              <div
                key={t.id}
                className={'thread-item' + (t.id === activeId ? ' active' : '')}
                onClick={() => onSelect(t.id)}
              >
                <span className="dot" style={{ background: STATUS_COLORS[t.status] || '#8e8e8e' }} />
                <span className="title">{t.title}</span>
              </div>
            ))}
          </div>
        ))}
        {Object.keys(groups).length === 0 && (
          <div style={{ padding: '20px 10px', color: 'var(--text-tertiary)', fontSize: 13 }}>No threads match</div>
        )}
      </div>

      <div className="sidebar-bottom">
        <div className="avatar">晚</div>
        <div className="user-name">晚风</div>
        <button className="settings-btn" title="Codex settings">
          <SettingsIcon />
        </button>
      </div>
    </aside>
  );
}
