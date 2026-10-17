import { useState } from 'react';
import {
  PlusIcon, SearchIcon, SettingsIcon, ClockIcon, ChevronDown, CheckIcon,
  PlugIcon, GitIcon, ChatIcon, SidebarIcon, BackIcon, ForwardIcon, FolderIcon,
} from './icons';
import { THREAD_MODES } from '../data/mock';

// 真实 Codex 侧栏（2026-07 真机截图 + 官方文档）：
// 顶部：红绿灯 + 开关 + 前进后退
// 模式：ChatGPT（Create, learn, and explore）/ Codex（Build, debug, and ship）
// 导航：New task / Scheduled / Plugins / Pull requests / Chat
// Projects：每个项目对应磁盘目录，下挂线程（标 Local/Worktree/Cloud 模式）
const MODE_STYLE = {
  local: { label: 'Local', color: '#00a240' },
  worktree: { label: 'Worktree', color: '#FA994C' },
  cloud: { label: 'Cloud', color: '#0169cc' },
};

export default function Sidebar({
  mode, onModeChange, nav, onNav,
  projects, activeProjectId, activeThreadId,
  onSelectThread, onNewTask, onOpenSettings,
}) {
  const [modeOpen, setModeOpen] = useState(false);
  const [expanded, setExpanded] = useState({ [activeProjectId]: true });
  const [pickMode, setPickMode] = useState(false);

  const NAV = [
    { id: 'new', label: 'New task', icon: <PlusIcon size={16} /> },
    { id: 'scheduled', label: 'Scheduled', icon: <ClockIcon size={16} /> },
    { id: 'plugins', label: 'Plugins', icon: <PlugIcon size={16} /> },
    { id: 'prs', label: 'Pull requests', icon: <GitIcon size={16} /> },
    { id: 'chat', label: 'Chat', icon: <ChatIcon size={16} /> },
  ];

  const startNew = (modeId) => {
    setPickMode(false);
    onNewTask(modeId);
  };

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
      </div>

      <nav className="sr-nav">
        {NAV.map((n) => n.id === 'new' ? (
          <div key={n.id} style={{ position: 'relative' }}>
            <button className={'sr-nav-item' + (nav === 'new' ? ' active' : '')}
              onClick={() => setPickMode(!pickMode)}>
              <span className="sr-nav-icon">{n.icon}</span>
              <span>{n.label}</span>
            </button>
            {pickMode && (
              <>
                <div className="drop-mask" onClick={() => setPickMode(false)} />
                <div className="drop-menu sr-mode-menu">
                  <div className="filter-menu-title">Choose mode</div>
                  {THREAD_MODES.map((m) => (
                    <div key={m.id} className="drop-item sr-mode-item" onClick={() => startNew(m.id)}>
                      <span style={{ flex: 1 }}>
                        <div className="sr-mode-item-name">
                          {m.name} <span className="mode-dot" style={{ background: MODE_STYLE[m.id].color }} />
                        </div>
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
        {(projects || []).map((p) => {
          const open = expanded[p.id];
          return (
            <div key={p.id}>
              <button className="sr-nav-item"
                onClick={() => setExpanded({ ...expanded, [p.id]: !open })}>
                <span className={'twisty' + (open ? ' open' : '')}><ChevronDown size={12} /></span>
                <span className="sr-proj-name" style={{ fontWeight: 600 }}>{p.name}</span>
              </button>
              {open && p.threads.map((t) => {
                const ms = MODE_STYLE[t.mode] || MODE_STYLE.local;
                return (
                  <button key={t.id}
                    className={'sr-nav-item sr-thread' + (t.id === activeThreadId ? ' active' : '')}
                    onClick={() => onSelectThread(p.id, t.id)}>
                    <span className="mode-dot" style={{ background: ms.color }} title={ms.label} />
                    <span className="sr-proj-name">{t.title}</span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      <div className="sr-bottom">
        <button className="sr-icon-btn" title="Settings" onClick={onOpenSettings}>
          <SettingsIcon size={16} />
        </button>
      </div>
    </aside>
  );
}

export { MODE_STYLE };
