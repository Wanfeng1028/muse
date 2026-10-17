import { useState } from 'react';
import {
  PlusIcon, SearchIcon, SettingsIcon, ClockIcon, ChevronDown, CheckIcon,
  PlugIcon, GitIcon, ChatIcon, SidebarIcon, BackIcon, ForwardIcon, FolderIcon,
  SitesIcon, HelpIcon, TaskIcon,
} from './icons';
import { THREAD_MODES } from '../data/mock';

// 最新版：ChatGPT Work（2026-10 合并版）
// 导航：New task / Scheduled / Plugins / Sites / Chat
// Projects 分区；Tasks 分区；底部用户
export default function Sidebar({
  nav, onNav,
  projects, activeProjectId, activeThreadId,
  onSelectThread, onNewTask, onOpenSettings,
}) {
  const [pickMode, setPickMode] = useState(false);

  const NAV = [
    { id: 'new', label: 'New task', icon: <TaskIcon size={16} />, plus: true },
    { id: 'scheduled', label: 'Scheduled', icon: <ClockIcon size={16} /> },
    { id: 'plugins', label: 'Plugins', icon: <PlugIcon size={16} /> },
    { id: 'sites', label: 'Sites', icon: <SitesIcon size={16} /> },
    { id: 'chat', label: 'Chat', icon: <ChatIcon size={16} /> },
  ];

  const startNew = (modeId) => {
    setPickMode(false);
    onNewTask(modeId);
  };

  const activeProject = projects.find((p) => p.id === activeProjectId);

  return (
    <aside className="sidebar-real">
      <div className="sr-top">
        <div className="traffic-lights sm">
          <span className="tl close" /><span className="tl min" /><span className="tl max" />
        </div>
        <button className="sr-icon-btn" title="Toggle sidebar"><SidebarIcon /></button>
        <button className="sr-icon-btn" title="Back"><BackIcon /></button>
        <button className="sr-icon-btn" title="Forward"><ForwardIcon /></button>
      </div>

      <div className="sr-title-row">
        <span className="sr-title">ChatGPT <span className="sr-title-light">Work</span></span>
        <button className="sr-icon-btn" title="Search"><SearchIcon size={16} /></button>
      </div>

      <nav className="sr-nav">
        {NAV.map((n) => n.id === 'new' ? (
          <div key={n.id} style={{ position: 'relative' }}>
            <button className={'sr-nav-item' + (nav === 'new' ? ' active' : '')}
              onClick={() => setPickMode(!pickMode)}>
              <span className="sr-nav-icon">{n.icon}</span>
              <span style={{ flex: 1 }}>{n.label}</span>
            </button>
            {pickMode && (
              <>
                <div className="drop-mask" onClick={() => setPickMode(false)} />
                <div className="drop-menu sr-mode-menu">
                  <div className="filter-menu-title">Choose mode</div>
                  {THREAD_MODES.map((m) => (
                    <div key={m.id} className="drop-item sr-mode-item" onClick={() => startNew(m.id)}>
                      <span style={{ flex: 1 }}>
                        <div className="sr-mode-item-name">{m.name}</div>
                        <div className="sr-mode-item-desc">{m.desc}</div>
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        ) : (
          <button key={n.id}
            className={'sr-nav-item' + (nav === n.id ? ' active' : '')}
            onClick={() => onNav(n.id)}>
            <span className="sr-nav-icon">{n.icon}</span>
            <span>{n.label}</span>
          </button>
        ))}
      </nav>

      <div className="sr-section">Projects</div>
      <div className="sr-projects">
        {projects.map((p) => (
          <div key={p.id}>
            <button className={'sr-nav-item' + (p.id === activeProjectId ? ' sr-proj-active' : '')}
              onClick={() => p.threads[0] && onSelectThread(p.id, p.threads[0].id)}>
              <span className="sr-nav-icon"><FolderIcon size={15} /></span>
              <span className="sr-proj-name">{p.name}</span>
            </button>
            {p.id === activeProjectId && p.threads.map((t) => (
              <button key={t.id}
                className={'sr-nav-item sr-thread' + (t.id === activeThreadId ? ' active' : '')}
                onClick={() => onSelectThread(p.id, t.id)}>
                <span className="sr-proj-name">{t.title}</span>
                {(t.status === 'active' || t.unread) && <span className="blue-dot" />}
              </button>
            ))}
            {p.id === activeProjectId && p.threads.length > 3 && (
              <button className="sr-show-more">Show more</button>
            )}
          </div>
        ))}
      </div>

      <div className="sr-section">Tasks</div>
      <div className="sr-tasks-empty">No tasks</div>

      <div className="sr-bottom">
        <div className="sr-avatar">晚</div>
        <span className="sr-user-name">晚风</span>
        <span style={{ flex: 1 }} />
        <button className="sr-icon-btn" title="Help"><HelpIcon size={15} /></button>
        <button className="sr-icon-btn" title="Settings" onClick={onOpenSettings}>
          <SettingsIcon size={16} />
        </button>
      </div>
    </aside>
  );
}
