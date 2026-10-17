import { useState } from 'react';
import {
  PlusIcon, SearchIcon, SettingsIcon, ClockIcon, ChevronDown, CheckIcon,
  PlugIcon, GitIcon, ChatIcon, SidebarIcon, BackIcon, ForwardIcon, FolderIcon,
  BellIcon, ExploreIcon, HelpIcon,
} from './icons';
import { THREAD_MODES } from '../data/mock';

// 真实 Codex 侧栏（flaviocopes.com 真机截图逐像素对照）：
// 导航：New chat / Pull requests / Scheduled / Plugins / Explore
// Pinned 分区置顶；线程蓝点=未读/活跃；底部 Projects> / Recents>；左下头像
export default function Sidebar({
  mode, onModeChange, nav, onNav,
  projects, activeProjectId, activeThreadId,
  onSelectThread, onNewTask, onOpenSettings,
}) {
  const [modeOpen, setModeOpen] = useState(false);
  const [expanded, setExpanded] = useState({ p1: true });
  const [pickMode, setPickMode] = useState(false);

  const NAV = [
    { id: 'new', label: 'New chat', icon: <ChatIcon size={16} />, plus: true },
    { id: 'prs', label: 'Pull requests', icon: <GitIcon size={16} /> },
    { id: 'scheduled', label: 'Scheduled', icon: <ClockIcon size={16} /> },
    { id: 'plugins', label: 'Plugins', icon: <PlugIcon size={16} /> },
    { id: 'explore', label: 'Explore', icon: <ExploreIcon size={16} /> },
  ];

  const startNew = (modeId) => {
    setPickMode(false);
    onNewTask(modeId);
  };

  const pinnedProject = projects[0];

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

      <div className="sr-mode-row">
        <div style={{ position: 'relative', flex: 1 }}>
          <button className="sr-mode-btn" onClick={() => setModeOpen(!modeOpen)}>
            <span className="sr-mode-name">{mode === 'codex' ? 'Codex' : 'ChatGPT'}</span>
            <ChevronDown size={14} />
          </button>
          {modeOpen && (
            <>
              <div className="drop-mask" onClick={() => setModeOpen(false)} />
              <div className="drop-menu sr-mode-menu">
                {[
                  { id: 'chatgpt', name: 'ChatGPT', desc: 'Create, learn, and explore' },
                  { id: 'codex', name: 'Codex', desc: 'Build, debug, and ship' },
                ].map((m) => (
                  <div key={m.id} className="drop-item sr-mode-item"
                    onClick={() => { onModeChange(m.id); setModeOpen(false); }}>
                    <span style={{ flex: 1 }}>
                      <div className="sr-mode-item-name">{m.name}</div>
                      <div className="sr-mode-item-desc">{m.desc}</div>
                    </span>
                    {mode === m.id && <CheckIcon size={14} />}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <button className="sr-icon-btn" title="Search"><SearchIcon size={16} /></button>
        <button className="sr-icon-btn" title="Notifications"><BellIcon size={16} /></button>
      </div>

      <nav className="sr-nav">
        {NAV.map((n) => n.id === 'new' ? (
          <div key={n.id} style={{ position: 'relative' }}>
            <button className={'sr-nav-item' + (nav === 'new' ? ' active' : '')}
              onClick={() => setPickMode(!pickMode)}>
              <span className="sr-nav-icon">{n.icon}</span>
              <span style={{ flex: 1 }}>{n.label}</span>
              <PlusIcon size={13} />
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

      {/* Pinned 分区 */}
      <div className="sr-section">Pinned</div>
      <div className="sr-projects">
        {pinnedProject && (
          <div>
            <button className="sr-nav-item sr-proj-active">
              <span className="sr-nav-icon"><FolderIcon size={15} /></span>
              <span className="sr-proj-name" style={{ fontWeight: 500 }}>{pinnedProject.name}</span>
            </button>
            {pinnedProject.threads.map((t) => (
              <button key={t.id}
                className={'sr-nav-item sr-thread' + (t.id === activeThreadId ? ' active' : '')}
                onClick={() => onSelectThread(pinnedProject.id, t.id)}>
                <span className="sr-proj-name">{t.title}</span>
                {(t.status === 'active' || t.unread) && <span className="blue-dot" />}
              </button>
            ))}
            <button className="sr-show-more">Show more</button>
          </div>
        )}
        {projects.slice(1).map((p) => (
          <button key={p.id} className="sr-nav-item"
            onClick={() => onSelectThread(p.id, p.threads[0]?.id)}>
            <span className="sr-nav-icon"><FolderIcon size={15} /></span>
            <span className="sr-proj-name">{p.name}</span>
          </button>
        ))}
      </div>

      <div className="sr-links">
        <button className="sr-link">Projects <span>›</span></button>
        <button className="sr-link">Recents <span>›</span></button>
      </div>

      <div className="sr-bottom">
        <div className="sr-avatar">晚</div>
        <span style={{ flex: 1 }} />
        <button className="sr-icon-btn" title="Help"><HelpIcon size={15} /></button>
        <button className="sr-icon-btn" title="Settings" onClick={onOpenSettings}>
          <SettingsIcon size={16} />
        </button>
      </div>
    </aside>
  );
}
