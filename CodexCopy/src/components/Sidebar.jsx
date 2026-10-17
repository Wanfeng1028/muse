import { useState } from 'react';
import { PlusIcon, SearchIcon, SettingsIcon, ClockIcon, FolderIcon, ChevronDown, CheckIcon } from './icons';

const STATUS_COLORS = { working: '#FA994C', done: '#00a240', idle: '#8f8f8f' };

// 侧栏：项目中心结构（逆向证据："This remote folder will appear as its own project in the sidebar"）
// 过滤器： "Filter sidebar chats" / "All chats" / "Relevant"
export default function Sidebar({ projects, activeChatId, activeProjectId, onSelectChat, onNewChat, onOpenSettings, onOpenSchedules, currentView }) {
  const [filter, setFilter] = useState('');
  const [showFilter, setShowFilter] = useState('all'); // all | relevant
  const [filterOpen, setFilterOpen] = useState(false);
  const [expanded, setExpanded] = useState({ [activeProjectId]: true });

  const toggleExpand = (pid) => setExpanded({ ...expanded, [pid]: !expanded[pid] });

  const matchFilter = (title) => !filter || title.toLowerCase().includes(filter.toLowerCase());

  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <button className="new-thread-btn" onClick={onNewChat}>
          <PlusIcon />
          <span>New chat</span>
        </button>
        <div style={{ position: 'relative' }}>
          <button className="icon-btn" title="Filter sidebar chats" onClick={() => setFilterOpen(!filterOpen)}>
            <SearchIcon />
          </button>
          {filterOpen && (
            <div className="filter-menu">
              <div className="filter-menu-title">Show</div>
              {[
                { id: 'all', label: 'All chats', desc: 'Show threads from all branches' },
                { id: 'relevant', label: 'Relevant', desc: 'Current branch, worktrees, needs attention' },
              ].map((o) => (
                <div key={o.id} className="filter-menu-item" onClick={() => { setShowFilter(o.id); setFilterOpen(false); }}>
                  <span style={{ flex: 1 }}>
                    <div style={{ fontSize: 13 }}>{o.label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{o.desc}</div>
                  </span>
                  {showFilter === o.id && <CheckIcon size={13} />}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="sidebar-search">
        <SearchIcon />
        <input
          id="thread-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter sidebar chats"
          style={{ background: 'transparent', border: 'none', outline: 'none', color: 'inherit', fontSize: 'inherit', width: '100%' }}
        />
        <kbd>⌘K</kbd>
      </div>

      <div className="thread-groups">
        {projects.map((p) => {
          const chats = p.chats.filter((c) => matchFilter(c.title));
          if (showFilter === 'relevant' && p.id !== activeProjectId) return null;
          if (chats.length === 0 && filter) return null;
          const isOpen = expanded[p.id];
          return (
            <div key={p.id} className="project-group">
              <div className="project-head" onClick={() => toggleExpand(p.id)}>
                <span className={'twisty' + (isOpen ? ' open' : '')}><ChevronDown size={12} /></span>
                <span className="project-icon"><FolderIcon /></span>
                <span className="project-name">{p.name}</span>
                <span className="project-branch">{p.branch}</span>
              </div>
              {isOpen && chats.map((c) => (
                <div
                  key={c.id}
                  className={'thread-item nested' + (c.id === activeChatId ? ' active' : '')}
                  onClick={() => onSelectChat(p.id, c.id)}
                >
                  <span className="dot" style={{ background: STATUS_COLORS[c.status] || '#8f8f8f' }} />
                  <span className="title">{c.title}</span>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div className="sidebar-bottom">
        <div className="avatar">晚</div>
        <div className="user-name">晚风</div>
        <button className={'settings-btn' + (currentView === 'schedules' ? ' active' : '')} title="Automations" onClick={onOpenSchedules}>
          <ClockIcon />
        </button>
        <button className={'settings-btn' + (currentView === 'settings' ? ' active' : '')} title="Codex settings" onClick={onOpenSettings}>
          <SettingsIcon />
        </button>
      </div>
    </aside>
  );
}
